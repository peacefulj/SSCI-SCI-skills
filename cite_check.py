"""引用格式对账：把 skill 的四套引用规范变成可执行检查。

**为什么需要这个模块**（已实测确认的三处断链）：

1. skill 的 `rules/rules.yaml` 里 CIT 族有 16 条规则，但 `genre` 只挂
   ei-conf / ai-conf / sci-journal / ssci / dissertation，**不含 quant**——
   而一键成稿最常用的体裁就是 quant，于是整族规则一条都不适用。
2. 16 条里只有 4 条带检测器，且全是 GB/T 与 IEEE 专用；APA 四条全无，
   `CIT-CHK-001`（正文与文献表双向对应）也无。
3. `refs.py` 自己实现了四套格式化，从未读过 `assets/citation-*.md`。

`skill/**` 是只读的，不能往里加检测器，所以检测建在这里：只读 skill 的
`assets/citation-*.md` 当依据（`basis` 字段会写出来源小节），不改动它。

所有检查都是**词面可见的硬错误**，不做语义判断——"这条引用是否支撑该论点"
必须人来看，本模块不假装能判。
"""

from __future__ import annotations

import re
from pathlib import Path

import paths

# skill 资产只读：打包后在 _MEIPASS，源码运行即项目根
SKILL_ROOT = paths.resource_root() / "skill" / "academic-writing-v1.1"
ASSETS = SKILL_ROOT / "assets"

# 依据文件（只读，用于在报告里标注出处；缺失也不影响检查）
BASIS = {
    "apa": "assets/citation-apa.md",
    "ieee": "assets/citation-ieee.md",
    "gb7714": "assets/citation-gb7714.md",
    "chicago": "assets/citation-quickref.md",
}

HEAD_WORDS = {"references", "reference list", "bibliography", "literature cited",
              "参考文献", "參考文獻"}

# 正文引用形态（著者-年制）
PAREN_CITE = re.compile(r"\(([A-Z][A-Za-z\u00C0-\u024F'’\-]{1,24})"
                        r"(?:\s*(?:&|and|et al\.)\s*[A-Za-z\u00C0-\u024F'’\-]*)?"
                        r",?\s*(\d{4})[a-z]?\)")
NARR_CITE = re.compile(r"\b([A-Z][A-Za-z\u00C0-\u024F'’\-]{1,24})"
                       r"\s+(?:et al\.|and\s+[A-Z][A-Za-z\u00C0-\u024F'’\-]+)?"
                       r"\s*\((\d{4})[a-z]?\)")

NUM_CITE = re.compile(r"\[(\d{1,3})(?:\s*[-,–]\s*(\d{1,3}))?\]")

# OpenAlex 的 source 字段不是刊名的典型情形（电子书平台 / 聚合库）
BAD_VENUE = re.compile(r"(eBooks?|CrossRef|PubMed|OpenAlex|Semantic Scholar|"
                       r"Social Science Research Network|SSRN Electronic Journal)", re.I)

DOI_LINK = re.compile(r"https?://(?:dx\.)?doi\.org/\S+", re.I)
DOI_BARE = re.compile(r"\b10\.\d{4,9}/\S+")

# 作者姓只有一个字母：OpenAlex 显示名解析失败的典型产物（"A, H. D." / "Y, J. S."）。
# 前面可能是行首、句点、分号，也可能是逗号（"Mueller, A. I., Y, J. S., & Topa"）。
ONE_LETTER_SURNAME = re.compile(r"(?:^|[.,;]\s+)([A-Z]),\s+[A-Z]\.")

# 稿件末尾会附一段统计（题目/主线/占位计数…），它们不是文献条目
NOT_REF_LINE = re.compile(r"^(题目|主线|数据状态|章节|待填|未解决|文献装配|自检结果|"
                          r"title|track|data status)\s*[:：]", re.I)


def _add(out: list, level: str, code: str, msg: str, fix: str,
         where: str = "", basis: str = "") -> None:
    out.append({"id": code, "level": level, "where": where,
                "msg": msg, "fix": fix, "basis": basis})


def split_refs(text: str) -> tuple[str, list[str]]:
    """切出正文与参考文献条目。取**最后一个**纯标题行，避免正文里 "see References" 误判。"""
    lines = (text or "").splitlines()
    idx = None
    for i, ln in enumerate(lines):
        s = re.sub(r"^[#*\s]+", "", ln).strip().strip("*").strip()
        if s.lower().rstrip(":：") in HEAD_WORDS:
            idx = i
    if idx is None:
        return text, []
    body = "\n".join(lines[:idx])
    entries = []
    for ln in lines[idx + 1:]:
        s = ln.strip().lstrip("-*•").strip()
        if not s or s.startswith("#") or NOT_REF_LINE.match(s):
            continue
        # 文献条目的最低特征：有年份或 DOI。稿件末尾的统计行两者都没有。
        if not re.search(r"\b(19|20)\d{2}[a-z]?\b", s) and not DOI_BARE.search(s):
            continue
        entries.append(s)
    return body, entries


