# -*- coding: utf-8 -*-
"""文献装配：把正文里的 `[CITE: ...]` 占位换成 OpenAlex 可核实记录。

设计原则（与项目铁律一致）：
1. **只认真实记录**：每条引用都来自 OpenAlex 的检索结果，含 DOI、作者、年份、出处。
   检索不到就保留 `[CITE: ...]` 并写明原因，绝不编造作者与年份。
2. **白名单校验**：剔除仓储/预印本、无 DOI、年份异常、类型不符的记录；
   再按「核心术语是否命中标题」打分，命中不足则判为未解决。
3. **可复核**：每条替换都记录「原始占位 → 命中的文献 → DOI → 判定依据」，
   落到 `06_refs.md`，作者可逐条回溯。
4. 只依赖标准库（urllib），与 topic_trend.py 风格一致。

对外主函数：`assemble(cfg, sections, call)`。
"""
from __future__ import annotations

import json
import random
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import litcache

OA = "https://api.openalex.org/works"
CR = "https://api.crossref.org/works"
SELECT = ("id,doi,display_name,publication_year,authorships,biblio,"
          "primary_location,type,cited_by_count")
# 联系方式必须是真的：OpenAlex / Crossref 都按这个地址把请求归入「礼貌池」，
# 假邮箱（example.com）和匿名请求同档，恰是限流最先收紧的那一档。
MAILTO = "sunzhiyao@yuanqiaiot.com"
# 之前 20s 太长了：用户看到的是「卡死」，而快速失败再重试体验更好。
TIMEOUT = 9
UA = f"academic-writing-agent refs/1.2 (mailto:{MAILTO})"

MARKER_RE = re.compile(r"\[CITE:\s*([^\[\]]{2,400}?)\]", re.I)


class SearchDown(RuntimeError):
    """检索源整体不可用（不是限流，也不是「查不到」）。

    单独建类型是为了让装配流程的熔断能可靠识别——早先靠匹配报错文案里的
    「OpenAlex 检索失败」子串，后来文案一改就静默失效了（连续失败时还会
    把几十条检索挨个白等一遍）。用类型判断，文案怎么改都不影响。
    """

# OpenAlex 的 work type：只收正式出版物
ALLOWED_TYPES = {"article", "review", "book-chapter", "book", "proceedings-article", "report"}
# 出处类型：拒仓储/预印本
BAD_SOURCE_TYPES = {"repository"}

STOP = {
    "the", "and", "for", "with", "from", "that", "this", "these", "those", "into",
    "about", "study", "studies", "paper", "evidence", "effect", "effects", "using",
    "based", "between", "among", "their", "there", "which", "have", "has", "been",
    "more", "than", "also", "such", "can", "may", "not", "but", "are", "was", "were",
}

# 跨学科通用的「方法 / 评价」词。它们会出现在几乎任何学科的同名方法论文里，
# 所以不能当作「领域一致」的证据：一篇讲筋膜测量的文章和一篇讲感官评审的
# 文章都会出现 reliability、analysis、assessment。判定领域是否相同时先剔掉这些。
_METHOD_WORDS = {
    "reliability", "validity", "analysis", "analyses", "assessment", "evaluation",
    "method", "methods", "methodology", "measurement", "measure", "measures",
    "framework", "approach", "model", "models", "modelling", "modeling",
    "review", "overview", "survey", "comparison", "comparative", "evidence",
    "empirical", "quantitative", "qualitative", "statistical", "statistics",
    "data", "dataset", "datasets", "sample", "samples", "case", "cases",
    "application", "applications", "practice", "practices", "design", "designs",
    "index", "indices", "coefficient", "score", "scores", "rating", "ratings",
    "inter", "intra", "rater", "raters", "panel", "panels", "expert", "experts",
    "inter-rater", "intra-rater", "inter-rater-reliability",
    "prediction", "estimation", "inference", "learning", "training", "testing",
}


# ---------------------------------------------------------------- 基础工具


def _fetch(url: str, retries: int = 2, timeout: float | None = None) -> dict:
    """通用 JSON 请求。429 / 5xx / 网络错误退避重试。

    429 是限流不是故障：退避重试，别把「暂时没配额」当成「查不到」。
    退避加抖动（jitter）：论文装配是串行连发几十条，固定间隔容易整批
    撞在同一秒，抖动能把请求摊开。
    """
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout or TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 5xx 属于「服务端抽风」，和 429 一样值得重试；其余 4xx 重试也没用
            retryable = e.code == 429 or 500 <= e.code < 600
            if retryable and attempt < retries:
                time.sleep(min(8.0, 1.0 * 2 ** attempt) + random.uniform(0, 0.4))
                continue
            raise
        except Exception:
            if attempt < retries:
                time.sleep(0.8 * (attempt + 1) + random.uniform(0, 0.3))
                continue
            raise
    return {}


def extract(text: str) -> list[str]:
    """按出现顺序取出 `[CITE: ...]` 里的描述文本。"""
    return [re.sub(r"\s+", " ", m.group(1)).strip() for m in MARKER_RE.finditer(text or "")]


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z\-]{3,}", (s or "").lower()) if w not in STOP}


# 只在检索式兜底时剔除的词：描述里常见的虚词与「我要一篇论文」这类元话语，
# 它们出现在检索式里只会把结果带偏。
_QUERY_FILLER = {
    "a", "an", "the", "of", "on", "in", "for", "and", "or", "to", "with", "by",
    "study", "studies", "paper", "article", "review", "reviews", "evidence",
    "documentation", "example", "etc", "such", "as", "some", "any",
    "original", "specific", "applicable", "relevant", "prior",
}

# 描述里常见的动词/形容词。它们出现在标题里的概率极低，更不该被当成
# 「核心术语」——「a prior study **defining** tobacco leaf grade」若把
# defining 当术语，任何标题带 defining 的文章都会得分。
_VERBISH = {
    "defining", "attributing", "limited", "quantifying", "reporting", "comparing",
    "measuring", "assessing", "evaluating", "identifying", "exploring", "examining",
    "reviewing", "proposing", "demonstrating", "establishing", "introducing",
    "applied", "proposed", "reported", "related", "relevant", "necessary",
    "available", "explicit", "systematic", "comprehensive", "recent", "current",
    "widely", "poorly", "rarely", "often", "typically", "commonly",
    "small", "large", "limited-size", "size", "sized", "high", "low", "major",
    "minor", "key", "main", "important", "possible", "potential", "future",
    "limitation", "limitations", "problem", "issue", "issues", "challenge", "gap",
}


def fallback_query(marker: str) -> str:
    """没有模型规划时，把占位描述直接压成检索式。

    这是兜底而不是主路径：描述往往是「a review of X practice or Y overview」，
    压完仍带噪声，但 OpenAlex 的 `search` 是全文/摘要匹配，通常还能召回
    正确方向的文献，再由 `pick()` 用标题术语把关。**空检索式才是真正的失败**。
    """
    words = re.findall(r"[A-Za-z][A-Za-z\-]{1,}", (marker or "").lower())
    keep = [w for w in words if w not in _QUERY_FILLER and len(w) > 1]
    # 去重但保序，最多 8 个词
    seen, out = set(), []
    for w in keep:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return " ".join(out[:8])


def fallback_terms(marker: str) -> list[str]:
    """兜底核心术语：按「学科区分度」而不是长度来挑。

    早先按词长排序，选出的是 overview / formulation 这类**跨学科通用词**，
    于是「tobacco blend formulation overview」的最高分落在
    «Interferon-Based Biopharmaceuticals: Overview»——两个术语全中，
    却和烟草毫无关系。改成：先剔掉方法与评价词，在剩下的领域词里
    按出现顺序取前两个，因为描述通常把最主要的概念写在前面。
    """
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", (marker or "").lower())
             if w not in _QUERY_FILLER and w not in STOP]
    words = [w for w in words if w not in _METHOD_WORDS and w not in _VERBISH]
    seen, out = set(), []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out[:2]


