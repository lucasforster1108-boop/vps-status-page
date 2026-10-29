# vps-status-page

一个极简的多机 VPS 状态页：一张静态网页 + 一个每分钟跑一次的采集脚本，
一眼看全你所有服务器的在线状态、CPU 负载、内存、磁盘、当月流量和关键服务存活。
可选开启远程开机/关机/重启按钮。

> 本仓库是一个个人自用项目脱敏后的通用模板：所有示例 IP 均为文档占位段
> （203.0.113.0/24），配置、密钥、令牌一律由使用者自己填写，仓库内不含任何真实信息。

## 效果

- 卡片式布局（桌面 4 列、手机 2 列），深色主题，支持 PWA 添加到手机主屏
- 每台机器一张卡：状态圆点（在线/失联）、IP 与地区、用途说明、CPU 负载、
  内存与磁盘进度条（70% 变黄、90% 变红）、当月流量与额度进度条、运行时长
- 可选 TCP 服务探活（如某端口在不在监听），结果直接显示在卡片上
- 页面每 60 秒自动刷新，切回前台时立即刷新
- 可选控制按钮：给指定机器渲染开机/关机/重启，经一个本机小 API 执行你预先配置好的命令

## 结构

```
.
├── config.example.json     # 配置示例：复制为 config.json 后填自己的服务器
├── collector/
│   └── check_status.py     # 采集脚本：本机直读 + 远程机一条 SSH 取回全部指标，写 status.json
├── web/
│   ├── index.html          # 单文件状态页（样式与脚本全内联，部署即用）
│   ├── manifest.json       # PWA 清单（图标 icon-192/512.png 自行放同目录，可选）
│   └── status.example.json # status.json 样例，可直接预览页面渲染效果
├── control/
│   └── control_api.py      # 可选：远程控制 API（默认禁用，读环境变量 token）
└── deploy/
    ├── nginx-status.conf.example       # nginx 站点示例（Basic Auth + 反代控制 API）
    ├── crontab.example                 # 每分钟采集的 cron 示例
    └── server-control.service.example  # 控制 API 的 systemd 单元示例
```

数据流：`cron 每分钟 → check_status.py → status.json → nginx 静态托管 → 浏览器 fetch 渲染`。
全部组件只用 Python 3 标准库 + 系统自带命令（free/df/vnstat），没有第三方依赖。

## 快速开始

1. **准备配置**

   ```bash
   cp config.example.json config.json   # 已被 .gitignore 排除，放心填真实值
   ```

   按下面「配置说明」把 `servers` 改成你自己的机器，`output_path` 指向站点根目录。

2. **部署页面**：把 `web/` 里的文件放到站点根目录（如 `/var/www/status/`），
   `index.html` 与采集生成的 `status.json` 同目录即可。

3. **挂采集 cron**（见 `deploy/crontab.example`）：

   ```
   * * * * * VPS_STATUS_CONFIG=/opt/vps-status/config.json /usr/bin/python3 /opt/vps-status/collector/check_status.py >> /var/log/vps-status.log 2>&1
   ```

   远程机走 SSH 密钥登录：运行采集的用户要持有 config 里引用的私钥，
   并先手动连一次各机把指纹写入 known_hosts。

4. **（可选）上 nginx**：参考 `deploy/nginx-status.conf.example`，
   生成密码文件 `sudo htpasswd -c /etc/nginx/.status_htpasswd 你的用户名` 后启用站点。
   纯内网自用的话，任何静态文件服务器都可以。

5. **（可选）开启控制按钮**：
   - `openssl rand -hex 24` 生成 token；
   - config.json 里把 `control.enabled` 改为 true，并在 `control.commands` 里
     按服务器 id 配好各动作的 shell 命令（只配你敢开放的，例如本机只配 reboot）；
   - 用 `deploy/server-control.service.example` 以 systemd 跑起 `control/control_api.py`，
     token 通过环境变量 `STATUS_CONTROL_TOKEN` 注入；
   - `web/index.html` 顶部 `PAGE_CONFIG` 里打开 `controlEnabled` 并填同一个 token，
     同时在 config 里给服务器加 `control_actions`（如 `["reboot"]`），按钮才会出现。
   - ⚠️ token 写在静态页面里等于半公开，站点务必加 Basic Auth；控制 API 只监听
     127.0.0.1，不要直接暴露公网。

