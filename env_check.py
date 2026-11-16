#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PaperMate 环境自检 / 依赖安装。

    python env_check.py            只检查，打印报告（缺依赖时退出码 1）
    python env_check.py --install  缺依赖则自动安装；默认源失败自动换国内镜像
    python env_check.py --json     机器可读（给脚本用）

只用标准库，所以「什么都没装」时也能跑起来告诉你缺什么。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import paths

BASE_DIR = paths.data_root()
MIN_PY = (3, 10)

# 模块名 -> 显示名（import 名与包名常常不一样，这里分开写）
REQUIRED = [
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("yaml", "PyYAML"),
    ("requests", "requests"),
    ("multipart", "python-multipart"),
    ("docx", "python-docx"),
    ("lxml", "lxml"),
    ("openpyxl", "openpyxl"),
]

MIRRORS = [
    ("默认源", []),
    ("清华镜像", ["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]),
    ("阿里云镜像", ["-i", "https://mirrors.aliyun.com/pypi/simple"]),
]


def _have(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def _soffice() -> str | None:
    for c in (os.environ.get("SOFFICE_PATH"), shutil.which("soffice"),
              shutil.which("libreoffice"),
              r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if c and Path(c).exists():
            return c
    return None


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _writable(d: Path) -> tuple[bool, str]:
    try:
        d.mkdir(parents=True, exist_ok=True)
        p = d / f".probe_{os.getpid()}"
        p.write_text("ok", encoding="utf-8")
        p.unlink()
        return True, ""
    except Exception as e:
        return False, str(e)


def _env_key() -> str:
    p = paths.env_path()
    if not p.exists():
        return os.environ.get("DEEPSEEK_API_KEY", "")
    raw = p.read_bytes()
    text = None
    for enc in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].strip()
        if line.startswith("DEEPSEEK_API_KEY=") and "=" in line:
            v = line.split("=", 1)[1].strip().strip('"').strip("'")
            if v:
                return v
    return os.environ.get("DEEPSEEK_API_KEY", "")


def collect() -> dict:
    py_ok = sys.version_info >= MIN_PY
    frozen = paths.is_frozen()
    miss = [label for mod, label in REQUIRED if not _have(mod)]
    missing_mods = [mod for mod, label in REQUIRED if not _have(mod)]
    up_ok, up_err = _writable(BASE_DIR / "uploads")
    job_ok, job_err = _writable(BASE_DIR / "_oneshot")
    return {
        "frozen": frozen,
        "paths": paths.describe(),
        "python": {
            "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "executable": sys.executable,
            "bits": 64 if sys.maxsize > 2 ** 32 else 32,
            "ok": py_ok,
            "need": "%d.%d+" % MIN_PY,
        },
        "required": {"missing": miss, "missing_modules": missing_mods,
                     "total": len(REQUIRED), "ok": not miss},
        "optional": {
            "xlsx": _have("openpyxl"),
            "pdf": _have("pymupdf") or _have("fitz"),
            "pandas": _have("pandas"),
            "libreoffice": bool(_soffice()),
        },
        "dirs": {"uploads": up_ok, "uploads_err": up_err,
                 "_oneshot": job_ok, "_oneshot_err": job_err},
        "port_8000": _port_free(8000),
        "api_key": bool(_env_key()),
        "ready": bool(py_ok and not miss and up_ok and job_ok),
    }


def report(r: dict) -> None:
    line = "-" * 60
    print(line)
    print("  PaperMate 环境自检")
    print(line)

    py = r["python"]
    if not r.get("frozen"):
        mark = "[OK]" if py["ok"] else "[缺]"
        print(f"  {mark} Python {py['version']} ({py['bits']} 位)"
              + ("" if py["ok"] else f" —— 需要 {py['need']}，请升级 Python"))
        if not py["ok"]:
            print(f"       当前解释器：{py['executable']}")

    req = r["required"]
    if r.get("frozen"):
        # 打包分发版：依赖已随 exe 内置，不存在"用户自己 pip 装"这一环
        print(f"  [OK] 运行方式：独立安装包（Python 与依赖已内置，无需另装）")
        if not req["ok"]:
            print(f"  [缺] 安装包不完整，缺少：{', '.join(req['missing'])}")
            print("       这说明安装过程中有文件被杀毒软件隔离或未完整解压，")
            print("       请重新运行安装包，并把安装目录加入杀毒软件白名单。")
    elif req["ok"]:
        print(f"  [OK] 必需依赖 {req['total']}/{req['total']} 齐全")
    else:
        print(f"  [缺] 缺少依赖：{', '.join(req['missing'])}")
        print("       修复：python -m pip install -r requirements.txt")
        print("       国内慢：python -m pip install -r requirements.txt "
              "-i https://pypi.tuna.tsinghua.edu.cn/simple")

    o = r["optional"]
    on = [n for n, k in (("xlsx", "xlsx"), ("PDF", "pdf"),
                         ("dta/sav", "pandas"), ("LibreOffice", "libreoffice")) if o[k]]
    if on:
        print("  [OK] 可选能力已启用：" + " / ".join(on))
    weak = []
    if not o["xlsx"]:
        weak.append("xlsx 数据上传" + ("" if r.get("frozen") else "（装 openpyxl）"))
    if not o["pdf"]:
        weak.append("PDF 上传" + ("" if r.get("frozen") else "（装 PyMuPDF）"))
    if not o["pandas"]:
        weak.append("dta/sav/parquet（可选，或先导出 csv）")
    if not o["libreoffice"]:
        weak.append(".doc/.xls/.ods 上传（可选：装 LibreOffice，或先另存为 docx/xlsx）")
    for w in weak:
        print(f"  [--] 未启用：{w}")

    d = r["dirs"]
    if d["uploads"] and d["_oneshot"]:
        print("  [OK] 数据目录可写")
    else:
        print("  [缺] 数据目录不可写：")
        if not d["uploads"]:
            print(f"       uploads/  {d['uploads_err']}")
        if not d["_oneshot"]:
            print(f"       _oneshot/ {d['_oneshot_err']}")
        print("       请把文件夹解压到「文档」或桌面这类有写权限的位置，")
        print("       不要放在 Program Files、只读盘，或直接在压缩包里运行。")

    if r["port_8000"]:
        print("  [OK] 8000 端口可用")
    else:
        print("  [--] 8000 端口已被占用；启动时会自动顺延到 8001/8002…")

    if r["api_key"]:
        print("  [OK] API Key 已配置")
    else:
        print("  [--] 未配置 API Key（启动后在网页右上角「设置」里填也可以）")

    print(line)
    if r["ready"]:
        print("  结论：可以启动。下一步 -> python server.py（或双击 start.bat）")
    else:
        print("  结论：还差上面的 [缺] 项，先补齐再启动。")
    print(line)


def install() -> int:
    if paths.is_frozen():
        print("当前是独立安装包，依赖已内置，无需 pip 安装。")
        print("若提示安装包不完整，请重新运行安装包，并检查杀毒软件是否隔离了文件。")
        return 1
    req = BASE_DIR / "requirements.txt"
    if not req.exists():
        print(f"找不到 {req}")
        return 1
    for name, extra in MIRRORS:
        print(f"\n==> 用{name}安装依赖（首次约 2–10 分钟，取决于网络，请不要关窗口）...")
        cmd = [sys.executable, "-m", "pip", "install", "-r", str(req)] + extra
        try:
            rc = subprocess.call(cmd)
        except Exception as e:
            print(f"    启动 pip 失败：{e}")
            continue
        if rc == 0:
            print(f"==> 安装完成（{name}）")
            return 0
        print(f"==> {name}失败（退出码 {rc}）")
    print("\n三个源都失败了。可尝试："
          "\n  1) 检查网络/公司代理；"
          "\n  2) 手动执行 pip install -r requirements.txt -i <镜像地址>；"
          "\n  3) 若只缺 PDF 功能，可先删掉 requirements.txt 里的 PyMuPDF 行。")
    return 1


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--install", action="store_true", help="缺依赖时自动安装")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    r = collect()
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        report(r)

    if args.install and not r["required"]["ok"]:
        if install() != 0:
            return 1
        r = collect()
        if not args.json:
            print()
            report(r)

    return 0 if r["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