def search(query: str, per_page: int = 8) -> list[dict]:
    """检索文献，返回 **OpenAlex 结构** 的 work 列表。查询词为空返回空。

    三源兜底，全部产出同一套字段，下游 `whitelist_problems` / `pick` /
    `record` 不需要区分来源：

    1. 本地缓存 —— 命中直接返回，毫秒级；
    2. OpenAlex —— 主源，字段最全（有 `cited_by_count` 供打分）；
    3. Crossref —— 兜底，DOI 官方注册机构，稳定性最好。

    只有两者都失败才抛错。OpenAlex 失败但 Crossref 成功时，把 Crossref
    结果**记到 OpenAlex 的缓存键下**：这样在 OpenAlex 恢复之前，同样的
    检索词不必每次先白等一次超时。
    """
    q = (query or "").strip()
    if not q:
        return []

    hit = litcache.get("merged", q, per_page)
    if hit is not None:
        return hit

    oa_err = None
    try:
        res = _search_openalex(q, per_page)
        litcache.put("merged", q, per_page, res)
        return res
    except Exception as e:                       # noqa: BLE001 - 兜底要吞掉任何失败
        oa_err = e

    try:
        res = _search_crossref(q, per_page)
    except Exception as cr_err:                  # noqa: BLE001
        # 两源都挂才是真失败。文案给一条结论 + 两条原因，避免用户看到
        # 两段堆在一起的长报错而不知道该等还是该查网络。
        raise SearchDown(f"文献检索失败（两个数据源均不可用）："
                         f"OpenAlex — {oa_err}；Crossref — {cr_err}")

    litcache.put("merged", q, per_page, res)
    return res


def _search_openalex(query: str, per_page: int) -> list[dict]:
    """OpenAlex 检索。429/5xx 交给 `_fetch` 退避，这里只做一次整体重试。"""
    url = (f"{OA}?search={urllib.parse.quote(query)}&per-page={per_page}"
           f"&select={SELECT}&mailto={MAILTO}")
    for attempt in range(2):
        try:
            return _fetch(url).get("results") or []
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            if attempt == 1:
                raise RuntimeError(f"OpenAlex 检索失败：{e}")
            time.sleep(1.2 + random.uniform(0, 0.4))
    return []


# ---------------------------------------------------------------- Crossref 兜底

# Crossref 的 type → OpenAlex 的 type。只映射到正式出版物；
# 映射表里没有的（component / dataset / peer-review…）保持原样，
# 交给白名单判为「非正式出版物」，绝不放宽。
CR_TYPE = {
    "journal-article": "article",
    "proceedings-article": "proceedings-article",
    "book-chapter": "book-chapter",
    "book-section": "book-chapter",
    "book-part": "book-chapter",
    "book": "book",
    "monograph": "book",
    "edited-book": "book",
    "reference-book": "book",
    "report": "report",
}

CR_SELECT = ("DOI,title,author,issued,container-title,volume,issue,page,"
             "type,publisher,is-referenced-by-count")


def _cr_year(item: dict) -> int | None:
    """`issued.date-parts` 形如 [[2023, 5, 12]]，也见过 [[2023]]、[] 或缺字段。

    优先 issued，没有就退回 published-print / published-online / created，
    再没有就返回 None（交给白名单判年份异常，不猜）。
    """
    for field in ("issued", "published-print", "published-online", "published", "created"):
        parts = ((item.get(field) or {}).get("date-parts") or [[]])
        try:
            y = parts[0][0]
        except (IndexError, TypeError):
            continue
        if isinstance(y, int) and 1000 < y < 2200:
            return y
    return None


def _cr_pages(page: str) -> tuple[str, str]:
    """Crossref 的 `page` 是 "125-137" / "e12345" / "12" / "100-105, 108" 这类。

    只取第一段连续页码；分隔符统一成 `-`（`record()` 会用 en dash 渲染）。
    """
    s = str(page or "").strip()
    if not s:
        return "", ""
    s = s.split(",")[0].strip()
    m = re.match(r"^([A-Za-z]?\d+)\s*[-–—]\s*([A-Za-z]?\d+)$", s)
    if m:
        return m.group(1), m.group(2)
    return s, s


def cr_to_work(item: dict) -> dict:
    """把 Crossref 条目转成 OpenAlex work 结构。

    只填下游真正会用到的字段（见模块顶部 `SELECT`），缺的字段给 None/空，
    让白名单照常判——**不补齐、不猜测**，宁可这条不合格而留空。
    """
    doi = (item.get("DOI") or "").strip()
    titles = item.get("title") or []
    title = (titles[0] if titles else "") or ""
    title = re.sub(r"<[^>]+>", "", title).strip()        # Crossref 标题常带 <i>/<sub>

    authorships = []
    for a in (item.get("author") or []):
        name = " ".join(x for x in (a.get("given") or "", a.get("family") or "") if x).strip()
        if not name:
            name = (a.get("name") or "").strip()          # 机构作者只给 name
        if name:
            authorships.append({"author": {"display_name": name}})

    container = item.get("container-title") or []
    venue = (container[0] if container else "") or ""
    venue = re.sub(r"<[^>]+>", "", venue).strip()

    first, last = _cr_pages(item.get("page"))

    # 没有作者字段的记录，Crossref 是有的（出版商上传元数据时就没给）。
    # 作者是参考文献的必需项，逐条著录一条「无作者」的文献属残次品：
    # 交给白名单被判不合格、留空让作者手补，比硬塞进正文诚实。
    if not authorships:
        return {}

    return {
        "id": f"https://doi.org/{doi}" if doi else "",
        "doi": f"https://doi.org/{doi}" if doi else None,   # OpenAlex 也带前缀，record() 会剥
        "display_name": title,
        "publication_year": _cr_year(item),
        "authorships": authorships,
        "biblio": {
            "volume": (item.get("volume") or "").strip(),
            "issue": (item.get("issue") or "").strip(),
            "first_page": first,
            "last_page": last,
        },
        "primary_location": {
            "source": {
                "display_name": venue or (item.get("publisher") or "").strip(),
                "type": "",                                  # Crossref 不区分期刊/仓储，留空
            }
        },
        "type": CR_TYPE.get((item.get("type") or "").strip().lower(),
                            (item.get("type") or "").strip()),
        # Crossref 不提供引用数。_score 里这一项最多贡献 2 分，
        # 而单个术语命中就是 10 分，置 0 不影响相关性判定。
        "cited_by_count": int(item.get("is-referenced-by-count") or 0),
        "_source": "crossref",
    }


def _search_crossref(query: str, per_page: int) -> list[dict]:
    """Crossref 检索（DOI 官方注册机构，稳定性优于 OpenAlex）。"""
    params = {
        "query": query,
        "rows": max(1, min(int(per_page), 100)),
        "select": CR_SELECT,
        "mailto": MAILTO,
    }
    url = f"{CR}?{urllib.parse.urlencode(params)}"
    data = _fetch(url)
    items = ((data.get("message") or {}).get("items")) or []
    out = []
    for it in items:
        try:
            w = cr_to_work(it)
        except Exception:
            continue                                   # 单条畸形记录不该毁掉整批
        if w:                                          # 空 dict = 作者缺失，已在上游剔除
            out.append(w)
    return out


def whitelist_problems(w: dict) -> list[str]:
    """白名单校验：返回不通过的原因（空列表 = 通过）。"""
    bad = []
    if not (w.get("doi") or "").strip():
        bad.append("无 DOI，无法核实")
    title = (w.get("display_name") or "").strip()
    if len(title) < 12:
        bad.append("标题缺失或过短")
    year = w.get("publication_year")
    now = datetime.now().year
    if not isinstance(year, int) or year < 1950 or year > now + 1:
        bad.append(f"年份异常（{year}）")
    if (w.get("type") or "") not in ALLOWED_TYPES:
        bad.append(f"文献类型 {w.get('type')} 非正式出版物")
    src = ((w.get("primary_location") or {}).get("source") or {})
    if (src.get("type") or "") in BAD_SOURCE_TYPES:
        bad.append("出自仓储/预印本平台")
    return bad


