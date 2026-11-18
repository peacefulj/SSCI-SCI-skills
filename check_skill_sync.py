"""校验内嵌 skill 与已安装 skill 源的规则层是否一致，并可刷新 .radar-addon 基线指纹。

用法：
    python check_skill_sync.py                 # 只比对，不一致时退出码 1
    python check_skill_sync.py --refresh-baseline   # 规则层有意改动后，刷新 manifest 的 baseline_sha256

规则层（rules.yaml / detectors.yaml）必须两边逐字节一致；
SKILL.md / 使用教程.md 只报告差异，不强制（PaperMate 可能有自己的附加说明）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
EMBED = HERE / "skill" / "academic-writing-v1.1"
SOURCE = Path(os.environ.get("AW_SKILL_SOURCE")
              or Path.home() / ".workbuddy" / "skills" / "academic-writing")
STRICT = ["rules/rules.yaml", "rules/detectors.yaml"]
SOFT = ["SKILL.md", "使用教程.md"]


def sha(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-baseline", action="store_true")
    a = ap.parse_args()

    bad = 0
    print(f"内嵌：{EMBED}\n源  ：{SOURCE}")
    for rel in STRICT + SOFT:
        e, s = sha(EMBED / rel), sha(SOURCE / rel)
        same = e == s
        tag = "一致" if same else ("源缺失" if s is None else "不一致")
        print(f"  {rel:24s} {tag}  {(e or '-')[:12]} / {(s or '-')[:12]}")
        if rel in STRICT and not same and s is not None:
            bad += 1

    man = EMBED / ".radar-addon" / "manifest.json"
    if man.exists():
        d = json.loads(man.read_text(encoding="utf-8"))
        base = d.get("baseline_sha256") or {}
        drift = [k for k, v in base.items() if sha(EMBED / k) != v]
        if a.refresh_baseline:
            for k in list(base) or STRICT + SOFT:
                h = sha(EMBED / k)
                if h:
                    base[k] = h
            d["baseline_sha256"] = base
            d["baseline_refreshed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            man.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("已刷新 .radar-addon 基线指纹")
        elif drift:
            print("  addon 基线与当前文件不符：" + "、".join(drift)
                  + "（若是有意改规则，请加 --refresh-baseline）")
            bad += 1

    print("结果：" + ("通过" if not bad else f"{bad} 项不一致"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
