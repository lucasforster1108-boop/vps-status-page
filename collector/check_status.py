#!/usr/bin/env python3
"""VPS 多机状态采集脚本（模板版）。

读取 config.json 中的服务器列表：
  - 本机（local: true）直接读 /proc、free、df、vnstat；
  - 远程机通过一条 SSH 命令批量取回 loadavg / meminfo / df / uptime / 路由 / vnstat JSON 再解析。
把结果写成 status.json，供 web/index.html 展示。设计为 cron 每分钟跑一次。

用法:
    python3 check_status.py [--config /path/to/config.json]

只依赖 Python 3 标准库；远程机装了 vnstat 时可额外显示当月流量，没装自动跳过。
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time

# 通过一条命令取回全部原始数据，用 --- 分段，避免多次 SSH 往返
REMOTE_CMD = (
    "cat /proc/loadavg; echo ---; "
    "grep -E 'MemTotal|MemAvailable' /proc/meminfo; echo ---; "
    "df -h / | tail -1; echo ---; "
    "cat /proc/uptime; echo ---; "
    "ip route show default; echo ---; "
    "vnstat --json m 2>/dev/null"
)


def sh(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def tcp_ok(host, port, timeout=5):
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


def fmt_bytes(b):
    b = float(b)
    for u in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if abs(b) < 1024 or u == "PB":
            return "%.2f %s" % (b, u)
        b /= 1024.0


def parse_traffic(route_txt, json_txt):
    """route_txt: `ip route show default` 输出；json_txt: `vnstat --json m` 输出。
    取默认路由网卡的当月 {rx, tx} 字节数，取不到返回 None。"""
    try:
        iface = ""
        toks = (route_txt or "").split()
        if "dev" in toks:
            iface = toks[toks.index("dev") + 1]
        d = json.loads(json_txt)
        now = time.localtime()
        ifaces = d.get("interfaces") or []

        def month_of(itf):
            tr = itf.get("traffic") or {}
            for m in tr.get("month") or tr.get("months") or []:
                dt2 = m.get("date") or {}
                if dt2.get("year") == now.tm_year and dt2.get("month") == now.tm_mon:
                    return {"rx": int(m.get("rx") or 0), "tx": int(m.get("tx") or 0)}
            return None

        if iface:
            for itf in ifaces:
                if itf.get("name") == iface:
                    return month_of(itf)
        # 路由未知时的回退：跳过虚拟网卡，取第一个有当月数据的网卡
        for itf in ifaces:
            nm = itf.get("name") or ""
            if nm == "lo" or nm.startswith(("docker", "br-", "veth")):
                continue
            r = month_of(itf)
            if r:
                return r
    except Exception:
        return None
    return None


def traf_fields(t, quota_gb, note):
    """流量字段：quota 按「当月出站 tx / 额度」计算百分比（与原版口径一致）。"""
    if not t:
        return {}
    f = {
        "traf_rx_s": fmt_bytes(t["rx"]),
        "traf_tx_s": fmt_bytes(t["tx"]),
        "traf_note": note or "",
        "traf_pct": None,
    }
    if quota_gb:
        quota = float(quota_gb) * 1024 ** 3
        f["traf_quota_s"] = fmt_bytes(quota)
        f["traf_pct"] = round(t["tx"] / quota * 100, 2)
    return f


def ssh_base(server):
    ssh = server.get("ssh") or {}
    user = ssh.get("user", "root")
    port = int(ssh.get("port", 22))
    key = ssh.get("key", "")
    parts = [
        "timeout 25 ssh",
        "-o ConnectTimeout=15 -o BatchMode=yes -o StrictHostKeyChecking=accept-new",
    ]
    if key:
        parts.append("-i " + os.path.expanduser(key))
    if port != 22:
        parts.append("-p %d" % port)
    parts.append("%s@%s" % (user, server["host"]))
    return " ".join(parts)


def get_stats(server):
    """采集一台服务器的指标，失败返回 None。"""
    if server.get("local"):
        out = sh(REMOTE_CMD, timeout=20)
    else:
        out = ""
        for _ in range(2):  # 与原版一致：失败重试一次
            out = sh(ssh_base(server) + ' "' + REMOTE_CMD + '"', timeout=40)
            if len([p for p in out.split("---") if p.strip()]) >= 3:
                break
            time.sleep(8)
    parts = [p.strip() for p in out.split("---") if p.strip()]
    if len(parts) < 3:
        return None
    try:
        load = parts[0].split()[0]
        mem = {}
        for line in parts[1].split("\n"):
            kv = line.split()
            if len(kv) >= 2:
                mem[kv[0].rstrip(":")] = int(kv[1])
        mt = mem["MemTotal"] // 1024
        ma = mem["MemAvailable"] // 1024
        mu = mt - ma
        dcols = parts[2].split("\n")[0].split()
        up_str = ""
        if len(parts) >= 4:
            secs = int(float(parts[3].split()[0]))
            dd, rr = divmod(secs, 86400)
            hh, rr = divmod(rr, 3600)
            mm = rr // 60
            seg = []
            if dd:
                seg.append(str(dd) + (" day" if dd == 1 else " days"))
            if hh:
                seg.append(str(hh) + (" hour" if hh == 1 else " hours"))
            seg.append(str(mm) + (" minute" if mm == 1 else " minutes"))
            up_str = "up " + ", ".join(seg)
        result = {
            "uptime": up_str,
            "cpu_load": load,
            "mem_total": str(mt) + "M",
            "mem_used": str(mu) + "M",
            "mem_avail": str(ma) + "M",
            "mem_pct": round(mu / mt * 100) if mt else 0,
            "disk_total": dcols[1],
            "disk_used": dcols[2],
            "disk_avail": dcols[3],
            "disk_pct": dcols[4],
        }
        if len(parts) >= 6:
            t = parse_traffic(parts[4], parts[5])
            result.update(traf_fields(t, server.get("traffic_quota_gb"),
                                        server.get("traffic_note", "")))
        return result
    except Exception:
        return None


def server_state(server, reachable):
    """可选：config 里给服务器配了 state_cmd 时，用它的输出作为云厂商状态
    （例如某云的 CLI 查询命令）；没配则用可达性推导。"""
    cmd = server.get("state_cmd")
    if cmd:
        out = sh(cmd, timeout=30)
        if out:
            return out.splitlines()[0].strip()
    return "RUNNING" if reachable else "UNKNOWN"


def collect(cfg):
    servers = []
    for srv in cfg.get("servers", []):
        stats = get_stats(srv)
        entry = {
            "id": srv.get("id", srv["host"]),
            "name": srv.get("name", srv["host"]),
            "ip": srv["host"],
            "loc": srv.get("location", ""),
            "state": server_state(srv, stats is not None),
            "reach": stats is not None,
            "role": srv.get("role", ""),
        }
        if stats:
            entry.update(stats)
        else:
            entry["detail"] = "SSH 不可达"
        # 可选的 TCP 服务存活检查（如某个端口的服务是否在监听）
        services = []
        for chk in srv.get("checks", []):
            if chk.get("type") == "tcp" and chk.get("port"):
                services.append({
                    "label": chk.get("label", "port %s" % chk["port"]),
                    "ok": tcp_ok(srv["host"], int(chk["port"])),
                })
        if services:
            entry["services"] = services
        # 把允许的远程控制动作透传给前端（控制 API 是可选组件，见 control/）
        actions = srv.get("control_actions") or []
        if actions:
            entry["control_actions"] = actions
        servers.append(entry)
    offset = cfg.get("display_timezone_offset_hours")
    if offset is not None:
        updated = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + float(offset) * 3600))
    else:
        updated = time.strftime("%Y-%m-%d %H:%M:%S")
    return {"updated": updated, "servers": servers}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.environ.get("VPS_STATUS_CONFIG", "config.json"))
    args = ap.parse_args()
    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    out_path = cfg.get("output_path", "status.json")
    data = collect(cfg)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print("OK", data["updated"], "servers:", len(data["servers"]))


if __name__ == "__main__":
    sys.exit(main())