def _score(w: dict, terms: list[str], query: str) -> tuple[float, int, int]:
    """(总分, 术语命中数, 检索词重合数)。

    「术语命中」只认 terms 里那几个核心构念词。检索式里剩下的词（领域词）
    通过 overlap 体现，权重较低——这样「tobacco」这类领域词的命中不会
    被当成核心构念命中，但也不会被完全忽略。
    """
    title = (w.get("display_name") or "").lower()
    hits = 0
    for t in terms or []:
        t = (t or "").strip().lower()
        if t and (t in title or (t + "s") in title):
            hits += 1
    overlap = len(_tokens(query) & _tokens(title))
    cited = int(w.get("cited_by_count") or 0)
    score = hits * 10 + min(overlap, 4) * 2 + min(cited, 200) / 100.0
    return score, hits, overlap


def pick(cands: list[dict], terms: list[str], query: str,
         used: dict[str, int] | None = None) -> tuple[dict | None, dict]:
    """在白名单通过的候选里挑最可能匹配的一条。

    相关性门槛（两把尺子一起用，避免「只命中一个泛词」就被判为匹配）：
    - hit：核心术语是否出现在标题里；
    - ratio：检索词的内容词有多大比例出现在标题里。
    低于门槛一律判未解决——宁可留空，也不塞一条不相干的文献进正文。

    `used` 记录**本篇文章里已经被别的占位用掉**的 DOI 次数。同一篇文献
    在全文中最多复用两次（正常综述引用也会重复），超过就要换一条：
    实测见过一篇关于烟草配方的方法稿，48 个占位全部落到同一篇
    «Metals in Biology» 上——相关性打分是够的，但那不是「装配了文献」，
    而是一条文献撑起了整篇文章。复用到上限的候选降到次选。
    """
    MAX_REUSE = 2
    passed = [(w, whitelist_problems(w)) for w in cands]
    good = [w for w, bad in passed if not bad]
    meta = {"seen": len(cands), "pass": len(good), "weak": False}
    if not good:
        if cands:
            meta["reason"] = "；".join(passed[0][1]) or "候选均未通过白名单"
        else:
            meta["reason"] = "OpenAlex 未检索到记录"
        return None, meta

    used = used or {}

    def _reuse(w: dict) -> int:
        return used.get(w.get("doi") or w.get("id") or "", 0)

    qt = _tokens(query)
    domain = {t for t in qt if t not in _METHOD_WORDS}
    # 排序键最后加 `_reuse` 升序：相关性相同的候选里，优先选没用过的。
    scored = sorted(((_score(w, terms, query), w) for w in good),
                    key=lambda x: (x[0][0], x[0][1], -_reuse(x[1])), reverse=True)
    fresh = [(s, w) for s, w in scored if _reuse(w) < MAX_REUSE]
    meta["reuse_capped"] = len(scored) - len(fresh)
    if fresh:
        scored = fresh
    (sc, hits, overlap), best = scored[0]
    ratio = (overlap / len(qt)) if qt else 0.0
    # 收紧（v1.2.6）：旧规则里 `len(terms) <= 1 and hits == 1` 就算强匹配，
    # 于是「气候金融与非洲 NEET」能判成「青年 NEET 决定因素」的强匹配。
    # 现在要求至少两个核心术语同时命中，且重合率过半，才算强匹配；
    # 宁可判未解决留空，也不塞一条似是而非的文献进正文。
    strong = hits >= 2 and ratio >= 0.6
    ok = (hits >= 2 and ratio >= 0.4) or (hits >= 1 and ratio >= 0.6) or ratio >= 0.85
    # 标题很短时（「Tobacco leaf quality data management system」只有 6 个词），
    # 重合率天然上不去，上面的规则会把它判死。补一条：核心术语命中 + 领域词
    # 也命中，就认为主题对上了——这正是「短标题但确实是这个领域」的情形。
    title_tokens_pre = _tokens(best.get("display_name") or "")
    if not ok and hits >= 1 and domain and (domain & title_tokens_pre) and ratio >= 0.3:
        ok = True
        meta["short_title"] = True
    meta.update({"score": round(sc, 1), "hits": hits, "ratio": round(ratio, 2)})
    # 领域词一致性：术语重合不等于主题相同。检索式里去掉方法词后剩下的
    # 领域词（烟草 / 焊接 / 青少年…）若与标题毫无交集，说明这条文献只是
    # 共用了一个方法词——实测「inter-rater reliability sensory panels」
    # 会把一篇「胸腰筋膜超声测量」判成弱匹配并通过。正文里挂一条主题
    # 不符的引用，比留空更糟，所以这里硬性拦掉。
    if ok and domain:
        title_tokens = _tokens(best.get("display_name") or "")
        if not (domain & title_tokens):
            ok = False
            meta["reason"] = ("检索到候选，但标题与检索式没有一个共同领域词"
                              f"（领域词 {sorted(domain)[:4]}），判为不相关")
    if not ok:
        if not meta.get("reason"):
            meta["reason"] = (f"检索到 {len(good)} 条，但标题与核心术语/检索词的吻合度不足"
                              f"（术语命中 {hits}，检索词重合 {ratio:.0%}），判为不相关")
        meta.setdefault("candidates", [(w.get("display_name") or "")[:90] for w in good[:3]])
        return None, meta
    meta["weak"] = not strong
    return best, meta


# ---------------------------------------------------------------- 记录规范化


# GB/T 7714 文献类型标识（单字母）。默认 [J]：绝大多数是期刊论文。
GB_TYPE_TAG = {"article": "J", "review": "J", "book-chapter": "M", "book": "M",
               "edited-book": "M", "monograph": "M", "proceedings-article": "C",
               "report": "R", "dissertation": "D", "preprint": "Z"}


def _clean_serial(v, kind: str) -> str:
    """卷期字段常原样带着 `Vol.` / `No.` / `Issue` 前缀。

    OpenAlex 的 biblio 有的记录就是 "Vol. 51"，直接照抄会写出
    `Revue économique, Vol. 51(1)` —— APA 7 要求 `51(1)`。这里只剥前缀，不改数值。
    """
    s = str(v or "").strip()
    if not s:
        return ""
    if kind == "volume":
        s = re.sub(r"^(vol\.?|volume)\s*", "", s, flags=re.I)
    else:
        s = re.sub(r"^(no\.?|number|issue)\s*", "", s, flags=re.I)
    return s.strip(" ,;")


# 检索平台把「电子书平台名」放在 source 字段里，它不是刊名也不是出版社。
# 去掉平台后缀后剩下的通常才是出版社（例：Emerald Group Publishing Limited eBooks）。
PLATFORM_TAIL = re.compile(r"\s*[—–-]?\s*(eBooks?|e-books?|CrossRef|PubMed|"
                           r"Semantic Scholar|OpenAlex)\s*$", re.I)


def record(w: dict) -> dict:
    """把 OpenAlex work 收成著录需要的字段。"""
    src = ((w.get("primary_location") or {}).get("source") or {})
    bib = w.get("biblio") or {}
    authors = []
    for a in (w.get("authorships") or []):
        name = ((a.get("author") or {}).get("display_name") or "").strip()
        if name:
            authors.append(name)
    first, last = bib.get("first_page"), bib.get("last_page")
    pages = ""
    if first and last and first != last:
        pages = f"{first}–{last}"
    elif first:
        pages = str(first)
    doi = (w.get("doi") or "").strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I)
    venue = (src.get("display_name") or "").strip()
    if PLATFORM_TAIL.search(venue):
        venue = PLATFORM_TAIL.sub("", venue).strip(" ,")
    vol = _clean_serial(bib.get("volume"), "volume")
    iss = _clean_serial(bib.get("issue"), "issue")
    # 有的记录把期号塞进卷字段（"No. 39"）。剥掉前缀后若卷号不是数字而期号为空，
    # 说明原本就是期号/丛书卷，挪回 issue，免得写出 "vol. No. 39"。
    if vol and not iss and not re.fullmatch(r"[\dIVXivxl]+", vol):
        raw_vol = str(bib.get("volume") or "")
        if re.match(r"^(no\.?|number|issue)\s*\d", raw_vol, re.I):
            iss, vol = _clean_serial(raw_vol, "issue"), ""
    return {
        "id": w.get("id"),
        "title": (w.get("display_name") or "").strip(),
        "year": w.get("publication_year"),
        "authors": authors,
        "venue": venue,
        "venue_type": src.get("type") or "",
        "volume": vol,
        "issue": iss,
        "pages": pages,
        "doi": doi,
        "type": w.get("type") or "",
        "cited": int(w.get("cited_by_count") or 0),
    }


