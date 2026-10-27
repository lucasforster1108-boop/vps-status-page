#!/usr/bin/env python3
"""可选组件：状态页远程控制 API（模板版，默认不启用）。

作用：给状态页的「开机 / 关机 / 重启」按钮提供后端。页面 POST /api/control
{token, server, action}，本服务按 config.json 中 control.commands 里为该
服务器 id 预先配置好的 shell 命令执行对应动作。

安全须知（务必先读）：
  - 这是一个能对你的服务器执行命令的接口。只监听 127.0.0.1（默认），
    由 nginx 反代并在站点层再加 Basic Auth（见 deploy/nginx-status.conf.example）。
  - token 从环境变量读取（变量名由 config 的 control.token_env 指定，
    默认 STATUS_CONTROL_TOKEN），不要把真实 token 写进仓库。
    生成方法：openssl rand -hex 24
  - 只在 commands 里配置你确实要开放的服务器与动作；没配的组合一律拒绝。
    例如采集机本机通常只开放 reboot，且命令就是本机 /sbin/reboot。

用法:
    STATUS_CONTROL_TOKEN=... python3 control_api.py [--config /path/to/config.json]
"""
import argparse
import hmac
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

ALLOWED_ACTIONS = ("start", "stop", "reset", "reboot")


def load_cfg(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Ctx:
    cfg = None
    token = ""
    servers = {}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if urlparse(self.path).path != "/api/control":
            self.send_error(404)
            return
        try:
            ln = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(ln) or b"{}")
        except Exception:
            body = {}
        if not hmac.compare_digest(str(body.get("token", "")), Ctx.token):
            self._reply(403, {"ok": False, "msg": "token 无效"})
            return
        server = body.get("server", "")
        action = body.get("action", "")
        commands = (Ctx.cfg.get("control", {}).get("commands") or {}).get(server)
        if action not in ALLOWED_ACTIONS or not commands or action not in commands:
            self._reply(400, {"ok": False, "msg": "参数错误或该动作未配置"})
            return
        srv = Ctx.servers.get(server, {})
        cmd = commands[action].format(host=srv.get("host", ""), id=server)
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                msg = (r.stdout or "命令已执行").strip()[:200]
                self._reply(200, {"ok": True, "msg": msg or "命令已执行"})
            else:
                err = (r.stderr or r.stdout or "命令执行失败").strip()
                self._reply(500, {"ok": False, "msg": "执行失败: " + err[:200]})
        except Exception as e:
            self._reply(500, {"ok": False, "msg": str(e)[:200]})

    def _reply(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.environ.get("VPS_STATUS_CONFIG", "config.json"))
    args = ap.parse_args()
    cfg = load_cfg(args.config)
    control = cfg.get("control", {})
    if not control.get("enabled"):
        print("control.enabled 不是 true，拒绝启动。确认要启用远程控制后再改。", file=sys.stderr)
        return 1
    token_env = control.get("token_env", "STATUS_CONTROL_TOKEN")
    token = os.environ.get(token_env, "")
    if not token:
        print("环境变量 %s 未设置或为空，拒绝启动。" % token_env, file=sys.stderr)
        return 1
    Ctx.cfg = cfg
    Ctx.token = token
    Ctx.servers = {s.get("id", s.get("host")): s for s in cfg.get("servers", [])}
    listen = control.get("listen", "127.0.0.1")
    port = int(control.get("port", 8898))
    print("control api listening on %s:%d" % (listen, port))
    HTTPServer((listen, port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
