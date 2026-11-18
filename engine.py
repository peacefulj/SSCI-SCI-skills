# -*- coding: utf-8 -*-
"""规则引擎：加载 skill 规则库 + 复用原生脚本做词面检测与结构检查。

关键设计：词面检测不重写、不复刻，直接 import skill 自带的 score.py /
check_structure.py，调用其原生函数，保证与官方脚本 100% 一致。
"""
import importlib.util
import os
import re
import tempfile
from pathlib import Path

import yaml

import paths

# skill 规则库是只读资源：打包后位于 _MEIPASS，源码运行即项目根
SKILL_ROOT = paths.resource_root() / "skill" / "academic-writing-v1.1"
RULES_PATH = SKILL_ROOT / "rules" / "rules.yaml"
DETECTORS_PATH = SKILL_ROOT / "rules" / "detectors.yaml"
VENUES_PATH = SKILL_ROOT / "assets" / "target-venues.yaml"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 复用 skill 原生脚本（不重写判定逻辑）
_score = _load_module("acw_score", SKILL_ROOT / "scripts" / "score.py")
_check = _load_module("acw_check", SKILL_ROOT / "scripts" / "check_structure.py")

# 规则库（惰性加载，避免 import 时报错）
_RULES = None
_DETECTORS = None
_RULES_BY_ID = None


def _ensure_loaded():
    global _RULES, _DETECTORS, _RULES_BY_ID
    if _RULES is None:
        _RULES = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))["rules"]
        _DETECTORS = yaml.safe_load(DETECTORS_PATH.read_text(encoding="utf-8"))["detectors"]
        _RULES_BY_ID = {r["id"]: r for r in _RULES}


TRACKS = ["quant", "predictive", "qualitative", "basic-science", "clinical",
          "reporting", "ei-conf", "ai-conf", "sci-journal", "ssci", "dissertation"]

TRACK_LABELS = {
    "quant": "定量实证（经济/管理/金融/社会学）",
    "predictive": "预测建模 / 数据科学",
    "qualitative": "质性研究（案例/现象学/扎根）",
    "basic-science": "基础科学实验（化/生/材/物）",
    "clinical": "临床与医学",
    "reporting": "报告规范（EQUATOR）",
    "ei-conf": "工程会议（EI）",
    "ai-conf": "AI 会议",
    "sci-journal": "工程/科学期刊（SCI）",
    "ssci": "社科期刊（SSCI）",
    "dissertation": "博士大论文",
}

GENRE_LABELS = {
    "ei-conf": "EI 会议", "ai-conf": "AI 会议", "sci-journal": "科学期刊（SCI）",
    "ssci": "社科期刊（SSCI）", "dissertation": "博士大论文", "quant": "定量实证",
    "predictive": "预测建模", "qualitative": "质性研究", "basic-science": "基础科学",
    "clinical": "临床医学",
}

SECTION_LABELS = {
    "abstract": "摘要", "title": "标题", "introduction": "引言", "related-work": "相关工作",
    "method": "方法", "experiments": "实验", "results": "结果", "discussion": "讨论",
    "conclusion": "结论", "references": "参考文献", "general": "全文通用",
    "submission": "投稿相关", "rebuttal": "返修", "review": "审稿", "ethics": "伦理",
    "chapter-structure": "章节结构", "contribution": "贡献", "defense": "答辩",
}

# 规则 section -> 稿件章节 的映射（用于 LLM 判读时取相关文本）
SECTION_TEXT_MAP = {
    "abstract": "abstract", "title": "title", "introduction": "introduction",
    "related-work": "related-work", "method": "method", "experiments": "method",
    "results": "results", "discussion": "discussion", "conclusion": "conclusion",
    "references": "references", "contribution": "introduction",
    "general": None, "submission": None, "rebuttal": None, "review": None,
    "ethics": None, "chapter-structure": None, "defense": None,
}