_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def _split_name(full: str) -> tuple[str, str]:
    """把 "Given Family" 拆成 (given, family)。

    中文姓名常常整段是汉字（"任 Xuefeng"、"张伟"），若仍按「最后一段是姓」
    处理，"任 Xuefeng" 会变成 given="任"、family="Xuefeng"，著录里就出现
    ", 任." 这种怪东西。凡含汉字的一段都当作**姓**，剩下的当名。

    纯汉字且无分隔的名字（"任维羡"）无法可靠地判断哪部分是名、哪部分是姓
    （复姓如「欧阳」更难）。这时**整段当姓**：APA 输出 `任维羡.`，
    虽然少了名首字母，但不会把名字拆错，也不会产生 `, 任.` 这种空名。
    """
    parts = [p for p in re.split(r"\s+", (full or "").strip()) if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        only = parts[0]
        if _CJK.search(only):
            # 纯中文名：整段作姓，given 留空，著录走「姓.」形式
            return "", only
        return only, ""
    cjk = [p for p in parts if _CJK.search(p)]
    if len(cjk) == 1:
        family = cjk[0]
        given = " ".join(p for p in parts if p is not family)
        return given, family
    return " ".join(parts[:-1]), parts[-1]


def _initials(given: str) -> str:
    out = []
    for tok in re.split(r"[\s]+", given.replace(".", " ").strip()):
        if not tok:
            continue
        if "-" in tok:
            out.append("-".join(p[0].upper() + "." for p in tok.split("-") if p))
        else:
            out.append(tok[0].upper() + ".")
    return " ".join(out)


def _apa_authors(names: list[str]) -> str:
    items = []
    for nm in names[:20]:
        given, family = _split_name(nm)
        ini = _initials(given)
        if family and ini:
            items.append(f"{family}, {ini}")
        elif family:
            # 纯中文名等无法拆出名的情况：只写姓，别留一个空的名位
            items.append(family)
        elif given:
            items.append(given)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) <= 20:
        return ", ".join(items[:-1]) + ", & " + items[-1]
    return ", ".join(items[:19]) + ", ... " + items[-1]


def _ieee_authors(names: list[str]) -> str:
    items = []
    for nm in names[:6]:
        given, family = _split_name(nm)
        ini = _initials(given)
        items.append((ini + " " + family).strip())
    if not items:
        return ""
    if len(names) > 6:
        return items[0] + " et al."
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return items[0] + " and " + items[1]
    return ", ".join(items[:-1]) + ", and " + items[-1]


def _chicago_authors(names: list[str]) -> str:
    if not names:
        return ""
    given, family = _split_name(names[0])
    first = f"{family}, {given}".strip().rstrip(",")
    rest = []
    for nm in names[1:6]:
        g, f = _split_name(nm)
        rest.append(f"{g} {f}".strip())
    if not rest:
        return first
    if len(names) > 6:
        return first + ", et al."
    if len(rest) == 1:
        return first + ", and " + rest[0]
    return first + ", " + ", ".join(rest[:-1]) + ", and " + rest[-1]


def _gb_authors(names: list[str]) -> str:
    items = []
    for nm in names[:3]:
        given, family = _split_name(nm)
        items.append((family.upper() + " " + _initials(given).replace(".", "").replace(" ", "")).strip())
    if not items:
        return ""
    if len(names) > 3:
        return ", ".join(items) + ", et al"
    return ", ".join(items)


def inline(style: str, num: int, rec: dict) -> str:
    """文内引用标记。数字制返回 [n]，著者-年制返回 (Author, Year)。"""
    if style in ("ieee", "gb7714"):
        return f"[{num}]"
    if rec.get("dataset"):
        nm = rec.get("inline_name") or rec.get("org") or "Data"
        yr = rec.get("year") or "n.d."
        return f"({nm} {yr})" if style == "chicago" else f"({nm}, {yr})"
    given_first = rec["authors"][0] if rec["authors"] else ""
    _, family = _split_name(given_first)
    family = family or "Anon"
    n = len(rec["authors"])
    if style == "apa":
        if n >= 3:
            who = f"{family} et al."
        elif n == 2:
            who = f"{family} & {_split_name(rec['authors'][1])[1]}"
        else:
            who = family
        return f"({who}, {rec['year']})"
    # chicago author-date
    if n >= 3:
        who = f"{family} et al."
    elif n == 2:
        who = f"{family} and {_split_name(rec['authors'][1])[1]}"
    else:
        who = family
    return f"({who} {rec['year']})"


def _clean_title(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip()).rstrip(".")


def _short_authors(rec: dict) -> str:
    names = rec.get("authors") or []
    if not names:
        return "Anon."
    fams = [(_split_name(n)[1] or n) for n in names]
    if len(fams) == 1:
        return fams[0]
    if len(fams) == 2:
        return f"{fams[0]} & {fams[1]}"
    return f"{fams[0]} et al."


def reference(style: str, num: int, rec: dict) -> str:
    """参考文献条目。"""
    # 数据集（World Bank / ILO / 统计局…）：按「机构 + 年份 + 数据集名 + URL」著录，
    # 不能套期刊论文的卷期页模板——它没有卷期。
    if rec.get("dataset"):
        org = rec.get("org") or ""
        title = rec.get("title") or ""
        year = rec.get("year") or "n.d."
        url = rec.get("url") or ""
        if style in ("ieee", "gb7714"):
            tail = f"[Online]. Available: {url}" if url else ""
            return f"[{num}] {org}, {title} [Data set], {year}. {tail}".rstrip()
        if style == "chicago":
            return f"{org}. {year}. {title} [Data set]. {url}".strip()
        return f"{org}. ({year}). {title} [Data set]. {url}".strip()

    title = _clean_title(rec["title"])
    venue = rec["venue"]
    year = rec["year"]
    vol, iss, pp = rec["volume"], rec["issue"], rec["pages"]
    doi = f"https://doi.org/{rec['doi']}" if rec["doi"] else ""

    if style == "ieee":
        auth = _ieee_authors(rec["authors"])
        s = f"[{num}] "
        if auth:
            s += auth + ", "
        if title:
            s += f'"{title}," '
        if venue:
            s += venue
        tail = []
        # 书章 / 专著的卷期是丛书卷，按 IEEE 期刊写法拼会出 "vol. , no. 39" 这类怪串
        book_like = rec.get("type") in ("book-chapter", "book", "report", "dissertation",
                                        "edited-book", "monograph")
        if vol and not book_like:
            tail.append(f"vol. {vol}")
        if iss and not book_like:
            tail.append(f"no. {iss}")
        if pp:
            tail.append(f"pp. {pp}")
        if year:
            tail.append(str(year))
        if doi:
            tail.append(f"doi: {rec['doi']}")
        if tail:
            s += (", " if venue else "") + ", ".join(tail)
        return s.rstrip() + "."

    if style == "gb7714":
        auth = _gb_authors(rec["authors"])
        # 文献类型标识按实际类型给：书章用 [M]、会议用 [C]。
        # 以前无条件写 [J]，等于把所有书章都标成期刊论文（CIT-GBT-001 正是查这个）。
        tag = GB_TYPE_TAG.get(rec.get("type") or "", "J")
        s = f"[{num}] " + (auth + ". " if auth else "") + f"{title}[{tag}]. "
        s += f"{venue}, " if venue else ""
        s += str(year) if year else "n.d."
        if vol:
            s += f", {vol}"
        if iss:
            s += f"({iss})"
        if pp:
            s += f": {pp}"
        return s + "."
    
    if style == "chicago":
        auth = _chicago_authors(rec["authors"])
        s = (auth.rstrip(".") + ". " if auth else "") + f"{year}. "
        s += f'"{title}." ' if title else ""
        book_like = rec.get("type") in ("book-chapter", "book", "report", "dissertation",
                                        "edited-book", "monograph")
        if venue:
            s += venue
            if vol and not book_like:
                s += f" {vol}"
            if iss and not book_like:
                s += f" ({iss})"
            if pp:
                s += f", {pp}" if book_like else f": {pp}"
            s += "."
        if doi:
            s += " " + doi
        return s.strip()

    # APA 7
    auth = _apa_authors(rec["authors"])
    s = (auth + " " if auth else "") + f"({year}). "
    s += f"{title}. " if title else ""
    # 书章 / 专著 / 报告的卷期与期刊语义不同（那是丛书卷），APA 不按期刊写法拼
    book_like = rec.get("type") in ("book-chapter", "book", "report", "dissertation",
                                    "edited-book", "monograph")
    if book_like:
        vol, iss = "", ""
    if venue:
        s += venue
        if vol:
            s += f", {vol}"
        if iss:
            s += f"({iss})"
        if pp:
            s += f", {pp}"
        s += "."
    elif pp:
        s += f"{pp}."
    if doi:
        s += " " + doi
    return s.strip()


