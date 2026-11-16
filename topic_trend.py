# -*- coding: utf-8 -*-
"""选题雷达 · OpenAlex 全球发文趋势（后端模块）。

供 /api/topic/trend 调用。逻辑与 skill 的 scripts/topic_radar.py 一致，
但组织成可 import 的函数，返回结构化 JSON 供前端渲染。
仅用标准库 urllib（与 skill 原生脚本风格一致）。
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime

OA = "https://api.openalex.org/works"
TIMEOUT = 25
# 真邮箱才进 OpenAlex 的「礼貌池」，配额更宽、限流更晚触发
MAILTO = "sunzhiyao@yuanqiaiot.com"
START_YEAR = 2021          # 检索起点，补齐刻度时也用它


def _fetch_json(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"academic-writing-agent topic-trend (mailto:{MAILTO})"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fill_years(groups, start=START_YEAR):
    """OpenAlex 的 group_by 只返回「有记录」的年份，缺年不会出现。

    补齐成 start..今年 的连续刻度，缺失年记 0，当前年标记 partial。
    这样柱状图的形状才是真实的（某年 0 篇，本身就是一个信号）。
    """
    now = datetime.now().year
    by_year = {}
    for g in groups:
        try:
            by_year[int(g["year"])] = g["count"]
        except (TypeError, ValueError):
            continue
    years = list(range(start, now + 1))
    return [{"year": str(y), "count": by_year.get(y, 0), "partial": y == now} for y in years]


def get_trend(topic):
    """返回结构化趋势结果。"""
    q = urllib.parse.quote(topic)
    url = (f"{OA}?filter=title_and_abstract.search:{q},from_publication_date:{START_YEAR}-01-01"
           f"&group_by=publication_year&mailto={MAILTO}")
    data = _fetch_json(url)
    groups = data.get("group_by", [])
    if not groups:
        url2 = (f"{OA}?search={q}&filter=from_publication_date:{START_YEAR}-01-01"
                f"&group_by=publication_year&mailto={MAILTO}")
        groups = _fetch_json(url2).get("group_by", [])

    groups = [{"year": str(g["key"]), "count": g["count"]} for g in groups]
    groups = _fill_years(groups)

    growth, label, hint, base_year, last_year, note = _judge(groups)
    return {
        "topic": topic,
        "groups": groups,
        "growth": growth,
        "base_year": base_year,
        "last_year": last_year,
        "note": note,
        "label": label,
        "hint": hint,
        "small_sample": _is_small(groups),
    }


def _judge(groups):
    """按「最早有记录年 → 最近完整年」算增长率。

    只有 1 个完整年份有记录时不给增长率（旧的写法会硬算成 +0%，
    并把文案写成「2021→最近完整年」，与数据实际起止年不符，容易误读）。
    """
    now = datetime.now().year
    full = [g for g in groups if int(g["year"]) < now]
    if not full:
        return None, "📊 数据不足", "当前年份数据尚未完整，无法判断趋势。", None, None, \
            "尚无完整年份的记录"

    last = full[-1]
    has_data = [g for g in full if g["count"] > 0]
    if not has_data:
        return None, "📊 无相关记录", "该检索词在 OpenAlex 上没有记录，建议换更通用的英文检索词。", \
            None, None, "全部年份均为 0 篇"

    base = has_data[0]
    if base["year"] == last["year"]:
        n = base["count"]
        return (None, "📊 数据不足",
                "只有 1 个完整年份有记录，无法判断升温还是回落；样本小时不宜据此决策。",
                base["year"], last["year"],
                f"仅 {base['year']} 年有记录（{n} 篇），其余年份为 0 篇")

    growth = round((last["count"] - base["count"]) / base["count"] * 100)
    if growth > 20:
        label, hint = "🔥 快速升温赛道", "方向活跃、可跟，但要找差异化切入点，避免红海同质"
    elif growth < -20:
        label, hint = "📉 热度回落", "选题必要性存疑：问题可能已解决，或该问法已过时"
    else:
        label, hint = "⚖️ 平稳领域", "成熟稳定，选题价值要靠「边际贡献是否清晰」支撑"
    note = f"{base['year']} 年 {base['count']} 篇 → {last['year']} 年 {last['count']} 篇"
    return growth, label, hint, base["year"], last["year"], note


def _is_small(groups):
    if not groups:
        return True
    counts = [g["count"] for g in groups if not g["partial"]]
    if not counts:
        return True
    return max(counts) < 10