# 中文论文常用复合式章节标题（「数据与研究设计」「实证结果」「结论与讨论」），
# skill 的 SECTION_PATTERNS 要求关键词紧跟标题行首，这类标题会被漏判成「缺章节」。
# 这里只在 skill 判缺时做一次展示层补充识别：不改 skill 文件，也不改变任何规则的命中。
_EXTRA_SECTION_PATTERNS = {
    "method": r"(研究设计|研究方案|数据与研究|数据与方法|数据来源|样本选择|"
              r"变量(定义|选取|说明|测度)|模型设定|计量模型|实证策略|识别策略|研究假设)",
    "results": r"(实证结果|回归结果|结果与分析|估计结果|基准回归|描述性统计|"
               r"稳健性检验|异质性(分析|检验)|机制检验)",
    "discussion": r"(结论与讨论|讨论与结论|进一步讨论|政策含义|研究局限)",
}


def _heading_like_lines(text: str) -> list[str]:
    """取形似标题的行：Markdown 标题，或短且不以句末标点结尾的独立行。"""
    out = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        s = raw.strip("#").strip()
        if not s or len(s) > 30 or len(s) < 2:
            continue
        if raw.startswith("#") or not re.search(r"[。，；,;：:]$", s):
            out.append(s)
    return out


def _extend_sections(text: str, secs: dict) -> tuple[dict, list[str]]:
    heads = _heading_like_lines(text)
    merged = dict(secs)
    extended: list[str] = []
    for name, pat in _EXTRA_SECTION_PATTERNS.items():
        if merged.get(name):
            continue
        if any(re.search(pat, h) for h in heads):
            merged[name] = True
            extended.append(name)
    return merged, extended


def get_rules():
    _ensure_loaded()
    return _RULES


def get_detectors():
    _ensure_loaded()
    return _DETECTORS


def get_rules_by_id():
    _ensure_loaded()
    return _RULES_BY_ID


def get_venues():
    """目标期刊/会议清单（6 范式），供选题环节下拉。"""
    if VENUES_PATH.exists():
        return yaml.safe_load(VENUES_PATH.read_text(encoding="utf-8")) or {}
    return {}


# track -> 期刊清单范式 key 的映射（target-venues.yaml 用范式名作 key）
TRACK_VENUE_KEY = {
    "quant": "quant",
    "predictive": "eng",
    "qualitative": "qual",
    "basic-science": "basicexp",
    "clinical": "clinical",
    "ei-conf": "eng",
    "ai-conf": "eng",
    "sci-journal": "basicexp",
    "ssci": "quant",
    "dissertation": "quant",
    "reporting": "clinical",
}


def venues_for_track(track):
    """返回某 track 对应的目标期刊清单（list）。"""
    v = get_venues()
    key = TRACK_VENUE_KEY.get(track, "quant")
    return v.get(key, [])


def required_sections(genre):
    """某体裁的必需章节清单（直接取 skill 原生 GENRE_SECTIONS，只读不改）。"""
    return list(_check.GENRE_SECTIONS.get(genre, _check.GENRE_SECTIONS["quant"]))


def applicable_rules(track):
    """返回某主线适用的规则（与 score.py 的 applicable 逻辑一致）。"""
    _ensure_loaded()
    return [r for r in _RULES
            if r.get("track") == track or (track in (r.get("genre") or []))]


def auto_rule_ids(track):
    """返回该主线下实际会跑词面检测器的规则 id 集合（与 score_file 的分派一致）。

    对齐 score.py v1.3.2：检测器按 rules.yaml 的 genre 归属分派，PRD-* 等
    track=predictive 但 genre 含 ei-conf/sci-journal 的检测器也要算进来，
    否则工程/AI 主线的"需人工"数量会被高估（实际能自动跑的规则被算成人工）。
    """
    _ensure_loaded()
    app_ids = {r["id"] for r in applicable_rules(track)}
    dets = [d for d in _DETECTORS
            if (d.get("track") == track or d.get("track") is None or d["id"] in app_ids)]
    return {d["id"] for d in dets}


def _silent_ids(track):
    """返回"跑了检测器但不会产出 pass"的规则 id（真正的跨主线检测器）。

    与 score.py 的 cross 判定严格一致：检测器自身 track 非空、且不等于当前
    track、且该规则适用本主线。track=None 的通用检测器不算跨主线，它的 pass
    是可信的（不算静默跳过）。
    这类规则在 score_file 里只收 defect、不产出 pass；defect 未命中时它既不在
    defects、也不在 passed/na 里，等于静默跳过，必须仍然交给大模型判读。
    """
    _ensure_loaded()
    app_ids = {r["id"] for r in applicable_rules(track)}
    return {d["id"] for d in _DETECTORS
            if d.get("track") is not None
            and d.get("track") != track
            and d["id"] in app_ids}


