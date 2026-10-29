# vps-status-page

English | [简体中文](README_zh.md)

A status page for my VPS fleet: one static page plus a collector script that runs every minute. Each machine gets a card — up or down, CPU load, memory, disk, monthly traffic, uptime — plus optional TCP probes for services I care about, and optional power buttons (start/stop/reboot) if you are brave.

This is the sanitized template of the page I actually run. Example IPs are from the documentation range (203.0.113.0/24); configs, keys and tokens are yours to fill in — there is nothing real in here.

How it fits together: cron every minute → `collector/check_status.py` reads the local box directly and pulls the rest over one SSH call each → writes `status.json` → nginx serves `web/` statically → the page fetches and renders, refreshing every 60 s (and immediately when it comes back to the foreground). Python stdlib plus free/df/vnstat, no third-party anything.

Quick start:

1. `cp config.example.json config.json`; fill in `servers` and `output_path`.
2. Put `web/` in your site root; `index.html` and the generated `status.json` live side by side.
3. Cron the collector (`deploy/crontab.example`). Remote boxes are SSH-key only, and you should connect once by hand first so `known_hosts` is populated.
4. Optional nginx with Basic Auth (`deploy/nginx-status.conf.example`). For a LAN-only page, any static file server works.
5. Optional control buttons: set `control.enabled` and per-server commands in the config, run `control/control_api.py` under systemd with the token in an environment variable, and flip `controlEnabled` in the page's `PAGE_CONFIG`. The token sits inside a static page, so treat it as semi-public: Basic Auth is not optional in that setup, and the API listens on 127.0.0.1 only.

Config, short version: `servers[].{id, name, location, role, host, local, ssh, traffic_quota_gb, checks, control_actions}`, `output_path`, `display_timezone_offset_hours`, and the `control` block. `config.example.json` documents every field. Traffic needs `vnstat` on each box; without it, that card simply has no traffic bar.

Security: `config.json`, private keys and tokens are gitignored — keep it that way. Give the collector its own SSH key, authorized only on the monitored boxes. Every example token in this repo is empty and every example command is an `echo` placeholder.

Needs Python 3.8+ and an OpenSSH client on the collector; sshd and procps on the targets.

MIT, see [LICENSE](LICENSE).
