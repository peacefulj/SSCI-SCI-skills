#!/usr/bin/env python3
"""结构自检脚本 v1.1.0 —— 多体裁/多学科路由

用法:
    python check_structure.py manuscript.txt                    # 默认 ei-conf
    python check_structure.py manuscript.txt --genre sci-journal
    python check_structure.py manuscript.txt --genre quant
    python check_structure.py manuscript.txt --genre qualitative --lang zh
    python check_structure.py manuscript.txt --genre clinical

支持 --genre: ei-conf | ai-conf | sci-journal | ssci | dissertation |
               quant | predictive | qualitative | basic-science | clinical

说明: 本脚本只做结构与词面启发式检查。规则库中不可词面判定的条目，
      需按 rules.yaml 的 signal 人工核对；批量打分请用 scripts/score.py。
"""
import argparse
import re
from pathlib import Path

# ---------- 通用章节词面（中英双语）----------
SECTION_PATTERNS = {
    "abstract": r"^[\s#>*\-\d\.]{0,10}(abstract|summary|摘要)\b",
    "introduction": r"^[\s#>*\-\d\.]{0,10}(introduction|引言|前言)\b",
    "related-work": r"^[\s#>*\-\d\.]{0,10}(related\s+work|background|literature\s+review|相关工作|文献综述)\b",
    "method": r"^[\s#>*\-\d\.]{0,10}(method|methods|materials?\s+and\s+methods?|methodology|method\s+and\s+data|data\s+and\s+methods?|empirical\s+(strategy|design|approach)|research\s+design|study\s+design|identification|方法|材料与方法|研究设计|数据与方法)\b",
    "results": r"^[\s#>*\-\d\.]{0,10}(results?|findings|experiments?|evaluation|结果|实验)\b",
    "discussion": r"^[\s#>*\-\d\.]{0,10}(discussion|讨论)\b",
    "conclusion": r"^[\s#>*\-\d\.]{0,10}(conclusions?|结论)\b",
    "references": r"^[\s#>*\-\d\.]{0,10}(references|bibliography|参考文献)\b",
}

# ---------- 各体裁/学科的必需章节 ----------
GENRE_SECTIONS = {
    "ei-conf": ["abstract", "introduction", "related-work", "method", "results", "conclusion", "references"],
    "ai-conf": ["abstract", "introduction", "related-work", "method", "results", "conclusion", "references"],
    "sci-journal": ["abstract", "introduction", "method", "results", "discussion", "conclusion", "references"],
    "ssci": ["abstract", "introduction", "method", "results", "discussion", "references"],
    "dissertation": ["introduction", "method", "results", "discussion", "conclusion", "references"],
    "quant": ["abstract", "introduction", "method", "results", "discussion", "references"],
    "predictive": ["abstract", "introduction", "method", "results", "discussion", "references"],
    "qualitative": ["abstract", "introduction", "method", "results", "discussion", "references"],
    "basic-science": ["abstract", "introduction", "method", "results", "discussion", "references"],
    "clinical": ["abstract", "introduction", "method", "results", "discussion", "references"],
}

# ---------- 词面检查组 ----------
GAP_MARKERS = [r"\bhowever\b", r"\bremains\b", r"\bunresolved\b", r"\blimited\b",
               r"\bshortcomings\b", r"\bdrawbacks\b", r"\bstill\s+(?:suffer|lack|struggle)\b",
               r"然而", r"尚(?:未|无)", r"不足"]
CONTRIB_MARKERS = [r"\bcontributions?\b", r"\bwe\s+propose\b", r"\bwe\s+introduce\b",
                   r"\bwe\s+present\b", r"本文(?:提出|贡献)", r"主要贡献"]
LIMITATION_MARKERS = [r"\blimitation\b", r"\bfuture\s+work\b", r"\bout\s+of\s+scope\b",
                      r"局限", r"不足之?处"]
ABLATION_MARKERS = [r"\bablation\b", r"\bablate\b", r"消融"]
DBL_RISK_MARKERS = [r"\bour\s+(?:prior|previous)\b", r"\bour\s+lab\b", r"\buniversity\s+of\b",
                    r"\bfund(?:ed|ing)\b", r"\bthanks\b"]
EMPTY_CLAIMS = [r"\bnovel\s+framework\b", r"\bsignificantly\s+outperforms\b", r"首次提出", r"显著优于"]

IDENT_MARKERS = [r"identification strategy", r"we exploit", r"source of variation", r"识别策略"]
CAUSAL_LANG = [r"\bcauses?\b", r"\bleads? to\b", r"\bresults? in\b", r"导致", r"带来"]
REPORT_STD = [r"CONSORT", r"STROBE", r"PRISMA", r"STARD", r"CARE\b", r"TRIPOD", r"报告规范"]


def load_text(path):
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def word_count(text):
    return len(re.findall(r"\b[\w-]+\b", text))


