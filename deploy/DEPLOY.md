# PaperMate 1.3.0 · 云部署手册

本版本在 1.2.8 的全部能力之上，补上了「部署到公网服务器」所需的改造。桌面版
行为完全不变：不设任何新增环境变量时，启动的仍是本地 `127.0.0.1` 服务。

---

## 0. 先弄清楚：1.2.8 为什么上不了云

1.2.8 本来就是**网页版**（前端 HTML + 后端 FastAPI，用浏览器访问），但它只
为「本机单用户」设计。直接搬到云服务器会遇到七件事：

| 问题 | 1.2.8 的做法 | 云上的后果 |
|---|---|---|
| 监听地址 | 写死 `127.0.0.1` | 外网连不进来 |
| 自动开浏览器 | 启动就弹浏览器 | 容器里没有浏览器，启动被拖慢 |
| 端口被占 | 自动顺延到下一个 | 反代写死 8000，一顺延全盘不通 |
| 会话与任务 | 全在进程内存 | 重启/重建后全部丢失 |
| 数据目录 | `%LOCALAPPDATA%` | Linux 容器里没有这个变量 |
| 访问控制 | 无 | 谁能连上端口谁就能用你的 Key |
| Key 归属 | 服务端一份全组共用 | 无法区分谁在用、用量算不清 |

1.3.0 逐条解决，且**每一种改动都只在新环境变量存在时生效**，不影响桌面版。

---

## 1. 三条部署路线，选一条

### 路线 A：Docker Compose（推荐）

适用：任何云主机（阿里云 / 腾讯云 / 华为云 / AWS / 自建 K8s 节点）。

```bash
# 1) 上传并解压
scp PaperMate-1.3.0-cloud-src.zip root@your-server:/opt/
cd /opt && unzip PaperMate-1.3.0-cloud-src.zip && cd academic-writing-agent

# 2) 生成配置
cp .env.cloud.example .env
python3 -c "import secrets;print(secrets.token_urlsafe(24))"   # 复制输出
vi .env        # 填 PAPERMATE_ACCESS_TOKEN 和 DEEPSEEK_API_KEY

# 3) 启动
docker compose up -d --build

# 4) 看日志与健康
docker compose logs -f
curl http://127.0.0.1:8000/api/health
```

浏览器打开 `http://服务器IP:8000`，输入上一步生成的口令即可。

需要处理 `.doc` / `.xls` 老格式时，把 `docker-compose.yml` 里
`# target: with-office` 那行取消注释再重新 `build`（镜像涨到约 1.2GB）。

### 路线 B：裸机 systemd

适用：不想装 Docker 的 Linux 云主机。

```bash
sudo bash deploy/install.sh
```

脚本会做：建 `papermate` 系统用户 → 同步代码到 `/opt/papermate` →
建 venv 装依赖（走清华镜像）→ 生成 `/etc/papermate/papermate.env`（自动
随机口令并打印）→ 装 systemd 单元 → 启动 → 自检。**幂等**，可重复执行。

数据在 `/var/lib/papermate`，配置在 `/etc/papermate/papermate.env`。

### 路线 C：Docker + systemd 都要

两条都照上面做即可，互不冲突：Docker 跑在容器里，systemd 管的是宿主机上的
原生进程，选一种启动就行，别同时开。

---

## 2. 配 Nginx 反代（线路 A/B 都需要）

裸端口对外既不安全也没法上 HTTPS。用 `deploy/nginx.conf`：

```bash
sudo cp deploy/nginx.conf /etc/nginx/conf.d/papermate.conf
sudo vi /etc/nginx/conf.d/papermate.conf   # 改 server_name 与证书路径
sudo nginx -t && sudo systemctl reload nginx
```

配置里有三处**不能删**：

| 指令 | 值 | 为什么 |
|---|---|---|
| `client_max_body_size` | `100m` | 论文 PDF 常见 20–50MB；默认 1M 直接 413 |
| `proxy_read_timeout` | `1800s` | 一键成稿单步可能跑 10 分钟以上；默认 60s 会 504，而任务其实还在跑 |
| `proxy_buffering` | `off` | 将来加流式输出时，缓冲会让前端一个字都收不到 |

走 HTTPS 后必须在 `.env` 里加一行，否则登录 Cookie 会被浏览器丢弃
（表现：登录成功但一直跳回登录页）：

```ini
PAPERMATE_HTTPS=1
```

---

## 3. 访问控制怎么配

由两个变量决定，三种组合：

### 组合一：`shared`（课题组内部推荐）

```ini
PAPERMATE_ACCESS_TOKEN=<随机口令>
PAPERMATE_ALLOW_SERVER_KEY=1
DEEPSEEK_API_KEY=sk-xxxx
```

