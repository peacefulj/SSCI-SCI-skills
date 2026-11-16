# PaperMate 云端镜像（1.2.9）
#
# 构建：docker build -t papermate:1.2.9 .
# 运行：见 docker-compose.yml（推荐）或下方注释里的 docker run
#
# 设计取舍说明：
# 1. 基础镜像用 slim 而非 alpine。PyMuPDF / lxml / python-docx 都是 C 扩展或带
#    预编译轮子，alpine 的 musl 会让 pip 回退到源码编译，装一次十几分钟且常失败。
#    slim 的 glibc 与轮子匹配，装得又快又稳。
# 2. LibreOffice 单独做成一个可选 stage。它让镜像从 ~450MB 涨到 ~1.2GB，
#    只影响「上传 .doc/.xls 老格式」这一个能力。默认不装，需要时加 --build-arg。
# 3. 不装 gunicorn/多 worker。oneshot 的任务状态在进程内存里（加磁盘快照），
#    多 worker 会导致「A worker 接的任务、B worker 查不到」。要扩容就横着加容器
#    并共享同一个数据卷，不要在一个容器里开多 worker。
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

# 时区数据：容器默认 UTC，任务日志里的时间会差 8 小时，排查问题时很误导
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates tzdata curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依赖单独一层：改代码不会让 pip 重装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码（只读资源：static/ skill/ 等）
COPY . .

# 非 root 运行。容器逃逸的代价太大，这一行没有理由省。
# UID 固定 10001，docker-compose 里挂出来的卷用同一 UID，省得 chown 来 chown 去。
RUN useradd -m -u 10001 -s /bin/bash papermate \
    && mkdir -p /data \
    && chown -R papermate:papermate /app /data

USER papermate

# 数据卷：uploads / _oneshot / _sessions / cache / .env 全在这里
ENV PAPERMATE_DATA_DIR=/data \
    PAPERMATE_HOST=0.0.0.0 \
    PAPERMATE_PORT=8000

VOLUME ["/data"]
EXPOSE 8000

# start-period 给足 30s：PyMuPDF 首次加载 + 规则库 393 条 YAML 解析
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["python", "server.py"]


# ---------------------------------------------------------------- 可选：带 LibreOffice
# 仅当需要上传 .doc / .xls / .ods 老格式时构建：
#   docker build --target with-office -t papermate:1.2.9-office .
FROM base AS with-office

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui libreoffice-calc-nogui \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# nogui 版本没有 soffice 启动器，实操里叫 libreoffice；建个软链兼容两处硬编码
RUN ln -sf /usr/bin/libreoffice /usr/local/bin/soffice || true

USER papermate