# ---------------------------------------------------------------- 引用需求分流
# 实测：30 处占位里约 8 处要的不是「一篇论文」，而是「一份数据」或「点名的那一篇」。
# 一律丢进关键词检索必然配错——要 WDI 的 IT.NET.USER.ZS 指标，会配成一篇
# 讨论 WDI 的俄文文章；点名 Romano–Wolf，会配成另一篇置换检验。
# 所以先分流，再检索。

DATASET_SOURCES = [
    {"pat": r"\bworld bank\b|\bWDI\b|world development indicator",
     "org": "World Bank", "title": "World Development Indicators",
     "base": "https://data.worldbank.org",
     # 两种写法都要认：「…/indicator/IT.NET.USER.ZS」与「indicator IT.NET.USER.ZS」
     "url_pat": r"(?:/indicator/|\bindicator\s+)([A-Z]{2,3}\.[A-Z0-9._]+)"},
    {"pat": r"\bILO\b|\bilostat\b|international labour organization",
     "org": "International Labour Organization", "title": "ILOSTAT",
     "base": "https://ilostat.ilo.org"},
    {"pat": r"\bITU\b|international telecommunication union",
     "org": "International Telecommunication Union", "title": "ITU Statistics",
     "base": "https://www.itu.int/en/ITU-D/Statistics"},
    {"pat": r"\bOECD\b", "org": "OECD", "title": "OECD Data",
     "base": "https://data.oecd.org"},
    {"pat": r"\bIMF\b|international monetary fund",
     "org": "International Monetary Fund", "title": "IMF Data",
     "base": "https://www.imf.org/en/Data"},
    {"pat": r"\bEurostat\b", "org": "Eurostat", "title": "Eurostat Database",
     "base": "https://ec.europa.eu/eurostat"},
    {"pat": r"国家统计局|national bureau of statistics",
     "org": "国家统计局", "title": "国家数据", "base": "https://data.stats.gov.cn"},
    {"pat": r"\bUNCTAD\b", "org": "UNCTAD", "title": "UNCTADstat",
     "base": "https://unctadstat.unctad.org"},
    {"pat": r"penn world table|\bPWT\b",
     "org": "Feenstra, Inklaar & Timmer", "title": "Penn World Table",
     "base": "https://www.rug.nl/ggdc/productivity/pwt"},
]

# 只有 marker 在说「数据/指标/统计/方法学文档」时才按数据源处理，
# 否则 "World Bank (2020) shows that ..." 这种叙述句会被误判成要数据。
DATA_HINT = re.compile(
    r"indicator|\bdata\b|dataset|statistic|estimate|series|database|tabulation|"
    r"documentation|methodolog|manual|handbook|指标|数据|统计|数据库|年鉴", re.I)

# 点名文献：Autor (2003) / Autor and Dorn (2013) / Autor, Levy and Murnane (2003)
# 第 2、3 组也要捕获——无年份时靠「几个点名的姓同时命中」锁定是哪一篇。
NAMED_YEAR = re.compile(
    r"\b([A-Z][A-Za-z\u00C0-\u024F'’\-]{2,20})"
    r"(?:\s*,\s*([A-Z][A-Za-z\u00C0-\u024F'’\-]{2,20}))?"
    r"(?:\s*,?\s+and\s+([A-Z][A-Za-z\u00C0-\u024F'’\-]{2,20}))?"
    r"\s*(?:et\s+al\.)?\s*\((\d{4})\)")
# 点名但没给年份：Autor, Levy and Murnane's …（要求至少两个姓氏，避免把普通名词当人名）
NAMED_PLAIN = re.compile(
    r"\b([A-Z][a-z]{2,20}),\s*([A-Z][a-z]{2,20})\s+and\s+([A-Z][a-z]{2,20})")


def _match_dataset(marker: str) -> dict | None:
    """识别「要一份数据」的需求，直接给数据集引用，不去搜论文。"""
    m = marker or ""
    if not DATA_HINT.search(m):
        return None
    for ds in DATASET_SOURCES:
        if not re.search(ds["pat"], m, re.I):
            continue
        code = ""
        if ds.get("url_pat"):
            mm = re.search(ds["url_pat"], m)
            if mm:
                code = mm.group(1)
        ym = re.search(r"\b(19|20)\d{2}\b", m)
        return {
            "dataset": True,
            "id": "dataset:" + ds["base"] + code,
            "org": ds["org"], "inline_name": ds["org"],
            "title": ds["title"] + (f": {code}" if code else ""),
            "year": int(ym.group(0)) if ym else None,
            "url": ds["base"] + (f"/indicator/{code}" if code else ""),
            "authors": [ds["org"]], "venue": "", "volume": "", "issue": "",
            "pages": "", "doi": "", "type": "dataset", "cited": 0,
        }
    return None


# 复合姓氏（Romano–Wolf / Kim–Lee）：两侧都大写开头才算，避免误伤 cross-country、
# Difference-in-Differences 这类普通复合词。
NAMED_HYPHEN = re.compile(r"\b([A-Z][a-z]{2,20})[–\-]([A-Z][a-z]{2,20})\b")

# 机构名常被当成「姓」：叙述句 "World Bank (2020) shows that…" 会解析出 (Bank, 2020)。
ORG_WORDS = {"bank", "organization", "organisation", "commission", "council",
             "association", "institute", "institution", "bureau", "fund", "office",
             "agency", "ministry", "department", "union", "group", "limited", "inc",
             "statistics", "eurostat", "oecd", "imf", "ilo", "itu", "unesco",
             "european", "national", "international", "world", "committee", "board"}


def _named(marker: str) -> dict | None:
    """marker 里是否点名了具体文献。

    返回 {"surname": 首选检索姓, "names": 全部点到的姓氏, "year": 年份或 None}；
    未点名返回 None。多个姓氏要留着——无年份时靠「几个姓同时命中」来判断是不是那一篇。
    """
    m = marker or ""
    hit = NAMED_HYPHEN.search(m)
    if hit:
        ym = re.search(r"\((\d{4})\)", m[hit.end():hit.end() + 60])
        return {"surname": hit.group(1), "names": [hit.group(1)],
                "year": int(ym.group(1)) if ym else None}
    hit = NAMED_YEAR.search(m)
    if hit:
        names = [g for g in hit.groups()[:3] if g]
        if names and names[0].lower() not in ORG_WORDS:
            return {"surname": names[0], "names": names, "year": int(hit.group(4))}
    hit = NAMED_PLAIN.search(m)
    if hit:
        names = [g for g in hit.groups()[:3] if g]
        if names and names[0].lower() not in ORG_WORDS:
            return {"surname": names[0], "names": names, "year": None}
    return None