def _first_surname(entry: str) -> str:
    m = re.match(r"([A-Z][A-Za-z\u00C0-\u024F'’\-]{1,24}),", entry)
    return m.group(1) if m else ""


def _entry_year(entry: str) -> str:
    m = re.search(r"\((\d{4})[a-z]?\)", entry) or re.search(r"\b(19|20)\d{2}\b", entry)
    if not m:
        return ""
    return m.group(0).strip("()")


def _chk_volume(entries: list[str], style: str, out: list, basis: str) -> None:
    for i, e in enumerate(entries, 1):
        if style in ("apa", "chicago"):
            if re.search(r"\bVol\.\s*\d", e) or re.search(r"\bNo\.\s*\d", e):
                _add(out, "must", "CIT-VOL-001",
                     "条目含 `Vol.` / `No.` 前缀", "APA 7 写 `42(4)`，不加 Vol./No.",
                     f"条目 {i}", basis)
            if re.search(r",\s*\d+\s+\(\d+\)", e):
                _add(out, "must", "CIT-VOL-002",
                     "卷号与期号之间有空格", "APA 7 卷期相连：`42(4)`，中间不留空格",
                     f"条目 {i}", basis)
        elif style == "ieee":
            if re.search(r",\s*\d+\s*\(\d+\)", e) and "vol." not in e.lower():
                _add(out, "must", "CIT-IEEE-VOL",
                     "IEEE 条目用 `42(4)` 表示卷期", "IEEE 写 `vol. 42, no. 4`",
                     f"条目 {i}", basis)


def _chk_doi(entries: list[str], style: str, out: list, basis: str) -> None:
    for i, e in enumerate(entries, 1):
        link = DOI_LINK.search(e)
        if link and e.count("https://doi.org/") > 1:
            _add(out, "must", "CIT-DOI-001", "DOI 链接重复拼叠",
                 "DOI 只保留一个 `https://doi.org/10.xxxx`", f"条目 {i}", basis)
            continue
        if not DOI_BARE.search(e):
            continue
        # 注意方向：APA 要求「有链接」，IEEE/GB 要求「不带链接前缀」。
        # 写成「没有链接就报」会把 IEEE 的正确写法判错。
        if style in ("apa", "chicago"):
            if not link:
                _add(out, "must", "CIT-DOI-002", "DOI 未写成可点击链接",
                     "APA 7 要求 `https://doi.org/10.xxxx`", f"条目 {i}", basis)
        elif style == "ieee":
            if link:
                _add(out, "should", "CIT-IEEE-DOI", "IEEE 的 DOI 写作 `doi: 10.xxxx`，不用 https 链接",
                     "去掉 `https://doi.org/` 前缀，写成 `doi: 10.xxxx`", f"条目 {i}", basis)
        elif style == "gb7714":
            if link:
                _add(out, "should", "CIT-GBT-DOI", "GB/T 7714 的 DOI 写作 `DOI: 10.xxxx`",
                     "统一为 `DOI: 10.xxxx`", f"条目 {i}", basis)


def _chk_authors(entries: list[str], out: list, basis: str) -> None:
    for i, e in enumerate(entries, 1):
        if ONE_LETTER_SURNAME.search(e):
            _add(out, "must", "CIT-AUT-001",
                 "作者姓只有一个字母，通常是检索源的显示名解析失败",
                 "打开 DOI 核对真实姓名后手工改正；这类条目不要直接投稿",
                 f"条目 {i}", basis)


def _chk_venue(entries: list[str], out: list, basis: str) -> None:
    for i, e in enumerate(entries, 1):
        m = BAD_VENUE.search(e)
        if not m:
            continue
        _add(out, "must", "CIT-VEN-001",
             f"来源写成了检索平台的字段名（`{m.group(0)}`），不是刊名或出版社",
             "按原文核对：期刊论文写刊名，书章写书名与出版社",
             f"条目 {i}", basis)


def _chk_mix(body: str, entries: list[str], style: str, out: list, basis: str) -> None:
    """CIT-STY-001：体系一致性。skill 里这条规则存在但无检测器。"""
    nums = [int(n) for n, _ in NUM_CITE.findall(body)]
    nums = [n for n in nums if n <= len(entries) + 5]     # 排除表格编号与公式编号误判
    if style in ("apa", "chicago") and nums:
        _add(out, "must", "CIT-STY-001",
             "正文用编号制 `[n]`，文末却是著者-年制（字母序）",
             "统一为一套：APA 用 `(Author, Year)`，IEEE 用 `[n]`", "全文", basis)
    if style in ("ieee", "gb7714") and not nums and entries:
        _add(out, "must", "CIT-STY-002",
             "文末为数字制，但正文找不到 `[n]` 引用标记",
             "按首次出现顺序编号，并逐处替换正文标记", "全文", basis)


