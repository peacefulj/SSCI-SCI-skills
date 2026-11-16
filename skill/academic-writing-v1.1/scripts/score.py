#!/usr/bin/env python3
"""score.py —— 学术写作规则批量打分器（v1.1.0）

用法：
  单文件：
    python score.py samples/qnt_good_1.md --track quant
  批量（按 manifest）：
    python score.py --suite tests/samples --manifest tests/manifest.yaml
  导出 JSON：
    python score.py ... --json out.json

设计说明：
  只有 rules/detectors.yaml 中登记了词面检测器的规则才能自动判定；
  其余规则属"需人工核对"，脚本在 coverage 一栏明确报出，不假装已检查。

  判定语义：
    require      —— 文本必须命中 patterns 之一，否则记 1 处缺陷
    forbid       —— 文本命中 patterns 之一即记 1 处缺陷
    require_when —— 仅当 when 命中时才要求 patterns 命中
    forbid_when  —— 仅当 when 命中时，patterns 命中才记缺陷
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("需要 PyYAML：pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "rules" / "rules.yaml"
DETECTORS = ROOT / "rules" / "detectors.yaml"

SECTIONS = {
    "abstract": r"^[\s#>*\-\d\.]{0,10}(abstract|summary|摘要)\b",
    "introduction": r"^[\s#>*\-\d\.]{0,10}(introduction|引言|前言)\b",
    "related-work": r"^[\s#>*\-\d\.]{0,10}(related\s+work|background|literature\s+review|相关工作|文献综述)\b",
    "method": r"^[\s#>*\-\d\.]{0,10}(method|methods|materials?\s+and\s+methods?|methodology|method\s+and\s+data|data\s+and\s+methods?|empirical\s+(strategy|design|approach)|research\s+design|study\s+design|identification|方法|材料与方法|研究数据与方法|研究设计)\b",
    "results": r"^[\s#>*\-\d\.]{0,10}(results?|findings|experiments?|结果|实验)\b",
    "discussion": r"^[\s#>*\-\d\.]{0,10}(discussion|讨论)\b",
    "conclusion": r"^[\s#>*\-\d\.]{0,10}(conclusions?|结论)\b",
    "references": r"^[\s#>*\-\d\.]{0,10}(references|bibliography|参考文献)\b",
}


def load_yaml(p):
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_text(p):
    return Path(p).read_text(encoding="utf-8", errors="ignore")


def any_match(patterns, text):
    for pat in patterns:
        try:
            if re.search(pat, text, re.IGNORECASE | re.MULTILINE):
                return True
        except re.error:
            continue
    return False


def eval_detector(det, text):
    """返回 (状态, 说明)。状态：defect / pass / na"""
    kind = det["kind"]
    pats = det.get("patterns", [])
    when = det.get("when", [])
    not_when = det.get("not_when", [])

    # 作用域排除：命中 not_when 说明该设计不适用此条，直接判 na
    if not_when and any_match(not_when, text):
        return ("na", "该设计不适用此条")

    if kind == "require":
        return ("pass", None) if any_match(pats, text) else ("defect", "缺失必需要素")

    if kind == "forbid":
        return ("defect", "命中禁用表述") if any_match(pats, text) else ("pass", None)

    if kind == "require_when":
        if not any_match(when, text):
            return ("na", "前提条件未出现，不适用")
        return ("pass", None) if any_match(pats, text) else ("defect", "前提已出现但缺少配套要素")

    if kind == "forbid_when":
        if not any_match(when, text):
            return ("na", "前提条件未出现，不适用")
        return ("defect", "前提情境下出现禁用表述") if any_match(pats, text) else ("pass", None)

    return ("na", f"未知 kind {kind}")



REF_HEAD = r"(?im)^[\s#>*\-]*\d*[.\s]*(references|bibliography|works cited|literature cited|参考文献)\s*[:：]?\s*$"


def body_only(text):
    """切掉参考文献列表，避免文献题名污染正文规则判定。
    取文档后半段最后一次出现的参考文献标题作为切点；找不到则返回全文。"""
    hits = [m.start() for m in re.finditer(REF_HEAD, text)]
    if not hits:
        return text
    cut = [h for h in hits if h > len(text) * 0.5]
    return text[:cut[-1]] if cut else text


def detect_sections(text):
    found = {}
    low = text.lower()
    for name, pat in SECTIONS.items():
        found[name] = bool(re.search(pat, low, re.MULTILINE))
    return found


def score_file(path, track, rules_by_id, detectors, verbose=True):
    full = read_text(path)
    text = body_only(full)
    dets = [d for d in detectors if d.get("track") == track or d.get("track") is None]
    applicable = [r for r in rules_by_id.values()
                  if r.get("track") == track or (track in (r.get("genre") or []))]

    results = []
    for d in dets:
        tgt = full if d.get("scope") == "references" else text
        status, reason = eval_detector(d, tgt)
        results.append({"id": d["id"], "status": status, "reason": reason,
                        "severity": d.get("severity", "should")})

    defects = [r for r in results if r["status"] == "defect"]
    must = [r for r in defects if r["severity"] == "must"]
    should = [r for r in defects if r["severity"] == "should"]
    nice = [r for r in defects if r["severity"] == "nice"]
    passed = [r for r in results if r["status"] == "pass"]
    na = [r for r in results if r["status"] == "na"]
    words = len(re.findall(r"\b[\w-]+\b", text))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))

    # 摘要级文本的提醒：require 类规则会因缺少章节而大量误报，需明确告知
    thin = words + cjk // 2 < 500

    report = {
        "file": str(path),
        "thin_text": thin,
        "track": track,
        "words": words,
        "cjk_chars": cjk,
        "applicable_rules": len(applicable),
        "auto_checked": len(dets),
        "manual_only": len(applicable) - len([d for d in dets if d["id"] in rules_by_id]),
        "defect_count": len(defects),
        "must_count": len(must),
        "should_count": len(should),
        "nice_count": len(nice),
        "defects": defects,
        "passed": [p["id"] for p in passed],
        "na": [n["id"] for n in na],
        "sections": detect_sections(text),
    }

    if verbose:
        print(f"\n=== {os.path.basename(path)} | track={track} ===")
        print(f"  词数 {words} / 汉字 {cjk} | 适用规则 {len(applicable)} | 自动检查 {len(dets)} | 需人工 {report['manual_only']}")
        if defects:
            print(f"  命中 {len(defects)} 处（硬伤 {len(must)} / 建议 {len(should)} / 可选 {len(nice)}）：")
            for tag, group in (("硬伤", must), ("建议", should), ("可选", nice)):
                for d in group:
                    print(f"    [{tag}] {d['id']}  ({d['reason']})")
        else:
            print("  命中 0 处")
        if na:
            print(f"  不适用 {len(na)} 条（前提情境未出现）")
        if thin:
            print("  [注意] 文本量偏小（疑似仅摘要），require 类命中多为缺章节所致，不代表真实缺陷")
        missing = [k for k, v in report["sections"].items() if not v]
        if missing:
            print(f"  未见章节标题：{', '.join(missing)}")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", help="单个稿件路径")
    ap.add_argument("--track", default=None,
                    choices=["quant", "predictive", "qualitative", "basic-science", "clinical", "reporting",
                             "ei-conf", "ai-conf", "sci-journal", "ssci", "dissertation"])
    ap.add_argument("--suite", help="样稿目录")
    ap.add_argument("--manifest", help="manifest.yaml 路径")
    ap.add_argument("--json", help="导出 JSON 路径")
    args = ap.parse_args()

    rules = load_yaml(RULES)["rules"]
    rules_by_id = {r["id"]: r for r in rules}
    detectors = load_yaml(DETECTORS)["detectors"]

    out = []
    if args.file:
        if not args.track:
            sys.exit("单文件模式必须给 --track")
        out.append(score_file(args.file, args.track, rules_by_id, detectors))
    elif args.suite and args.manifest:
        man = load_yaml(args.manifest)
        rows = []
        for item in man["samples"]:
            p = Path(args.suite) / item["file"]
            if not p.exists():
                print(f"缺文件 {p}")
                continue
            rep = score_file(p, item["track"], rules_by_id, detectors, verbose=False)
            rep["grade"] = item["grade"]
            rep["expect"] = item.get("expect")
            out.append(rep)
            rows.append((item["file"], item["track"], item["grade"], rep["defect_count"], rep["must_count"], item.get("expect")))

        print("\n" + "=" * 78)
        print(f"{'样稿':34s}{'track':13s}{'档':6s}{'总':>3s}{'硬伤':>4s}  预期")
        print("-" * 78)
        bad = []
        for f, t, g, c, mc, e in rows:
            flag = ""
            if e:
                lo, hi = e if isinstance(e, list) else (e, e)
                if not (lo <= c <= hi):
                    flag = "  <<< 越界"
                    bad.append((f, c, e))
            print(f"{f[:33]:34s}{t:13s}{g:6s}{c:3d}{mc:4d}  {e}{flag}")
        print("-" * 78)
        if bad:
            print(f"共 {len(bad)} 份样稿偏离预期，需校准检测器")
        else:
            print("全部样稿落在预期区间内")
    else:
        sys.exit("用法：score.py <file> --track T  或  score.py --suite DIR --manifest M")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\n已导出 {args.json}")


if __name__ == "__main__":
    main()