def _find_by_author(surname: str, year: int | None, terms: list[str],
                    per_page: int = 8) -> list[dict]:
    """按「作者 + 年份」精确取候选。

    两路，因为同名作者是个真问题：
    1. 作者 ID → 其该年作品。准，但 `/authors?search=Romano` 的首条是
       1949 篇作品的 "M. Romano"，不是 Joseph P. Romano，会挑错人；
    2. 路径 1 落空时，用主题词检索 + 年份过滤，再本地筛「作者列表含该姓」。
    不用 `filter=raw_author_name.search:`——实测它把 "Autor" 匹配到葡语
    "Autor Desconhecido"（未知作者）。
    """
    out: list[dict] = []
    q = urllib.parse.quote(surname)
    au_url = (f"{OA.replace('/works', '/authors')}?search={q}"
              f"&per-page=20&select=id,display_name,works_count&mailto={MAILTO}")
    try:
        found = _fetch(au_url)
        picks = [a for a in (found.get("results") or [])
                 if surname.lower() in (a.get("display_name") or "").lower()]
        picks.sort(key=lambda a: -(a.get("works_count") or 0))
        aid = str((picks[0] or {}).get("id") or "").rstrip("/").split("/")[-1] if picks else ""
        if aid:
            flt = f"author.id:{aid}"
            if year:
                flt += f",publication_year:{year}"
                url = f"{OA}?filter={flt}&per-page={per_page}&select={SELECT}&mailto={MAILTO}"
                if terms:
                    url += "&search=" + urllib.parse.quote(" ".join(str(t) for t in terms[:3]))
            else:
                url = (f"{OA}?filter={flt}&sort=cited_by_count:desc"
                       f"&per-page={max(per_page, 20)}&select={SELECT}&mailto={MAILTO}")
            time.sleep(0.2)
            out = _fetch(url).get("results") or []
    except Exception:
        out = []

    if out or not terms:
        return out

    # 路径 2：主题检索 + 年份，本地按作者筛
    qq = urllib.parse.quote(" ".join(str(t) for t in terms[:3]))
    u = f"{OA}?search={qq}&per-page=25&select={SELECT}&mailto={MAILTO}"
    if year:
        u += f"&filter=publication_year:{year}"
    try:
        time.sleep(0.2)
        cands = _fetch(u).get("results") or []
    except Exception:
        cands = []
    if not cands:
        # 路径 3：OpenAlex 不可用/查不到 → Crossref 按作者 + 主题搜，再本地筛姓。
        # 点名文献不能因为主源故障就判「定位不到」。
        try:
            cr = _search_crossref(f"{surname} {' '.join(str(t) for t in terms[:3])}".strip(), 25)
            if year:
                cr = [w for w in cr if w.get("publication_year") == year] or cr
            cands = cr
        except Exception:
            return []
    return [w for w in cands
            if any(surname.lower() in str((a.get("author") or {}).get("display_name") or "").lower()
                   for a in (w.get("authorships") or []))]


# ---------------------------------------------------------------- 检索词规划


PLAN_SYSTEM = """You convert citation needs into precise English literature search queries.

Rules:
- Output English only, inside the given JSON shape, nothing else.
- 'query' must be 3-7 words of core concepts, no boolean operators, no quotes.
- 'terms' must be 1-3 short English phrases that a relevant paper's TITLE would contain
  (construct names, e.g. "digital financial inclusion", "investment efficiency").
  Avoid generic words such as "study", "evidence", "effect".
- Never invent author names or paper titles."""


def _plan_queries(markers: list[str], call, lang: str = "en") -> dict[int, dict]:
    """一次模型调用，把每条占位翻译成英文检索式 + 核心术语。"""
    if not markers:
        return {}
    lines = [f"{i}. {m}" for i, m in enumerate(markers, start=1)]
    user = (
        "【任务】下面是一篇英文学术稿件中需要补文献的位置。每条是作者写的"
        "「需要什么样的来源」描述（可能是中文）。请为每条设计 OpenAlex 检索方案。\n\n"
        + "\n".join(lines)
        + "\n\n要求：\n"
        "1. query：3-7 个英文词，只放核心概念，不要布尔操作符、不要引号、不要年份。\n"
        "2. terms：1-3 个核心术语，应当是理想文献**标题里会出现**的英文短语"
        "（构念名，如 \"digital financial inclusion\"、\"investment efficiency\"）；"
        "不要用 study/evidence/effect 这类空词。\n"
        "3. 只输出 JSON，不要解释：\n"
        '{"items":[{"n":1,"query":"...","terms":["..."]}]}\n'
    )
    raw = call(PLAN_SYSTEM, user)
    m = re.search(r"\{[\s\S]*\}", raw or "")
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except Exception:
        return {}
    out = {}
    for it in data.get("items") or []:
        try:
            n = int(it.get("n"))
        except (TypeError, ValueError):
            continue
        q = str(it.get("query") or "").strip()
        terms = [str(t).strip() for t in (it.get("terms") or []) if str(t).strip()]
        if q:
            out[n] = {"query": q, "terms": terms[:3]}
    return out


# ---------------------------------------------------------------- 文献库（前置建库）
#
# 为什么要有这一层：旧流程是「先写正文 → 留 [CITE: 描述] → 事后去检索猜该配哪篇」。
# 结构上的毛病是写作时不知道自己能引用什么，于是
#   (a) 描述写成「a review of X practice」这种没法检索的笼统话，命中率极低；
#   (b) 一条文献被反复命中，充当四五个不同位置的出处；
#   (c) 点名文献与原句要求南辕北辙（见 1.2.9 之前的 Akerman 事故）。
#
# 改成「先建库、再写作」：成稿前针对题目与大纲一次检索出 20~50 条真实记录，
# 编号后交给写作者当**可引用白名单**，正文只准标 `[1]`…`[n]`。这样
# 参考文献天然就是真实存在的，事后核对只需检查编号是否越界，而不必再猜。

LIB_MIN = 18          # 少于这个数说明库太薄，正文会大面积无引用可用
LIB_MAX = 48


def probe_queries(title: str, outline: list[str], call) -> list[str]:
    """让模型把题目 + 大纲转成 4~6 条**互不重复**的英文检索式。

    一条检索式只覆盖一个子领域，避免全是同义词改写导致结果高度重叠——
    重叠正是「一条文献撑全篇」的源头。
    """
    heads = "\n".join(f"- {h}" for h in outline if h)[:1600]
    user = (
        f"【论文题目】{title}\n\n【章节标题】\n{heads}\n\n"
        "【任务】为这篇论文设计 4-6 条英文文献检索式，用于建立它的参考文献库。\n"
        "要求：\n"
        "1. 每条检索式覆盖论文的一个不同方面（如：核心构念、方法传统、"
        "该领域经典问题、可类比的其他领域应用、评测标准）。\n"
        "2. 每条 3-7 个英文词，只放名词与名词短语，不要布尔操作符、不要年份、不要引号。\n"
        "3. 必须是真实学术文献标题里会出现的用词（学科术语），不要写成口语问句。\n"
        "4. 不要在两条检索式里重复同样的词组合。\n"
        '只输出 JSON：{"queries":["...","..."]}'
    )
    try:
        raw = call("You design literature search strategies for academic papers. "
                   "You output only JSON.", user) or ""
    except Exception:
        return []
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except Exception:
        return []
    out, seen = [], set()
    for q in data.get("queries") or []:
        q = re.sub(r"\s+", " ", str(q or "")).strip()
        k = q.lower()
        if q and k not in seen and 2 <= len(q.split()) <= 12:
            seen.add(k)
            out.append(q)
    return out[:6]


