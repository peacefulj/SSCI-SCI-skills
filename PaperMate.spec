# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 —— PaperMate（开源论文搭子）。

    python -m PyInstaller --noconfirm --clean PaperMate.spec

产物：`dist/PaperMate/PaperMate.exe`（onedir，非 onefile）

**为什么用 onedir 而不是 onefile**

1. onefile 每次启动都要把上百 MB 解包到临时目录，冷启动常 10s+，用户会以为没反应；
2. onefile 的 `_MEIPASS` 每次运行都换路径，杀软更容易重复扫描、也更容易误杀；
3. `skill/` 规则库需要稳定落盘（指纹校验依赖文件路径），onedir 天然满足。

**资源与排除的两条原则**

- `static/` 与 `skill/` 必须原样带进去：前者是前端，后者是 393 条规则库 + 原生检测脚本。
- 排除 `pymupdf_layout` / `onnxruntime` / `matplotlib` 等：PDF 只用到 `get_text()`，
  版式模型（onnxruntime 45MB、631 个文件）与绘图层本项目从不调用，带上纯属浪费体积与启动时间。
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve()

# ---------- 数据文件 ----------
# skill/ 会整目录拷进去，本地跑过验证脚本就会留下 __pycache__（.pyc）。
# 这些字节码与本机 Python 版本绑定，打进去既没用、还会让 skill 指纹比对出现噪声，
# 所以在收集阶段就滤掉（维护 skill 时反复运行脚本很容易撞上）。
def _clean(tree_src: str, dest_root: str) -> list[tuple[str, str]]:
    """遍历目录树，产出 (源文件, 目标子目录)，跳过 __pycache__ / .pyc。

    目标路径必须保留 dest_root 前缀（如 "skill"），否则 skill 目录会被打平，
    运行时按 skill/academic-writing-v1.1/... 就找不到规则库。
    """
    import os as _os
    out = []
    for dirpath, dirnames, filenames in _os.walk(tree_src):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if fn.endswith((".pyc", ".pyo")):
                continue
            full = _os.path.join(dirpath, fn)
            rel = _os.path.relpath(dirpath, tree_src)
            dest = dest_root if rel == "." else _os.path.join(dest_root, rel)
            out.append((full, dest))
    return out


datas = [
    *_clean(str(ROOT / "static"), "static"),
    *_clean(str(ROOT / "skill"), "skill"),
    (str(ROOT / ".env.example"), "."),
    (str(ROOT / "requirements.txt"), "."),
    (str(ROOT / "README.md"), "."),
]

# ---------- 体积排除 ----------
# pymupdf_layout 一旦被自动收集，就会连带 onnxruntime(45MB) + numpy(51MB)；
# ingest.py 只用 pymupdf.open + get_text，不需要版式模型。
EXCLUDES = [
    "pymupdf_layout",
    "pymupdf4llm",
    "onnxruntime",
    "matplotlib",
    "scipy",
    "PIL",
    "IPython",
    "pytest",
    "setuptools",
    "pip",
    "tkinter",
    "PyQt5",
    "PySide6",
    "notebook",
    "jupyter",
    "pandas",      # 只有 dataset.py 里 try-import，缺了会降级提示
    "numpy",
    "torch",
    "tensorflow",
]

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "anyio._backends._asyncio",
    "multipart",
    "multipart.multipart",
    "yaml",
    "requests",
    "docx",
    "openpyxl",
    "pymupdf",
]

# 显式收集 uvicorn 子模块：打包后 uvicorn 走 importlib 动态加载协议实现，
# 静态分析看不到，必须手动列进去，否则启动报 "Could not import ..."
hiddenimports += collect_submodules("uvicorn")
hiddenimports = sorted(set(hiddenimports))


a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PaperMate",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX 压缩会被部分杀软标记为可疑，分发场景一律不开
    console=True,       # 保留控制台：自检报告、端口、报错都要让用户看得到
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PaperMate",
)