所有人输同一个口令进入，共用服务端这个 Key。最省事。

### 组合二：`byok`（公开分享推荐）

```ini
PAPERMATE_ACCESS_TOKEN=<随机口令>
PAPERMATE_ALLOW_SERVER_KEY=0
```

每人登录后必须在页面「设置」里填自己的 Key。**服务端 Key 一律不参与**
——即使 `.env` 里写了也会被忽略（这是接口层的硬拦截，不是前端藏输入框）。
Key 只存在用户自己的浏览器 `localStorage` 里，服务端不落盘。

### 组合三：`private`（不要用在公网）

```ini
# 不设 PAPERMATE_ACCESS_TOKEN
```

等价于桌面版：无鉴权。启动横幅会打印红色警告。**仅限本机或纯内网。**

> 安全底线：`PAPERMATE_HOST=0.0.0.0` + 不设口令 = 谁扫到端口谁就能刷你的
> 额度。启动日志里出现 `[!!] 警告` 就说明踩到了组合三。

---

## 4. 环境变量总表

| 变量 | 默认 | 说明 |
|---|---|---|
| `PAPERMATE_HOST` | `127.0.0.1` | 容器里必须 `0.0.0.0`；非回环值会开启「服务端模式」 |
| `PAPERMATE_PORT` | `8000` | 服务端模式不做端口顺延，端口被占直接报错退出 |
| `PAPERMATE_DATA_DIR` | `/data`（容器）/ `./data` | 可写数据根目录，优先级最高 |
| `PAPERMATE_ACCESS_TOKEN` | 空 | 访问口令。空 = 不鉴权 |
| `PAPERMATE_ALLOW_SERVER_KEY` | `1` | `0` = BYOK，服务端 Key 被忽略 |
| `PAPERMATE_SECRET` | 从口令派生 | Cookie 签名密钥。改口令会让所有登录立即失效（通常正是想要的） |
| `PAPERMATE_HTTPS` | 空 | `1` = 登录 Cookie 带 Secure。纯 HTTP 千万别设 |
| `PAPERMATE_TRUSTED_PROXIES` | `127.0.0.1` | 可信反代 IP，决定 `X-Forwarded-For` 是否可信 |
| `DEEPSEEK_API_KEY` | 空 | 服务端 Key（byok 模式忽略） |
| `DEEPSEEK_BASE_URL` | DeepSeek 官方 | 也支持 Anthropic / Lumda AI |
| `DEEPSEEK_MODEL` | `deepseek-chat` | |

---

## 5. 数据目录里都有什么

容器/裸机都只有一个可写根目录（`/data` 或 `/var/lib/papermate`）：

```
/data/
├── .env                 配置（安装器或你手写）
├── uploads/             上传的图片、原始数据文件
├── _oneshot/            一键成稿任务
│   └── <job_id>/
│       ├── _state.json  任务状态（阶段、进度、产物清单）
│       └── NN_*.md      各步骤产物
├── _sessions/           追问会话（7 天过期，最多 500 条）
├── _exports/            导出的 docx/tex/md
└── cache/
    └── litcache.sqlite3 文献检索缓存（正 30 天 / 负 3 天）
```

**备份就是拷这个目录。** 迁移到另一台机器：拷过去、改 `.env`、起服务。

---

## 6. 1.3.0 到底改了什么

### 6.1 服务端模式（新增 `paths.is_server()`）

判据只看 `PAPERMATE_HOST` 是否为非回环地址。一旦成立：

- 数据目录默认 `/data`（容器 VOLUME），不可写则退 `/app/data`
- 不再自动开浏览器（容器里没有，还会等 xdg-open 超时）
- 端口被占**不再顺延**，直接报错——反代和防火墙都按固定端口配，悄悄换端口只会让人查不出原因
- 日志走 stdout（容器日志采集靠它），`log_level` 提到 `info`
- 单实例检测关闭（容器里本机探测永远成功会直接退出，编排会误判成短暂重启）
- 启动横幅多打印一行「模式 服务端（监听 0.0.0.0）」

### 6.2 访问控制（新增 `auth.py`）

- 统一拦截中间件：除 `/api/health`、`/api/auth/*`、静态资源外，全部要口令
- 口令 → HMAC-SHA256 签名的 HttpOnly Cookie，有效期 30 天
- 用标准库 `hmac` 而不是 JWT：少一个依赖，精简镜像里 `cryptography` 经常编译失败
- 浏览器直访受保护接口时 303 跳 `/login.html`；XHR 拿到 401 由前端跳登录
- 未启用的 `private` 模式直接放行，桌面版零改动

