# -*- coding: utf-8 -*-
"""一键成稿（学术小白）：从选题到英文初稿的七步流水线编排。

铁律（与项目既有约定一致）：
1. 只读引用 skill/ 下的规则库与参考文档，**不修改其中任何文件**。
2. 不编造数据与文献：无数据处写 `[TBD: ...]` 占位；引用处先写 `[CITE: ...]`，再由第 6 步
   「文献装配」用 OpenAlex 真实检索结果（带 DOI）替换；检索不到就保留占位，绝不虚构。
3. 英文优先：规则库基于国际期刊规范（SCI/SSCI/EI/AI 会议），默认产出英文稿；
   中文为受限通道，界面与报告里都写明"国内刊惯例不在规则库内"。
4. 每一步产物落盘到 `_oneshot/<job>/NN_*.md`，可单步重跑、可断点续跑。

本模块只做编排与提示词拼装，判定逻辑一律复用 engine / topic_trend / export。
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path

import cite_check
import dataset
import datasource
import engine
import ingest
import llm
import refs
import topic_trend

import paths

# 可写数据目录：源码运行 = 项目根（老用户 _oneshot/ 原地续用），
# 打包运行 = exe 同级 data/（或安装器指定的 %LOCALAPPDATA%\PaperMate）
BASE_DIR = paths.data_root()
JOB_DIR = BASE_DIR / "_oneshot"

# 单次成稿的字数上限/下限（中文按字，英文按词，统一叫 words）
WORD_MIN, WORD_MAX = 3000, 15000

SUPPORTED_TRACKS = [
    "quant", "predictive", "qualitative", "basic-science", "clinical",
    "ei-conf", "ai-conf", "sci-journal", "ssci", "dissertation",
]

TRACK_SHORT = {
    "quant": "empirical social science (economics / management / finance)",
    "predictive": "predictive modeling / data science",
    "qualitative": "qualitative research (case study / phenomenology)",
    "basic-science": "experimental natural science",
    "clinical": "clinical medicine",
    "ei-conf": "engineering conference paper (EI)",
    "ai-conf": "AI conference paper (NeurIPS/ICML/CVPR/ACL style)",
    "sci-journal": "SCI journal article",
    "ssci": "SSCI journal article",
    "dissertation": "PhD dissertation chapter",
}

CITATION_LABEL = {
    "ieee": "IEEE (numeric, [1])",
    "apa": "APA 7th (author-date)",
    "chicago": "Chicago author-date",
    "gb7714": "GB/T 7714-2015 (顺序编码制，中文刊)",
}

LANG_LABEL = {"en": "English", "zh": "Chinese"}

# 模型看到的不是裸枚举值而是一句可读状态：find/demo 单独丢过去没有语义
DATA_EN = {
    "yes": "author has real data; report actual analyses, leave only unknown cells blank",
    "partial": "author has partial data; write what exists, mark the rest as [TBD: ...]",
    "no": "no data; analysis frame, table skeletons and model equations only, every estimate [TBD: ...]",
    "find": "no data; author asked for help locating public data sources — use the source list below, never invent one",
    "demo": "demonstration only; author wants a layout-preview draft. The main manuscript must keep every "
            "number as [TBD: ...]. A SEPARATE demo file may contain clearly-labeled simulated values "
            "for layout checking only — never present them as real, never merge into the main text",
}
DATA_CN = {"yes": "已有真实数据", "partial": "部分数据", "no": "无数据",
           "find": "无数据（已请求荐源 + 代下载公开源）", "demo": "演示模式（模拟值仅排版预览）"}

# ---------------------------------------------------------------- 步骤定义

STEPS = [
    ("topic", "选题与候选"),
    ("chosen", "定题"),
    ("design", "研究设计"),
    ("outline", "大纲与字数分配"),
    ("draft", "分章成稿"),
    ("refs", "文献装配"),
    ("check", "自检与体检"),
]

STEP_ARTIFACT = {
    "topic": "01_topic.md",
    "chosen": "02_chosen.md",
    "design": "03_design.md",
    "outline": "04_outline.md",
    "draft": "05_draft.md",
    "refs": "06_refs.md",
    "check": "07_check.md",
}

# 各体裁的章节配比：key -> (英文标题, 权重)。abstract 单独固定字数，不参与配比。
SECTION_PLANS = {
    "quant": [
        ("intro", "Introduction", 0.16),
        ("related", "Literature Review and Hypotheses", 0.12),
        ("method", "Methods", 0.20),
        ("results", "Results", 0.26),
        ("discussion", "Discussion", 0.16),
        ("conclusion", "Conclusion", 0.10),
    ],
    "ssci": [
        ("intro", "Introduction", 0.16),
        ("related", "Literature Review and Hypotheses", 0.12),
        ("method", "Methods", 0.20),
        ("results", "Results", 0.26),
        ("discussion", "Discussion", 0.16),
        ("conclusion", "Conclusion", 0.10),
    ],
    "predictive": [
        ("intro", "Introduction", 0.16),
        ("related", "Related Work", 0.12),
        ("method", "Methods", 0.22),
        ("results", "Results", 0.28),
        ("discussion", "Discussion", 0.12),
        ("conclusion", "Conclusion", 0.10),
    ],
    "sci-journal": [
        ("intro", "Introduction", 0.16),
        ("method", "Methods", 0.22),
        ("results", "Results", 0.26),
        ("discussion", "Discussion", 0.24),
        ("conclusion", "Conclusion", 0.12),
    ],
    "ei-conf": [
        ("intro", "Introduction", 0.18),
        ("related", "Related Work", 0.15),
        ("method", "Methods", 0.22),
        ("results", "Results", 0.30),
        ("conclusion", "Conclusion", 0.15),
    ],
    "ai-conf": [
        ("intro", "Introduction", 0.18),
        ("related", "Related Work", 0.15),
        ("method", "Methods", 0.22),
        ("results", "Results", 0.30),
        ("conclusion", "Conclusion", 0.15),
    ],
    "qualitative": [
        ("intro", "Introduction", 0.15),
        ("related", "Literature Review", 0.12),
        ("method", "Methods", 0.20),
        ("results", "Results", 0.28),
        ("discussion", "Discussion", 0.15),
        ("conclusion", "Conclusion", 0.10),
    ],
    "basic-science": [
        ("intro", "Introduction", 0.16),
        ("method", "Methods", 0.22),
        ("results", "Results", 0.28),
        ("discussion", "Discussion", 0.24),
        ("conclusion", "Conclusion", 0.10),
    ],
    "clinical": [
        ("intro", "Introduction", 0.15),
        ("method", "Methods", 0.20),
        ("results", "Results", 0.30),
        ("discussion", "Discussion", 0.25),
        ("conclusion", "Conclusion", 0.10),
    ],
    "dissertation": [
        ("intro", "Introduction", 0.20),
        ("related", "Literature Review", 0.20),
        ("method", "Methods", 0.20),
        ("results", "Results", 0.25),
        ("discussion", "Discussion", 0.15),
    ],
}

# 章节参考文档
SECTION_DOC = {
    "intro": "references/section-introduction.md",
    "related": "references/section-introduction.md",
    "method": "references/section-methods.md",
    "results": "references/section-results.md",
    "discussion": "references/section-discussion.md",
    "conclusion": "references/section-discussion.md",
}

ABSTRACT_WORDS = {"en": 220, "zh": 320}

# ---------------------------------------------------------------- 工具


def _read_skill(relpath: str, limit: int = 6000) -> str:
    p = engine.SKILL_ROOT / relpath
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="ignore")[:limit]


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _log(job: dict, msg: str) -> None:
    job["log"].append({"t": _now(), "msg": msg})
    if len(job["log"]) > 200:
        job["log"] = job["log"][-200:]


def _log_safe(job: dict, msg: str) -> None:
    """给可能没有 log 键的旧任务用：记不上日志不该让装配失败。"""
    try:
        _log(job, msg)
    except Exception:
        pass


TAG_RE = re.compile(r"<!--ONESHOT:(\{[\s\S]*?\})-->")


def _pick_json(text: str) -> dict:
    m = TAG_RE.search(text or "")
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def _strip_fence(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^```(?:markdown|md)?\s*\n", "", t)
    t = re.sub(r"\n```\s*$", "", t)
    return t.strip()


def _call(llm_cfg: dict, system: str, user: str, temperature: float = 0.4) -> str:
    """单次调用，失败重试一次；仍失败抛出带上下文的错误。"""
    last = None
    for attempt in range(2):
        try:
            return llm.chat(
                llm_cfg["api_key"],
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                base_url=llm_cfg.get("base_url"),
                model=llm_cfg.get("model"),
                temperature=temperature,
            )
        except Exception as e:  # 网络抖动/超时重试一次
            last = e
            if attempt == 0:
                time.sleep(2)
    raise RuntimeError(f"模型调用失败（已重试）：{last}")


def _body_counts(job: dict) -> tuple[int, int]:
    """正文里的占位计数（只看章节正文，不算草稿声明/生成说明里的示例文字）。"""
    t = "\n".join(s.get("text") or "" for s in (job.get("draft_sections") or []))
    return t.count("[TBD:"), len(refs.extract(t))


def _write(job: dict, name: str, text: str) -> Path:
    p = Path(job["dir"]) / name
    p.write_text(text, encoding="utf-8")
    job["artifacts"][name] = len(text.encode("utf-8"))
    return p


# ---------------------------------------------------------------- 配置与闸门


def normalize_cfg(cfg: dict) -> dict:
    cfg = dict(cfg or {})
    track = str(cfg.get("track") or "quant")
    genre = str(cfg.get("genre") or track)
    lang = str(cfg.get("language") or "en").lower()
    data = str(cfg.get("data") or "no").lower()
    try:
        words = int(cfg.get("words") or 7000)
    except Exception:
        words = 7000
    return {
        "track": track,
        "genre": genre if genre in engine.GENRE_LABELS else track,
        "level": str(cfg.get("level") or "journal"),
        "venue": str(cfg.get("venue") or "").strip(),
        "citation": str(cfg.get("citation") or ("gb7714" if lang == "zh" else "apa")).lower(),
        "language": "zh" if lang == "zh" else "en",
        "words": max(WORD_MIN, min(WORD_MAX, words)),
        # find = 「无数据 + 请求荐源」：写作行为等同 no，差别只在第 3 步给可核实的数据源清单 + 代下载公开源
        # demo = 「演示模式」：正文仍 [TBD]，另产一份带标注模拟值的演示稿（仅排版预览，不进正文）
        "data": data if data in ("yes", "no", "partial", "find", "demo") else "no",
        # 前端已查过的荐源结果（限 10 条、只留必要字段），跑批时命中就不再联网
        "sources": [
            {k: str(s.get(k) or "")[:400] for k in ("name", "kind", "access", "url", "why", "how", "cite")}
            for s in (cfg.get("sources") or []) if isinstance(s, dict) and s.get("url")
        ][:10],
        # 表单已不再单独收「研究方向」：题目即研究方向，下游提示词统一用它兜底
        "direction": str(cfg.get("direction") or cfg.get("title") or "").strip(),
        "query_en": str(cfg.get("query_en") or "").strip(),
        # 作者从选题页自己复制过来的题目：有它就不再让模型另挑候选
        "title": str(cfg.get("title") or "").strip()[:300],
        "dataset_id": str(cfg.get("dataset_id") or "").strip()[:32],
        # 自检时让大模型对 must 级词面命中做 3 票全文复核（默认关；需 API Key，按调用计费）
        "recheck": str(cfg.get("recheck") or "").lower() in ("1", "true", "yes", "on"),
    }


CJK_RE = re.compile(r"[\u3400-\u9fff]")


def _nodata(cfg: dict) -> bool:
    """结果章是否必须走「不得编数」分支。

    find 是「无数据 + 请求荐源」，写作行为与 no 完全一致——只是第 3 步多一份来源清单
    并代下载公开源。
    demo 是「演示模式」：正文同样必须 [TBD] 占位（红线不破），只是额外产一份隔离的
    演示稿放模拟值。所以 demo 也归入「不得在正文编数」。
    所有判断数据有无的地方都走这里，新增档位时才不会漏掉某处分支。
    """
    return cfg.get("data") in ("no", "partial", "find", "demo")


def has_cjk(text: str) -> bool:
    """题名里是否含汉字。含汉字则需译成英文题名——本工具产出英文期刊稿。"""
    return bool(CJK_RE.search(str(text or "")))


def _clean_title(raw: str) -> str:
    """模型有时会带引号、代码块、"Title:" 前缀或句号，统一剥掉。"""
    s = str(raw or "").strip()
    s = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", s).strip()
    s = re.sub(r"^(?:title|english\s+title|translation)\s*[:：]\s*", "", s, flags=re.I)
    s = s.strip().strip('"').strip("“”").strip("'").strip("‘’")
    s = s.strip().rstrip(".").rstrip("。").strip()
    s = re.sub(r"\s+", " ", s)
    return s[:300].strip()


_TITLE_TRANSLATE_PROMPT = """Translate this research paper title into a publishable academic English title.

Rules:
- Use the standard English term for each technical concept, not a literal gloss.
  (e.g. 数字普惠金融 -> digital financial inclusion; 融资约束 -> financing constraints;
   县域制造业企业 -> county-level manufacturing firms; 投资效率 -> investment efficiency)
- Title Case. One line. No quotes, no period, no "Title:" prefix, no explanation, no Chinese left.
- Preserve the study design and scope markers: Evidence from X / A Case Study of X /
  Quasi-Experimental Evidence / Evidence from China.
- Keep proper nouns and place names in their conventional English form.
- Do NOT add claims, methods or regions that the original title does not contain.

Title: {title}