def _chk_pairs(body: str, entries: list[str], style: str, out: list, basis: str) -> None:
    """CIT-CHK-001：正文引用与文献表双向对应。skill 里这条规则无检测器。"""
    if style in ("ieee", "gb7714"):
        used = {int(n) for n, _ in NUM_CITE.findall(body) if n}
        for n in sorted(used):
            if n > len(entries):
                _add(out, "must", "CIT-CHK-001",
                     f"正文引用 [{n}]，但文献表只有 {len(entries)} 条",
                     "补上该条文献，或修正编号", "全文", basis)
        return

    in_refs = set()
    for e in entries:
        sur, yr = _first_surname(e), _entry_year(e)
        if sur:
            in_refs.add((sur.lower(), yr))

    cited = set()
    for rx in (PAREN_CITE, NARR_CITE):
        for m in rx.finditer(body):
            cited.add((m.group(1).lower(), m.group(2)))

    for sur, yr in sorted(cited - in_refs):
        if sur in ("table", "figure", "section", "appendix", "note", "year"):
            continue
        _add(out, "must", "CIT-CHK-001",
             f"正文引用 `{sur.title()} ({yr})` 在参考文献表里找不到",
             "补上该条文献，或把它改成 `[TBD: source]` 待补", "全文", basis)

    # 门槛按文献表条数而不是正文引用数：三条文献只引了一条，本身就是要报的
    if len(entries) >= 3:
        uncited = in_refs - cited
        if uncited:
            sample = "、".join(f"{s.title()} ({y})" for s, y in sorted(uncited)[:3])
            _add(out, "should", "CIT-CHK-003",
                 f"{len(uncited)} 条文献未在正文出现（{sample}…）",
                 "删掉未被引用的条目——挂着不引会被审稿人当成凑数", "全文", basis)


def _chk_title_case(entries: list[str], style: str, out: list, basis: str) -> None:
    """APA 要求文章题名 sentence case。只提示，不自动改（会自动毁掉缩写与专有名词）。"""
    if style != "apa":
        return
    bad = []
    for e in entries:
        m = re.search(r"\(\d{4}[a-z]?\)\.\s+(.{15,140}?)\.\s", e)
        if not m:
            continue
        title = m.group(1)
        words = re.findall(r"\b[A-Z][a-z]{2,}\b", title)
        if len(words) >= 3:
            bad.append(title[:60])
    if bad:
        _add(out, "should", "CIT-APA-002",
             f"{len(bad)} 条题名仍是 Title Case（例：{bad[0]}…）",
             "APA 7 文章题名用 sentence case；专有名词与缩写保持原样，需人工确认后再改",
             "", basis)


def check(manuscript: str, style: str = "apa", lang: str = "en") -> dict:
    """对一份已装配好文献的稿件做格式对账。纯本地，不联网。"""
    style = (style or "apa").lower()
    basis = BASIS.get(style, BASIS["apa"])
    body, entries = split_refs(manuscript)
    out: list[dict] = []

    if not entries:
        return {"style": style, "entries": 0, "findings": [], "basis": basis,
                "counts": {"must": 0, "should": 0, "nice": 0},
                "note": "未找到参考文献表（可能尚未装配文献）"}

    _chk_volume(entries, style, out, basis)
    _chk_doi(entries, style, out, basis)
    _chk_authors(entries, out, basis)
    _chk_venue(entries, out, basis)
    _chk_mix(body, entries, style, out, basis)
    _chk_pairs(body, entries, style, out, basis)
    _chk_title_case(entries, style, out, basis)

    counts = {"must": 0, "should": 0, "nice": 0}
    for f in out:
        counts[f["level"]] = counts.get(f["level"], 0) + 1
    return {"style": style, "entries": len(entries), "findings": out,
            "counts": counts, "basis": basis}


def report_md(res: dict) -> str:
    """生成 07_check.md 里的「引用格式」小节。"""
    s = res.get("counts") or {}
    if res.get("note"):
        return f"_引用格式未检查：{res['note']}_\n"
    head = (f"按 `{res['basis']}` 对账 {res['entries']} 条参考文献："
            f"硬伤 {s.get('must', 0)} · 建议 {s.get('should', 0)} · 提示 {s.get('nice', 0)}。\n")
    if not res.get("findings"):
        return head + "\n词面层面未发现格式硬伤（格式合规不代表引用得对，仍须逐条核对 DOI）。\n"
    lines = [head]
    for lv, label in (("must", "硬伤"), ("should", "建议"), ("nice", "提示")):
        group = [f for f in res["findings"] if f["level"] == lv]
        if not group:
            continue
        lines.append(f"\n**{label}（{len(group)}）**\n")
        for f in group[:8]:
            where = f"（{f['where']}）" if f.get("where") else ""
            lines.append(f"- `{f['id']}`{where} {f['msg']} → {f['fix']}")
    lines.append("\n_这些检查只覆盖能词面判定的格式项（卷期、DOI、作者名、来源类型、双向对应）。"
                 "「这条引用是否真的支撑该论点」机器判不了，必须打开 DOI 逐条看。_")
    return "\n".join(lines)


if __name__ == "__main__":       # 手工验收：python cite_check.py <稿件.md> [apa]
    import sys
    p = Path(sys.argv[1])
    style = sys.argv[2] if len(sys.argv) > 2 else "apa"
    r = check(p.read_text(encoding="utf-8"), style)
    print(report_md(r))
