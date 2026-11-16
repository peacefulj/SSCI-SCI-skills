#!/usr/bin/env bash
# PaperMate 裸机 / 云主机安装脚本（Ubuntu 22.04+ / Debian 12+）
#
# 用法（在解压后的源码根目录执行）：
#   sudo bash deploy/install.sh
#
# 做七件事：建用户 → 建目录 → 建 venv 装依赖 → 生成配置 → 装 systemd →
# 起服务 → 自检。全部幂等，重复执行只会更新代码和依赖。
set -euo pipefail

APP_DIR=/opt/papermate
DATA_DIR=/var/lib/papermate
CONF_DIR=/etc/papermate
SERVICE=papermate
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

info(){ printf '\033[32m[OK]\033[0m %s\n' "$*"; }
warn(){ printf '\033[33m[!!]\033[0m %s\n' "$*"; }
die(){  printf '\033[31m[ERR]\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "请用 root 或 sudo 运行"

# ---------------------------------------------------------------- 1. 环境
command -v python3 >/dev/null || die "缺少 python3，请先 apt install python3"
PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)' \
  || die "Python $PYV 太低，本程序要求 3.10 或更高"

if ! python3 -c 'import venv' 2>/dev/null; then
    warn "缺 python3-venv，尝试安装"
    apt-get update -qq && apt-get install -y -qq python3-venv python3-pip
fi

# ---------------------------------------------------------------- 2. 用户与目录
if ! id papermate >/dev/null 2>&1; then
    useradd --system --create-home --shell /usr/sbin/nologin papermate
    info "已创建系统用户 papermate"
fi

mkdir -p "$APP_DIR" "$DATA_DIR" "$CONF_DIR"
# 代码从当前源码目录同步过去；--delete 让删掉的文件也跟着删，
# 但排除用户数据目录，避免把运行时文件一起清掉
if [ "$SRC_DIR" != "$APP_DIR" ]; then
    command -v rsync >/dev/null || apt-get install -y -qq rsync
    rsync -a --delete \
        --exclude '.venv' --exclude 'data' --exclude 'uploads' \
        --exclude '_oneshot' --exclude '_sessions' --exclude '_exports' \
        --exclude 'cache' --exclude '__pycache__' --exclude '.env' \
        "$SRC_DIR/" "$APP_DIR/"
    info "代码已同步到 $APP_DIR"
fi
chown -R papermate:papermate "$APP_DIR" "$DATA_DIR"
chmod 750 "$DATA_DIR"

# ---------------------------------------------------------------- 3. 依赖
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
    python3 -m venv "$APP_DIR/.venv"
    info "已创建 venv"
fi
# 国内机器默认源经常超时，用清华镜像；已配置过镜像也无妨（同一个包）
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt" \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
  || "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
chown -R papermate:papermate "$APP_DIR/.venv"
info "依赖已安装"

# ---------------------------------------------------------------- 4. 配置
CONF="$CONF_DIR/papermate.env"
if [ ! -f "$CONF" ]; then
    TOKEN=$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')
    cat > "$CONF" <<EOF
# PaperMate 环境配置（由 install.sh 生成于 $(date '+%F %T')）
# 改完执行 systemctl restart $SERVICE 生效

# 访问口令：进站点要先输入这个
PAPERMATE_ACCESS_TOKEN=$TOKEN

# 1 = 全组共用一个服务端 Key；0 = 每人自带 Key
PAPERMATE_ALLOW_SERVER_KEY=1

# 模型 Key（不填也可以在网页「设置」里填，但只对当前浏览器有效）
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
EOF
    chown root:papermate "$CONF"
    chmod 640 "$CONF"
    info "已生成配置 $CONF"
    warn "访问口令：$TOKEN"
    warn "请立刻记下来，同时写入 DEEPSEEK_API_KEY"
else
    info "配置已存在，保留不动：$CONF"
fi

# ---------------------------------------------------------------- 5. systemd
install -m 644 "$APP_DIR/deploy/papermate.service" "/etc/systemd/system/$SERVICE.service"
systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null
systemctl restart "$SERVICE"
info "systemd 单元已安装并启动"

# ---------------------------------------------------------------- 6. 自检
echo -n "等待服务就绪"
for i in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
        echo; info "服务已就绪"; break
    fi
    echo -n "."
    sleep 1
    [ "$i" -eq 30 ] && { echo; die "30 秒内没起来，看日志：journalctl -u $SERVICE -n 50 --no-pager"; }
done

curl -fsS http://127.0.0.1:8000/api/health | python3 -m json.tool || true

# ---------------------------------------------------------------- 7. 下一步
cat <<EOF

============================================================
安装完成。下一步：

1) 配 Nginx 反代（推荐，否则只能本机访问）
   cp $APP_DIR/deploy/nginx.conf /etc/nginx/conf.d/papermate.conf
   # 改 server_name 与证书路径，然后：
   nginx -t && systemctl reload nginx

2) 走 HTTPS 时，在 $CONF 里加一行：
   PAPERMATE_HTTPS=1
   然后 systemctl restart $SERVICE

3) 常用命令
   systemctl status  $SERVICE
   journalctl -u $SERVICE -f
   systemctl restart $SERVICE

数据目录：$DATA_DIR   （备份直接拷这个目录）
配置文件：$CONF
============================================================
EOF