def build_library(cfg: dict, title: str, outline: list[str], call,
                  per_query: int = 12) -> dict:
    """建立可引用文献库，返回 {entries, by_num, queries, log}。

    entries 是 `record()` 规范化后的记录，`num` 为 1..n 的引用编号。
    同一 DOI 只进库一次（不同检索式命中同一篇是正常现象）。
    """
    queries = probe_queries(title, outline, call)
    if not queries:
        # 模型没给出可用检索式时退回题目本身，宁可库薄也不要空手写作
        queries = [re.sub(r"[^\w\s-]", " ", title).strip()[:120]]
    log, seen, entries = [], {}, []
    for q in queries:
        try:
            cands = search(q, per_page=per_query)
        except Exception as e:                    # noqa: BLE001 - 单条失败不该毁掉整库
            log.append({"query": q, "kept": 0, "error": str(e)[:120]})
            continue
        kept = 0
        for w in cands:
            bad = whitelist_problems(w)
            if bad:
                continue
            rec = record(w)
            key = (rec["doi"] or rec["id"] or rec["title"]).lower()
            if key in seen:
                continue
            seen[key] = True
            rec["num"] = len(entries) + 1
            rec["_query"] = q
            entries.append(rec)
            kept += 1
            if len(entries) >= LIB_MAX:
                break
        log.append({"query": q, "kept": kept})
        if len(entries) >= LIB_MAX:
            break
    by_num = {r["num"]: r for r in entries}
    return {"entries": entries, "by_num": by_num, "queries": log,
            "thin": len(entries) < LIB_MIN}