Output the English title only."""


def translate_title(title: str, llm_cfg: dict) -> str:
    """把中文题名译成学术英文题名。失败返回空串，由调用方决定降级方式。"""
    title = str(title or "").strip()
    if not title:
        return ""
    out = llm.chat(
        llm_cfg.get("api_key"),
        [{"role": "user", "content": _TITLE_TRANSLATE_PROMPT.format(title=title)}],
        base_url=llm_cfg.get("base_url"),
        model=llm_cfg.get("model"),
        temperature=0,
        timeout=90,
        max_tokens=300,
    )
    en = _clean_title(out)
    # 还带汉字说明没译完，宁可报错也不要把半中半英的题名塞进稿子
    if not en or has_cjk(en):
        return ""
    return en


def gate_check(cfg: dict) -> dict:
    """前置条件检查（不调模型）。返回 {ok, checks, fatal, plan}。"""
    cfg = normalize_cfg(cfg)
    checks: list[dict] = []
    fatal: list[str] = []

    def add(key, label, status, detail):
        checks.append({"key": key, "label": label, "status": status, "detail": detail})
        if status == "fail":
            fatal.append(f"{label}：{detail}")

    # 1 定题（题目是唯一必填的学术输入：不再单独收「研究方向」）
    if not cfg["title"]:
        add("title", "已定题目", "fail",
            "必须填题目：先去「选题」页用雷达定题，点结果卡上的「复制题目」粘到这里——"
            "选题的判断（数据拿不拿得到、导师认不认）模型替不了")
    else:
        add("title", "已定题目", "pass", cfg["title"][:120] + ("…" if len(cfg["title"]) > 120 else ""))
        if len(cfg["title"]) < 15:
            checks[-1]["status"] = "warn"
            checks[-1]["detail"] = (f"{cfg['title']}（偏短，不像完整学术题名；"
                                    "建议含研究对象 + 方法/数据线索 + 贡献指向）")
        elif has_cjk(cfg["title"]):
            checks[-1]["status"] = "warn"
            checks[-1]["detail"] = (f"{cfg['title'][:80]}（含中文；开启时会自动译为英文题名，"
                                    "确认后再开始更稳妥）")

    # 2 学科主线
    if cfg["track"] not in SUPPORTED_TRACKS:
        if cfg["track"] in ("theory", "math", "theory-econ"):
            add("track", "学科主线", "fail", "纯理论数理（定义-定理-证明）不支持：规则库基于 IMRaD，无实验/结果章节")
        else:
            add("track", "学科主线", "fail", f"未知主线 {cfg['track']}")
    else:
        tr = engine.track_stats().get(cfg["track"], {})
        add("track", "学科主线", "pass",
            f"{engine.TRACK_LABELS.get(cfg['track'], cfg['track'])} · 适用规则 {tr.get('rules', '—')} 条 · 词面检测器 {tr.get('detectors', '—')} 个")

    # 3 体裁与主线是否一致
    if cfg["genre"] != cfg["track"]:
        add("genre", "体裁", "warn",
            f"体裁 {engine.GENRE_LABELS.get(cfg['genre'], cfg['genre'])} 与主线不同，结构检查按体裁、规则按主线")
    else:
        add("genre", "体裁", "pass", engine.GENRE_LABELS.get(cfg["genre"], cfg["genre"]))

    # 4 语言（英文优先）
    if cfg["language"] == "en":
        add("language", "语言", "pass", "English —— 与规则库（国际期刊规范）一致")
    else:
        add("language", "语言", "warn",
            "中文为受限通道：规则库基于国际期刊规范，政策建议/研究局限等国内刊惯例不在库内，成稿需按目标刊要求人工改写")

    # 5 引用体系
    if cfg["language"] == "en" and cfg["citation"] == "gb7714":
        add("citation", "引用体系", "warn", "英文稿配 GB/T 7714 不常见，建议 IEEE 或 APA")
    elif cfg["language"] == "zh" and cfg["citation"] != "gb7714":
        add("citation", "引用体系", "warn", "中文稿通常用 GB/T 7714")
    else:
        add("citation", "引用体系", "pass", CITATION_LABEL.get(cfg["citation"], cfg["citation"]))

    # 6 字数
    add("words", "目标字数", "pass",
        f"{cfg['words']} {'words' if cfg['language'] == 'en' else '字'}（正文，不含摘要与文献）")

    # 7 数据状态 → 分支说明
    data_note = {
        "yes": ("pass", "有真实数据：结果章按真实分析写，表与图给出结构，数值由作者填入"),
        "partial": ("warn", "部分数据：结果章对已有部分写实、缺的部分用 [TBD: ...] 占位"),
        "no": ("warn", "无数据：结果章只写分析框架 + 表格骨架 + 模型设定式，数据处 [TBD: ...] 占位，不可直接投稿"),
        "find": ("warn", "无数据 + 请求荐源：结果章同「无数据」处理；第 3 步会检索可公开获取的数据源，"
                          "给链接、检索式与口径说明，并**代下载白名单公开源**（世行 / Zenodo / Dataverse）落盘，"
                          "但下载文件不解析、不注入正文，数值仍 [TBD: ...]"),
        "demo": ("warn", "演示模式：正文仍按「无数据」处理（[TBD: ...] 占位），另产一份**隔离的演示稿**"
                         "（模拟值仅排版预览，明确标注 SIMULATED，绝不进正文、不可投稿）"),
    }[cfg["data"]]
    add("data", "数据状态", data_note[0], data_note[1])
    if cfg["data"] == "find" and not cfg.get("dataset_id"):
        add("data_find", "荐源前提", "warn",
            "未上传数据表：荐源只能按题目检索，命中率偏低。先上传表结构，检索会按缺的列做定向匹配")

    # 7b 数据文件（只读结构）
    did = cfg.get("dataset_id") or ""
    prof = dataset.load_profile(did, JOB_DIR) if did else None
    if prof:
        flag = "（已截断：只扫描前 %d 行）" % prof.get("scanned", 0) if prof.get("truncated") else ""
        add("dataset", "数据文件", "pass",
            f"{prof.get('filename') or '数据'} · {prof.get('rows')} 行 × {prof.get('cols')} 列 · "
            f"{len(prof.get('id_like') or [])} 个疑似 ID 列{flag}；只读结构，行级数据不发给模型")
        if cfg["data"] == "no":
            checks[-1]["status"] = "warn"
            checks[-1]["detail"] += "；但数据状态选了「无数据」，建议改为「部分数据」或「已有真实数据」"
        elif cfg["data"] == "find":
            checks[-1]["detail"] += "；已按体检结果做定向荐源（缺哪列就找哪类来源）"
    elif did:
        add("dataset", "数据文件", "warn", "数据画像已失效（可能被移除），请重新上传或点「移除」后再开始")
    else:
        add("dataset", "数据文件", "warn",
            "未上传数据文件：变量名将由模型拟（[TBD] 占位）。若手上有 csv/xlsx，上传后可让表格用你的真实变量名")

    # 7c 数据特征与学科主线是否匹配（只提示，不改用户选择）
    sug = (prof or {}).get("suggest") or {}
    if prof and sug.get("track"):
        cur = cfg["track"]
        cur_label = engine.TRACK_LABELS.get(cur, cur)
        sug_label = engine.TRACK_LABELS.get(sug["track"], sug["track"])
        why = "；".join((sug.get("reasons") or [])[:2])
        if sug["track"] == cur:
            add("autotrack", "数据匹配", "pass", f"数据特征与所选主线一致：{sug_label}" + (f"（依据：{why}）" if why else ""))
        else:
            add("autotrack", "数据匹配", "warn",
                f"数据特征更像「{sug_label}」（依据：{why}），当前选的是「{cur_label}」。"
                "若数据只是辅助材料可忽略；否则建议在「学科主线」里改过去，规则子集与体裁文档会一起换。")
    elif prof:
        add("autotrack", "数据匹配", "pass", "数据特征未命中明确方法族，按你选的主线走；变量名仍以画像为准")

    # 7d 数据体检：判「按现有数据哪些分析做不了」，不做插补、不生成模拟值
    if prof:
        gap = dataset.gap_report(prof)
        c = gap["counts"]
        if c["risk"]:
            bad = [i for i in gap["items"] if i["status"] == "risk"]
            add("data_gap", "数据体检", "warn",
                f"阻断 {c['risk']} 项（分析层面做不了，但仍可成稿）："
                + "；".join(f"{i['label']}—{i['detail']}" for i in bad)[:260]
                + "。缺的列可在数据卡点「查可用数据源」找公开来源；"
                  "期数/样本量不足只能改设计，本系统不插补、不模拟")
        elif c["warn"]:
            add("data_gap", "数据体检", "warn",
                f"{c['warn']} 项需注意："
                + "；".join(f"{i['label']}—{i['detail']}"
                           for i in gap["items"] if i["status"] == "warn")[:260])
        else:
            add("data_gap", "数据体检", "pass",
                f"{c['pass']} 项全部通过（样本量、可分析变量、缺失率、结构深度）")

    # 8 目标期刊
    if cfg["venue"]:
        add("venue", "目标期刊/会议", "pass", cfg["venue"])
    else:
        add("venue", "目标期刊/会议", "warn", "未指定：按通用 SCI/SSCI 结构生成，投稿前须按目标刊格式调整")

    # 9 必需章节（取自 skill 原生 GENRE_SECTIONS，只读）
    required = engine.required_sections(cfg["genre"])
    add("sections", "必需章节", "pass", " / ".join(required))

    # 10 规则覆盖面（说明边界，避免"已通过全部规则"的误解）
    tr = engine.track_stats().get(cfg["track"], {})
    tot = tr.get("rules") or 0
    auto = tr.get("detectors") or 0
    manual = tr.get("manual") or 0
    add("coverage", "自检覆盖面", "warn",
        f"共 {tot} 条适用规则，其中 {auto} 条有词面检测器，{manual} 条需人工或大模型判读"
        "（跨主线检测器的规则两者都算，故两数之和可能大于总数）")

    # 11 文献装配口径
    add("refs", "文献装配", "pass",
        "正文引用由 OpenAlex 真实检索装配（逐条带 DOI，可点开核对）；检索不到的位置保留 "
        "[CITE: ...] 并写明原因，不编造作者与年份")

    plan = _plan_sections(cfg)
    return {"ok": not fatal, "checks": checks, "fatal": fatal,
            "cfg": cfg, "plan": plan}


def _plan_sections(cfg: dict) -> list[dict]:
    """按体裁给出章节计划（含字数分配）。"""
    base = SECTION_PLANS.get(cfg["genre"]) or SECTION_PLANS["quant"]
    weights = sum(w for _, _, w in base)
    body = cfg["words"]
    out = []
    for i, (key, title, w) in enumerate(base, start=1):
        out.append({
            "key": key,
            "title": title,
            "heading": f"{i}. {title}",
            "words": int(round(body * w / weights)),
        })
    if cfg["language"] == "zh":
        zh_map = {"Introduction": "引言", "Literature Review and Hypotheses": "文献综述与研究假设",
                  "Literature Review": "文献综述", "Related Work": "相关工作", "Methods": "研究方法",
                  "Results": "研究结果", "Discussion": "讨论", "Conclusion": "结论"}
        for i, s in enumerate(out, start=1):
            s["title"] = zh_map.get(s["title"], s["title"])
            s["heading"] = f"{i}、{s['title']}"
        if cfg["track"] in ("quant", "ssci") and cfg["language"] == "zh":
            out.append({"key": "policy", "title": "政策建议", "heading": f"{len(out) + 1}、政策建议",
                        "words": max(400, int(body * 0.08))})
    return out


# ---------------------------------------------------------------- 提示词

SYSTEM_WRITER = """You are a senior academic writer and methodologist who publishes in international peer-reviewed venues.

Hard rules — violating any of them makes the output unusable:
1. Write ONLY the requested part, in {lang}, in Markdown, starting with the given heading line.
2. NEVER fabricate data, statistics, effect sizes, sample sizes, or results. If a number is unknown, insert a specific, actionable placeholder: [TBD: Table 2, column (1), coefficient of X]. A placeholder that says exactly what must be filled in is always better than an invented number.
3. NEVER invent references. If a numbered reference library is supplied in the user message, cite ONLY those numbers as [n]; never cite anything not on that list, and write [NEEDCITE: what kind of source is needed] when the library has nothing suitable. If no library is supplied, write [CITE: what kind of source is needed, e.g. "a DID study of mobile money adoption in East Africa"].
4. Terminology must match the outline exactly; define every acronym at first use.
5. Academic register: precise, hedged where the evidence is thin, no marketing language, no bullet-point padding. Continuous prose with clear topic sentences; each paragraph makes one point.
6. Obey the section conventions in the reference document supplied by the user."""

SYSTEM_METHOD = """You are a research design reviewer for international journals. You are rigorous, specific, and allergic to vague advice.

