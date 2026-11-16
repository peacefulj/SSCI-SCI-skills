"""公开数据源荐引（P2）——给线索 + 可代下载白名单公开源，仍不解析、不落数值。

**本模块的职责边界（v1.2.7 起）**

1. 真正能免 key 自动取到的只有两类：World Bank 的国别宏观面板、Zenodo /
   Harvard Dataverse 的论文复现数据包。而实证论文最常缺的企业级、个体级变量
   （CSMAR、Wind、ESG 评级、CFPS）全部是授权制或付费，没有开放 API。
2. 跨源拼接口径（单位、样本期、统计口径变更、汇率）一旦错配，**错数进表比留空
   更危险**——那是未经作者核验的二手数据。
3. 所以本模块回答三件事：去哪儿取、怎么取、取回来怎么引用；并可在作者显式选了
   「帮我找数据源 / 演示模式」时**代下载白名单公开源**，把文件落盘供作者核对。

硬约束（不可越界）：
- 只代下载白名单公开源（World Bank API / Zenodo / Harvard Dataverse）；
  MANUAL 三类（统计局 / 北大 / CSMAR）是授权或付费，**绝不代下载**，只给入口。
- 下载 ≠ 分析：落盘后**不解析数值、不写回画像、不注入正文**；作者核对口径后再
  自行上传走 dataset.gap_report 体检。
- 不生成任何模拟值（演示稿里的模拟值由 oneshot 层单独隔离生成，不在本模块）。
网络策略与 refs.py 一致：短超时、失败即降级，绝不阻断成稿。
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request

import llm

UA = "PaperMate/1.2 (+academic-writing-assistant)"
TIMEOUT = 12
WB_API = "https://api.worldbank.org/v2"
WB_DASH = "https://data.worldbank.org/indicator"

# 指标代码均已逐一实测存在（2026-11）。关键词用于把题目里的概念映射到指标，
# 只做本地匹配，不联网猜。
WB_INDICATORS: list[tuple[str, str, tuple[str, ...]]] = [
    ("NY.GDP.PCAP.CD", "人均 GDP（现价美元）",
     ("gdp", "growth", "economic", "income", "经济增长", "人均", "发展水平")),
    ("NY.GDP.MKTP.KD.ZG", "GDP 增长率（不变价）",
     ("growth", "增长", "gdp growth", "经济增速")),
    ("SP.POP.TOTL", "总人口", ("population", "人口", "demograph")),
    ("SP.URB.TOTL.IN.ZS", "城镇化率", ("urban", "城镇化", "城市", "城镇")),
    ("GB.XPD.RSDV.GD.ZS", "研发支出占 GDP 比重",
     ("r&d", "research and development", "研发", "创新投入", "technolog")),
    ("IP.PAT.RESD", "居民专利申请量", ("patent", "专利", "innovation", "创新")),
    ("EN.GHG.CO2.PC.CE.AR5", "人均二氧化碳排放",
     ("co2", "carbon", "emission", "碳", "排放", "环境", "绿色")),
    ("EG.USE.PCAP.KG.OE", "人均能源使用量", ("energy", "能源", "能耗")),
    ("BX.KLT.DINV.WD.GD.ZS", "FDI 净流入占 GDP",
     ("fdi", "foreign direct", "外资", "外商")),
    ("NE.TRD.GNFS.ZS", "贸易开放度（进出口占 GDP）",
     ("trade", "openness", "贸易", "开放", "出口")),
    ("SE.SEC.ENRR", "中学毛入学率", ("education", "school", "教育", "人力资本")),
    ("SE.XPD.TOTL.GD.ZS", "教育支出占 GDP", ("education spending", "教育支出", "财政")),
    ("SP.DYN.LE00.IN", "出生时预期寿命", ("life expectancy", "寿命", "健康", "health")),
    ("IT.NET.USER.ZS", "互联网使用率",
     ("internet", "digital", "互联网", "数字化", "数字经济")),
    ("SL.UEM.TOTL.ZS", "失业率", ("unemploy", "失业", "labor", "就业")),
    ("SI.POV.GINI", "基尼系数", ("gini", "inequality", "基尼", "不平等", "收入差距")),
    ("NV.IND.MANF.ZS", "制造业增加值占 GDP",
     ("manufactur", "制造业", "industrial", "产业升级")),
    ("GC.DOD.TOTL.GD.ZS", "政府债务占 GDP", ("debt", "债务", "fiscal", "财政")),
]

# 手工 / 授权入口：系统取不到，但作者自己能取。只给路径，不代劳。
MANUAL: list[dict] = [
    {
        "key": "nbs",
        "name": "国家统计局 · 国家数据",
        "kind": "官方统计",
        "access": "手工下载",
        "url": "https://data.stats.gov.cn/",
        "why": "中国宏观与分省年度/季度数据的权威口径。实测脚本直连返回 403，"
               "只能在网页上按指标树导出，所以这里不给直链",
        "how": "网页选「年度数据」→ 展开指标树勾选指标 → 导出 csv → 回到一键成稿上传，系统会重新画像并体检",
        "cite": "国家统计局. 国家数据[DB/OL]. https://data.stats.gov.cn/",
    },
    {
        "key": "pku",
        "name": "北京大学开放研究数据平台（CFPS / CGSS / CHARLS 等）",
        "kind": "微观调查",
        "access": "注册申请",
        "url": "https://opendata.pku.edu.cn/",
        "why": "个体/家庭级微观调查不在任何开放 API 里，须实名注册并说明研究用途",
        "how": "注册 → 找到对应调查项目 → 提交数据使用申请 → 通过后下载 → 上传（超大可先抽样成 csv）",
        "cite": "按各项目要求引用（如 CFPS 须引用北京大学中国社会科学调查中心）",
    },
    {
        "key": "csmar",
        "name": "CSMAR / Wind / 华证 ESG 等商业数据库",
        "kind": "商业数据库",
        "access": "付费或校内订阅",
        "url": "https://data.csmar.com/",
        "why": "企业财务、ESG 评级、专利明细的主要来源；高校多有图书馆订阅",
        "how": "经学校图书馆数据库入口登录导出；导出的表常有合并单元格与多级表头，上传前先整理成一行一记录",
        "cite": "按数据库要求格式引用（CSMAR 须注明数据库名称与版本）",
    },
]

_STOP = {"the", "and", "for", "with", "from", "evidence", "study", "analysis",
         "effect", "effects", "based", "using", "research", "does", "how", "why",
         "impact", "impacts", "role", "new", "case", "data"}


# ---------------------------------------------------------------- 基础工具
def _get(url: str) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _has_cjk(s: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in (s or ""))


def _ascii_terms(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text or "")
    out: list[str] = []
    for w in words:
        lw = w.lower()
        if lw in _STOP or lw in out:
            continue
        out.append(lw)
    return out[:8]


def _llm_queries(text: str, llm_cfg: dict | None) -> tuple[list[str], str]:
    """中文题目 → 英文检索词。没有 key 就跳过，绝不因此报错。"""
    if not llm_cfg or not llm_cfg.get("api_key"):
        return [], "未配置模型，跳过英文检索词转换（Zenodo/Dataverse 检索略过）"
    system = (
        "You convert a research topic into English search queries for finding datasets. "
        "Reply with ONLY a JSON array of 2 short queries (3-6 words each), no prose, "
        "no explanation. Use academic terms, not Chinese."
    )
    try:
        raw = llm.chat(
            llm_cfg["api_key"],
            [{"role": "system", "content": system},
             {"role": "user", "content": (text or "")[:300]}],
            base_url=llm_cfg.get("base_url"),
            model=llm_cfg.get("model"),
            temperature=0.2,
            timeout=25,
        )
        m = re.search(r"\[[\s\S]*\]", raw or "")
        arr = json.loads(m.group(0)) if m else []
        qs = [str(x).strip() for x in arr if str(x).strip()]
        return qs[:2], ""
    except Exception as e:
        return [], f"检索词转换失败（{type(e).__name__}），已跳过在线检索"


def _en_query(text: str, n: int = 6) -> str:
    """整句题目 → 短检索式。

    Zenodo/Dataverse 对长句是 OR 匹配，整句丢进去会捞回一堆不相关条目
    （实测：一篇讲数字化转型的题目捞回了外交话语分析）。所以先砍副标题，
    再只保留内容词。
    """
    core = re.split(r"[:：;；—–]|\bevidence\b|\bbased on\b", text or "")[0]
    words = _ascii_terms(core)
    return " ".join(words[:n])


def _relevant(title: str, q: str, min_hits: int = 2) -> bool:
    """标题里至少要命中检索式的两个内容词，否则视为跑题的检索噪声。

    单字命中太松：查「digital transformation…」会捞回一篇德文讲
    "Transformation in der heterogenen Gruppe" 的条目（实测）。
    """
    t = (title or "").lower()
    toks = [w for w in (q or "").lower().split() if len(w) > 2]
    if not toks:
        return True
    need = 1 if len(toks) == 1 else min_hits
    return sum(1 for w in toks if w in t) >= need


def _terms(topic: str, need: list[str], llm_cfg: dict | None) -> tuple[list[str], list[str]]:
    text = " ".join([topic or ""] + [str(x) for x in (need or [])]).strip()
    if not text:
        return [], ["题目为空，无法生成检索词"]
    if not _has_cjk(text):
        q = _en_query(text)
        return ([q] if q else []), ([] if q else ["题目里没有可用的英文内容词"])
    qs, note = _llm_queries(text, llm_cfg)
    if qs:
        return qs, []
    bits = _ascii_terms(text)
    if bits:
        return [" ".join(bits[:6])], ([note] if note else [])
    return [], [note or "题目没有可用检索词"]


# ---------------------------------------------------------------- 各数据源
MICRO_RE = re.compile(
    r"\b(firms?|enterprises?|corporate|listed|compan(?:y|ies)|smes?|plants?|establishments?|micro)\b",
    re.I)
MICRO_CN = ("企业", "公司", "上市公司", "微观", "个体", "农户", "员工", "工厂", "门店")


def _micro_level(text: str) -> bool:
    """题目主体是不是企业/个体层面。

    微观题推国别宏观面板没有意义（「数字化转型→企业绿色创新」配 GDP 毫无用处），
    所以这类题把世行指标降到兜底位，并标注适用条件。
    """
    t = text or ""
    return bool(MICRO_RE.search(t)) or any(w in t for w in MICRO_CN)


def _wb_hits(text: str, limit: int = 4, country: str = "CHN", micro: bool = False) -> list[dict]:
    """题目关键词 → 世行指标（本地匹配，不联网猜）。"""
    low = (text or "").lower()
    scored = []
    for code, label, kws in WB_INDICATORS:
        hit = [k for k in kws if k in low]
        if hit:
            scored.append((len(hit), code, label, hit))
    scored.sort(key=lambda x: -x[0])
    if micro:
        limit = min(limit, 1)
    out = []
    for _, code, label, hit in scored[:limit]:
        out.append({
            "name": label,
            "kind": "国别宏观面板",
            "access": "网页导出 csv",
            "url": f"{WB_DASH}/{code}",
            "why": f"题目命中「{'、'.join(hit[:3])}」；World Development Indicators 口径"
                   + ("；⚠ 国别层面：仅当你的设计是省/国别面板时适用，企业级变量请走下面的商业数据库"
                      if micro else ""),
            "how": f"页面右侧 Download 选 csv/excel（默认全国家；可筛 {country} 等）。"
                   f"程序化可取 JSON：{WB_API}/country/{country}/indicator/{code}?format=json "
                   "（本机实测时快时慢，csv 直连常超时，故给网页入口）。"
                   "网页口径与国内统计年鉴不完全一致，混用须在方法里说明",
            "cite": f"World Bank. World Development Indicators: {label} [{code}]. {WB_DASH}/{code}",
        })
    return out


def _search_zenodo(q: str, limit: int = 3) -> list[dict]:
    # 不加 sort=mostrecent：那会按上传时间而不是相关性返回，实测同一检索式下
    # 捞回的全是无关记录（相关率从 3/5 掉到 0/5）。size 取大于 limit，
    # 因为 _relevant 会刷掉一部分，取太少容易互相抵消成空结果。
    url = "https://zenodo.org/api/records?" + urllib.parse.urlencode(
        {"q": q, "size": max(limit * 3, 8), "type": "dataset"})
    d = _get(url)
    out = []
    for h in (d.get("hits") or {}).get("hits") or []:
        if len(out) >= limit:
            break
        meta = h.get("metadata") or {}
        title = (meta.get("title") or "").strip()
        if not title or not _relevant(title, q):
            continue
        doi = (h.get("doi") or meta.get("doi") or "").strip()
        out.append({
            "name": title[:120],
            "kind": "公开复现数据包",
            "access": "可直接下载",
            "url": f"https://doi.org/{doi}" if doi else "https://zenodo.org/",
            "why": f"Zenodo 检索「{q}」命中（{meta.get('publication_date') or '日期未标注'}）",
            "how": "打开条目看 Files，优先取 csv/dta；下载后上传，系统会重新画像并体检",
            "cite": (f"{title}. Zenodo. https://doi.org/{doi}" if doi else title),
        })
    return out


def _search_dataverse(q: str, limit: int = 3) -> list[dict]:
    url = "https://dataverse.harvard.edu/api/search?" + urllib.parse.urlencode(
        {"q": q, "type": "dataset", "per_page": limit})
    d = _get(url)
    out = []
    for it in (d.get("data") or {}).get("items") or []:
        name = (it.get("name") or "").strip()
        if not name or not _relevant(name, q):
            continue
        gid = (it.get("global_id") or "").strip()
        link = it.get("url") or (
            "https://doi.org/" + gid[4:] if gid.startswith("doi:") else "")
        if not link:
            continue
        out.append({
            "name": name[:120],
            "kind": "公开复现数据包",
            "access": "可直接下载",
            "url": link,
            "why": f"Harvard Dataverse 检索「{q}」命中"
                   + (f"（{it.get('published_at')}）" if it.get("published_at") else ""),
            "how": "多为论文复现包：先读 README 确认变量定义与你的口径一致，再取数据文件上传",
            "cite": (gid.replace("doi:", "https://doi.org/") if gid else name),
        })
    return out


# ---------------------------------------------------------------- 对外入口
def suggest(topic: str = "", need: list[str] | None = None,
            profile: dict | None = None, llm_cfg: dict | None = None,
            country: str = "CHN") -> dict:
    """按题目给出可公开获取的数据源线索。

    profile 只用于说明「当前数据缺什么」，不参与检索；返回值里的数字一律为空——
    本函数不下载、不解析、不写回。调用方（前端）只负责展示链接。
    """
    terms, notes = _terms(topic or "", need or [], llm_cfg)
    items: list[dict] = []
    fails = 0
    for q in (terms or [])[:2]:
        if fails >= 2:
            break
        for fn in (_search_zenodo, _search_dataverse):
            try:
                items.extend(fn(q, 3))
            except Exception as e:
                fails += 1
                notes.append(f"{fn.__name__.strip('_')} 检索失败（{type(e).__name__}）")
    if fails >= 2:
        notes.append("在线检索不可用（网络或限流）：已降级为白名单入口，稍后可重试")

    n_repo = len(items)
    micro = _micro_level(" ".join([topic or ""] + [str(x) for x in (need or [])]))
    wb = _wb_hits(" ".join([topic or ""] + [str(x) for x in (need or [])]),
                  country=country, micro=micro)
    # 微观题：手工/授权入口（CSMAR、CFPS 等）才是正解，世行只作兜底，排到后面
    if micro:
        items.extend(MANUAL)
        items.extend(wb)
    else:
        items.extend(wb)
        items.extend(MANUAL)

    seen, uniq = set(), []
    for it in items:
        u = it.get("url") or ""
        if u in seen:
            continue
        seen.add(u)
        uniq.append(it)

    gap_note = ""
    if profile:
        try:
            import dataset  # 延迟导入，避免环
            rep = dataset.gap_report(profile)
            risk = [i["label"] for i in rep.get("items") or [] if i["status"] == "risk"]
            if risk:
                gap_note = "当前数据体检的阻断项：" + "、".join(risk[:4]) + "。"
        except Exception:
            gap_note = ""

    return {
        "ok": True,
        "items": uniq,
        "terms": terms,
        "notes": notes,
        "gap_note": gap_note,
        "counts": {"repo": n_repo, "wb": len(wb), "manual": len(MANUAL)},
        "disclaimer": (
            "只给线索，不落数字：本功能不下载、不解析、不写入任何数值。"
            "取回后请核对单位、样本期与统计口径再上传——口径不一致的数据拼进同一张表，"
            "比留 `[TBD: ...]` 更危险。"
        ),
    }


# ---------------------------------------------------------------- 代下载（白名单）
# 只代下载「确实能免 key 公开取到」的来源；其余（授权/付费/被反爬）一律拒绝并说明。
ALLOWED_HOSTS = {
    "api.worldbank.org": "wdi",
    "zenodo.org": "zenodo",
    "doi.org": "doi",
    "dataverse.harvard.edu": "dataverse",
}
# 单文件上限：公开复现包可能上百 MB，超过就只给链接不下，避免拖垮服务。
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
_DL_TIMEOUT = 30


def _allowed(url: str) -> str | None:
    """返回该 url 属于哪类白名单源；不在白名单（含授权/付费/反爬站点）返回 None。"""
    try:
        host = urllib.parse.urlparse(url or "").netloc.lower()
    except Exception:
        return None
    host = host.split(":")[0]
    for h, kind in ALLOWED_HOSTS.items():
        if host == h or host.endswith("." + h):
            return kind
    return None


def _safe_name(url: str, idx: int) -> str:
    """从 url 里取一个可落盘的文件名；取不到就用序号占位（不含非法字符）。"""
    try:
        path = urllib.parse.urlparse(url or "").path
        base = os.path.basename(path)
    except Exception:
        base = ""
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base or "")[:80]
    return base or f"source_{idx}.json"


def download(items: list[dict], outdir: str) -> dict:
    """代下载白名单公开源，落盘到 outdir（文件隔离，不解析、不写回画像）。

    每个 item 需含 `url`（`suggest()` 已保证只产出白名单或手工入口的 url）。
    返回 {downloaded: [...], skipped: [...], failed: [...], files: [...], notes: [...]}。
    任何单条失败都不影响其余条目，也绝不抛出异常阻断成稿。
    """
    os.makedirs(outdir, exist_ok=True)
    downloaded: list[dict] = []
    skipped: list[dict] = []
    failed: list[dict] = []
    files: list[str] = []
    notes: list[str] = []

    for i, it in enumerate(items or []):
        url = (it.get("url") or "").strip()
        name = (it.get("name") or "").strip()
        if not url:
            skipped.append({"name": name, "reason": "无链接"})
            continue
        kind = _allowed(url)
        if kind is None:
            # 授权/付费/反爬站点（统计局、CSMAR、北大、CFPS 等）：只给链接不代劳
            skipped.append({"name": name, "url": url,
                            "reason": "需授权或付费，系统不代下载，请按提示手工取"})
            continue

        path = os.path.join(outdir, _safe_name(url, i))
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept": "application/json,*/*"})
            with urllib.request.urlopen(req, timeout=_DL_TIMEOUT) as resp:
                clen = resp.headers.get("Content-Length")
                if clen and int(clen) > MAX_DOWNLOAD_BYTES:
                    skipped.append({"name": name, "url": url,
                                    "reason": f"文件过大（>{MAX_DOWNLOAD_BYTES // (1024 * 1024)}MB），"
                                              "请点链接手工下载"})
                    continue
                data = resp.read(MAX_DOWNLOAD_BYTES + 1)
                if len(data) > MAX_DOWNLOAD_BYTES:
                    skipped.append({"name": name, "url": url,
                                    "reason": f"文件过大（>{MAX_DOWNLOAD_BYTES // (1024 * 1024)}MB），"
                                              "请点链接手工下载"})
                    continue
            with open(path, "wb") as f:
                f.write(data)
            files.append(path)
            downloaded.append({"name": name, "url": url, "file": path,
                               "bytes": len(data)})
        except Exception as e:
            failed.append({"name": name, "url": url,
                           "reason": f"{type(e).__name__}: {str(e)[:80]}"})

    if skipped:
        notes.append(f"{len(skipped)} 条需手工取（授权/付费/文件过大），已给出链接")
    if failed:
        notes.append(f"{len(failed)} 条下载失败（网络或源站限制），可稍后重试或点链接手工取")
    if downloaded:
        notes.append(f"已代下载 {len(downloaded)} 个文件到 {outdir}，"
                     "**未经解析与核对**，请先检查口径再上传")
    return {"downloaded": downloaded, "skipped": skipped, "failed": failed,
            "files": files, "notes": notes, "outdir": outdir}