## 配置说明（config.json）

| 字段 | 说明 |
|---|---|
| `output_path` | status.json 的输出路径（站点根目录下） |
| `display_timezone_offset_hours` | 可选。「更新于」时间按此时区偏移显示（如 8）；不填则用采集机本地时间 |
| `servers[].id` | 机器唯一标识，页面与控制 API 都用它 |
| `servers[].name` / `location` / `role` | 卡片上显示的名称、地区、用途说明 |
| `servers[].host` | IP 或域名 |
| `servers[].local` | true 表示采集脚本就跑在这台机器上，直读本机指标，不走 SSH |
| `servers[].ssh` | 远程机的 `{user, key, port}`，key 为私钥路径 |
| `servers[].traffic_quota_gb` | 当月流量额度（GB，出站口径）；null 表示未录入、只显示用量 |
| `servers[].traffic_note` | 流量条下方的小字说明 |
| `servers[].checks` | TCP 探活列表：`{type:"tcp", port:443, label:"HTTPS"}` |
| `servers[].state_cmd` | 可选：一条命令，输出第一行作为云厂商状态（如各云 CLI 查询命令）；不配则按可达性显示 RUNNING/UNKNOWN |
| `servers[].control_actions` | 可选：允许在页面显示的控制动作子集 `["start","stop","reset","reboot"]` |
| `control` | 可选控制组件配置：`enabled`、`listen`、`port`、`token_env`、`commands`（按服务器 id 配命令模板，支持 `{host}` `{id}` 占位） |

流量统计依赖各机安装 `vnstat`；没装的机器自动不显示流量条，不影响其他指标。

## 安全说明

- `config.json`、私钥、token 都不要提交进仓库（`.gitignore` 已预置排除规则）。
- 给采集用的 SSH 私钥建议单独生成、只授权登录被监控机，并考虑在被监控机的
  `authorized_keys` 里用 `command=`/只读账号等方式收紧权限（进阶，自行评估）。
- 仓库里的示例 token 位置一律为空、示例命令为 `echo` 占位，没有任何可用的真实凭据。

## 依赖

- 采集机：Python 3.8+、OpenSSH 客户端；被监控机：OpenSSH 服务端、procps（free/df），
  流量统计可选装 vnstat
- 托管：任意静态文件服务器；控制组件反代示例使用 nginx

## License

MIT，见 [LICENSE](LICENSE)。

---

# vps-status-page (English)

A minimal multi-server VPS status page: one static web page plus a collector script that runs once a minute, giving you an at-a-glance view of every server's online state, CPU load, memory, disk, monthly traffic, and key service health. Optional remote power buttons (start / stop / reboot).

> This repository is a sanitized, generic template of a personal project: all example IPs are from the documentation range (203.0.113.0/24), and all configuration, keys, and tokens are filled in by the user — the repo contains no real information.

## What you get

- Card layout (4 columns on desktop, 2 on mobile), dark theme, PWA support for adding to a phone home screen
- One card per machine: status dot (online / unreachable), IP and region, role description, CPU load, memory and disk bars (yellow at 70%, red at 90%), monthly traffic against quota, uptime
- Optional TCP service probes (is a given port listening?), shown right on the card
- The page auto-refreshes every 60 seconds, and refreshes immediately when it returns to the foreground
- Optional control buttons: renders start/stop/reboot for designated machines, executed through a small local API running commands you pre-configure

## Structure

```
.
├── config.example.json     # Example config: copy to config.json and fill in your servers
├── collector/
│   └── check_status.py     # Collector: reads the local machine directly, fetches all metrics from remote machines over one SSH call, writes status.json
├── web/
│   ├── index.html          # Single-file status page (styles and scripts inline, deploy as-is)
│   ├── manifest.json       # PWA manifest (put icon-192/512.png alongside it, optional)
│   └── status.example.json # Sample status.json — preview the rendered page directly
├── control/
│   └── control_api.py      # Optional: remote-control API (disabled by default, token via environment variable)
└── deploy/
    ├── nginx-status.conf.example       # Example nginx site (Basic Auth + reverse proxy for the control API)
    ├── crontab.example                 # Example cron entry for per-minute collection
    └── server-control.service.example  # Example systemd unit for the control API
```