def library_prompt_block(lib: dict, limit: int = LIB_MAX) -> str:
    """把文献库渲染成写作者能直接用的编号清单。"""
    if not lib or not lib.get("entries"):
        return ""
    lines = [
        "【可引用文献库 — 正文只能引用这里的编号】",
        "下面是本篇论文的真实文献库（已核验 DOI，来自 OpenAlex/Crossref）。",
        "写作时**只能**用 `[n]` 的形式引用这些编号，禁止写作者名、年份或任何库外文献。",
        "每条编号后给出题名，请按题名判断它在哪个句子后引用最合适。",
        "",
    ]
    for r in lib["entries"][:limit]:
        au = _short_authors(r)
        t = (r.get("title") or "")[:150]
        lines.append(f"[{r['num']}] {au} ({r['year']}). {t}")
    lines += [
        "",
        "使用规则：",
        "1. 只在确实需要出处的论断后引用，不要每句都挂引用；每段 0-3 处。",
        "2. 若某个论断在库里找不到合适文献，**不要硬引**——在句末写 "
        "`[NEEDCITE: 需要什么样的来源]`，装配阶段会再检索一次。",
        "3. 引用的文献必须真的支持那句话；宁可少引，不要张冠李戴。",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- 主流程


def assemble(cfg: dict, sections: list[dict], call, *, max_markers: int = 60,
             per_page: int = 8) -> dict:
    """把 sections 里的 `[CITE: ...]` 换成真实文献。

    sections: [{"key","heading","text"}]，不改原对象，返回新文本。
    返回 {sections, entries, items, summary}。
    """
    style = (cfg.get("citation") or "apa").lower()
    lang = cfg.get("language") or "en"

    # 1) 按顺序收集占位（同文本去重，保持首次出现顺序）
    ordered: list[str] = []
    for sec in sections:
        for m in extract(sec.get("text") or ""):
            if m not in ordered:
                ordered.append(m)

    truncated = max(0, len(ordered) - max_markers)
    targets = ordered[:max_markers]

    # 2) 一次性规划检索词
    plan = {}
    if targets:
        try:
            plan = _plan_queries(targets, call)
        except Exception:
            plan = {}

    # 3) 逐条检索 + 白名单 + 匹配
    resolved: dict[str, dict] = {}
    items: list[dict] = []
    cache: dict[str, tuple] = {}
    # 同一篇文献在本篇里被多少个占位命中。用来发现「一条文献撑起全篇」。
    reuse: dict[str, int] = {}
    # 网络熔断：单条失败要等 20s×2 次重试。断网 / OpenAlex 不可达时，
    # 60 条占位会白等 40 分钟才走到「全部失败」。连续 3 条网络错误就停，
    # 剩余的直接标 network-down，装配结果照样产出（占位原样保留）。
    net_fails = 0
    net_down = False
    for i, marker in enumerate(targets, start=1):
        # 分流 1：这是「要一份数据」，不是「要一篇论文」。直接给数据集引用，不检索。
        ds_rec = _match_dataset(marker)
        if ds_rec:
            resolved[marker] = ds_rec
            items.append({"n": i, "marker": marker, "status": "ok", "rec": ds_rec,
                          "reason": "机构数据源：按数据集格式著录，未去检索论文", "query": ""})
            continue
        p = plan.get(i) or {}
        query = p.get("query") or ""
        terms = p.get("terms") or []
        if not query:
            # 规划模型没回（没配 Key、被限流、或返回了非法 JSON）。旧行为是直接
            # 判 no-query 留空，等于整段装配全军覆没。这里退回「把描述本身当
            # 检索式」：去掉冠词/空词后通常仍是可用的英文短语，比什么都不做强。
            query = fallback_query(marker)
            terms = fallback_terms(marker)
        # 分流 2：marker 点名了具体文献 → 按「作者 + 年份」精确取，不用关键词盲搜。
        named = _named(marker)
        if named and not net_down:
            surnames, nyear = named["names"], named["year"]
            try:
                lit = _find_by_author(named["surname"], nyear, terms or [])
                net_fails = 0
            except Exception as e:
                lit = []
                if isinstance(e, SearchDown) and "429" not in str(e):
                    net_fails += 1
                    if net_fails >= 3:
                        net_down = True
            if lit:
                def _hits(w):
                    au = " ".join(str((a.get("author") or {}).get("display_name") or "")
                                  for a in (w.get("authorships") or [])).lower()
                    return sum(1 for n in surnames if n.lower() in au)
                lit.sort(key=lambda w: (-_hits(w), -_score(w, terms, query or marker)[0]))
                rec = record(lit[0])
                resolved[marker] = rec
                _k = rec["doi"] or rec["id"] or rec["title"]
                reuse[_k] = reuse.get(_k, 0) + 1
                got = _hits(lit[0])
                how = (f"点名文献：按作者 {'/'.join(surnames)}"
                       + (f" + {nyear}" if nyear else "（原句未给年份）")
                       + f"锁定，命中 {got}/{len(surnames)} 个点名的姓")
                items.append({"n": i, "marker": marker, "status": "ok" if nyear and got >= 1 else "weak",
                              "rec": rec, "reason": how, "query": query})
                continue
            # 点名了却定位不到：**留空**。以前这里会静默落回关键词检索，
            # 结果把 "Altonji, Elder and Taber (2005)" 配成一篇抗精神病药物研究。
            items.append({"n": i, "marker": marker, "status": "unresolved", "rec": None,
                          "reason": f"点名文献（{'/'.join(surnames)}"
                                    + (f", {nyear}" if nyear else "，原句未给年份")
                                    + "）未能精确定位，已留空——请手工补这一条，不要用相近文献顶替",
                          "query": query})
            continue
        if not query:
            items.append({"n": i, "marker": marker, "status": "no-query", "rec": None,
                          "reason": "未能生成英文检索式"})
            continue
        if net_down:
            items.append({"n": i, "marker": marker, "status": "network-down", "rec": None,
                          "reason": "网络不可用，已跳过（前 3 条检索均失败）", "query": query})
            continue
        try:
            if query in cache:
                cands = cache[query]
            else:
                cands = search(query, per_page=per_page)
                cache[query] = cands
                time.sleep(0.25)          # 轻限速：0.12s≈8 req/s 太贴近 10/s 上限，易 429
            best, meta = pick(cands, terms, query, used=reuse)
            net_fails = 0
        except Exception as e:
            msg = str(e)[:160]
            # 429 是限流不是断网，不参与熔断（否则偶发限流会误判成没网）
            if isinstance(e, SearchDown) and "429" not in msg:
                net_fails += 1
                if net_fails >= 3:
                    net_down = True
            items.append({"n": i, "marker": marker, "status": "error", "rec": None,
                          "reason": msg, "query": query})
            continue
        if best is None:
            items.append({"n": i, "marker": marker, "status": "unresolved", "rec": None,
                          "reason": meta.get("reason") or "无匹配", "query": query,
                          "candidates": meta.get("candidates") or []})
            continue
        rec = record(best)
        resolved[marker] = rec
        _k = rec["doi"] or rec["id"] or rec["title"]
        reuse[_k] = reuse.get(_k, 0) + 1
        weak_notes = []
        if meta.get("weak"):
            weak_notes.append("标题未同时命中多个核心术语")
        if reuse[_k] > 1:
            weak_notes.append(f"该文献本篇已引 {reuse[_k] - 1} 次，请确认这里确实需要重复引用")
        if rec["doi"].lower().startswith("10.2139"):
            weak_notes.append("DOI 指向 SSRN 预印本版本")
        items.append({"n": i, "marker": marker,
                      "status": "weak" if weak_notes else "ok",
                      "rec": rec, "reason": "；".join(weak_notes), "query": query,
                      "score": meta.get("score"), "hits": meta.get("hits"),
                      "ratio": meta.get("ratio")})

    # 4) 编号（数字制按首次出现；著者-年制只需去重）
    numbers: dict[str, int] = {}      # doi -> num
    entries: list[dict] = []
    for it in items:
        rec = it.get("rec")
        if not rec:
            continue
        key = rec["doi"] or rec["id"] or rec["title"]
        if key in numbers:
            it["num"] = numbers[key]
            continue
        numbers[key] = len(entries) + 1
        it["num"] = numbers[key]
        rec["num"] = numbers[key]
        entries.append(rec)

    # 5) 替换正文
    new_sections = []
    for sec in sections:
        text = sec.get("text") or ""

        def _sub(m):
            marker = re.sub(r"\s+", " ", m.group(1)).strip()
            rec = resolved.get(marker)
            if not rec:
                return m.group(0)
            num = numbers.get(rec["doi"] or rec["id"] or rec["title"], 1)
            return inline(style, num, rec)

        new_sections.append({**sec, "text": MARKER_RE.sub(_sub, text)})

    # 6) 参考文献表：数字制按编号，著者-年制按字母序
    if style in ("ieee", "gb7714"):
        ordered_entries = sorted(entries, key=lambda r: r["num"])
        lines = [reference(style, r["num"], r) for r in ordered_entries]
    else:
        ordered_entries = sorted(
            entries,
            key=lambda r: ((_split_name(r["authors"][0])[1] if r["authors"] else "zzz").lower(),
                           r["year"] or 0))
        lines = [reference(style, i, r) for i, r in enumerate(ordered_entries, start=1)]

    ok = sum(1 for i in items if i["status"] == "ok")
    weak = sum(1 for i in items if i["status"] == "weak")
    down = sum(1 for i in items if i["status"] == "network-down")
    unresolved = sum(1 for i in items if i["status"] in
                     ("unresolved", "no-query", "error", "network-down"))
    summary = {
        "style": style,
        "language": lang,
        "markers": len(ordered),
        "attempted": len(targets),
        "resolved": ok + weak,
        "ok": ok,
        "weak": weak,
        "unresolved": unresolved + truncated,
        "network_down": down,
        "unique": len(entries),
        "with_doi": sum(1 for r in entries if r["doi"]),
        "truncated": truncated,
        # 复用最高的那条的占用次数：>2 说明这篇稿子的引用绝大多数压在少数几篇上，
        # 报告要明说，不能让它看起来像「装配成功」。
        "max_reuse": max(reuse.values()) if reuse else 0,
    }
    return {"sections": new_sections, "entries": lines, "items": items, "summary": summary}


def report_md(cfg: dict, res: dict) -> str:
    """生成 06_refs.md 的内容：逐条对照 + 参考文献表 + 边界说明。"""
    s = res["summary"]
    style_label = {"ieee": "IEEE", "apa": "APA 7th", "chicago": "Chicago author-date",
                   "gb7714": "GB/T 7714-2015"}.get(s["style"], s["style"])
    out = [
        "# 第 6 步 · 文献装配\n",
        f"引用体系：{style_label} ｜ 正文占位 {s['markers']} 处 ｜ 已装配 {s['resolved']} 处"
        f"（强匹配 {s['ok']} / 弱匹配 {s['weak']}）｜ 未解决 {s['unresolved']} 处 ｜ 去重后 {s['unique']} 条\n",
        "> 所有条目均来自 OpenAlex 检索结果，含 DOI，可点开核对。检索不到的位置保留 `[CITE: ...]`，"
        "没有编造任何作者或年份。\n",
        "## 逐条对照\n",
        "| # | 原文需要什么来源 | 检索式 | 命中文献 | DOI | 判定 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if s.get("network_down"):
        out.insert(3,
                   f"> ⚠ 有 {s['network_down']} 处因**网络不可达**没有检索（连续 3 条失败后已自动停止，"
                   "避免每条白等 40 秒）。这些位置保留了 `[CITE: ...]` 占位——"
                   "检查网络（能否打开 api.openalex.org / api.crossref.org）后单独重跑「文献装配」即可补上。\n")
    # 「一条文献撑起全篇」要显式报出来。这种情况数字上像装配成功，实质是没装配。
    if s.get("resolved") and s.get("unique", 1) and s["resolved"] >= 6 \
            and s["resolved"] / max(s["unique"], 1) >= 3:
        out.insert(3,
                   f"> ⚠ **引用高度集中**：{s['resolved']} 处引用只落在 {s['unique']} 条文献上"
                   f"（单条最多被引 {s.get('max_reuse', 0)} 次）。这通常说明这些 `[CITE: ...]` 描述"
                   "写得太笼统，检索只能反复命中同一篇。建议把描述改得更具体后重跑本步，"
                   "或在「文献库」里直接把已知的真实文献挂到对应位置。\n")
    for it in res["items"]:
        marker = (it["marker"] or "").replace("|", "／").replace("\n", " ")[:70]
        q = (it.get("query") or "—").replace("|", "／")
        rec = it.get("rec")
        if rec:
            title = (rec["title"] or "").replace("|", "／")
            hit = f"{_short_authors(rec)} ({rec['year']}) — {title[:60]}"
            doi = rec["doi"]
            verdict = "强匹配" if it["status"] == "ok" else "弱匹配 — " + (it.get("reason") or "请人工确认")
        else:
            hit = "—（保留占位）"
            doi = "—"
            verdict = it.get("reason") or "未解决"
        out.append(f"| {it['n']} | {marker} | {q} | {hit} | {doi} | {verdict} |")

    out.append("\n## 参考文献表\n")
    if res["entries"]:
        out.extend(res["entries"])
    else:
        out.append("_本次没有可装配的引用。_")

    out.append("\n## 边界说明\n")
    out.append("- 检索源为 OpenAlex（全球学术图谱），只收期刊/图书章节/会议等正式出版物，"
               "仓储与预印本一律剔除。")
    out.append("- 「弱匹配」表示标题里没有出现预设的核心术语，只靠检索词重合选中，"
               "引用前请打开 DOI 核对是否真的是你要引的那篇。")
    out.append("- 未解决的位置不会被伪造替代：要么换一句更具体的 `[CITE: ...]` 重跑本步，"
               "要么自己补一条可核实的文献。")
    out.append("- 装配只保证「这条文献真实存在且主题相关」，不保证它就是该论点最合适的出处。")
    return "\n".join(out) + "\n"