def manual_rules(track):
    """返回该主线下需 LLM 逐条判读的规则。

    口径：适用本主线、且没有"能给出 pass/defect 结论"的专属检测器。
    跨主线检测器（只收 defect）不算，因为它没命中时不能说明规则通过。
    """
    _ensure_loaded()
    app = applicable_rules(track)
    auto_ids = auto_rule_ids(track) - _silent_ids(track)
    return [r for r in app if r["id"] not in auto_ids]


def track_stats():
    """每个主线的规则/检测器/需人工 统计，供前端能力矩阵展示。

    detectors = 实际参与词面检测的检测器数（与 score_file 一致）；
    manual    = 仍需大模型判读的条数（口径见 manual_rules）。
    两者相加未必等于 rules：跨主线检测器的规则既往检测、也需判读。
    """
    _ensure_loaded()
    stats = {}
    for t in TRACKS:
        app = applicable_rules(t)
        stats[t] = {
            "rules": len(app),
            "detectors": len(auto_rule_ids(t)),
            "manual": len(manual_rules(t)),
        }
    return stats


def split_sections(text):
    """把稿件按章节标题切分成 dict，供 LLM 判读取相关文本。

    修复（fix/review-pipeline）：
    - skill 的 SECTION_PATTERNS 是小写正则（check_structure 先 lower() 再匹配），
      原实现缺 re.IGNORECASE，导致 "## Methods" 等标题全部识别失败（40 篇实测 0 章节）。
    - 同一章节名多次出现时（如方法章内含多个小节、讨论后再出现 "results" 字样），
      合并所有片段而非只留最后一个，避免证据被覆盖。
    """
    positions = []
    for name, pat in _check.SECTION_PATTERNS.items():
        try:
            for m in re.finditer(pat, text, re.MULTILINE | re.IGNORECASE):
                positions.append((m.start(), name))
        except re.error:
            continue
    positions.sort()
    sections = {}
    for i, (pos, name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        sections[name] = sections.get(name, "") + text[pos:end]
    if positions:
        sections["title"] = text[:positions[0][0]]
    return sections


def body_only(text):
    """去参考文献（复用 skill 原生 body_only，保证与 score.py 口径一致）。"""
    return _score.body_only(text)


def _section_text_for_rule(text, rule):
    """按规则的 section 字段取相关文本（不截断，由调用方负责分块）。

    修复：原实现对通用规则截 12000 字、兜底截 8000 字，长稿关键证据常被截掉。
    现改为：通用规则用去参考文献的全文；章节缺失时也用全文，而不是摘要+引言。
    """
    body = body_only(text)
    target = SECTION_TEXT_MAP.get(rule.get("section"), None)
    if target is None:
        return body
    sections = split_sections(body)
    if sections.get(target):
        return sections[target]
    return body


def lexical_review(text, track, genre=None):
    """词面检测 + 结构检查，完全复用 skill 原生脚本。"""
    _ensure_loaded()
    genre = genre or track

    # 1) 写临时文件，调用原生 score_file（100% 复用，不重写）
    fd, tmp = tempfile.mkstemp(suffix=".md", prefix="acw_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        report = _score.score_file(tmp, track, _RULES_BY_ID, _DETECTORS, verbose=False)
    finally:
        os.unlink(tmp)

    # 2) 结构检查，复用原生 check_structure 的常量与函数
    secs = _check.check_sections(text)
    secs, sec_extended = _extend_sections(text, secs)
    required = _check.GENRE_SECTIONS.get(genre, _check.GENRE_SECTIONS["quant"])
    missing = [s for s in required if not secs.get(s)]

    # 3) 通用质量（复用 check_structure 的 markers 与 has_any）
    body = _score.body_only(text)
    quality = {
        "gap": _check.has_any(body, _check.GAP_MARKERS),
        "contrib": _check.has_any(body, _check.CONTRIB_MARKERS),
        "limitation": _check.has_any(body, _check.LIMITATION_MARKERS),
    }
    if genre in ("ei-conf", "ai-conf", "predictive"):
        quality["ablation"] = _check.has_any(body, _check.ABLATION_MARKERS)

    # 4) 给每个词面缺陷关联完整规则详情（signal/fix/source/rule）
    defects = []
    for d in report["defects"]:
        detail = _RULES_BY_ID.get(d["id"], {})
        defects.append({
            "id": d["id"],
            "status": d["status"],
            "reason": d.get("reason"),
            "severity": d.get("severity", "should"),
            "rule": detail.get("rule", ""),
            "signal": detail.get("signal", ""),
            "fix": detail.get("fix", ""),
            "source": detail.get("source", ""),
            "example_good": detail.get("example_good", ""),
            "section": detail.get("section", ""),
        })

    return {
        "track": track,
        "genre": genre,
        "words": report["words"],
        "cjk_chars": report["cjk_chars"],
        "thin_text": report["thin_text"],
        "applicable_rules": report["applicable_rules"],
        "auto_checked": report["auto_checked"],
        "manual_only": len(manual_rules(track)),
        "defect_count": report["defect_count"],
        "must_count": report["must_count"],
        "should_count": report["should_count"],
        "nice_count": report["nice_count"],
        "defects": defects,
        "passed": report["passed"],
        "na": report["na"],
        "sections": secs,
        "sections_extended": sec_extended,
        "required": required,
        "missing": missing,
        "quality": quality,
    }


def get_addon_info():
    """读取扩展包挂载信息（.radar-addon/manifest.json）。未挂载时返回 None。

    选题雷达是可选扩展：原 skill 版本始终是 1.2.0，扩展是否存在单独上报，
    便于前端明确区分“原能力”与“可选增强”。
    """
    man = SKILL_ROOT / ".radar-addon" / "manifest.json"
    if man.exists():
        try:
            import json

            d = json.loads(man.read_text(encoding="utf-8"))
            return {
                "name": d.get("addon", ""),
                "version": d.get("addon_version", ""),
                "installed_at": d.get("installed_at", ""),
            }
        except Exception:
            return None
    return None


def get_skill_version():
    """读内嵌 skill 的 SKILL.md 版本号（frontmatter 里的 `version: "x.y.z"`）。

    首页页脚展示的是"规则库版本"而不是应用版本，两者独立演进
    （应用 1.3.1 / 规则库 1.3.2）。取不到就返回空串，前端回退到写死的值。
    """
    try:
        for line in (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()[:20]:
            line = line.strip()
            if line.startswith("version:"):
                return line.split(":", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def skill_label():
    """规则库的版本描述，供成稿声明等对外文本使用。

    以前 oneshot 的草稿声明里写死 "Academic Writing Skill v1.2.0, 393 rules"，
    规则库升到 1.3.2 后，用户手里的每份成稿都带着错误版本号。这里统一从
    SKILL.md + 实际规则数生成，不再硬编码。
    """
    _ensure_loaded()
    ver = get_skill_version()
    name = f"Academic Writing Skill v{ver}" if ver else "Academic Writing Skill"
    return f"{name}\uff0c{len(_RULES)} \u6761\u89c4\u5219"


def skill_label_en():
    """skill_label 的英文版（成稿的英文草稿声明用）。"""
    _ensure_loaded()
    ver = get_skill_version()
    name = f"Academic Writing Skill v{ver}" if ver else "Academic Writing Skill"
    return f"{name}, {len(_RULES)} rules"


def meta():
    """前端所需元数据。"""
    _ensure_loaded()
    return {
        "tracks": {t: TRACK_LABELS[t] for t in TRACKS},
        "genres": GENRE_LABELS,
        "sections": SECTION_LABELS,
        "track_stats": track_stats(),
        "rule_count": len(_RULES),
        "detector_count": len(_DETECTORS),
        "skill_version": get_skill_version(),
        "venues": get_venues(),
        "version": "1.3.1",
        "addon": get_addon_info(),
    }