def cjk_count(text):
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def check_sections(text):
    low = text.lower()
    return {name: bool(re.search(pat, low, re.MULTILINE)) for name, pat in SECTION_PATTERNS.items()}


def has_any(text, markers):
    for pat in markers:
        if re.search(pat, text, re.I):
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--genre", default="ei-conf", choices=list(GENRE_SECTIONS.keys()))
    ap.add_argument("--lang", default="auto", choices=["auto", "en", "zh"])
    args = ap.parse_args()

    text = load_text(args.path)
    genre = args.genre
    wc, cjk = word_count(text), cjk_count(text)
    lang = args.lang if args.lang != "auto" else ("zh" if cjk > wc else "en")

    print(f"=== 结构自检: {args.path} ===")
    print(f"体裁/学科: {genre} | 语言: {lang} | 词数 {wc} | 汉字 {cjk}")

    secs = check_sections(text)
    required = GENRE_SECTIONS[genre]
    print("\n[必需章节]")
    miss = 0
    for name in required:
        ok = secs[name]
        if not ok:
            miss += 1
        print(f"  {'OK  ' if ok else 'MISS'} {name}")
    if miss:
        print(f"  缺失 {miss} 个必需章节（若无明确标题，请补章节标题便于检索）")

    print("\n[通用质量]")
    print(f"  {'OK  ' if has_any(text, GAP_MARKERS) else 'MISS'} gap 句 (WRI-INT-002)")
    print(f"  {'OK  ' if has_any(text, CONTRIB_MARKERS) else 'MISS'} 贡献声明 (WRI-INT-003)")
    print(f"  {'OK  ' if has_any(text, LIMITATION_MARKERS) else 'MISS'} 局限性 (WRI-CON-001)")

    if genre in ("ei-conf", "ai-conf", "predictive"):
        print(f"  {'OK  ' if has_any(text, ABLATION_MARKERS) else 'MISS'} 消融/对照实验 (WRI-EXP-002)")
        for pat in DBL_RISK_MARKERS:
            if re.search(pat, text, re.I):
                print(f"  WARN 疑似双盲风险 /{pat}/ (WRI-DBL-001)")
        for pat in EMPTY_CLAIMS:
            if re.search(pat, text, re.I):
                print(f"  WARN 疑似空泛宣称 /{pat}/ (WRI-INT-004)")

    if genre in ("quant", "dissertation"):
        print("\n[定量实证专项]")
        print(f"  {'OK  ' if has_any(text, IDENT_MARKERS) else 'MISS'} 识别策略 (QNT-IDF-001)")
        if not has_any(text, IDENT_MARKERS) and has_any(text, CAUSAL_LANG):
            print("  WARN 出现因果措辞但无识别策略 (QNT-WRT-001)")

    if genre == "qualitative":
        print("\n[质性研究专项]")
        for label, pats, rid in [
            ("抽样策略", [r"purposive", r"purposeful", r"目的性?抽样"], "QLT-DSN-003"),
            ("编码方法", [r"first[- ]cycle", r"thematic analys", r"open coding", r"编码"], "QLT-COD-001"),
            ("饱和判据", [r"saturation", r"饱和"], "QLT-SAT-001"),
            ("反身性", [r"reflexiv", r"positionality", r"反身性"], "QLT-TRU-003"),
            ("引文编号", [r"\bP\d{1,2}\b", r"参与者\s*\d"], "QLT-DSP-003"),
        ]:
            print(f"  {'OK  ' if has_any(text, pats) else 'MISS'} {label} ({rid})")

    if genre == "basic-science":
        print("\n[基础科学专项]")
        print(f"  {'OK  ' if re.search(r'[±]', text) else 'MISS'} 误差/不确定度 (SCI-RES-002)")
        if has_any(text, [r"ANOVA", r"t-?test", r"Tukey", r"SPSS", r"Origin"]):
            print("  OK   统计方法 (SCI-MET-004)")
        else:
            print("  MISS 统计方法 (SCI-MET-004)")

    if genre == "clinical":
        print("\n[临床报告规范专项]")
        print(f"  {'OK  ' if has_any(text, REPORT_STD) else 'MISS'} 报告规范声明 (CLN-RPG-001)")
        for label, pats, rid in [
            ("流程图", [r"flow (diagram|chart)", r"流程图"], "CLN-CON-002"),
            ("注册号", [r"NCT\d{6,}", r"ChiCTR", r"ISRCTN", r"注册号"], "CLN-CON-009"),
            ("95% 置信区间", [r"95\s*%\s*(CI|confidence)", r"置信区间"], "CLN-STA-001"),
            ("伦理审批", [r"ethics (committee|approval)", r"IRB", r"伦理"], "CLN-ETH-001"),
        ]:
            print(f"  {'OK  ' if has_any(text, pats) else 'MISS'} {label} ({rid})")

    print("\n[提示] 脚本仅覆盖可词面化的条目。完整规则判定请用:")
    print(f"        python scripts/score.py {args.path} --track {genre}")
    print("[完成]")


if __name__ == "__main__":
    main()
