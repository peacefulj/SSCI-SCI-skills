# -*- coding: utf-8 -*-
"""资源路径解析 —— 源码运行与 PyInstaller 打包运行共用一套。

**为什么需要这一层**

打包后 `__file__` 指向的是 PyInstaller 的解包目录（`sys._MEIPASS`），
它有三个致命限制：只读、每次升级会变、用户看不到。而本应用同时需要两类路径：

| 类别 | 例子 | 特征 | 打包后放哪 |
|---|---|---|---|
| 只读资源 | `static/`、`skill/` | 随版本发布，不许改 | `_MEIPASS`（exe 旁的 `_internal/`） |
| 可写数据 | `uploads/`、`_oneshot/`、`.env`、`_exports/` | 用户产生，必须留存 | exe 同级的 `data/` |

把两者混用是打包后最常见的坑：`uploads` 写进 `_MEIPASS` 会 PermissionError，
`skill` 从数据目录读会在升级后失联（规则指纹校验就过不了）。

**解析规则**

- `resource_root()`：目录，只读资源基准。源码运行 = 本文件所在目录；打包运行 = `_MEIPASS`。
- `data_root()`：目录，可写数据基准。源码运行 = 本文件所在目录（保持与旧版一致，
  老用户的 `uploads/` 原地续用）；打包运行 = exe 同级 `data/`。
- `env_path()`：`.env` 位置。源码运行 = 项目根；打包运行 = 可写数据目录
  （安装到 Program Files 时 `.env` 不可写，必须落在用户数据目录）。
- `cache_path()`：文献检索缓存。永远在可写数据目录的 `cache/` 下。
- `is_frozen()`：是否处于 PyInstaller 打包环境。

**一条硬约束**：本模块只依赖标准库，且必须在任何业务模块之前可导入——
环境自检在「装了一半依赖」的机器上也要能跑。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包产物里。"""
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """只读资源基准目录（`static/`、`skill/` 的父目录）。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent


def exe_dir() -> Path:
    """可执行文件所在目录；源码运行时退化为项目根。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# 安装器写入 exe 旁边的引导文件：内容是用户数据目录的绝对路径。
# 为什么用文件而不是环境变量：用户可能从开始菜单、桌面快捷方式、甚至直接双击
# exe 启动，这几种方式都拿不到安装时设置的环境变量，而文件一定读得到。
DATA_HOME_FILE = "datahome.txt"


def _data_home_from_file() -> Path | None:
    try:
        f = exe_dir() / DATA_HOME_FILE
        if f.is_file():
            raw = f.read_text(encoding="utf-8").strip()
            if raw:
                return Path(raw).expanduser().resolve()
    except Exception:
        pass
    return None


def is_server() -> bool:
    """是否运行在「服务端 / 容器」模式（监听非回环地址）。

    判据只看 `PAPERMATE_HOST`：桌面版从不设置它，云上部署一定设置。
    这个开关同时决定三件事——数据目录默认值、是否自动开浏览器、
    以及日志该写 stdout 还是文件。
    """
    host = (os.environ.get("PAPERMATE_HOST") or "").strip().lower()
    return host not in ("", "127.0.0.1", "localhost", "::1")


def default_data_dir() -> Path:
    """没有显式指定数据目录时，各平台的合理默认值。

    - Windows 打包版：exe 同级 `data/`（绿色版），或安装器写的引导文件
    - Linux/macOS 服务端：`/data`（Dockerfile 里就是这个卷）→ 不可写则 `./data`
    - 源码运行：项目根（保持与旧版一致，老用户的 `uploads/` 原地续用）

    **为什么服务端优先 `/data`**：容器里 `/data` 是显式声明的 VOLUME，
    容器重建后挂回来还在；而镜像层里的目录一删就没了。
    """
    if os.name != "nt" and is_server():
        p = Path("/data")
        if p.exists() and os.access(p, os.W_OK):
            return p
        return Path("/app/data")
    return exe_dir() / "data"


def data_root() -> Path:
    """可写数据基准目录（`uploads/`、`_oneshot/` 等的父目录）。

    优先级：环境变量 `PAPERMATE_DATA_DIR` > 引导文件 `datahome.txt`
    > 平台默认值（见 `default_data_dir()`）> 项目根（源码运行）。

    **为什么安装版必须走引导文件**：安装到 `%LOCALAPPDATA%\\Programs\\PaperMate`
    后，程序目录会在卸载/覆盖升级时被删。若稿件和 `.env` 留在程序目录，
    升级一次就全没了。安装器因此把数据目录指到 `%LOCALAPPDATA%\\PaperMate`，
    并在 exe 旁写入 `datahome.txt` 告知程序。

    **容器里为什么不需要引导文件**：`PAPERMATE_DATA_DIR=/data` 由
    docker-compose 或 systemd 的环境变量直接给出，优先级最高，最先命中。
    """
    override = os.environ.get("PAPERMATE_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if is_frozen():
        from_file = _data_home_from_file()
        if from_file:
            return from_file
        return default_data_dir()
    if is_server():
        return default_data_dir()
    return Path(__file__).resolve().parent


def env_path() -> Path:
    """`.env` 文件位置。优先可写数据目录，回退到源码/资源根。"""
    p = data_root() / ".env"
    if p.exists():
        return p
    legacy = exe_dir() / ".env"
    if legacy.exists():
        return legacy
    return p


def cache_path() -> Path:
    """文献检索缓存（SQLite）。必须落在可写数据目录——
    写进 `_MEIPASS` 在打包后会直接 PermissionError 或静默丢缓存。"""
    return data_root() / "cache" / "litcache.sqlite3"


def ensure_dir(p: Path) -> tuple[bool, str]:
    """建目录并做一次写探针。返回 (可写?, 错误信息)。"""
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / f".probe_{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True, ""
    except Exception as e:  # noqa: BLE001 - 探针要吞掉所有异常
        return False, str(e)


def describe() -> dict:
    """当前路径解析结果，供自检与 `--diagnose` 输出。"""
    r = resource_root()
    d = data_root()
    return {
        "frozen": is_frozen(),
        "server_mode": is_server(),
        "resource_root": str(r),
        "data_root": str(d),
        "exe": sys.executable,
        "python": "%d.%d.%d" % sys.version_info[:3],
        "platform": "windows" if os.name == "nt" else sys.platform,
        "static_ok": (r / "static" / "index.html").is_file(),
        "skill_ok": (r / "skill" / "academic-writing-v1.1" / "rules" / "rules.yaml").is_file(),
        "data_writable": ensure_dir(d)[0],
        "env": str(env_path()),
        "cache": str(cache_path()),
    }
