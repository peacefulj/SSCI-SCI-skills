# -*- coding: utf-8 -*-
"""验证 AI 水印警示：三种导出格式 + 普通阶段不受影响 + 前端文案存在。"""
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "_wtest"
os.environ["PAPERMATE_DATA_DIR"] = str(DATA)
os.environ["PAPERMATE_NO_BROWSER"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

c = TestClient(server.app)
ok_n = bad_n = 0


def check(name, cond, extra=""):
    global ok_n, bad_n
    if cond:
        ok_n += 1
        print(f"  [OK] {name}")
    else:
        bad_n += 1
        print(f"  [!!] {name}  {extra}")


MD = "# 引言\n\n本文研究了某效应。\n\n## 方法\n\n样本 200 份。\n"
KEY = "AI 生成内容警示"
KEY_SHORT = "禁止直接用于投稿"


def post(body):
    return c.post("/api/export", json=body)


print("\n=== 1. md 导出（ai_generated=True）===")
r = post({"markdown": MD, "format": "md", "title": "t1", "ai_generated": True})
txt = r.content.decode("utf-8")
check("HTTP 200", r.status_code == 200, str(r.status_code))
check("含水印警示标题", KEY in txt, txt[:80])
check("含『禁止直接用于投稿』", KEY_SHORT in txt, txt[:80])
check("警示在正文之前", txt.index(KEY) < txt.index("# 引言"))
check("正文未丢失", "# 引言" in txt and "样本 200 份" in txt)

print("\n=== 2. md 导出（普通阶段 ai_generated=False）===")
r = post({"markdown": MD, "format": "md", "title": "t2"})
txt2 = r.content.decode("utf-8")
check("HTTP 200", r.status_code == 200, str(r.status_code))
check("不含水印警示", KEY not in txt2)
check("与原文完全一致", txt2 == MD)

print("\n=== 3. docx 导出 ===")
r = post({"markdown": MD, "format": "docx", "title": "t3", "ai_generated": True})
check("HTTP 200", r.status_code == 200, str(r.status_code)[:80])
if r.status_code == 200:
    try:
        import docx
        d = docx.Document(io.BytesIO(r.content))
        body = "\n".join(p.text for p in d.paragraphs)
        check("docx 含水印警示", KEY in body, body[:100])
        check("docx 含禁止投稿句", KEY_SHORT in body)
        check("docx 正文完整", "样本 200 份" in body)
    except ImportError:
        check("docx 校验（缺 python-docx 跳过）", True)

print("\n=== 4. docx 普通阶段无水印 ===")
r = post({"markdown": MD, "format": "docx", "title": "t4"})
check("HTTP 200", r.status_code == 200)
if r.status_code == 200:
    try:
        import docx
        d = docx.Document(io.BytesIO(r.content))
        body = "\n".join(p.text for p in d.paragraphs)
        check("普通 docx 不含警示", KEY not in body)
        check("普通 docx 正文完整", "样本 200 份" in body)
    except ImportError:
        pass

print("\n=== 5. tex 导出 ===")
r = post({"markdown": MD, "format": "tex", "title": "t5", "ai_generated": True})
check("HTTP 200", r.status_code == 200, str(r.status_code))
ct = r.headers.get("content-type", "")
if "zip" in ct:
    z = zipfile.ZipFile(io.BytesIO(r.content))
    tex = z.read("main.tex").decode("utf-8")
    check("zip 内 main.tex 含警示", KEY in tex, tex[:80])
else:
    tex = r.content.decode("utf-8")
    check("tex 含警示注释", KEY in tex, tex[:80])
check("警示是注释形式（不污染排版）", tex.lstrip().startswith("%%") or "%%" in tex[:200])

print("\n=== 6. 前端与页面文案 ===")
html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
check("一键成稿页顶部有警示块", 'id="osAiWatermark"' in html)
check("警示含『严禁』", "严禁" in html)
check("警示含『水印』", "水印" in html)
check("能力边界新增条目", "AI 生成内容带水印，不可直接使用" in html)
check("成稿结果区注入警示", "AI_WATERMARK_HTML" in js)
check("前端 md 导出带警示", "AI_WATERMARK_MD" in js)
check("前端标记 7 阶段为 AI 产出", '{"7": 1}' in js.replace(" ", "").replace('"7":1', '"7": 1'))

print(f"\n{'='*50}")
print(f"通过 {ok_n} 项，失败 {bad_n} 项")
sys.exit(1 if bad_n else 0)
