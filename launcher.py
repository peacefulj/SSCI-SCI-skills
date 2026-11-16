# -*- coding: utf-8 -*-
"""PaperMate 打包入口（PyInstaller 的入口脚本）。

**只做打包相关的事，不承担业务逻辑**

启动顺序：
1. 确定可写数据目录（安装器通过 `PAPERMATE_DATA_DIR` 指定，否则 exe 同级 `data/`）；
   首次运行时建目录、把 `.env.example` 复制成 `.env`（已存在则不动）。
2. 把数据目录设为工作目录，让 `uploads/`、`_oneshot/` 的相对行为可预期。
3. 交给 `server.main()`——它自带单实例检测、端口顺延、浏览器打开。

**为什么单独一个文件**
若直接拿 `server.py` 当入口，PyInstaller 写死的 `sys.argv[0]` 与
`__file__` 语义都会变；用一层薄入口更容易控制，也方便将来加"更新检查"之类
的分发期逻辑而不污染业务代码。
"""
from __future__ import annotations

import os
import shutil
import sys
import traceback
from pathlib import Path


def _bootstrap_data_dir() -> Path:
    """确保可写数据目录存在，并补一份 .env。返回数据目录。"""
    import paths

    data = paths.data_root()
    ok, err = paths.ensure_dir(data)
    if not ok:
        # 数据目录不可写时退回用户目录，避免整个程序起不来
        fallback = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "PaperMate"
        try:
            fallback.mkdir(parents=True, exist_ok=True)
            os.environ["PAPERMATE_DATA_DIR"] = str(fallback)
            data = fallback
            print(f"[提示] 数据目录不可写（{err}），改用：{data}")
        except Exception:
            print(f"[警告] 数据目录不可写且无法回退：{err}")

    for sub in ("uploads", "_oneshot"):
        try:
            (data / sub).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    # 首次运行给一份 .env（从资源目录的模版复制），已有就绝不覆盖
    env_file = data / ".env"
    if not env_file.exists():
        src = paths.resource_root() / ".env.example"
        if src.is_file():
            try:
                shutil.copyfile(src, env_file)
                print(f"[提示] 已生成配置文件：{env_file}")
                print("       在里面填 DEEPSEEK_API_KEY，或在网页右上角「设置」里填。")
            except Exception:
                pass
    return data


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

    try:
        data = _bootstrap_data_dir()
        try:
            os.chdir(data)
        except Exception:
            pass

        import server
        return server.main() or 0
    except SystemExit as e:
        return int(e.code or 0)
    except Exception:
        print("\n" + "=" * 60)
        print("  启动失败，下面是详细错误（请截图发给开发者）")
        print("=" * 60)
        traceback.print_exc()
        try:
            import paths
            print("\n路径诊断：")
            for k, v in paths.describe().items():
                print(f"  {k}: {v}")
        except Exception:
            pass
        try:
            input("\n按回车键关闭窗口…")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
