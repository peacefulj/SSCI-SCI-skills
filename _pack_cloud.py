# -*- coding: utf-8 -*-
"""打 1.3.0 云部署源码包。

只装源码与部署文件，不装桌面版打包产物（dist/ dist_installer/ build/ 合计 300MB，
云上完全用不到）。排除项同时兼顾「不带密钥」与「不带用户数据」。
"""
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "PaperMate-1.3.0-cloud-src.zip"
TOP = "PaperMate-1.3.0-cloud-src"

# 目录整棵排除
SKIP_DIRS = {
    "dist", "dist_installer", "build", "installer",
    "_exports", "_oneshot", "_sessions", "uploads", "cache",
    "__pycache__", ".git", ".venv", "venv",
    "_inspect", "data", ".pytest_cache", "_reftest", "_cloudtest",
}
# 只在**项目根**排除的目录：skill/ 下的同名目录是规则库自身的一部分
# （`_dev/` 是规则合并底稿，`tests/` 是 12 篇真实论文校准样本），
# 整棵跳过会让规则指纹与校准基线对不上。1.2.8 踩过这个坑。
SKIP_DIRS_ROOT_ONLY = {"_dev", "tests"}
# 扩展名排除
SKIP_EXT = {".pyc", ".pyo", ".sqlite3", ".sqlite3-wal", ".sqlite3-shm",
            ".bak", ".tmp", ".log"}
# 单文件排除（密钥、日志、附件、桌面版产物）
SKIP_FILES = {".env", ".env.local", "icon.ico"}

count = 0
files = 0
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = Path(dirpath).relative_to(ROOT)
        # 就地裁剪遍历，避免进大目录
        skip = SKIP_DIRS | (SKIP_DIRS_ROOT_ONLY if rel_dir == Path(".") else set())
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            p = Path(dirpath) / fn
            if fn in SKIP_FILES:
                continue
            if p.suffix.lower() in SKIP_EXT:
                continue
            # 顶层大文件：桌面版安装包、旧源码包、图片素材
            if rel_dir == Path(".") and p.suffix.lower() in (".exe", ".zip", ".ico"):
                continue
            arc = Path(TOP) / rel_dir / fn
            z.write(p, str(arc).replace(os.sep, "/"))
            files += 1

size = OUT.stat().st_size
print(f"打包完成：{OUT}")
print(f"  条目 {files} 个，体积 {size/1048576:.1f} MB")

# 自检：包里必须没有 .env 与密钥
with zipfile.ZipFile(OUT) as z:
    names = z.namelist()
    bad = [n for n in names if n.endswith("/.env")]
    print(f"  .env 泄漏检查：{'发现 ' + str(bad) if bad else '无'}")
    for must in ("server.py", "Dockerfile", "docker-compose.yml",
                 ".env.cloud.example", "deploy/DEPLOY.md",
                 "deploy/papermate.service", "deploy/nginx.conf",
                 "deploy/install.sh", "static/login.html", "auth.py",
                 "state_store.py",
                 "skill/academic-writing-v1.1/rules/rules.yaml"):
        ok = any(n.endswith("/" + must) for n in names)
        print(f"  {'[OK]' if ok else '[XX]'} {must}")
