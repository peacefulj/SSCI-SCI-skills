# -*- coding: utf-8 -*-
"""Docker/systemd 部署文件的静态校验。

本机 Docker 守护进程未启动，无法真构建镜像。退而求其次：逐条核对
「Dockerfile 里 COPY 的东西真的存在」「.dockerignore 不会把运行时必需资源
排掉」「systemd 的路径与脚本一致」。这些是最容易出错、也最容易静态查出的部分。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(n, c, e=""):
    print(("  [OK] " if c else "  [XX] ") + n + (f"   {e}" if e else ""))
    if not c:
        fails.append(n)


def read(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


print("=== 1. Dockerfile ===")
df = read("Dockerfile")
check("基础镜像是 python:3.11-slim", "FROM python:3.11-slim" in df)
check("COPY requirements.txt", "COPY requirements.txt" in df)
check("COPY 整个上下文", re.search(r"^COPY \. \.", df, re.M) is not None)
check("非 root 用户", "USER papermate" in df)
check("声明 VOLUME /data", 'VOLUME ["/data"]' in df)
check("暴露 8000", "EXPOSE 8000" in df)
check("有 HEALTHCHECK", "HEALTHCHECK" in df)
check("启动命令 python server.py",
      'CMD ["python", "server.py"]' in df)
check("提供 with-office 可选 stage", "AS with-office" in df)
check("服务端模式环境变量齐全",
      all(k in df for k in ("PAPERMATE_DATA_DIR=/data",
                            "PAPERMATE_HOST=0.0.0.0",
                            "PAPERMATE_PORT=8000")))
# healthcheck 端口须与 PORT 一致
hc = re.search(r"HEALTHCHECK.*?CMD (.*?)\n", df, re.S)
check("healthcheck 命中 /api/health", hc and "/api/health" in hc.group(1))

print("\n=== 2. 构建上下文里必需的文件都真实存在 ===")
for p in ("requirements.txt", "server.py", "engine.py", "paths.py", "auth.py",
          "state_store.py", "oneshot.py", "llm.py", "refs.py", "litcache.py",
          "ingest.py", "dataset.py", "export.py", "datasource.py",
          "topic_trend.py", "cite_check.py", ".env.cloud.example",
          "static/index.html", "static/login.html", "static/app.js",
          "static/style.css", "static/render.js",
          "skill/academic-writing-v1.1/rules/rules.yaml"):
    check(p, os.path.exists(os.path.join(ROOT, p)))

print("\n=== 3. .dockerignore 不能排掉运行时资源 ===")
di = read(".dockerignore")
lines = [l.strip() for l in di.splitlines() if l.strip() and not l.startswith("#")]
for must_keep in ("static", "static/", "skill", "skill/", "server.py", "*.py"):
    check(f"未排除 {must_keep}", must_keep not in lines)
check("排除了 .env（密钥不进镜像）", ".env" in lines)
check("排除了 data/（用户数据不进镜像）", "data/" in lines)
check("排除了 _sessions", "_sessions/" in lines)

print("\n=== 4. docker-compose.yml ===")
# 没有 PyYAML 也能凑合看，但项目依赖里有 yaml，直接用
import yaml
dc = yaml.safe_load(read("docker-compose.yml"))
svc = (dc.get("services") or {}).get("papermate") or {}
check("有 papermate 服务", bool(svc))
check("restart: unless-stopped", svc.get("restart") == "unless-stopped")
check("读 .env", ".env" in (svc.get("env_file") or []))
check("挂 ./data:/data", any(":/data" in str(v) for v in (svc.get("volumes") or [])))
check("暴露 8000", any("8000" in str(p) for p in (svc.get("ports") or [])))
envs = svc.get("environment") or {}
check("HOST=0.0.0.0", envs.get("PAPERMATE_HOST") == "0.0.0.0")
check("DATA_DIR=/data", str(envs.get("PAPERMATE_DATA_DIR")) == "/data")
check("有 healthcheck", bool(svc.get("healthcheck")))
check("healthcheck 打 /api/health",
      any("/api/health" in str(x) for x in (svc["healthcheck"].get("test") or [])))
check("限制了日志大小", bool((svc.get("logging") or {}).get("options")))

print("\n=== 5. systemd 单元 ===")
su = read("deploy/papermate.service")
check("ExecStart 指向 .venv 的 python",
      "/opt/papermate/.venv/bin/python /opt/papermate/server.py" in su)
check("WorkingDirectory=/opt/papermate", "WorkingDirectory=/opt/papermate" in su)
check("DATADIR=/var/lib/papermate",
      "PAPERMATE_DATA_DIR=/var/lib/papermate" in su)
check("HOST=127.0.0.1（靠反代对外）",
      "PAPERMATE_HOST=127.0.0.1" in su)
check("EnvironmentFile 用 - 前缀（文件缺失不致启动失败）",
      "EnvironmentFile=-/etc/papermate/papermate.env" in su)
check("Restart=always", "Restart=always" in su)
check("运行用户与 install.sh 一致（papermate）", "User=papermate" in su)
check("WantedBy=multi-user.target", "WantedBy=multi-user.target" in su)
check("有 NoNewPrivileges 加固", "NoNewPrivileges=true" in su)
check("ReadWritePaths 放开数据目录",
      "ReadWritePaths=/var/lib/papermate" in su)

print("\n=== 6. install.sh 与 systemd/路径一致性 ===")
ins = read("deploy/install.sh")
check("APP_DIR=/opt/papermate", "APP_DIR=/opt/papermate" in ins)
check("DATA_DIR=/var/lib/papermate", "DATA_DIR=/var/lib/papermate" in ins)
check("CONF_DIR=/etc/papermate", "CONF_DIR=/etc/papermate" in ins)
check("单元名 papermate", "SERVICE=papermate" in ins)
check("装了 systemd 单元", "install -m 644" in ins and "papermate.service" in ins)
check("Python 版本门槛 3.10", "(3,10)" in ins)
check("幂等：配置已存在则保留", "保留不动" in ins)
check("set -euo pipefail", "set -euo pipefail" in ins)

print("\n=== 7. nginx.conf 三处必需指令 ===")
ng = read("deploy/nginx.conf")
check("client_max_body_size 100m", "client_max_body_size 100m" in ng)
check("proxy_read_timeout 1800s", "proxy_read_timeout  1800s" in ng)
check("proxy_buffering off", "proxy_buffering off" in ng)
check("透传 X-Forwarded-For", "X-Forwarded-For" in ng)
check("挡住数据目录直访", re.search(r"location ~ \^/\(data\|", ng) is not None)

print("\n=== 8. 环境变量模板 ===")
ec = read(".env.cloud.example")
for k in ("PAPERMATE_ACCESS_TOKEN", "PAPERMATE_ALLOW_SERVER_KEY",
          "PAPERMATE_SECRET", "PAPERMATE_HTTPS", "DEEPSEEK_API_KEY"):
    check(f"含 {k}", k in ec)
check("模板不含真实 Key（DEEPSEEK_API_KEY 为空）",
      re.search(r"^DEEPSEEK_API_KEY=\s*$", ec, re.M) is not None)

print("\n" + "=" * 50)
if fails:
    print(f"失败 {len(fails)} 项：")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("全部通过")