### 6.3 状态落盘（新增 `state_store.py`）

- 追问会话：`_sessions/<sid>.json`，写时先临时文件再 `os.replace`，进程被杀不留半截 JSON
- 成稿任务：每个阶段结束写 `_oneshot/<job_id>/_state.json`
- **`llm` 字段（含 api_key）永不落盘**——容器卷一旦被备份/分享就泄露
- 启动时 `restore()` 把 `running` 改判为 `interrupted`：进程已经不在了，
  留着 running 会让前端一直转圈等一个永远不来的结果
- `interrupted` 状态**允许重跑**（这是修掉的一个真实缺陷：初版把 interrupted
  也挡在 rerun 外面，重启后任务就永远点不动了）

### 6.4 重跑补 Key

从磁盘恢复的任务内存里没有 Key（不落盘），所以 `/api/oneshot/rerun` 请求体
新增 `api_key`/`base_url`/`model`，前端 `osRerun` 自动带上。不加这条，重启后
重跑会在第一次模型调用处报「未配置 API Key」，而用户明明填过。

### 6.5 `/api/health` 扩展

新增 `version`、`access_mode`、`data_dir`、`jobs`。注意它**不因缺 Key 返回
非 200**——否则容器编排会把「没配 Key」当成「服务挂了」反复重启。

### 6.6 前端

- 新增 `static/login.html`（独立登录页，含开放重定向防护）
- `api()` 遇 401 自动跳登录并带回跳地址
- 顶部栏在口令模式下显示「退出」
- BYOK 模式下 Key 提示文案改为「本站不提供公共 Key」
- `interrupted` 状态有专门文案和重跑按钮，不再显示「未知错误」

---

## 7. 验收清单（12 条）

部署完逐条打勾。前 30 条自动化断言见 `_verify_cloud.py` / `_verify_state.py`。

```bash
# 1. 健康检查带版本
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
#    要求：version=1.3.0，access_mode 与预期一致

# 2. 未登录被挡
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/meta
#    要求：401

# 3. 登录页可访问
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/login.html
#    要求：200

# 4. 规则库完整
#    登录后页面显示 393 条规则；或看 /api/meta 的 rule_count

# 5. 数据目录正确
docker compose exec papermate ls -la /data
#    要求：见 .env / uploads / _oneshot / _sessions / cache

# 6. 程序目录不含 data/
docker compose exec papermate ls /app/data 2>&1 | head -1
#    要求：No such file or directory

# 7. 写文件生效（拿一个上传件或导出件落地）
# 8. 重启后登录仍有效
docker compose restart && curl -b "<cookie>" .../api/meta
# 9. 重启后任务变 interrupted 且可重跑
# 10. 上传 30MB PDF 不被 413 挡（走反代测，不是直连 8000）
# 11. HTTPS 下登录 Cookie 带 Secure；HTTP 下不带
# 12. BYOK 模式下即使 .env 有 Key，resolve_llm 也返回空
```

---

## 8. 已知边界（别当成 bug）

| 现象 | 原因 | 应对 |
|---|---|---|
| 趋势图偶尔 500 | 趋势模块只有 OpenAlex，无 Crossref 兜底（Crossref 没有年份聚合接口） | 重试或换个时段；文献检索不受影响 |
| 重启后正在跑的任务停下 | 进程内存里的执行线程随容器消失 | 点「重跑」从断点继续，已完成步骤的产物都在 |
| 不能开多 worker | 任务状态在进程内存（加磁盘快照），多 worker 会互相查不到任务 | 扩容请横着加容器并共享同一数据卷 |
| `.doc`/`.xls` 上传失败 | 默认镜像没装 LibreOffice | 用 `--target with-office` 重新构建 |
| 首次启动 30s 内 healthcheck 不过 | 393 条规则 YAML + PyMuPDF 加载 | `start_period` 已给 30s，无需处理 |
| 登录后一直跳回登录页 | 走了 HTTPS 但没设 `PAPERMATE_HTTPS=1`（或反之） | 让 `PAPERMATE_HTTPS` 与实际协议一致 |

---

## 9. 常用运维命令

```bash
# Docker
docker compose logs -f --tail 100
docker compose restart
docker compose down && docker compose up -d --build   # 升级（数据卷不动）
docker stats papermate

# systemd
systemctl status papermate
journalctl -u papermate -f
systemctl restart papermate

# 备份 / 迁移
tar czf pm-backup-$(date +%F).tgz -C /path/to data
# 恢复：解压回原位，确认属主，重启服务

# 换口令（会让所有人重新登录）
vi .env   # 改 PAPERMATE_ACCESS_TOKEN
docker compose restart   # 或 systemctl restart papermate
```
