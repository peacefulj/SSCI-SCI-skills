# -*- coding: utf-8 -*-
"""参考文献链路验收：针对 AW_一键成稿.docx 暴露的问题逐条回归。

覆盖：
 A. 文献库前置（先建库、再写作）
 B. 编号引用解析（含多编号、越界、重复引用）
 C. 一条文献撑全篇的复用上限
 D. 主题不符的弱匹配要被拦下
 E. 无模型时不得整段装配失败（检索式兜底）
 F. 正文里的流水线内部提示必须被剥离
 G. 参考文献表只列被引文献
"""
from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("PAPERMATE_DATA_DIR",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)), "_reftest"))

import refs          # noqa: E402
import oneshot       # noqa: E402

PASS = FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [OK] {name}" + (f"   {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {name}   {detail}")


PLAN = ('{"queries":["tobacco leaf formulation blend optimization",'
        '"tobacco sensory quality chemical composition",'
        '"heterogeneous graph representation learning",'
        '"graph neural network recommendation",'
        '"Krippendorff alpha inter-rater reliability"]}')

TITLE = "Construction of Heterogeneous Attribute Graphs for Tobacco Leaf Formulation Design"


def fake_planner(system, user):
    return PLAN


def main():
    print("\n=== A. 文献库前置 ===")
    lib = refs.build_library({}, TITLE, ["1. Introduction", "2. Methods", "3. Results"],
                             fake_planner)
    n = len(lib["entries"])
    check("文献库建立成功", n >= 18, f"{n} 条")
    check("库内每条都有 DOI", all(r.get("doi") for r in lib["entries"]))
    check("编号从 1 连续", [r["num"] for r in lib["entries"]] == list(range(1, n + 1)))
    dois = [r["doi"].lower() for r in lib["entries"]]
    check("库内无重复 DOI", len(dois) == len(set(dois)))
    check("库覆盖了多个子领域", len(lib["queries"]) >= 3,
          str([q["kept"] for q in lib["queries"]]))
    block = refs.library_prompt_block(lib)
    check("白名单提示包含编号与题名",
          "[1]" in block and lib["entries"][0]["title"][:20] in block)
    check("白名单提示禁止库外引用", "禁止" in block and "NEEDCITE" in block)

    print("\n=== B. 编号引用解析 ===")
    raw = [
        {"key": "intro", "heading": "1. Introduction",
         "text": ("Blending has been optimised [1]. Sensory correlation is used [2; 4]. "
                  "Graphs transfer [3]. Out-of-range [99]. Reuse [1].")},
        {"key": "method", "heading": "2. Methods",
         "text": "We follow [2] and report alpha [12]."},
    ]
    cfg = {"citation": "apa", "language": "en"}
    res = oneshot._resolve_library({"cfg": cfg}, raw, lib, cfg)
    s = res["summary"]
    body = "\n".join(x["text"] for x in res["sections"])
    check("多编号引用正确合并", "(Li et al., 2026; Wu et al., 2025)" in body
          or "(Wu et al., 2025; " in body, body[:160])
    check("没有双重括号", "((" not in body and "))" not in body)
    check("越界编号被发现", s["bad_nums"] == [99], str(s["bad_nums"]))
    check("越界编号不留裸编号", "[99]" not in body)
    check("越界编号不被偷换成别的文献", "TODOFIX" in body)
    check("混合引用里合法编号仍保留", "(Li et al., 2026" in body or "2025" in body)
    check("参考文献表只含被引文献", s["unique"] <= s["library"])
    check("未引用文献不计入表", s["library_unused"] > 0, str(s["library_unused"]))

    print("\n=== C. 复用上限 ===")
    cands = refs.search("tobacco leaf formulation blend design", per_page=8)
    used = {}
    picked = []
    for _ in range(5):
        b, _m = refs.pick(cands, ["tobacco", "formulation", "blend"],
                          "tobacco leaf formulation blend design", used=used)
        if b:
            k = b.get("doi")
            used[k] = used.get(k, 0) + 1
            picked.append(k)
    check("同一篇不会被用超过 2 次",
          all(v <= 2 for v in used.values()), str(sorted(used.values(), reverse=True)))
    check("五次引用选出了多个不同文献", len(set(picked)) >= 3, str(len(set(picked))))

    print("\n=== D. 主题不符要被拦下 ===")
    bad, meta = refs.pick(refs.search("inter-rater reliability sensory panels", per_page=8),
                          ["inter-rater", "reliability"],
                          "inter-rater reliability sensory panels")
    check("无关主题的弱匹配被拒", bad is None,
          (meta.get("reason") or "")[:90])
    good, _ = refs.pick(refs.search("tobacco leaf formulation blend design", per_page=8),
                        ["tobacco", "formulation", "blend"],
                        "tobacco leaf formulation blend design")
    check("真正相关的仍能通过", good is not None,
          ((good or {}).get("display_name") or "")[:70])

    print("\n=== E. 无模型时装配不全灭 ===")
    # 这一项验的是**机制**：没有规划模型时，检索式兜底必须产出一个非空查询，
    # 而不是直接判 no-query。不能断言「一定装到了文献」——那取决于 OpenAlex
    # 当天返回什么，结果会随机失败（已经踩过一次）。
    q = refs.fallback_query("Krippendorff alpha coefficient computation")
    t = refs.fallback_terms("Krippendorff alpha coefficient computation")
    check("检索式兜底产出非空查询", bool(q.strip()), q)
    check("兜底术语剔除了方法词", all(x not in refs._METHOD_WORDS for x in t), str(t))
    r2 = refs.assemble(
        {"citation": "apa", "language": "en"},
        [{"key": "a", "heading": "x",
          "text": "See [CITE: Krippendorff alpha coefficient computation]."}],
        lambda system, user: "")
    st = [i["status"] for i in r2["items"]]
    check("无模型时不再全部判 no-query", "no-query" not in st, str(st))
    check("无模型时不伪造作者年份",
          all(not it["rec"] or (it["rec"].get("doi") or "").startswith("10.")
              for it in r2["items"]))

    print("\n=== F. 正文内部提示剥离 ===")
    dirty = ("Real text about results.\n\n"
             "> **Figure 1.** Schematic of the pipeline\n\n"
             "Plot type: conceptual diagram (four-stage flow)\n"
             "Required inputs: [TBD: data needed]\n"
             "Status: [TBD: draw later]\n\n"
             "More text about the current status of the field.\n")
    clean = oneshot._scrub_internal_notes(dirty)
    check("Plot type 被删除", "Plot type" not in clean)
    check("Required inputs 被删除", "Required inputs" not in clean)
    check("Status: 行被删除", "Status: [TBD" not in clean)
    check("图题被保留", "**Figure 1.**" in clean)
    check("正文里普通 status 词保留", "current status of the field" in clean)

    print("\n=== G. 生成说明里的图待办 ===")
    job = {"cfg": {"track": "quant", "genre": "empirical", "data": "none"},
           "data": {"figures": [{"id": "Figure 1", "notes": "four-stage flow diagram"}]},
           "draft_sections": [{"key": "intro", "heading": "1. Introduction", "text": "x"}]}
    note = oneshot._stat_note(job)
    check("图待办进稿末清单", "待补图表" in note and "four-stage" in note)

    print("\n" + "=" * 50)
    print(f"通过 {PASS} 项，失败 {FAIL} 项")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
