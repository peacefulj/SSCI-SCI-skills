#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
选题雷达 · OpenAlex 全球发文趋势脚本（可选工具）

移植自研墨平台 v1.10.0「选题雷达」的"跑趋势"能力。
用法：
    python scripts/topic_radar.py "移动支付与农户创业"
    python scripts/topic_radar.py "mobile money rural entrepreneurship"

功能：
    1. 调 OpenAlex 公开 API，按 title_and_abstract 检索 2021 年至今的逐年发文量
    2. 画文本柱状图
    3. 计算「2021 → 最近完整年」增长率，按三档判读（>20% 升温 / <-20% 回落 / 平稳）

说明：
    - 仅用 Python 标准库（urllib），与 score.py / check_structure.py 风格一致
    - 只做趋势，不做 AI 评估（评估由 agent 按 assets/topic-prompts.md 拼装提示词完成）
    - OpenAlex 偶发限流，失败时提示重试即可
"""

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime

OA = "https://api.openalex.org/works"
TIMEOUT = 25
# 真邮箱才进 OpenAlex 的「礼貌池」，配额更宽、限流更晚触发
MAILTO = "sunzhiyao@yuanqiaiot.com"


def fetch_json(url):
    """用 urllib 拉取 JSON，带 User-Agent（OpenAlex 建议标注联系方式，礼貌池）"""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"academic-writing-skill topic-radar (mailto:{MAILTO})"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_trend(topic):
    """返回 [(year, count), ...]，按年份升序"""
    q = urllib.parse.quote(topic)
    # 首选：题名+摘要检索，2021 起，按发表年分组
    url = (f"{OA}?filter=title_and_abstract.search:{q},from_publication_date:2021-01-01"
           f"&group_by=publication_year&mailto={MAILTO}")
    data = fetch_json(url)
    groups = data.get("group_by", [])
    if not groups:
        # 兜底：全文 search
        url2 = (f"{OA}?search={q}&filter=from_publication_date:2021-01-01"
                f"&group_by=publication_year&mailto={MAILTO}")
        groups = fetch_json(url2).get("group_by", [])
    groups = sorted(groups, key=lambda g: g["key"])
    return [(g["key"], g["count"]) for g in groups]


def draw_chart(groups, topic):
    """文本柱状图"""
    if not groups:
        print(f"「{topic}」在 OpenAlex 未检索到 2021 年以来的发文记录。")
        print("提示：OpenAlex 为英文库，中文主题请转英文检索词（如「移动支付与农户创业」→ mobile money rural entrepreneurship）。")
        return None
    max_c = max(c for _, c in groups)
    print(f"\n「{topic}」近年发文量（题名+摘要匹配；当前年份不完整）\n")
    for year, c in groups:
        bar_len = max(2, round(c / max_c * 40))
        print(f"  {year}  {'█' * bar_len}  {c}")
    return groups


def judge_trend(groups):
    """三档判读，返回 (growth, label)"""
    this_year = str(datetime.now().year)
    # 找最近一个"完整年"（排除当前年）
    last_full = None
    for year, c in reversed(groups):
        if year < this_year:
            last_full = (year, c)
            break
    if last_full is None and groups:
        last_full = groups[-1]
    first = groups[0][1]
    last = last_full[1]
    growth = round((last - first) / first * 100) if first else 0
    # 小样本防护：基期或末期绝对量过小，增长率会失真，须提示 agent 勿据此下强结论
    small_sample = (first < 10) or (last < 10)
    if growth > 20:
        label = "🔥 快速升温赛道"
        hint = "方向活跃、可跟，但要找差异化切入点，避免红海同质"
    elif growth < -20:
        label = "📉 热度回落"
        hint = "选题必要性存疑：问题可能已解决，或该问法已过时"
    else:
        label = "⚖️ 平稳领域"
        hint = "成熟稳定，选题价值要靠「边际贡献是否清晰」支撑"
    return growth, label, hint


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    topic = sys.argv[1].strip()
    if not topic:
        print("请提供研究主题。")
        sys.exit(1)

    print(f"拉取「{topic}」趋势中…")
    try:
        groups = get_trend(topic)
    except Exception as e:
        print(f"趋势获取失败：{e}")
        print("OpenAlex 偶发限流，稍等几秒重试即可。")
        sys.exit(1)

    if not draw_chart(groups, topic):
        sys.exit(0)

    growth, label, hint = judge_trend(groups)
    print(f"\n2021 → 最近完整年变化：{'+' if growth >= 0 else ''}{growth}%  {label}")
    print(f"含义：{hint}")
    first_c = groups[0][1]
    last_full_c = groups[-2][1] if groups[-1][0] == str(datetime.now().year) else groups[-1][1]
    if first_c < 10 or last_full_c < 10:
        print("⚠️ 样本量偏小（基期或末期不足 10 篇），增长率仅供参考，勿据此下强结论；建议换更通用的检索词再跑一次。")
    print("\n（下一步：让 agent 按 assets/topic-prompts.md 拼装提示词，做 AI 三维评估）")


if __name__ == "__main__":
    main()