Rules:
- Every recommendation must be actionable: state what to change and how.
- Never fabricate data sources, institutional details, or literature.
- When something is unknown, say what the author must supply and mark it [TBD: ...].
- Be explicit about what would make the design fail (identification threats, power, measurement error, selection).
- Write your analysis in Chinese (the user reads Chinese), but give all technical terms, variable names, section titles and model equations in English."""


def _ctx_block(job: dict, with_dataset: bool = True) -> str:
    cfg = job["cfg"]
    d = job.get("data", {})
    lines = [
        f"Discipline track: {cfg['track']} ({TRACK_SHORT.get(cfg['track'], '')})",
        f"Genre: {engine.GENRE_LABELS.get(cfg['genre'], cfg['genre'])}",
        f"Target venue: {cfg['venue'] or '(unspecified)'}",
        f"Author level: {cfg['level']}",
        f"Output language: {LANG_LABEL[cfg['language']]}",
        f"Target length: {cfg['words']} {'words' if cfg['language'] == 'en' else 'characters'} (body, excluding abstract and references)",
        f"Citation style: {CITATION_LABEL.get(cfg['citation'], cfg['citation'])}",
        f"Data status: {DATA_EN.get(cfg['data'], cfg['data'])}",
    ]
    # 题目即方向时不必重复一遍（title_en 会单独输出）
    if cfg["direction"] and cfg["direction"] != cfg["title"]:
        lines.append(f"Author's research direction (may be in Chinese): {cfg['direction']}")
    if d.get("title_en"):
        lines.append(f"Final title (English): {d['title_en']}")
    if d.get("keywords"):
        lines.append(f"Keywords: {', '.join(d['keywords'])}")
    if d.get("design"):
        lines.append("Research design digest:\n" + d["design"][:1200])
    if d.get("outline_digest"):
        lines.append("Outline digest:\n" + d["outline_digest"][:1800])

    prof = d.get("dataset") if with_dataset else None
    if prof:
        parts = prof.get("parts") or [prof]
        files_txt = "; ".join(
            f"{p.get('filename')} ({p.get('rows')} rows x {p.get('cols')} cols"
            + (", primary" if p.get("primary") else "") + ")"
            for p in parts[:6])
        lines.append(
            "Author's dataset — STRUCTURE PROFILE ONLY"
            + (f" ({len(parts)} file(s): {files_txt})." if len(parts) > 1
               else f" ({prof.get('rows')} rows x {prof.get('cols')} columns).")
            + " Row-level observations are NOT available to you, so never invent data points, "
            "coefficients or standard errors. Use the variable names below EXACTLY as written "
            "(do not rename, translate or add variables that are not in the list). "
            "Columns marked as ID are entity identifiers: never use them as regressors or "
            "report their means. Any number that is not in the profile must be written as [TBD: ...].")
        lines.append(prof.get("summary_md") or "")

        st = prof.get("structure") or {}
        if st.get("layout"):
            lay = {"panel": "panel (entity x time)", "time-series": "time series",
                   "cross-section": "cross-section", "text-corpus": "text corpus",
                   "table": "flat table"}.get(st.get("layout"), st.get("layout"))
            extra = []
            if st.get("entity"):
                extra.append(f"entity column {st['entity']} ({st.get('n_entities')} units)")
            if st.get("time"):
                extra.append(f"time column {st['time']} ({st.get('n_periods')} periods)")
            if st.get("balanced") is not None:
                extra.append("balanced" if st.get("balanced") else "unbalanced")
            lines.append(f"Detected data layout: {lay}" + (f" — {', '.join(extra)}" if extra else "") + ".")

        sigs = prof.get("signals") or []
        if sigs:
            lines.append("Detected design signals (hints, not orders): "
                         + "; ".join(f"{s.get('label')} ({s.get('evidence')})" for s in sigs[:5])
                         + ". If your identification strategy differs, state the reason in one sentence "
                           "instead of silently ignoring the structure.")
        if prof.get("truncated"):
            lines.append(f"(Profile scanned the first {prof.get('scanned')} rows only; "
                         "the study sample size must stay [TBD: n] unless the author provides it.)")
    return "\n".join(lines)


# ---------------------------------------------------------------- 各步骤


def _fetch_trend(job: dict, query: str) -> tuple[str, str]:
    """OpenAlex 趋势（失败不阻断）。返回 (markdown 表, 一行摘要)。"""
    trend_md, trend_line = "", "未获取到趋势数据（网络或检索词问题），本步跳过趋势判读。"
    try:
        tr = topic_trend.get_trend(query)
        groups = tr.get("groups") or []
        if groups:
            trend_line = "，".join(f"{g['year']}:{g['count']}" for g in groups)
            trend_line += f"；判定：{tr.get('label')}；{tr.get('hint')}"
            if tr.get("note"):
                trend_line += f"；{tr['note']}"
            rows = [f"| {g['year']} | {g['count']} |{' （当年，未完整）' if g.get('partial') else ''} |"
                    for g in groups]
            trend_md = "| 年份 | 发文量 | 备注 |\n| --- | --- | --- |\n" + "\n".join(rows)
            job["data"]["trend"] = trend_line
            job["data"]["trend_groups"] = groups
            _log(job, f"OpenAlex 趋势：{len(groups)} 年数据")
        else:
            _log(job, "OpenAlex 未返回年份分组，按无趋势处理")
    except Exception as e:
        _log(job, f"趋势获取失败（不阻断）：{e}")
    return trend_md, trend_line


def _step_topic_author(job: dict, llm_cfg: dict) -> None:
    """作者已在选题页自己定题：不换题、不重造候选，只做体检与定位。"""
    cfg = job["cfg"]
    title = cfg["title"]

    query = cfg.get("query_en") or ""
    if not query:
        raw = _call(llm_cfg, SYSTEM_METHOD,
                    f"把下面的英文论文题目转成 OpenAlex 检索式。\n题目：{title}\n\n"
                    "只要 3-6 个核心概念词，不要布尔操作符。只输出 JSON："
                    '{"query_en":"...","keywords":["..."],"field":"..."}',
                    temperature=0.1)
        mm = re.search(r"\{[\s\S]*\}", raw or "")
        info = {}
        if mm:
            try:
                info = json.loads(mm.group(0))
            except Exception:
                info = {}
        query = (info.get("query_en") or "").strip() or title
        job["data"]["keywords"] = info.get("keywords") or []
        _log(job, f"英文检索式：{query}")

    trend_md, trend_line = _fetch_trend(job, query)

    dir_line = ""
    if cfg["direction"] and cfg["direction"] != title:
        dir_line = f"作者的研究方向（中文，说明他真正想做什么）：{cfg['direction']}\n"
    user = (
        f"【任务】作者已经在「选题」环节用雷达评估，并**自己**定下了题目。"
        f"你要做的是体检与落位，不是替他换题。\n\n"
        f"作者原题目（英文，必须原样保留）：{title}\n"
        f"{dir_line}"
        f"学科主线：{cfg['track']}（{TRACK_SHORT.get(cfg['track'], '')}）\n"
        f"层级：{cfg['level']}；目标期刊/会议：{cfg['venue'] or '未指定'}\n"
        f"OpenAlex 检索式：{query}\n"
        f"全球发文趋势：{trend_line}\n\n"
        "请产出：\n"
        "1. **题目体检**：是否可证伪？核心变量是否在题目里可见？范围与层级是否匹配？"
        "有无因果表述过强（题目写了 effect 但设计只是相关）？逐项给 1-2 句判断。\n"
        "2. 若必须调整，给 1-2 个**最小改动版本**（保留作者原意与原研究对象），说明改了什么、为什么。"
        "不要另起一个新题目。\n"
        "3. 一句话研究问题（含变量与预期方向，可证伪）。\n"
        "4. 3-6 个英文关键词。\n"
        "5. 三条贡献（每条一句话，说明'相对谁、多了什么'）。\n"
        "6. 一句话 positioning：本文属于哪支文献、补哪个缺口。\n"
        "7. 若给了趋势，用一句话判断这个题现在的必要性（升温/平稳/回落）。\n"
        "用中文写说明，题目、变量名、关键词用英文。最后单独输出一行：\n"
        '<!--ONESHOT:{"title_en":"' + title.replace('"', "'") + '","title_zh":"...","question":"...",'
        '"keywords":["..."],"contribution":["..."],"positioning":"...","verdict":"keep|tweak|reconsider"}-->\n'
    )
    body = _call(llm_cfg, SYSTEM_METHOD, user, temperature=0.3)
    got = _pick_json(body)

    # 铁律：作者题目优先。模型只能在正文里建议微调，不得直接替换。
    got["title_en"] = title
    got["source"] = "author"
    job["data"]["topic_pick"] = got
    job["data"]["title_en"] = title
    job["data"]["keywords"] = got.get("keywords") or job["data"].get("keywords") or []
    job["data"]["chosen"] = {
        "title_en": title,
        "title_zh": got.get("title_zh") or "",
        "question": got.get("question") or "",
        "keywords": job["data"]["keywords"],
        "contribution": got.get("contribution") or [],
        "positioning": got.get("positioning") or "",
        "source": "author",
        "verdict": got.get("verdict") or "keep",
    }

    md = [
        "# 第 1 步 · 定题确认（作者自定，沿用选题页雷达结论）\n",
        f"- 题目：**{title}**",
        f"- 英文检索式：`{query}`",
        f"- 目标期刊/会议：{cfg['venue'] or '未指定'} ｜ 层级：{cfg['level']}",
        "- 说明：本步不生成候选题目；体检与微调建议仅供参考，题目以作者原题为准。\n",
        "## OpenAlex 发文趋势\n",
        trend_md or "_未获取到趋势数据_",
        "\n", f"> {trend_line}\n",
        "## 题目体检与定位\n", _strip_fence(body), "\n",
    ]
    _write(job, STEP_ARTIFACT["topic"], "\n".join(md))


def _step_topic(job: dict, llm_cfg: dict) -> None:
    cfg = job["cfg"]
    if cfg.get("title"):
        return _step_topic_author(job, llm_cfg)
    # 1) 英文检索词
    query = cfg.get("query_en") or ""
    if not query:
        raw = _call(llm_cfg, SYSTEM_METHOD,
                    f"研究方向的英文检索式设计。\n学科主线：{cfg['track']}\n研究方向：{cfg['direction']}\n\n"
                    "请给出：1) 一个适合 OpenAlex 的英文检索式（3-6 个词，只用核心概念，不要布尔操作符）；"
                    "2) 4-6 个英文关键词；3) 该方向所属的英文领域名。\n"
                    '只输出 JSON：{"query_en":"...","keywords":["..."],"field":"..."}',
                    temperature=0.2)
        mm = re.search(r"\{[\s\S]*\}", raw or "")
        info = {}
        if mm:
            try:
                info = json.loads(mm.group(0))
            except Exception:
                info = {}
        query = (info.get("query_en") or "").strip() or cfg["direction"]
        job["data"]["keywords"] = info.get("keywords") or []
        job["data"]["field_en"] = info.get("field") or ""
        _log(job, f"英文检索式：{query}")

    # 2) OpenAlex 趋势（失败不阻断）
    trend_md, trend_line = _fetch_trend(job, query)

    # 3) 三候选 + 三维打分
    dims = _read_skill("references/topic-scoring-dimensions.md", 6000)
    prompt_tpl = _read_skill("assets/topic-prompts.md", 4000)
    ref = _read_skill(f"references/genre-{_genre_file(cfg['track'])}", 3500)

    user = (
        f"【任务】为下面这位作者设计 3 个候选选题，并做三维评估。\n\n"
        f"学科主线：{cfg['track']}（{TRACK_SHORT.get(cfg['track'], '')}）\n"
        f"层级：{cfg['level']}\n"
        f"目标期刊/会议：{cfg['venue'] or '未指定'}\n"
        f"语言：{LANG_LABEL[cfg['language']]}\n"
        f"作者的研究方向（可能不成熟，需要你补齐成可做的题目）：{cfg['direction']}\n"
        f"英文检索式：{query}\n"
        f"OpenAlex 发文趋势：{trend_line}\n\n"
        "要求：\n"
        "1. 三个题目必须彼此不同（不同识别策略 / 不同数据 / 不同机制），不要同一题目的三种说法。\n"
        "2. 每题给：英文题目（≤20 words）、中文解释一句话、研究问题（可证伪）、数据来源、识别策略或分析方法、边际贡献。\n"
        "3. 三维打分（新颖性 / 可行性 / 数据·材料可得性，各 1-10 分），打分标准随学科主线与层级变化，"
        "每个分数后给一句理由；再给加权总分。\n"
        f"4. 明确说明：在当前层级（{cfg['level']}）下，哪个题目最现实，为什么。\n"
        "5. 用中文写分析，题目、变量名、方法名用英文。\n"
        "6. 最后单独输出一行机器可读标记（不要放进代码块）：\n"
        '<!--ONESHOT:{"title_en":"最佳题目的英文题目","title_zh":"中文题名","keywords":["k1","k2","k3"],"gap":"一句话说明文献缺口","method":"核心方法"}-->\n'
    )
    if dims:
        user += f"\n【评分维度矩阵（随范式与层级变化，必须据此打分）】\n{dims}\n"
    if prompt_tpl:
        user += f"\n【提示词模板参考】\n{prompt_tpl}\n"

    body = _call(llm_cfg, SYSTEM_METHOD, user, temperature=0.5)
    pick = _pick_json(body)
    job["data"]["topic_pick"] = pick
    job["data"]["query_en"] = query

    md = [f"# 第 1 步 · 选题与候选\n",
          f"- 英文检索式：`{query}`",
          f"- 目标期刊/会议：{cfg['venue'] or '未指定'}",
          f"- 层级：{cfg['level']}\n",
          "## OpenAlex 发文趋势\n",
          trend_md or "_未获取到趋势数据_",
          "\n", f"> {trend_line}\n",
          "## 候选题目与三维评估\n", _strip_fence(body), "\n"]
    if ref:
        md.append("## 附：本主线写作规范摘录\n\n" + ref + "\n")
    _write(job, STEP_ARTIFACT["topic"], "\n".join(md))


def _genre_file(track: str) -> str:
    mapping = {
        "quant": "quant-empirical.md", "predictive": "sci-journal.md",
        "qualitative": "qualitative.md", "basic-science": "sci-journal.md",
        "clinical": "sci-journal.md", "ei-conf": "ei-conference.md",
        "ai-conf": "ei-conference.md", "sci-journal": "sci-journal.md",
        "ssci": "ssci.md", "dissertation": "dissertation.md",
    }
    return mapping.get(track, "sci-journal.md")


def _step_chosen(job: dict, llm_cfg: dict) -> None:
    cfg = job["cfg"]
    pick = job["data"].get("topic_pick") or {}
    title = pick.get("title_en") or ""

    # 作者自定题目：第 1 步已产出完整的定题信息，这里不再让模型重定一次题，
    # 避免「作者定的是 A、第 2 步悄悄改成 B」。
    prev = job["data"].get("chosen") or {}
    if prev.get("source") == "author" and prev.get("title_en"):
        lines = [f"# 第 2 步 · 定题（沿用第 1 步 · 作者自定）\n",
                 f"**题目（英文）**：{prev['title_en']}\n"]
        if prev.get("question"):
            lines.append(f"**研究问题**：{prev['question']}\n")
        if prev.get("keywords"):
            lines.append(f"**关键词**：{', '.join(prev['keywords'])}\n")
        if prev.get("contribution"):
            lines.append("**贡献**\n")
            lines += [f"{i}. {c}" for i, c in enumerate(prev["contribution"], 1)]
            lines.append("")
        if prev.get("positioning"):
            lines.append(f"**Positioning**：{prev['positioning']}\n")
        lines.append("> 题目由作者在「选题」环节用雷达评估后自定；本步只做结构化落盘，不改题。\n")
        _write(job, STEP_ARTIFACT["chosen"], "\n".join(lines))
        _log(job, "作者自定题目：跳过二次定题，直接落盘")
        return

    dir_line = f"作者方向：{cfg['direction']}\n" if cfg["direction"] != (pick.get("title_en") or "") else ""
    user = (
        f"【任务】把候选题目定稿为可直接写稿的研究定位。\n\n"
        f"{dir_line}"
        f"已选候选：{json.dumps(pick, ensure_ascii=False)}\n"
        f"目标期刊/会议：{cfg['venue'] or '未指定'}；层级：{cfg['level']}\n\n"
        "请产出：\n"
        "1. 定稿英文题目（≤ 20 words，含研究对象、方法线索、贡献指向；不要副标题堆砌）\n"
        "2. 一句话研究问题（可证伪，含变量）\n"
        "3. 3-6 个英文关键词\n"
        "4. 核心贡献三条（每条一句话，说明'相对谁、多了什么'）\n"
        "5. 与研究方向的对应关系（作者原意是否被改变，若改变说明理由）\n"
        "6. 一句话 positioning：本文属于哪支文献、补哪个缺口\n"
        "用中文写说明，题目与关键词用英文。最后单独输出一行：\n"
        '<!--ONESHOT:{"title_en":"...","title_zh":"...","question":"...","keywords":["..."],"contribution":["..."],"positioning":"..."}-->\n'
    )
    body = _call(llm_cfg, SYSTEM_METHOD, user, temperature=0.35)
    got = _pick_json(body)
    if got.get("title_en"):
        job["data"]["title_en"] = got["title_en"]
    if got.get("keywords"):
        job["data"]["keywords"] = got["keywords"]
    job["data"]["chosen"] = got
    md = [f"# 第 2 步 · 定题\n", f"**题目（英文）**：{job['data'].get('title_en') or title or '（未解析到题目）'}\n",
          _strip_fence(body), "\n"]
    _write(job, STEP_ARTIFACT["chosen"], "\n".join(md))


def _data_shape_hint(job: dict) -> str:
    """把数据画像的结构与方法族信号压成一段中文提示，供第 3 步定识别策略。

    只陈述检测到的事实，不替作者决定方法；模型若走别的路子必须给理由。
    """
    prof = (job.get("data") or {}).get("dataset")
    if not prof:
        return ""
    st = prof.get("structure") or {}
    sigs = prof.get("signals") or []
    sug = prof.get("suggest") or {}
    lay = {"panel": "面板（实体 × 时间）", "time-series": "时间序列",
           "cross-section": "截面", "text-corpus": "文本语料",
           "table": "普通表格"}.get(st.get("layout"), "")

    lines = ["", "【数据特征（自动识别，供你确定识别策略；这些是事实，不要改写）】"]
    if lay:
        bits = [f"结构：{lay}"]
        if st.get("entity"):
            bits.append(f"实体列 {st['entity']}（{st.get('n_entities')} 个）")
        if st.get("time"):
            bits.append(f"时间列 {st['time']}（{st.get('n_periods')} 期）")
        if st.get("balanced") is not None:
            bits.append("平衡面板" if st.get("balanced") else "非平衡面板")
        lines.append("- " + "；".join(bits))
    for s in sigs[:5]:
        lines.append(f"- 信号：{s.get('label')}（{s.get('evidence')}）")
    if sug.get("track"):
        why = "；".join((sug.get("reasons") or [])[:3])
        lines.append(f"- 建议主线：{engine.TRACK_LABELS.get(sug['track'], sug['track'])}"
                     + (f"；依据：{why}" if why else ""))
    parts = prof.get("parts") or []
    if len(parts) > 1:
        lines.append("- 多份文件：" + "、".join(
            f"{p.get('filename')}（{'主表' if p.get('primary') else '附表'}）" for p in parts[:6])
            + "；若需合并请写明匹配键（如 firm_id + year），不要假设它们已经合并好")
    lines.append("- 变量名必须与画像完全一致；ID 列不进回归、不算均值；样本量未知写 [TBD: N]。")
    gap = dataset.gap_report(prof)
    holes = [i for i in gap["items"] if i["status"] in ("risk", "warn")]
    if holes:
        lines.append("- 数据缺口（结构事实，不得在正文里掩盖，也不得编造缺失部分）：")
        for i in holes[:5]:
            lines.append(f"  · {i['label']}：{i['detail']}")
        lines.append("  缺的部分写成 [TBD: ...] 或用一句话说明该分析为何做不了；"
                     "不要用「数据完整」「样本已清洗」等无依据的表述覆盖上述事实。")
    lines.append("- 若你的识别策略与上述信号不符，用一句话说明理由，不要默认忽略。")
    return "\n".join(lines)


SOURCE_ARTIFACT = "03b_sources.md"


def _need_terms(prof: dict | None) -> list[str]:
    """把体检的阻断项翻成一两个「数据集类型词」，只用来收窄检索类型。

    不把列名塞进检索式：Zenodo 是 OR 匹配，词一多就捞回不相干的记录（实测踩过）。
    """
    if not prof:
        return []
    try:
        rep = dataset.gap_report(prof)
    except Exception:
        return []
    risk = {i.get("key") for i in (rep.get("items") or []) if i.get("status") == "risk"}
    if "depth" not in risk:
        return []
    layout = ((prof.get("structure") or {}).get("layout") or "")
    if layout == "panel":
        return ["panel data"]
    if layout == "time-series":
        return ["time series"]
    return []


def _sources_for(job: dict) -> dict:
    """取一份可核实的数据源清单。任何异常都降级为空清单，绝不阻断成稿。"""
    cfg = job["cfg"]
    prof = (job.get("data") or {}).get("dataset")
    cached = cfg.get("sources") or []
    if cached:
        return {"items": cached, "terms": [], "notes": ["复用页面上已检索的结果，未重复联网"],
                "gap_note": "", "counts": {}, "cached": True}
    topic = ((job.get("data") or {}).get("title_en") or cfg.get("title")
             or cfg.get("direction") or "")
    try:
        res = datasource.suggest(topic=topic, need=_need_terms(prof), profile=prof,
                                 llm_cfg=job.get("llm"))
    except Exception as e:
        return {"items": [], "terms": [], "counts": {}, "cached": False, "gap_note": "",
                "notes": [f"在线检索不可用（{type(e).__name__}）：本次只按内置白名单给入口"]}
    res["cached"] = False
    return res


def _sources_download(job: dict, res: dict) -> None:
    """代下载白名单公开源到 _sources/ 目录（自动触发，失败不阻断）。

    只下载 datasource.download 允许的白名单来源；落盘后不解析、不注入正文。
    结果写进 job["data"]["downloads"] 供状态与产物引用；网络/限流失败则记录不报错。
    """
    cfg = job["cfg"]
    items = res.get("items") or []
    if not items:
        return
    outdir = os.path.join(job["dir"], "_sources")
    try:
        r = datasource.download(items, outdir)
        job["data"]["downloads"] = r
        if r.get("downloaded"):
            _log(job, f"已代下载 {len(r['downloaded'])} 个公开源文件到 _sources/（未解析，请核对口径）")
        for n in r.get("notes") or []:
            _log(job, "数据源下载：" + n)
        # 追加下载说明到 03b_sources.md（正文不清单，只补一段下载结果）
        if r.get("downloaded") or r.get("skipped") or r.get("failed"):
            _append_download_note(job, r)
    except Exception as e:
        job["data"]["downloads"] = {"downloaded": [], "skipped": [], "failed": [],
                                    "files": [], "notes": [f"代下载失败（{type(e).__name__}）"]}
        _log(job, f"代下载失败（不阻断）：{e}")


def _append_download_note(job: dict, r: dict) -> None:
    """把代下载结果追加进 03b_sources.md 末尾，供作者核对（不覆盖原清单）。"""
    lines = ["\n---\n## 代下载结果（自动，未经解析）\n",
             "> 以下文件由系统从白名单公开源自动下载，**只落盘、不解析、不核对口径**。",
             "> 请先核对单位、样本期与统计口径，再决定是否上传。" ]
    for it in r.get("downloaded") or []:
        lines.append(f"- ✅ {it.get('name')} → `{it.get('file')}`（{it.get('bytes', 0)} 字节）")
    for it in r.get("skipped") or []:
        lines.append(f"- ⏭ {it.get('name')}：{it.get('reason')}")
    for it in r.get("failed") or []:
        lines.append(f"- ❌ {it.get('name')}：{it.get('reason')}")
    lines.append("")
    try:
        p = os.path.join(job["dir"], SOURCE_ARTIFACT)
        with open(p, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception:
        pass


def _sources_prompt(res: dict, limit: int = 1200) -> str:
    """给第 3 步的来源清单：只给名称、链接、取法与口径提醒，不给任何数字。"""
    items = res.get("items") or []
    if not items:
        note = "；".join(res.get("notes") or []) or "未检索到结果"
        return ("\n【可核实的数据源清单】\n（本次检索未取得结果：" + note +
                "。不要凭印象点名数据库；改为说明需要哪类数据、如何自行检索。）\n")
    lines = ["\n【可核实的数据源清单】（只能引用以下来源，不得另编数据库或子库）"]
    if res.get("terms"):
        lines.append("检索式：" + " / ".join(res["terms"][:2]))
    if res.get("gap_note"):
        lines.append(res["gap_note"])
    for it in items[:8]:
        lines.append(f"- {it.get('name')}｜{it.get('kind')}｜{it.get('access')}｜{it.get('url')}")
        if it.get("why"):
            lines.append(f"  相关原因：{it['why']}")
        if it.get("how"):
            lines.append(f"  取法：{it['how']}")
    body = "\n".join(lines)
    return body[:limit] + ("\n（清单已截断，其余见 03b_sources.md）\n" if len(body) > limit else "\n")


def _sources_md(res: dict) -> str:
    """独立产物：给作者照着下载用，数字一律为空。"""
    items = res.get("items") or []
    md = ["# 数据源线索（自动检索，仅作线索）\n",
          "> **只给线索，不落数字。** 本清单不含任何数值：不下载、不解析、不写入表格。",
          "> 取回后请先核对单位、样本期与统计口径——口径不一致的数据拼进同一张表，比留 `[TBD: ...]` 更危险。\n"]
    if res.get("terms"):
        md.append("**检索式**：" + "、".join(f"`{t}`" for t in res["terms"][:3]))
    if res.get("gap_note"):
        md.append("**数据体检**：" + res["gap_note"])
    if res.get("notes"):
        md.append("**过程说明**：" + "；".join(res["notes"]))
    if not items:
        md.append("\n本次未取得检索结果。可先上传数据表结构后再试：有了列名，检索会按缺的变量做定向匹配。\n")
        return "\n".join(md) + "\n"

    online = [i for i in items if "下载" in (i.get("access") or "") or "导出" in (i.get("access") or "")]
    manual = [i for i in items if i not in online]
    for title, group in (("可直接获取", online), ("需手工检索或申请授权", manual)):
        if not group:
            continue
        md.append(f"\n## {title}\n")
        for i, it in enumerate(group, 1):
            md.append(f"### {i}. {it.get('name')}\n")
            md.append(f"- 类型：{it.get('kind')}　获取方式：{it.get('access')}")
            md.append(f"- 链接：{it.get('url')}")
            if it.get("why"):
                md.append(f"- 相关原因：{it['why']}")
            if it.get("how"):
                md.append(f"- 取法：{it['how']}")
            if it.get("cite"):
                md.append(f"- 引用：{it['cite']}")
            md.append("")
    md.append("\n---\n取回数据后，把文件重新上传到「数据文件」，并把数据状态改为「部分数据」或"
              "「已有真实数据」，结果章才会按真实数值写。\n")
    return "\n".join(md)


def _step_design(job: dict, llm_cfg: dict) -> None:
    cfg = job["cfg"]
    data_rule = {
        "yes": "作者有真实数据。请把数据来源、样本期、变量定义、清洗与检验步骤写清楚，供第 5 步直接据实写作。",
        "partial": "作者有部分数据。明确哪部分有、哪部分缺；缺的部分给出替代方案或 [TBD: ...] 说明。",
        "no": "作者没有数据。请给出一份可执行的数据采集方案（公开数据库名称、变量代理、样本期、匹配键），"
              "以及在没有数据时结果章应当报告什么（表格骨架、模型设定式、稳健性清单）。不要编造任何数据集细节。",
        "find": "作者没有数据，并明确要求帮忙找可用数据源。请给出一份可执行的数据采集方案："
                "对每个缺失变量，给出变量代理、候选数据源（名称 + 访问方式 + 授权类型）、样本期与匹配键、"
                "以及拿不到时的替代方案；并说明在数据到位前结果章应当报告什么（表格骨架、模型设定式、稳健性清单）。"
                "**只能引用下方【可核实的数据源清单】里出现的来源**；清单没有覆盖到的变量，"
                "写明「未检索到公开来源，需申请授权或换变量代理」，不得凭印象点名数据库或子库。"
                "不要编造任何数据集细节（样本量、年份覆盖、字段名）。",
        "demo": "演示模式：作者要一份能预览排版效果的稿子。正文仍按「无数据」写——所有数值用 "
                "[TBD: ...] 占位，不得编造。数据采集方案同「帮我找数据源」档，只能引用下方"
                "【可核实的数据源清单】。模拟值只出现在单独的演示稿里，绝不写进这份正文。",
    }[cfg["data"]]
    ref = _read_skill("references/evidence-and-data.md", 5000)
    src_block = ""
    if cfg["data"] in ("find", "demo"):
        res = _sources_for(job)
        job["data"]["sources"] = res.get("items") or []
        job["data"]["sources_meta"] = {k: res.get(k) for k in ("terms", "notes", "gap_note", "cached")}
        _write(job, SOURCE_ARTIFACT, _sources_md(res))
        src_block = _sources_prompt(res)
        # 代下载白名单公开源：自动触发，落盘到 _sources/，失败不阻断
        _sources_download(job, res)
    user = (
        f"{_ctx_block(job)}\n\n【任务】给出研究设计，供后续大纲与分章写作直接使用。\n{data_rule}\n"
        f"{src_block}"
        f"{_data_shape_hint(job)}\n\n"
        "必须包含：\n"
        "1. 识别策略（或分析策略）：为什么这个设计能回答研究问题；主要威胁是什么（内生性/选择/测量误差/功效）。\n"
        "2. 数据与样本：来源、时间范围、单位、样本量（未知则 [TBD: ...]）、清洗与异常值处理。\n"
        "3. 变量：被解释变量、核心解释变量、控制变量、固定效应/工具变量，给出英文变量名与定义表（Markdown 表格）。\n"
        "4. 模型设定：给出 2-3 个 LaTeX 公式（主模型、机制/异质性模型、稳健性），每个公式后一句话解读。\n"
        "5. 稳健性与证伪检验清单（4-6 条，具体到做法）。\n"
        "6. 伦理与数据可得性声明要点。\n"
        "用中文写说明，变量名、公式、表头用英文。\n"
    )
    if ref:
        user += f"\n【证据与数据规范参考】\n{ref}\n"
    body = _call(llm_cfg, SYSTEM_METHOD, user, temperature=0.35)
    job["data"]["design"] = body
    _write(job, STEP_ARTIFACT["design"], f"# 第 3 步 · 研究设计\n\n{_strip_fence(body)}\n")


def _step_outline(job: dict, llm_cfg: dict) -> None:
    cfg = job["cfg"]
    plan = job["plan"]
    plan_txt = "\n".join(f"- {s['heading']}（~{s['words']} {'words' if cfg['language'] == 'en' else '字'}；key={s['key']}）" for s in plan)
    user = (
        f"{_ctx_block(job)}\n\n【任务】按下面的章节与字数分配，给出写作大纲。\n{plan_txt}\n\n"
        "要求：\n"
        "1. 逐节给出 3-6 条要点（每要点一句话，说明这节要论证什么，而不是'介绍背景'这种空话）。\n"
        "2. 给出图表清单：每个表/图的编号、标题（英文）、要展示的变量或结果、放在哪一节。"
        f"至少 3 个表、1 个图或 1 个公式；数据状态为{DATA_CN.get(cfg['data'], cfg['data'])}时，表内数值用 [TBD: ...] 占位说明。\n"
        "3. 给出论证链：引言提出的问题 → 方法如何回答 → 结果如何支撑 → 讨论回到哪个理论争点。\n"
        "4. 用中文写要点，章节标题、图表标题用英文。\n"
        '5. 最后输出机器可读大纲（sections 的 key 必须与上面给的 key 一致）：\n'
        '<!--ONESHOT:{"sections":[{"key":"intro","title":"Introduction","words":900,"points":["...","..."]}],'
        '"tables":[{"id":"Table 1","caption":"...","section":"method"}],"figures":[{"id":"Figure 1","caption":"...","section":"results"}]}-->\n'
    )
    body = _call(llm_cfg, SYSTEM_METHOD, user, temperature=0.4)
    got = _pick_json(body)
    secs = got.get("sections") or []
    # 用模型给的要点覆盖计划里的点数，但字数以本地计划为准（防止模型乱配）
    by_key = {s["key"]: s for s in secs}
    for s in plan:
        s["points"] = (by_key.get(s["key"]) or {}).get("points") or []
    job["data"]["outline"] = got
    job["data"]["outline_digest"] = "\n".join(
        f"- {s['heading']}（{s['words']}）: " + "; ".join(s.get("points", [])[:3]) for s in plan)
    job["data"]["tables"] = got.get("tables") or []
    job["data"]["figures"] = got.get("figures") or []
    _write(job, STEP_ARTIFACT["outline"],
           f"# 第 4 步 · 大纲与字数分配\n\n{_strip_fence(body)}\n\n## 本地字数计划\n\n{plan_txt}\n")


def _digest_of(text: str, limit: int = 700) -> str:
    t = _strip_fence(text)
    return t[:limit]


# ---------------------------------------------------------------- 图表清单分发
#
# 第 4 步会产出 tables / figures 清单（编号、标题、归属章节、要展示什么）。过去这份
# 清单只被写进 job["data"]，第 5 步完全没读：于是正文写着「如表 3 所示」，稿子里
# 却一个表都没有。下面这组函数负责按章节分发清单、写进提示词、并在成稿后补图占位。

_ASSET_SECTION_ALIAS = {
    "intro": "intro", "introduction": "intro",
    "related": "related", "literature": "related",
    "method": "method", "methods": "method", "methodology": "method",
    "data": "method", "variables": "method",
    "results": "results", "empirical": "results", "analysis": "results",
    "experiment": "results", "experiments": "results", "evaluation": "results",
    "findings": "results", "finding": "results",
    "discussion": "discussion", "conclusion": "conclusion",
}


def _asset_sec(value, plan_keys: list[str]) -> str:
    """把大纲里写的 section 名收敛到本地章节 key。"""
    k = _ASSET_SECTION_ALIAS.get(str(value or "").strip().lower(), "")
    if k in plan_keys:
        return k
    return "results" if "results" in plan_keys else (plan_keys[-1] if plan_keys else "results")


def _section_assets(job: dict, key: str) -> tuple[list, list]:
    d = job.get("data") or {}
    plan_keys = [x["key"] for x in (job.get("plan") or [])]
    tables = [t for t in (d.get("tables") or []) if _asset_sec(t.get("section"), plan_keys) == key]
    figures = [f for f in (d.get("figures") or []) if _asset_sec(f.get("section"), plan_keys) == key]
    return tables, figures


def _assets_prompt(job: dict, key: str) -> str:
    """本节必须实际产出的表/图；没有就返回空串。"""
    tables, figures = _section_assets(job, key)
    if not tables and not figures:
        return ""
    lines = ["", "【本节必须实际产出的图表 — 不是只在正文提一句】"]
    seen: set[str] = set()
    for t in tables:
        tid = str(t.get("id") or "Table").strip()
        if tid.lower() in seen:
            continue
        seen.add(tid.lower())
        cap = (t.get("caption") or "").strip()
        note = (t.get("notes") or "").strip()
        lines.append(f"- {tid}. {cap}" + (f"｜要展示：{note}" if note else ""))
    for f in figures:
        fid = str(f.get("id") or "Figure").strip()
        if fid.lower() in seen:
            continue
        seen.add(fid.lower())
        cap = (f.get("caption") or "").strip()
        note = (f.get("notes") or "").strip()
        lines.append(f"- {fid}. {cap}" + (f"｜画法要点：{note}" if note else ""))
    lines += [
        "",
        "产出规则（必须遵守）：",
        "· 每个表：先写一行 `**Table N.** 标题`，紧接一个 GFM 表格（表头 + 至少 2 行）；"
        "无数据时单元格写 `[TBD: 要填什么]`，不要留空、不要编数字；表格前用一句话引出（如 `Table N reports ...`）。",
        "· 每个图：只写一行图题，不要伪造图片地址、不要写 `![]()` 指向不存在的文件：",
        "  `**Figure N.** 标题`（单独一段，不要附带任何画法说明）",
        "· 画法要点（Plot type / 需要什么数据）**不要写进正文**——它们是给作者的待办，"
        "系统会自动归到稿件末尾的「待补图表」清单里。正文里只有图题。",
        "· 图表编号必须与上面清单一致；正文引用时用同一个编号。",
        "· 每个编号全篇只出现一次：表标题 `**Table N.**` 和图占位 `> **Figure N.**` 都只写一次；"
        "同一节内需要再次提到时，用 `Table N reports ...` 这类正文引用，不要重写标题。",
    ]
    return "\n".join(lines)


def _count_tables(text: str) -> int:
    rows = [l for l in str(text or "").splitlines() if re.match(r"^\s*\|.*\|\s*$", l)]
    # 表头 + 分隔线 + 数据行；单张 3 列表就有 3 行以上
    return len(rows)


def _inject_figure_blocks(job: dict) -> int:
    """模型漏写的图，用占位块补齐；已写 Figure N 的不重复。"""
    figs = (job.get("data") or {}).get("figures") or []
    if not figs:
        return 0
    secs = job.get("draft_sections") or []
    by_key = {x["key"]: x for x in secs}
    plan_keys = [x["key"] for x in (job.get("plan") or [])]
    added = 0
    for f in figs:
        fid = str(f.get("id") or "").strip() or "Figure"
        cap = str(f.get("caption") or "").strip().rstrip(".")
        key = _asset_sec(f.get("section"), plan_keys)
        sec = by_key.get(key) or (secs[-1] if secs else None)
        if not sec:
            continue
        # 全篇查重：模型可能把这张图写在别的节（或写成 Figure 1 引用），不能按节判断，
        # 否则同一编号会在两节各出现一次。
        pat = re.compile(r"\*\*\s*" + re.escape(fid) + r"\b")
        if any(pat.search(x.get("text") or "") for x in secs):
            continue
        if any(re.search(r"!\s*\[", x.get("text") or "") for x in secs):
            continue
        note = str(f.get("notes") or "").strip()
        # 只写图题。以前这里连带写了 Plot type / Required inputs / Status，
        # 结果这三行原样印进正文，读者会看到「author to choose」这种流水线口吻。
        # 画法要点改由 _figure_todos() 汇总到稿末的待补清单。
        block = [f"**{fid}.** {cap}", ""]
        sec["text"] = (sec.get("text") or "").rstrip() + "\n\n" + "\n".join(block) + "\n"
        added += 1
    return added


_FIG_INTERNAL_RE = re.compile(
    r"^(?:>\s*)?(?:Plot type|Required inputs|Status|Suggested plot|Figure type)\s*[:：]",
    re.I)


def _scrub_internal_notes(text: str) -> str:
    """剥掉正文里残留的流水线内部提示行。

    模型可能不听话，仍把 `Plot type: ...` 写成引用块或独立段落。这些行对读者
    毫无意义，而且会出现在导出稿里，所以成稿前统一清理。只删**以这些标签开头**
    的行，正常段落里出现 "status" 之类的词不受影响。
    """
    out, dropped = [], 0
    for line in str(text or "").splitlines():
        if _FIG_INTERNAL_RE.match(line.strip()):
            dropped += 1
            continue
        out.append(line)
    s = "\n".join(out)
    # 清理后可能留下连续空行与孤立的 ">" 行
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"\n\s*>\s*\n", "\n", s)
    if dropped:
        s = s.strip() + "\n"
    return s


def _step_draft(job: dict, llm_cfg: dict) -> None:
    cfg = job["cfg"]
    plan = job["plan"]
    title = job["data"].get("title_en") or "Untitled Manuscript"
    written: list[tuple[str, str, str]] = []   # (heading, text, key)

    # 先建文献库，再把编号清单交给每一节当「可引用白名单」。
    # 旧流程是写完了才去找文献，写作时并不知道自己能引什么，于是描述笼统、
    # 一条文献被反复命中。建库失败不阻断写作（退回 CITE 占位老路），
    # 但要把原因记进日志，免得用户以为是模型不肯引。
    lib = job["data"].get("library")
    if lib is None:
        try:
            _log(job, "建立可引用文献库（按题目与大纲检索）…")
            lib = refs.build_library(cfg, title,
                                     [s["heading"] for s in plan],
                                     lambda system, user: _call(llm_cfg, system, user,
                                                                temperature=0.2))
        except Exception as e:
            _log(job, f"文献库建立失败，正文退回 [CITE:] 占位：{str(e)[:120]}")
            lib = {"entries": [], "by_num": {}, "queries": [], "thin": True}
        job["data"]["library"] = lib
        n = len(lib.get("entries") or [])
        _log(job, f"文献库：{n} 条可引用记录"
                  + ("（偏少，正文部分位置可能仍需占位）" if lib.get("thin") else ""))

    lib_block = refs.library_prompt_block(lib or {})
    use_lib = bool(lib and lib.get("entries"))

    # 摘要最后写（需要全文），先写正文
    for sec in plan:
        key, heading, words = sec["key"], sec["heading"], sec["words"]
        doc = _read_skill(SECTION_DOC.get(key, "references/section-introduction.md"), 4500)
        prior = "\n\n".join(f"### {h}\n{d}" for h, d, _ in written[-3:]) if written else "（这是第一节）"
        special = ""
        if key == "results" and _nodata(cfg):
            special = (
                "\n\n【数据缺失时的写作规范 — 必须遵守】\n"
                f"当前数据状态：{DATA_CN.get(cfg['data'], cfg['data'])}。结果章不得出现任何编造的数字、显著性、效应量或样本量。\n"
                "1. 先写分析框架：本节依次报告什么、对应哪个研究问题。\n"
                "2. 给出模型设定式（LaTeX 公式，用 $$...$$ 独立成段），并解释每个符号。\n"
                "3. 表格用 Markdown 表格给出**表头与行标签**，单元格数值一律写 `[TBD: ...]`，"
                "例如 `[TBD: coefficient of DFI, SE in parentheses]`。\n"
                "4. 用条件式表述说明结果如何解读（\"If the coefficient is positive and significant at 5%, this would indicate ...\"）。\n"
                "5. 末尾加一个 `> Note:` 段落，列出作者需要补做的分析（3-5 条，可执行）。\n"
            )
        if key == "abstract":
            continue
        assets = _assets_prompt(job, key)
        need_eq = cfg["track"] in ("quant", "predictive") and key in ("method", "results")
        user = (
            f"{_ctx_block(job, with_dataset=(key in ('method', 'results', 'data', 'empirical')))}\n\n"
            f"【本节任务】{heading}，目标 {words} {'words' if cfg['language'] == 'en' else '字'}。\n"
            f"本节要点：\n" + "\n".join(f"- {p}" for p in (sec.get("points") or ["（按大纲自行组织）"])) + "\n\n"
            f"{assets}\n"
            + (f"{lib_block}\n" if use_lib else "")
            + f"【前文（用于衔接，不要重复）】\n{prior}\n"
            f"{special}\n"
            "写作要求：\n"
            f"1. 只输出本节，以 `## {heading}` 开头。\n"
            + ("2. 引用处只写编号 `[n]`，且 n 必须是上面文献库里的编号；库外文献一律不引，"
               "库里没有合适文献时写 `[NEEDCITE: 需要什么来源]`。\n"
               if use_lib else
               "2. 引用处写 [CITE: 需要什么来源]，不要编造作者年份。\n")
            + "3. 不要写'本文结构如下'这类空转段落（除非是引言最后一段，且用一句话）。\n"
            "4. 段落之间要有逻辑推进，不要罗列。\n"
            + ("5. 本节必须给出模型设定式：用 `$$ ... $$` 独立成段，公式编号写在公式内末尾（如 `\\qquad (1)`），"
               "并在公式后逐句解释每个符号的含义与取值来源。\n" if need_eq else "")
        )
        if doc:
            user += f"\n【本节写作规范（来自规则库参考文档）】\n{doc}\n"
        text = _strip_fence(_call(llm_cfg, SYSTEM_WRITER.format(lang=LANG_LABEL[cfg["language"]]),
                                  user, temperature=0.55))

        # 模型偶尔只写「如表 3 所示」而不真的画表；缺表/缺设定式就补一次，不无限重试
        my_tables, _my_figs = _section_assets(job, key)
        miss_tbl = bool(my_tables) and _count_tables(text) < 3
        miss_eq = need_eq and "$$" not in text
        if miss_tbl or miss_eq:
            fix = ["【上一次输出缺少必需内容，请重写本节，其余要求不变】"]
            if miss_tbl:
                fix.append("必须逐个输出上面列出的表：`**Table N.** 标题` + GFM 表格（表头 + 至少 2 行），"
                           "无数据的单元格写 `[TBD: ...]`；不能只在正文提到表号。")
            if miss_eq:
                fix.append("必须包含至少一个 `$$ ... $$` 独立公式，并在公式后解释每个符号。")
            try:
                text2 = _strip_fence(_call(
                    llm_cfg, SYSTEM_WRITER.format(lang=LANG_LABEL[cfg["language"]]),
                    user + "\n" + "\n".join(fix), temperature=0.4))
                ok_tbl = (not miss_tbl) or _count_tables(text2) >= 3
                ok_eq = (not miss_eq) or ("$$" in text2)
                if ok_tbl and ok_eq and len(text2) > len(text) * 0.6:
                    text = text2
                    _log(job, f"补写：{heading}（缺{'表' if miss_tbl else ''}{'公式' if miss_eq else ''}，已重写一次）")
            except Exception as e:
                _log(job, f"补写失败，保留原稿：{heading}（{str(e)[:60]}）")

        written.append((heading, _digest_of(text, 260), key))
        job["draft_sections"].append({"key": key, "heading": heading, "text": text})
        _write(job, STEP_ARTIFACT["draft"], _assemble(job, title, written_all=True, partial=True))
        _log(job, f"已写：{heading}（{len(text)} 字符）")

    # 图由模型漏写时补占位块（不伪造图片，只说明该画什么、需要什么数据）
    fig_added = _inject_figure_blocks(job)
    if fig_added:
        _log(job, f"已补 {fig_added} 个图占位块（Figure 说明 + 所需数据，不含图片）")

    # 摘要
    body_digest = "\n\n".join(f"### {s['heading']}\n{s['text'][:900]}" for s in job["draft_sections"])
    user = (
        f"{_ctx_block(job)}\n\n【全文草稿（摘要节选）】\n{body_digest[:9000]}\n\n"
        f"【任务】写摘要（{ABSTRACT_WORDS[cfg['language']]} {'words' if cfg['language'] == 'en' else '字'}以内）。\n"
        "结构：背景与问题（1-2 句）→ 数据与方法（1-2 句）→ 主要发现（2-3 句）→ 贡献与含义（1-2 句）。\n"
        "不得出现 [1] 这类引用编号；缩写首次出现须展开；数据未定时用 [TBD: ...]，不要编造数字。\n"
        f"只输出摘要正文，以 `## Abstract` 开头（中文稿用 `## 摘要`）。\n"
    )
    abstract = _strip_fence(_call(llm_cfg, SYSTEM_WRITER.format(lang=LANG_LABEL[cfg["language"]]),
                                 user, temperature=0.4))
    job["draft_sections"].insert(0, {"key": "abstract", "heading": "Abstract" if cfg["language"] == "en" else "摘要",
                                     "text": abstract})
    manuscript = _assemble(job, title, written_all=True)
    job["manuscript"] = manuscript
    # 留一份「未装配文献」的原始草稿：文献装配步每次都从这份原文重做，
    # 这样重跑「文献装配」是幂等的（不会因为上次已替换而找不到占位）。
    job["data"]["draft_raw"] = [dict(s) for s in job["draft_sections"]]
    _write(job, STEP_ARTIFACT["draft"], manuscript)
    _write(job, "manuscript.md", manuscript)

    # 演示模式：额外产一份隔离的演示稿，把 [TBD: ...] 换成带 * 标注的模拟值，
    # 仅供排版预览；绝不覆盖 manuscript.md，也不进 draft_raw / refs / check。
    if cfg["data"] == "demo":
        _write_demo_preview(job)


def _write_demo_preview(job: dict) -> None:
    """演示模式专用：生成 demo_preview.md（模拟值隔离，仅排版预览）。

    红线：正文 manuscript.md 永远 [TBD: ...]；本函数只在一份独立文件里把占位换成
    明显标注的模拟值，并在文件头大字声明 SIMULATED、不可投稿。模拟值只做「数字形状」
    演示（系数/SE/N/百分比），不含任何可被误认为真实结论的表述。
    """
    man = job.get("manuscript") or ""
    if not man:
        return
    cfg = job["cfg"]
    lang = cfg["language"]
    header = (
        "> ⚠️ **SIMULATED DATA — LAYOUT PREVIEW ONLY, NOT FOR SUBMISSION**\n"
        ">\n"
        "> 本文件是「演示模式」的排版预览稿：所有带 `*` 的数字都是**模拟值**，"
        "仅用来让表格与正文看起来完整，不反映任何真实数据或结论。\n"
        "> 正式投稿请用 `manuscript.md`（数值仍为 `[TBD: ...]`），补入真实数据后再导出。\n"
        "\n"
    )
    # 占位 → 模拟值：不同占位类型给不同形状的数字，避免整篇都是一个数
    demo = _fill_simulated(man, lang)
    demo = header + demo
    job["data"]["demo_preview"] = demo
    _write(job, "demo_preview.md", demo)
    _log(job, "已生成演示稿 demo_preview.md（模拟值仅排版预览，正文 manuscript.md 仍为 [TBD] 占位）")


_SIM_COUNTER = {"n": 0}


def _fill_simulated(text: str, lang: str) -> str:
    """把正文里的 [TBD: ...] 占位替换为带 * 的模拟值。

    只替换占位，不触碰正文里任何已经存在的真实数字（演示模式下本不该有）。
    模拟值的形状按占位内容猜测（系数 / SE / N / 百分比 / 一般数值），
    全部带 `*` 后缀并在文首声明，确保不可被误读为真实结果。
    """
    def repl(m: re.Match) -> str:
        hint = (m.group(1) or "").lower().strip()
        _SIM_COUNTER["n"] += 1
        k = _SIM_COUNTER["n"]
        # 按占位提示给形状，避免全是一个数；带 * 标注
        if any(w in hint for w in ("coefficient", "coef", "effect", "estimate", "系数", "效应")):
            return f"{0.03 * (k % 9) + 0.01:.3f}* ({0.012 + 0.004 * (k % 5):.3f})*"
        if hint in ("se", "se ", "sd", "sd ", "standard error", "标准误"):
            return f"{0.008 + 0.003 * (k % 7):.3f}*"
        if hint in ("n", "n ") or any(w in hint for w in ("sample", "样本", "observations", "obs", "cases", "样本量")):
            return f"{(1200 + 347 * k) * 4}*"
        if any(w in hint for w in ("%", "percent", "pct", "比例", "占比")):
            return f"{8 + (k % 20)}.{k % 10}%*"
        if any(w in hint for w in ("p-value", "p value", "p=", "显著性")):
            return f"0.0{1 + (k % 5)}*"
        return f"{(k * 7) % 100}.{k % 10}*"
    # 只替换真正的数据占位；反引号包裹的 `` `[TBD: ...]` `` 是元数据说明文字，跳过不碰
    return re.sub(r"(?<!`)\[TBD:\s*([^\]]*)\](?!`)", repl, text or "")


NEEDCITE_RE = re.compile(r"\[NEEDCITE:\s*([^\[\]]{2,400}?)\]", re.I)
NUMCITE_RE = re.compile(r"\[(\d{1,3})((?:\s*[,;]\s*\d{1,3})*)\]")


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _resolve_library(job: dict, raw: list[dict], lib: dict, cfg: dict) -> dict:
    """把正文里的 `[n]` 换成正式引注，再把残余 `[NEEDCITE:]` 走一次检索补上。

    与旧 `assemble()` 的区别：`[n]` 不需要检索，也不需要打分——它指向的就是
    库里那条已经核验过的记录，只检查「编号是否存在」和「是否越界」。
    这样「参考文献配不上正文」这类错误在结构上就不可能发生。
    """
    by_num = (lib or {}).get("by_num") or {}
    style = (cfg.get("citation") or "apa").lower()
    entries = list((lib or {}).get("entries") or [])
    items, bad_nums, need_cites = [], [], []

    # 1) 编号引用：逐节替换，记录越界编号
    sections_out, used = [], {}
    for sec in raw:
        text = sec.get("text") or ""

        def _sub(m):
            nums = [int(m.group(1))] + [int(x) for x in re.findall(r"\d+", m.group(2) or "")]
            good, bad = [], []
            for n in nums:
                rec = by_num.get(n)
                if rec:
                    good.append(rec)
                    used[n] = used.get(n, 0) + 1
                else:
                    bad.append(n)
            if bad:
                bad_nums.extend(bad)
            if not good:
                # 越界编号（模型引了库里没有的号）不能送去补检索——按描述
                # 随便搜一篇回来，就等于把「模型编的编号」洗成「看起来合规的
                # 引用」，比留空更糟。这里留一个显式待办，交给人处理。
                return f"[TODOFIX: 此处原引用编号 {'/'.join(map(str, bad))} 不在文献库内，请人工确认该引哪一条]"
            marks = [refs.inline(style, r["num"], r) for r in good]
            if style in ("ieee", "gb7714"):
                # 数字制可直接合并成一个方括号 [1, 3]
                out = "[" + ", ".join(m.strip("[]") for m in marks) + "]"
            else:
                # 著者-年制每处都自带圆括号，合并时要剥掉内层括号
                out = "(" + "; ".join(m.strip("()") for m in marks) + ")"
            if bad:
                out += f" [TODOFIX: 原引用编号 {'/'.join(map(str, bad))} 不在文献库内]"
            return out

        sections_out.append({**sec, "text": NUMCITE_RE.sub(_sub, text)})

    # 2) 残余 NEEDCITE：真正缺来源的位置，走完整检索链
    for sec in sections_out:
        for m in NEEDCITE_RE.finditer(sec.get("text") or ""):
            d = _norm_ws(m.group(1))
            if d and d not in need_cites:
                need_cites.append(d)
    if need_cites:
        placeholder_sections = [{**s, "text": NEEDCITE_RE.sub(
            lambda m: f"[CITE: {_norm_ws(m.group(1))}]", s.get("text") or "")}
            for s in sections_out]
        try:
            sub = refs.assemble(cfg, placeholder_sections,
                                lambda system, user: _call(job.get("llm") or {}, system, user,
                                                           temperature=0.2))
        except Exception:
            sub = None
        if sub:
            sections_out = sub["sections"]
            # 补检索回来的记录追加进库，编号接在已有编号之后。
            # 注意 `entries` 存的是**已排版的引文字符串**，记录本身在 by_num 里，
            # 所以查重必须比 by_num，不能拿字符串当记录用。
            known = {(r.get("doi") or "").lower() for r in by_num.values()}
            added = 0
            for it in sub.get("items") or []:
                rec = it.get("rec")
                if not rec:
                    continue
                d = (rec.get("doi") or "").lower()
                if not d or d in known:
                    continue
                known.add(d)
                rec = dict(rec)
                rec["num"] = len(by_num) + 1
                by_num[rec["num"]] = rec
                added += 1
                items.append({**{k: it.get(k) for k in
                                 ("marker", "status", "reason", "query")},
                              "n": rec["num"], "rec": rec, "from": "needcite"})
            if added:
                _log_safe(job, f"补检索：{len(need_cites)} 处缺来源位置新增 {added} 条记录")
            # 补检索回来的记录也要落进正文：assemble 已把 [CITE: ...] 换成了
            # 它自己的引注，但正文此时还是 [NEEDCITE: ...]，要按**描述文本**
            # 一一对上。不能拿 `marker` 比：assemble 返回的 marker 已被归一化，
            # 且它可能把相近的描述映射到同一条，按序号配对更可靠。
            by_desc = {}
            for it in items:
                if it.get("from") == "needcite" and it.get("rec"):
                    by_desc.setdefault(_norm_ws(it.get("marker") or ""), it["rec"])
            fixed = []
            for sec in sections_out:
                def _sub2(m, _d=by_desc):
                    r = _d.get(_norm_ws(m.group(1)))
                    if not r:
                        return m.group(0)
                    used[r["num"]] = used.get(r["num"], 0) + 1
                    return refs.inline(style, r["num"], r)
                fixed.append({**sec, "text": NEEDCITE_RE.sub(_sub2, sec.get("text") or "")})
            sections_out = fixed

    # 3) 未在正文中出现的库内文献：不放进参考文献表（APA/IEEE 都不列未引文献）
    # `entries` 存的是排版好的字符串，记录本体在 by_num；取错会得到一堆 str。
    cited = [by_num[n] for n in sorted(used) if n in by_num]
    if style in ("ieee", "gb7714"):
        cited.sort(key=lambda r: r["num"])
        lines = [refs.reference(style, r["num"], r) for r in cited]
    else:
        cited.sort(key=lambda r: ((refs._split_name(r["authors"][0])[1]
                                   if r.get("authors") else "zzz").lower(), r.get("year") or 0))
        lines = [refs.reference(style, i, r) for i, r in enumerate(cited, start=1)]

    total_cites = sum(used.values())
    resolved_need = sum(1 for i in items if i["status"] in ("ok", "weak"))
    summary = {
        "style": style,
        "language": cfg.get("language") or "en",
        "mode": "library",
        "library": len((lib or {}).get("entries") or []),
        "markers": total_cites + len(need_cites),
        "attempted": len((lib or {}).get("entries") or []),
        "resolved": total_cites + resolved_need,
        "ok": total_cites + resolved_need,
        "weak": 0,
        "unresolved": max(0, len(need_cites) - resolved_need),
        "network_down": sum(1 for i in items if i["status"] == "network-down"),
        "unique": len(cited),
        "with_doi": sum(1 for r in cited if r.get("doi")),
        "truncated": 0,
        "max_reuse": max(used.values()) if used else 0,
        "bad_nums": sorted(set(bad_nums)),
        "library_unused": len((lib or {}).get("entries") or []) - len(cited),
    }
    return {"sections": sections_out, "entries": lines, "items": items,
            "summary": summary, "lib_entries": cited, "lib_refs": by_num,
            "usage": used}


def _step_refs(job: dict, llm_cfg: dict) -> None:
    """文献装配：把 `[CITE: ...]` 换成 OpenAlex 可核实记录（不编造）。

    每次都从「未装配的原始草稿」重做，保证本步可重复执行；
    检索不到的位置原样保留占位，并在 06_refs.md 里写明原因。
    """
    cfg = job["cfg"]
    raw = job["data"].get("draft_raw") or []
    if not raw:
        if job.get("draft_sections"):
            job["data"]["draft_raw"] = [dict(s) for s in job["draft_sections"]]
            raw = job["data"]["draft_raw"]
        else:
            raise RuntimeError("尚无草稿内容，无法装配文献；请先重跑「分章成稿」")

    title = job["data"].get("title_en") or "Untitled Manuscript"
    lib = job["data"].get("library") or {}
    has_lib = bool(lib.get("entries")) and any(
        NUMCITE_RE.search(s.get("text") or "") for s in raw)

    if has_lib:
        total = sum(len(NUMCITE_RE.findall(s.get("text") or "")) for s in raw)
        _log(job, f"正文已有 {total} 处编号引用，对照文献库核对（不再检索猜文献）")
        res = _resolve_library(job, raw, lib, cfg)
    else:
        total = sum(len(refs.extract(s.get("text") or "")) for s in raw)
        _log(job, f"待装配引用占位 {total} 处，开始 OpenAlex 检索")
        res = refs.assemble(cfg, raw,
                            lambda system, user: _call(llm_cfg, system, user, temperature=0.2))
    s = res["summary"]

    job["draft_sections"] = [dict(x) for x in res["sections"]]
    job["data"]["references"] = res["entries"]
    job["data"]["refs"] = {
        "summary": s,
        "entries": res["entries"],
        "items": [
            {"n": it["n"], "marker": it["marker"][:120], "status": it["status"],
             "reason": it.get("reason") or "", "query": it.get("query") or "",
             "title": ((it.get("rec") or {}).get("title") or "")[:120],
             "year": (it.get("rec") or {}).get("year"),
             "doi": (it.get("rec") or {}).get("doi") or ""}
            for it in res["items"]
        ],
    }
    job["manuscript"] = _assemble(job, title)
    _write(job, "manuscript.md", job["manuscript"])
    if s.get("mode") == "library":
        _write(job, STEP_ARTIFACT["refs"], _library_report(cfg, res))
        _log(job, f"文献核对完成：正文引用 {s['resolved']} 处，落到 {s['unique']} 条真实记录；"
                  f"库内共 {s['library']} 条，未被引用 {s['library_unused']} 条")
        if s.get("bad_nums"):
            _log(job, f"⚠ 正文引用了库外编号 {s['bad_nums']}，已替换为待补占位")
    else:
        _write(job, STEP_ARTIFACT["refs"], refs.report_md(cfg, res))
        _log(job, f"文献装配完成：{s['unique']} 条记录（强 {s['ok']} / 弱 {s['weak']}），"
                  f"未解决 {s['unresolved']} 处")
        if s.get("network_down"):
            _log(job, f"网络不可达：{s['network_down']} 处检索已跳过；"
                      "检查网络（api.openalex.org / api.crossref.org）后可单独重跑本步补上，正文占位不会丢")


def _library_report(cfg: dict, res: dict) -> str:
    """文献库模式的 06_refs.md：列出库里哪些被引、哪些没用上、哪些编号越界。"""
    s = res["summary"]
    style_label = {"ieee": "IEEE", "apa": "APA 7th", "chicago": "Chicago author-date",
                   "gb7714": "GB/T 7714-2015"}.get(s["style"], s["style"])
    out = [
        "# 第 6 步 · 文献核对（文献库模式）\n",
        f"引用体系：{style_label} ｜ 文献库 {s['library']} 条 ｜ 正文引用 {s['resolved']} 处 "
        f"｜ 参考文献表 {s['unique']} 条 ｜ 未被引用 {s['library_unused']} 条\n",
        "> 本篇采用「先建库、再写作」：文献库在成稿前一次性检索建立（含 DOI），"
        "正文只能引用库内编号。因此参考文献表中每一条都真实存在，且确实被正文引用过。\n",
    ]
    if s.get("bad_nums"):
        out.append(f"> ⚠ 正文出现了库外编号 {s['bad_nums']}（已替换为 `[NEEDCITE: ...]`）。"
                   "这说明模型没有严格遵守白名单，请检查这些位置。\n")
    out += ["## 被引用的文献", "", "| 编号 | 著录 | DOI | 正文引用次数 |",
            "| --- | --- | --- | --- |"]
    cited = res.get("lib_entries") or []
    counts = res.get("usage") or {}
    for e in cited:
        au = refs._short_authors(e)
        t = (e.get("title") or "").replace("|", "／")[:80]
        out.append(f"| {e.get('num')} | {au} ({e.get('year')}). {t} | "
                   f"{e.get('doi') or '—'} | {counts.get(e.get('num'), 0)} |")
    out += ["", "## 参考文献表", ""]
    out.extend(res.get("entries") or ["_无_"])
    out += ["", "## 边界说明", "",
            "- 文献库来自 OpenAlex / Crossref，只收期刊、图书、会议等正式出版物，仓储与预印本已剔除。",
            "- 编号制（APA/IEEE 著者-年制）下每处 `[n]` 都指向库内具体一条记录，不存在「凭关键字猜一篇」的环节。",
            "- 库内但未被引用的文献不列入参考文献表（符合 APA 与 IEEE 的要求）。",
            "- 仍需你确认：每条文献是否**真的**支持正文里那句话。系统只保证文献真实存在且主题相关。"]
    return "\n".join(out) + "\n"


_TBL_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TBL_CAP_RE = re.compile(r"\*\*\s*Table\s+(\d+)[.．\s:：]", re.I)
_FIG_CAP_RE = re.compile(r"\*\*\s*Figure\s+(\d+)[.．\s:：]", re.I)
_TBL_REF_RE = re.compile(r"(?<![A-Za-z0-9_-])Table\s+(\d+)")
_FIG_REF_RE = re.compile(r"(?<![A-Za-z0-9_-])Figure\s+(\d+)")


def _assets_audit(man: str) -> dict:
    """核对「正文提到的表/图」与「稿子里真实存在的表/图」。

    过去只查章节与 TBD，结果正文写着 Table 3、Figure 2 而稿子里根本没有，
    直到导出到 Word 才发现。这里把缺失变成可报告项。
    """
    text = str(man or "")
    rows = 0
    blocks = 0
    prev_row = False
    for line in text.splitlines():
        is_row = bool(_TBL_ROW_RE.match(line))
        if is_row:
            rows += 1
            if not prev_row:
                blocks += 1
        prev_row = is_row

    t_caps = {int(x) for x in _TBL_CAP_RE.findall(text)}
    f_caps = {int(x) for x in _FIG_CAP_RE.findall(text)}
    t_refs = {int(x) for x in _TBL_REF_RE.findall(text)}
    f_refs = {int(x) for x in _FIG_REF_RE.findall(text)}
    # 编号跨节复用会让 Word 里出现两张 Table 1，属于硬伤，单独报出来
    t_all = [int(x) for x in _TBL_CAP_RE.findall(text)]
    f_all = [int(x) for x in _FIG_CAP_RE.findall(text)]
    return {
        "table_blocks": blocks,
        "table_rows": rows,
        "tables": sorted(t_caps),
        "figures": sorted(f_caps),
        "table_dup": sorted({n for n in t_all if t_all.count(n) > 1}),
        "figure_dup": sorted({n for n in f_all if f_all.count(n) > 1}),
        "table_missing": sorted(t_refs - t_caps),
        "figure_missing": sorted(f_refs - f_caps),
    }


def _step_check(job: dict, llm_cfg: dict) -> None:
    """成稿后自检：复用 skill 原生词面检测 + 结构检查，给出可执行的待办清单。

    只读调用 engine（内部再调 skill 的 score.py / check_structure.py），
    不修改规则库，也不改写正文——发现的问题如实列出，不自动"美化"掉。
    """
    cfg = job["cfg"]
    man = job.get("manuscript") or ""
    if not man.strip():
        raise RuntimeError("尚无成稿内容，无法自检；请先重跑「分章成稿」")

    res = engine.lexical_review(ingest.normalize_for_rules(man), cfg["track"], cfg["genre"])
    defects = res.get("defects") or []
    tbd, cite = _body_counts(job)
    missing = res.get("missing") or []
    q = res.get("quality") or {}
    applicable = res.get("applicable_rules", 0)
    manual = res.get("manual_only", 0)
    stats = {
        "hits": res.get("defect_count", 0),
        "must": res.get("must_count", 0),
        "should": res.get("should_count", 0),
        "nice": res.get("nice_count", 0),
        "missing": missing,
        "tbd": tbd,
        "cite": cite,
        "words": res.get("words", 0),
        "applicable": applicable,
        # 按「适用规则 - 需人工」算自动覆盖面，避免与 auto_checked（含通用检测器）口径打架
        "auto": max(applicable - manual, 0),
        "manual": manual,
        "quality": q,
    }
    audit = _assets_audit(man)
    stats["assets"] = audit
    if audit["table_missing"] or audit["figure_missing"]:
        _log(job, "图表引用不一致：缺 "
             + "、".join([f"Table {n}" for n in audit["table_missing"]]
                        + [f"Figure {n}" for n in audit["figure_missing"]]))
    else:
        _log(job, f"图表一致：{len(audit['tables'])} 表 / {len(audit['figures'])} 图，"
                  f"{audit['table_rows']} 行表格")
    if audit["table_dup"] or audit["figure_dup"]:
        _log(job, "图表编号复用："
             + "、".join([f"Table {n}" for n in audit["table_dup"]]
                        + [f"Figure {n}" for n in audit["figure_dup"]])
             + " 出现了多次标题（导出后会重号）")

    rs = (job["data"].get("refs") or {}).get("summary") or {}
    if rs:
        stats["refs_total"] = rs.get("unique", 0)
        stats["refs_ok"] = rs.get("ok", 0)
        stats["refs_weak"] = rs.get("weak", 0)
        stats["refs_unresolved"] = rs.get("unresolved", 0)
        stats["refs_doi"] = rs.get("with_doi", 0)
    # 可选：大模型全文复核 must 级词面命中（40 篇实测：脚本 must 精度约 34%，复核后真缺陷全保留）
    recheck = None
    if cfg.get("recheck") and (llm_cfg or {}).get("api_key"):
        try:
            recheck = llm.recheck_lexical(
                man, cfg["track"], defects, llm_cfg["api_key"],
                base_url=llm_cfg.get("base_url"), model=llm_cfg.get("model"),
                votes=llm.RECHECK_VOTES, severities=("must",))
            rc = recheck.get("summary") or {}
            stats["recheck"] = rc
            stats["must_confirmed"] = rc.get("confirmed", 0)
            _log(job, f"复核：must {rc.get('checked', 0)} 条 → 确认 {rc.get('confirmed', 0)}／"
                      f"不适用 {rc.get('not_applicable', 0)}／已满足 {rc.get('passed', 0)}／"
                      f"待人工 {rc.get('review', 0)}")
        except Exception as e:
            recheck = None
            _log(job, f"复核未执行（{type(e).__name__}），沿用脚本结果")
    elif cfg.get("recheck"):
        _log(job, "复核已开启但未配置 API Key，跳过")
    job["data"]["selfcheck"] = stats
    _log(job, f"自检：词面命中 {stats['hits']} 条（硬伤 {stats['must']}）｜TBD {tbd} 处｜CITE {cite} 处")

    def badge(ok: bool) -> str:
        return "有" if ok else "**缺**"

    md = [
        "# 第 7 步 · 自检与体检\n",
        f"检测基线：{engine.TRACK_LABELS.get(cfg['track'], cfg['track'])} ｜ 体裁 "
        f"{engine.GENRE_LABELS.get(cfg['genre'], cfg['genre'])} ｜ "
        f"词数 {stats['words']} ｜ 适用规则 {stats['applicable']} 条（自动 {stats['auto']} / 需人工 {stats['manual']}）\n",
        "## 结构自检\n",
    ]
    req = res.get("required") or []
    secs = res.get("sections") or {}
    md.append("\n".join(f"- {s}：{badge(bool(secs.get(s)))}" for s in req) or "_无必需章节定义_")
    if res.get("sections_extended"):
        md.append("\n_其中 " + "、".join(res["sections_extended"]) + " 依据中文小标题补充识别。_")
    md.append("\n## 图表一致性\n")
    md.append(f"- 稿内表格：{len(audit['tables'])} 张（共 {audit['table_rows']} 行）"
              + (f"：{'、'.join('Table ' + str(n) for n in audit['tables'])}" if audit['tables'] else ""))
    md.append(f"- 稿内图占位：{len(audit['figures'])} 个"
              + (f"：{'、'.join('Figure ' + str(n) for n in audit['figures'])}" if audit['figures'] else ""))
    if audit["table_missing"]:
        md.append("- **正文引用了不存在的表（硬伤）**："
                  + "、".join("Table " + str(n) for n in audit["table_missing"])
                  + "。请重跑「分章成稿」补出表格，或删掉这些引用。")
    if audit["figure_missing"]:
        md.append("- **正文引用了不存在的图（硬伤）**："
                  + "、".join("Figure " + str(n) for n in audit["figure_missing"])
                  + "。图占位块应在所属章节内，请重跑「分章成稿」。")
    if audit["table_dup"]:
        md.append("- **表编号重复（硬伤）**："
                  + "、".join("Table " + str(n) for n in audit["table_dup"])
                  + " 的标题出现了不止一次，导出后 Word 里会重号。请删掉重复的标题块，保留一张表。")
    if audit["figure_dup"]:
        md.append("- **图编号重复（硬伤）**："
                  + "、".join("Figure " + str(n) for n in audit["figure_dup"])
                  + " 的占位块出现了不止一次，请只保留一处。")
    if not audit["table_missing"] and not audit["figure_missing"]:
        md.append("- 正文引用与稿内表/图编号一致。")

    md.append("\n## 通用质量\n")
    md.append(f"- 研究缺口（gap）句：{badge(bool(q.get('gap')))}")
    md.append(f"- 贡献声明：{badge(bool(q.get('contrib')))}")
    md.append(f"- 局限性：{badge(bool(q.get('limitation')))}")
    if "ablation" in q:
        md.append(f"- 消融/对照实验：{badge(bool(q.get('ablation')))}")

    md.append("\n## 词面检测\n")
    md.append("| 命中 | 硬伤 must | 建议 should | 可选 nice |")
    md.append("| --- | --- | --- | --- |")
    md.append(f"| {stats['hits']} | {stats['must']} | {stats['should']} | {stats['nice']} |")

    rc_map = {}
    rc_label = {"confirmed": "确认缺陷", "not_applicable": "不适用（已排除）",
                "passed": "已满足（已排除）", "review": "待人工"}
    if recheck:
        rc_map = {it["id"]: it["recheck"] for it in recheck.get("items") or []}
        rs_ = stats["recheck"]
        md.append(f"\n**大模型全文复核（{recheck.get('votes')} 票多数）**：must {rs_.get('checked', 0)} 条 → "
                  f"确认 {rs_.get('confirmed', 0)} ｜ 不适用 {rs_.get('not_applicable', 0)} ｜ "
                  f"已满足 {rs_.get('passed', 0)} ｜ 待人工 {rs_.get('review', 0)}"
                  f"（调用 {recheck.get('calls', 0)} 次）")

    md.append("\n## 缺陷清单（按严重度）\n")
    if defects:
        order = {"must": 0, "should": 1, "nice": 2}
        if rc_map:
            md.append("| 规则 | 级别 | 复核 | 为什么命中 | 改法 |")
            md.append("| --- | --- | --- | --- | --- |")
        else:
            md.append("| 规则 | 级别 | 为什么命中 | 改法 |")
            md.append("| --- | --- | --- | --- |")
        for d in sorted(defects, key=lambda x: order.get(x.get("severity"), 3)):
            why = (d.get("reason") or d.get("evidence") or "").replace("|", "／").replace("\n", " ")[:120]
            fix = (d.get("fix") or "").replace("|", "／").replace("\n", " ")[:120]
            if rc_map:
                r = rc_map.get(d.get("id"))
                tag = rc_label.get(r["final"], r["final"]) if r else "未复核"
                md.append(f"| {d.get('id','')} | {d.get('severity','should')} | {tag} | {why} | {fix} |")
            else:
                md.append(f"| {d.get('id','')} | {d.get('severity','should')} | {why} | {fix} |")
    else:
        md.append("_词面可判定的规则全部通过。这不等于全文合格——剩下 "
                  f"{stats['manual']} 条需人工/大模型判读，建议交回「投稿前审查」做深度判读。_")

    if rs:
        md.append("\n## 文献装配\n")
        md.append(f"- 已装配 {stats.get('refs_total', 0)} 条真实记录"
                  f"（强匹配 {stats.get('refs_ok', 0)} / 弱匹配 {stats.get('refs_weak', 0)}），"
                  f"其中含 DOI {stats.get('refs_doi', 0)} 条")
        md.append(f"- 未解决 {stats.get('refs_unresolved', 0)} 处（正文原样保留 `[CITE: ...]`）")
        md.append("- 逐条对照见 `06_refs.md`。弱匹配表示标题没有同时命中多个核心术语，"
                  "引用前请打开 DOI 核对是否确实是你要引的那篇。")

    # 引用格式对账：skill 的 CIT 族 16 条规则在我这体裁（quant）下全部不适用，
    # 且只有 4 条带检测器、都不含 APA，所以按 citation-*.md 自己查一遍。
    cite_must = 0
    try:
        cf = cite_check.check(man, cfg.get("citation") or "apa", cfg.get("language") or "en")
        md.append("\n## 引用格式\n")
        md.append(cite_check.report_md(cf))
        cite_must = sum(1 for f in cf.get("findings") or [] if f["level"] == "must")
    except Exception as e:
        md.append(f"\n## 引用格式\n_格式对账未执行（{type(e).__name__}）_")

    prof = (job.get("data") or {}).get("dataset")
    gap = dataset.gap_report(prof) if prof else None
    if gap and gap["items"]:
        md.append("\n## 数据体检\n")
        md.append(dataset.gap_md(gap))
        md.append("\n_体检只判断「按现有数据哪些分析做不了」：缺列要另找数据源，"
                  "期数与样本量不足只能改设计。本系统不插补、不模拟，"
                  "`[TBD: ...]` 仍须你用真实数据填。_")

    if cfg.get("data") in ("find", "demo"):
        d = job.setdefault("data", {})
        if not d.get("sources_meta"):
            # 单步重跑自检、或第 3 步被跳过时补一次（有缓存优先用缓存）
            res = _sources_for(job)
            d["sources"] = res.get("items") or []
            d["sources_meta"] = {k: res.get(k) for k in ("terms", "notes", "gap_note", "cached")}
        src = d.get("sources") or []
        meta = d.get("sources_meta") or {}
        md.append("\n## 可用的数据源线索\n")
        if src:
            md.append("按题目与体检阻断项检索到的公开来源，**只给线索、不含任何数值**；"
                      "数字请自行取回、核对口径后上传。完整取法与引用格式见 `03b_sources.md`。\n")
            for it in src[:8]:
                md.append(f"- **{it.get('name')}**（{it.get('kind')}／{it.get('access')}）  \n"
                          f"  {it.get('url')}")
            if meta.get("terms"):
                md.append("\n_检索式：" + "、".join(f"`{t}`" for t in meta["terms"][:2]) + "_")
        else:
            md.append("本次未取得检索结果："
                      + ("；".join(meta.get("notes") or []) or "网络不可用")
                      + "。可先上传数据表结构后重试（有列名才能按缺的变量定向检索），"
                        "或按 `03b_sources.md` 的内置入口手工检索。")
        # 代下载结果（白名单公开源自动落盘）
        dl = d.get("downloads") or {}
        if dl.get("downloaded"):
            md.append("\n已代下载以下白名单公开源到 `_sources/`（**未解析、未核对口径**）：")
            for x in dl["downloaded"][:8]:
                md.append(f"- {x.get('name')} → `{x.get('file')}`")
            md.append("_请核对单位、样本期与统计口径后再上传；口径不一致的数据拼进同一张表比留空更危险。_")

    md.append("\n## 投稿前必须处理\n")
    todo = []
    if missing:
        todo.append(f"补章节标题或正文：{'、'.join(missing)}（规则库按章节定位检查，缺标题会被判缺章）")
    if tbd:
        todo.append(f"用真实数据替换 `[TBD: ...]` 占位，共 {tbd} 处")
    if gap:
        bad = [i for i in gap["items"] if i["status"] == "risk"]
        if bad:
            todo.append("先解决数据体检的 "
                        + f"{len(bad)} 项阻断（{'、'.join(i['label'] for i in bad[:4])}）："
                        + "缺列另找数据源，样本期/样本量不足须改设计，见「数据体检」")
        note = [i for i in gap["items"] if i["status"] == "warn"]
        if note:
            todo.append(f"复核数据体检的 {len(note)} 项注意项，并在方法里写明相应处理")
    if cfg.get("data") == "find":
        todo.append("按 `03b_sources.md` 的线索取数：已代下载的公开源文件也要逐条核对单位、样本期与"
                    "统计口径后再上传，并把数据状态改为「部分数据」或「已有真实数据」——"
                    "系统代下载的是**未经核对**的原始文件，不解析、不保证口径一致")
    if cfg.get("data") == "demo":
        todo.append("演示稿 demo_preview.md 里的模拟值仅供排版预览，不可投稿；"
                    "正式成稿请用 manuscript.md 补入真实数据")
    if cite_must:
        todo.append(f"修 {cite_must} 处引用格式硬伤（卷期、DOI、作者名、来源类型、双向对应），"
                    "清单见「引用格式」小节")
    if cite:
        todo.append(f"剩下 {cite} 处 `[CITE: ...]` 未能自动装配，需人工补一条可核实文献"
                    "（或改写该处描述后重跑「文献装配」）")
    weak = stats.get("refs_weak", 0)
    if weak:
        todo.append(f"核对 {weak} 条弱匹配文献的 DOI，确认内容确实支撑该处论点")
    if recheck:
        rs_ = stats["recheck"]
        if rs_.get("confirmed"):
            todo.append(f"先处理复核确认的 {rs_['confirmed']} 条硬伤（会被直接拒稿的那类）")
        if rs_.get("review"):
            todo.append(f"人工判定 {rs_['review']} 条复核票数不过半的硬伤")
    elif stats["must"]:
        todo.append(f"先处理 {stats['must']} 条硬伤（会被直接拒稿的那类；"
                    "脚本 must 命中实测约 1/3 为真，可开启「大模型复核」过滤误报）")
    if cfg["language"] == "zh":
        todo.append("中文稿须按目标刊要求补政策建议/研究局限等国内刊惯例（规则库不含这些）")
    if not todo:
        todo.append("词面与结构层面未发现阻断项；仍建议走「投稿前审查」做深度判读并核对目标刊作者指南")
    md.append("\n".join(f"{i}. {t}" for i, t in enumerate(todo, start=1)))

    md.append("\n## 本次自检的边界\n")
    md.append(f"- 只覆盖可词面自动判定的 {stats['auto']} 条规则；其余 {stats['manual']} 条需大模型对照 signal 判读。")
    md.append("- 自检不判断数据真实性，也不判断装配到的文献是否就是该论点最合适的出处："
              "`[TBD]` 是留给你填数的，弱匹配与 `[CITE]` 是留给你核对的。")
    md.append("- 数据体检只按画像判「结构够不够做实证」，不核对数值真假、不做插补、"
              "不生成模拟值；「查可用数据源」给的是线索，取回后仍须你核对口径再上传。")
    md.append("- 规则库基于国际期刊规范（英文优先），中文期刊惯例不在库内。")
    _write(job, STEP_ARTIFACT["check"], "\n".join(md) + "\n")


def _front_matter(job: dict, title: str) -> str:
    cfg = job["cfg"]
    d = job.get("data", {})
    kw = "、".join(d.get("keywords") or []) if cfg["language"] == "zh" else ", ".join(d.get("keywords") or [])
    lines = [f"# {title}", ""]
    if cfg["language"] == "en":
        if kw:
            lines.append(f"**Keywords:** {kw}")
        lines.append(f"**Target venue:** {cfg['venue'] or 'unspecified'}  ")
        lines.append(f"**Citation style:** {CITATION_LABEL.get(cfg['citation'], cfg['citation'])}  ")
        lines.append(f"**Length target:** {cfg['words']} words (body)")
        lines.append("")
        rs = (d.get("refs") or {}).get("summary") or {}
        if rs.get("unique"):
            lines.append("> ⚠️ **Draft notice.** This manuscript was generated by a rule-driven writing pipeline "
                         "(Academic Writing Skill v1.2.0, 393 rules). Empirical values marked `[TBD: ...]` must be "
                         f"filled in from the author's own data. The {rs['unique']} references were assembled from "
                         f"OpenAlex records and carry a DOI; {rs.get('weak', 0)} of them are weak matches that "
                         f"must be checked before submission, and {rs.get('unresolved', 0)} citation"
                         " positions could not be matched, so they keep an explicit CITE placeholder. "
                         "This is a working draft, not a submission-ready manuscript.")
        else:
            lines.append("> ⚠️ **Draft notice.** This manuscript was generated by a rule-driven writing pipeline "
                         "(Academic Writing Skill v1.2.0, 393 rules). All empirical values marked `[TBD: ...]` must be "
                         "filled in from the author's own data; every CITE placeholder must be replaced with a verified "
                         "source. It is a working draft, not a submission-ready manuscript. The author is responsible "
                         "for data integrity, citation accuracy and journal-specific formatting.")
    else:
        if kw:
            lines.append(f"**关键词：**{kw}")
        lines.append(f"**目标期刊/会议：**{cfg['venue'] or '未指定'}  ")
        lines.append("")
        rs = (d.get("refs") or {}).get("summary") or {}
        if rs.get("unique"):
            lines.append(f"> ⚠️ **草稿声明**：本文由规则驱动的写作流水线生成（Academic Writing Skill v1.2.0，393 条规则）。"
                         f"所有 `[TBD: ...]` 处须由作者用真实数据填入。参考文献 {rs['unique']} 条来自 OpenAlex 真实记录"
                         f"（含 DOI），其中 {rs.get('weak', 0)} 条为弱匹配，引用前须核对；{rs.get('unresolved', 0)} 处"
                         "未能匹配到文献，正文保留 CITE 占位。本文为工作稿，不可直接投稿。")
        else:
            lines.append("> ⚠️ **草稿声明**：本文由规则驱动的写作流水线生成（Academic Writing Skill v1.2.0，393 条规则）。"
                         "所有 `[TBD: ...]` 处须由作者用真实数据填入，CITE 占位须替换为可核实的真实文献。"
                         "规则库基于国际期刊规范，中文期刊的政策建议/研究局限等惯例不在库内，投稿前须按目标刊要求改写。"
                         "本文为工作稿，不可直接投稿。")
    lines.append("")
    return "\n".join(lines)


def _assemble(job: dict, title: str, written_all: bool = True, partial: bool = False) -> str:
    cfg = job["cfg"]
    parts = [_front_matter(job, title)]
    for s in job["draft_sections"]:
        parts.append(_scrub_internal_notes(_strip_fence(s["text"])))
        parts.append("")
    if partial:
        parts.append("<!-- 生成中：尚有章节未写 -->")
    else:
        refs_title = "References" if cfg["language"] == "en" else "参考文献"
        parts.append(f"## {refs_title}")
        parts.append("")
        entries = (job.get("data") or {}).get("references") or []
        if entries:
            # 每条单独成段：Markdown 连续行会被合并成一段，导致参考文献全挤在一起
            for e in entries:
                parts.append(e)
                parts.append("")
        else:
            if cfg["language"] == "en":
                parts.append("_To be assembled from verified OpenAlex records in the reference stage. "
                             "Until then, every CITE placeholder in the text is an explicit to-do._")
            else:
                parts.append("_参考文献在文献装配阶段由 OpenAlex 真实检索记录生成；在此之前，正文中的 "
                             "CITE 占位均为待补项。_")
        parts.append("")
        parts.append("---")
        parts.append("")
        parts.append(_stat_note(job))
    return "\n".join(parts)


def _figure_todos(job: dict) -> list[str]:
    """把每张图的画法要点汇总成稿末待办，而不是塞进正文段落里。"""
    figs = (job.get("data") or {}).get("figures") or []
    lines = []
    for f in figs:
        fid = str(f.get("id") or "").strip()
        if not fid:
            continue
        note = str(f.get("notes") or "").strip()
        if note:
            lines.append(f"- {fid}：{note}")
    return lines


def _stat_note(job: dict) -> str:
    d = job.get("data", {})
    lines = ["### 生成说明（不进正文，导出时可删）", ""]
    lines.append(f"- 题目：{d.get('title_en') or '—'}")
    lines.append(f"- 主线/体裁：{job['cfg']['track']} / {job['cfg']['genre']}")
    lines.append(f"- 数据状态：{DATA_CN.get(job['cfg']['data'], job['cfg']['data'])}")
    if job["cfg"]["data"] == "demo":
        lines.append("- 演示稿：demo_preview.md（模拟值仅排版预览，标注 SIMULATED，不可投稿）")
        dl = d.get("downloads") or {}
        if dl.get("downloaded"):
            lines.append(f"- 已代下载 {len(dl['downloaded'])} 个公开源文件到 _sources/（未解析，请核对口径）")
    prof = d.get("dataset")
    if prof:
        lines.append(f"- 数据文件：{prof.get('filename')} · {prof.get('rows')} 行 × {prof.get('cols')} 列"
                     "（只读结构；变量名已用于正文，数值仍需你填）")
    lines.append(f"- 章节：{len(job.get('draft_sections') or [])} 节")
    todo = sum(s["text"].count("[TBD:") for s in (job.get("draft_sections") or []))
    cite = _body_counts(job)[1]
    lines.append(f"- 待填数值占位 `[TBD: ...]`：{todo} 处")
    s = (d.get("refs") or {}).get("summary") or {}
    if s.get("unique"):
        lines.append(f"- 未解决引用占位（CITE 标记）：{cite} 处")
        lines.append(f"- 文献装配：{s.get('unique')} 条真实记录（强匹配 {s.get('ok', 0)} / "
                     f"弱匹配 {s.get('weak', 0)}），未解决 {s.get('unresolved', 0)} 处；逐条对照见 06_refs.md")
    else:
        lines.append(f"- 待补文献占位（CITE 标记）：{cite} 处（文献装配未产出记录）")
    lines.append("- 自检结果见 07_check.md")
    todos = _figure_todos(job)
    if todos:
        lines.append("- 待补图表（画法与所需数据，不进正文）：")
        lines.extend("  " + t for t in todos)
    return "\n".join(lines)


_STEP_FUNCS = {
    "topic": _step_topic,
    "chosen": _step_chosen,
    "design": _step_design,
    "outline": _step_outline,
    "draft": _step_draft,
    "refs": _step_refs,
    "check": _step_check,
}


# ---------------------------------------------------------------- 任务调度

JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()

# 落盘时剔除的字段：这些不能进 JSON
# - `llm` 里有 api_key，写进磁盘等于把密钥明文落在数据目录，容器卷一被
#   备份/分享就泄露了。重启后用户重跑时前端会重新带上 Key。
# - `cancel` 是运行时开关，复用一个 False 即可。
_EPHEMERAL = ("llm", "cancel")


def _persist(job: dict) -> None:
    """把任务状态写进 `<job_dir>/_state.json`。

    **为什么每个阶段都写**：任务一跑十几分钟、二十几步 LLM 调用。只在结束时
    落盘的话，容器中途被重建就什么都没有。按阶段写，最坏只丢当前阶段的进度，
    前面已完成的产物和状态都能恢复。

    失败一律静默：磁盘满、权限只读都不该让正在跑的任务崩掉——那等于
    「备份失败把主库搞挂」。
    """
    try:
        d = Path(job.get("dir") or (JOB_DIR / job["id"]))
        snap = {k: v for k, v in job.items() if k not in _EPHEMERAL}
        snap["_saved_at"] = time.time()
        text = json.dumps(snap, ensure_ascii=False, default=str)
        tmp = d / "_state.tmp"
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, d / "_state.json")
    except Exception:
        pass


def restore() -> int:
    """启动时把历史任务索引读回内存，返回恢复条数。

    「运行中」的任务会被标成 `interrupted`：进程已经不在了，它不可能真的
    还在跑。留着 `running` 状态会让前端一直转圈等待一个永远不会来的结果。
    用户看到 interrupted 可以直接点重跑。
    """
    n = 0
    if not JOB_DIR.is_dir():
        return 0
    for d in JOB_DIR.iterdir():
        if not d.is_dir():
            continue
        f = d / "_state.json"
        if not f.is_file():
            continue
        try:
            job = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(job, dict) or not job.get("id"):
            continue
        job.pop("_saved_at", None)
        job.setdefault("dir", str(d))
        job["cancel"] = False
        job.pop("llm", None)
        if job.get("status") == "running":
            job["status"] = "interrupted"
            job["error"] = job.get("error") or "服务重启，任务中断，可重跑"
            # 正在跑的那一步也标成中断，否则界面会显示「第 12 步进行中」
            for s in job.get("steps") or []:
                if s.get("status") == "running":
                    s["status"] = "interrupted"
        JOBS[job["id"]] = job
        n += 1
    return n


def _new_job(cfg: dict, llm_cfg: dict) -> dict:
    jid = uuid.uuid4().hex[:12]
    d = JOB_DIR / jid
    d.mkdir(parents=True, exist_ok=True)
    job = {
        "id": jid,
        "dir": str(d),
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cfg": cfg,
        "plan": _plan_sections(cfg),
        "steps": [{"key": k, "title": t, "status": "pending", "seconds": 0,
                   "chars": 0, "note": ""} for k, t in STEPS],
        "status": "running",
        "current": -1,
        "error": "",
        "cancel": False,
        "log": [],
        "artifacts": {},
        "data": {"dataset": dataset.load_profile(cfg.get("dataset_id") or "", JOB_DIR)},
        "draft_sections": [],
        "manuscript": "",
        "llm": llm_cfg,
    }
    return job


def start(cfg: dict, llm_cfg: dict) -> str:
    cfg = normalize_cfg(cfg)
    gate = gate_check(cfg)
    if not gate["ok"]:
        raise ValueError("；".join(gate["fatal"]))
    if not llm_cfg.get("api_key"):
        raise ValueError("未配置 API Key，无法调用模型")

    # 题目是英文刊的题名：含汉字就在开跑前译一次，译不出来就保留原题（第 1 步会按原题体检）
    if has_cjk(cfg["title"]):
        try:
            en = translate_title(cfg["title"], llm_cfg)
        except Exception:
            en = ""
        if en:
            original = cfg["title"]
            cfg["title"] = en
            if cfg["direction"] == original:
                cfg["direction"] = en
            cfg["title_original"] = original

    job = _new_job(cfg, llm_cfg)
    if cfg.get("title_original"):
        _log(job, f"题目已自动译为英文：{cfg['title']}")
    with _LOCK:
        JOBS[job["id"]] = job
    _persist(job)
    t = threading.Thread(target=_run, args=(job, 0), daemon=True)
    t.start()
    return job["id"]


def _run(job: dict, start_index: int) -> None:
    for i in range(start_index, len(job["steps"])):
        step = job["steps"][i]
        if job.get("cancel"):
            job["status"] = "canceled"
            _log(job, "已取消")
            _persist(job)
            return
        job["current"] = i
        step["status"] = "running"
        step["note"] = ""
        t0 = time.time()
        _log(job, f"开始：{step['title']}")
        _persist(job)
        try:
            _STEP_FUNCS[step["key"]](job, job["llm"])
            step["status"] = "done"
            step["seconds"] = round(time.time() - t0, 1)
            art = STEP_ARTIFACT.get(step["key"])
            if art and art in job["artifacts"]:
                step["chars"] = job["artifacts"][art]
            _log(job, f"完成：{step['title']}（{step['seconds']}s）")
        except Exception as e:
            step["status"] = "error"
            step["seconds"] = round(time.time() - t0, 1)
            step["note"] = str(e)[:400]
            job["status"] = "error"
            job["error"] = f"{step['title']}失败：{e}"
            _log(job, job["error"])
            traceback.print_exc()
            _persist(job)
            return
        _persist(job)
    job["status"] = "done"
    job["current"] = len(job["steps"]) - 1
    _log(job, "全部完成")
    _persist(job)


def _dataset_brief(prof: dict | None) -> dict:
    if not prof:
        return {}
    parts = prof.get("parts") or []
    return {
        "id": prof.get("id", ""),
        "filename": prof.get("filename", ""),
        "rows": prof.get("rows", 0),
        "cols": prof.get("cols", 0),
        "kind": prof.get("kind", ""),
        "files": len(parts) or 1,
        "truncated": bool(prof.get("truncated")),
        "layout": (prof.get("structure") or {}).get("layout", ""),
        "suggest": prof.get("suggest") or {},
        "signals": [s.get("key") for s in (prof.get("signals") or [])][:6],
        "variables": [c.get("name") for c in (prof.get("columns") or [])][:40],
    }


def _downloads_brief(r: dict | None) -> dict:
    """把代下载结果裁剪成前端可安全展示的小结构（不含文件内容，只含路径与状态）。"""
    if not r:
        return {}
    return {
        "downloaded": [{"name": d.get("name"), "file": d.get("file"),
                        "bytes": d.get("bytes")} for d in (r.get("downloaded") or [])],
        "skipped": [{"name": s.get("name"), "reason": s.get("reason")}
                    for s in (r.get("skipped") or [])],
        "failed": [{"name": f.get("name"), "reason": f.get("reason")}
                   for f in (r.get("failed") or [])],
        "notes": r.get("notes") or [],
        "outdir": r.get("outdir") or "",
    }


def status(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if not job:
        raise KeyError(job_id)
    # 成稿正文只在「分章成稿」跑完后下发，避免轮询时反复传几十 KB
    draft_done = any(s["key"] == "draft" and s["status"] == "done" for s in job["steps"])
    man = job.get("manuscript") or ""
    tbd, cite = _body_counts(job)
    return {
        "id": job["id"],
        "status": job["status"],
        "current": job["current"],
        "error": job["error"],
        "cfg": job["cfg"],
        "plan": job["plan"],
        "steps": [dict(s) for s in job["steps"]],
        "log": job["log"][-60:],
        "artifacts": dict(job["artifacts"]),
        "manuscript": man if draft_done else "",
        "selfcheck": job.get("data", {}).get("selfcheck") or {},
        "refs": job.get("data", {}).get("refs") or {},
        "dataset": _dataset_brief(job.get("data", {}).get("dataset")),
        "demo_preview": (job.get("data", {}).get("demo_preview") or "") if draft_done else "",
        "downloads": _downloads_brief(job.get("data", {}).get("downloads")),
        "stats": {
            "chars": len(man),
            "sections": len(job.get("draft_sections") or []),
            "tbd": tbd,
            "cite": cite,
            "refs": ((job.get("data", {}).get("refs") or {}).get("summary") or {}).get("unique", 0),
            "hits": (job.get("data", {}).get("selfcheck") or {}).get("hits", 0),
        },
    }


def cancel(job_id: str) -> bool:
    job = JOBS.get(job_id)
    if not job:
        return False
    job["cancel"] = True
    return True


def rerun(job_id: str, step_key: str) -> dict:
    job = JOBS.get(job_id)
    if not job:
        raise KeyError(job_id)
    keys = [s["key"] for s in job["steps"]]
    if step_key not in keys:
        raise ValueError(f"未知步骤：{step_key}")
    if job["status"] == "running":
        raise ValueError("任务正在运行，请先取消")
    # 被系统重启打断的任务可以重跑——这正是 interrupted 存在的意义：
    # 它和 running 的区别就在于「进程已经没了」。若这里也挡住，
    # 云部署用户重启后就再也点不动重跑，只能从头新建任务。
    if job["status"] == "interrupted":
        job["error"] = ""
    idx = keys.index(step_key)
    # 重置该步及其后所有步骤
    for s in job["steps"][idx:]:
        s["status"] = "pending"
        s["seconds"] = 0
        s["chars"] = 0
        s["note"] = ""
    if idx <= keys.index("draft"):
        job["draft_sections"] = []
        job["manuscript"] = ""
        job["data"].pop("draft_raw", None)
        job["data"].pop("refs", None)
        job["data"].pop("references", None)
        job["data"].pop("selfcheck", None)
    job["cancel"] = False
    job["error"] = ""
    job["status"] = "running"
    t = threading.Thread(target=_run, args=(job, idx), daemon=True)
    t.start()
    return {"ok": True, "from": step_key}


def rerun_with_llm(job_id: str, step_key: str, llm_cfg: dict) -> dict:
    """重跑某一步，并补上 LLM 配置。

    **为什么需要这个入口**：任务状态落盘时会剔除 `llm` 字段（里面有 API Key，
    不能写磁盘）。于是服务重启后从磁盘恢复的任务，内存里是**没有** llm 配置
    的——直接调 `rerun()` 会在第一次 LLM 调用处炸掉，报一个看不懂的
    `TypeError: 'NoneType' object is not subscriptable`。
    容器部署下重启是常态，这条路径必须通。
    """
    job = JOBS.get(job_id)
    if not job:
        raise KeyError(job_id)
    job["llm"] = llm_cfg
    return rerun(job_id, step_key)


def artifact(job_id: str, name: str) -> Path:
    job = JOBS.get(job_id)
    if not job:
        raise KeyError(job_id)
    safe = re.sub(r"[^0-9A-Za-z_.\-]", "_", name)
    p = Path(job["dir"]) / safe
    if not p.exists():
        raise FileNotFoundError(name)
    return p