Data flow: `cron (every minute) → check_status.py → status.json → nginx static hosting → browser fetch & render`. Everything uses only the Python 3 standard library plus standard system tools (free/df/vnstat) — no third-party dependencies.

## Quick start

1. **Prepare the config**

   ```bash
   cp config.example.json config.json   # excluded by .gitignore, safe to fill in real values
   ```

   Edit `servers` to your own machines per the configuration reference below, and point `output_path` at your site root.

2. **Deploy the page**: put the files from `web/` into your site root (e.g. `/var/www/status/`); `index.html` and the generated `status.json` just need to be in the same directory.

3. **Set up the collection cron** (see `deploy/crontab.example`):

   ```
   * * * * * VPS_STATUS_CONFIG=/opt/vps-status/config.json /usr/bin/python3 /opt/vps-status/collector/check_status.py >> /var/log/vps-status.log 2>&1
   ```

   Remote machines are reached via SSH key login: the user running the collector must hold the private key referenced in the config, and you should connect to each machine once manually first to record its host fingerprint in known_hosts.

4. **(Optional) Put nginx in front**: follow `deploy/nginx-status.conf.example`, generate a password file with `sudo htpasswd -c /etc/nginx/.status_htpasswd your-username`, and enable the site. For purely internal use, any static file server works.

5. **(Optional) Enable the control buttons**:
   - Generate a token with `openssl rand -hex 24`;
   - In config.json set `control.enabled` to true, and under `control.commands` configure the shell command for each action per server id (only configure actions you are comfortable exposing — e.g. reboot only for the local machine);
   - Run `control/control_api.py` under systemd using `deploy/server-control.service.example`, injecting the token via the `STATUS_CONTROL_TOKEN` environment variable;
   - In the `PAGE_CONFIG` block at the top of `web/index.html`, set `controlEnabled` and fill in the same token, and add `control_actions` (e.g. `["reboot"]`) to the server in the config — only then do the buttons appear.
   - ⚠️ The token sits in a static page, which makes it semi-public: the site must be protected with Basic Auth; the control API listens on 127.0.0.1 only — never expose it directly to the public internet.

## Configuration (config.json)

| Field | Description |
|---|---|
| `output_path` | Output path of status.json (under the site root) |
| `display_timezone_offset_hours` | Optional. Show the "updated at" time with this UTC offset (e.g. 8); if unset, the collector machine's local time is used |
| `servers[].id` | Unique machine identifier, used by both the page and the control API |
| `servers[].name` / `location` / `role` | Name, region, and role description shown on the card |
| `servers[].host` | IP or domain name |
| `servers[].local` | true = the collector runs on this machine; metrics are read locally, no SSH |
| `servers[].ssh` | For remote machines: `{user, key, port}`, where key is the private key path |
| `servers[].traffic_quota_gb` | Monthly traffic quota (GB, outbound); null = not recorded, usage only |
| `servers[].traffic_note` | Small print shown under the traffic bar |
| `servers[].checks` | TCP probe list: `{type:"tcp", port:443, label:"HTTPS"}` |
| `servers[].state_cmd` | Optional: a command whose first output line is used as the cloud provider state (e.g. a cloud CLI query); if unset, state is shown as RUNNING/UNKNOWN based on reachability |
| `servers[].control_actions` | Optional: the subset of control actions to show on the page, `["start","stop","reset","reboot"]` |
| `control` | Optional control-component config: `enabled`, `listen`, `port`, `token_env`, `commands` (command templates per server id, supporting `{host}` and `{id}` placeholders) |

Traffic stats rely on `vnstat` being installed on each machine; machines without it simply don't show a traffic bar — all other metrics are unaffected.

## Security notes

- Never commit `config.json`, private keys, or tokens to the repo (`.gitignore` ships with exclusion rules preconfigured).
- Generate a dedicated SSH key for the collector, authorize it only on the monitored machines, and consider tightening it further on the monitored side (e.g. `command=` restrictions or a read-only account in `authorized_keys`) — advanced, evaluate for yourself.
- All example token slots in the repo are empty and example commands are `echo` placeholders — there are no usable real credentials anywhere in this repo.

## Dependencies

- Collector machine: Python 3.8+, OpenSSH client; monitored machines: OpenSSH server, procps (free/df), optionally vnstat for traffic stats
- Hosting: any static file server; the reverse-proxy example for the control component uses nginx

## License

MIT, see [LICENSE](LICENSE).
