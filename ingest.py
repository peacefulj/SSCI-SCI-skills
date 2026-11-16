# -*- coding: utf-8 -*-
"""文档摄取：把 Word / Markdown / LaTeX / HTML / PDF 统一转成 Markdown。

设计要点：
- 表格 -> GFM 表格（保住列结构，论文里的三线表不再变成一坨竖线）
- 图片 -> 抽取到 uploads/ 并在正文插入 ![](/media/xxx.png)
- Word 公式（OMML）-> LaTeX（$...$ / $$...$$）
- .doc 走 LibreOffice headless 转 docx；失败时给明确提示，不静默出错
- 只做格式转换，不改写任何学术内容
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import paths

# 可写数据目录（打包后 = exe 同级 data/，源码运行 = 项目根）
BASE_DIR = paths.data_root()
UPLOAD_DIR = BASE_DIR / "uploads"

# 解压到 Program Files、只读盘、或直接在压缩包里双击运行时，这里会 PermissionError，
# 过去会让整个服务起不来（import 阶段就崩）。现在退到系统临时目录：
# 图片/附件重启后会丢，但至少「能跑起来」，且横幅里会明确告知。
try:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    _probe = UPLOAD_DIR / f".w{uuid.uuid4().hex[:4]}"
    _probe.write_text("ok", encoding="utf-8")
    _probe.unlink()
except OSError as _e:
    UPLOAD_DIR = Path(tempfile.gettempdir()) / "papermate_uploads"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    try:  # 控制台编码不确定（GBK 控制台编不了部分字符），提示失败不影响运行
        print(f"[警告] 无法写入 {BASE_DIR / 'uploads'}（{_e}），"
              f"图片/附件改存临时目录：{UPLOAD_DIR}（重启后清空）")
    except Exception:
        pass

MEDIA_URL = "/media"

TEXT_EXT = {".md", ".markdown", ".txt", ".text"}
TEX_EXT = {".tex", ".latex", ".ltx"}
DOCX_EXT = {".docx", ".docm"}
DOC_EXT = {".doc"}
PDF_EXT = {".pdf"}
HTML_EXT = {".html", ".htm"}
RTF_EXT = {".rtf"}

MAX_BYTES = 25 * 1024 * 1024  # 25MB

# 扩展名经常撒谎（Word「另存为网页」得到的 .doc 其实是 HTML，导出工具写出的
# .docx 有时其实是 RTF/HTML），所以先按文件头判断真实格式，扩展名只作补充。
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class IngestError(Exception):
    pass


# ---------------- 通用工具 ----------------

def _new_asset_name(ext: str) -> str:
    return f"{uuid.uuid4().hex[:12]}{ext}"


def _save_bytes(data: bytes, ext: str) -> str:
    name = _new_asset_name(ext)
    (UPLOAD_DIR / name).write_bytes(data)
    return f"{MEDIA_URL}/{name}"


def _md_escape_cell(s: str) -> str:
    """表格单元格内的 | 与换行需要转义，否则 GFM 表格错列。"""
    s = (s or "").replace("\\", "\\\\").replace("|", "\\|")
    return re.sub(r"\s*\n+\s*", "<br>", s.strip())


# ---------------- OMML(Word 公式) -> LaTeX ----------------

M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# 常用符号/函数名直接保留 Unicode 由 MathJax 处理；这里只处理需要一个 LaTeX 命令的
_OMML_FUNCS = {
    "sin": r"\sin", "cos": r"\cos", "tan": r"\tan", "log": r"\log", "ln": r"\ln",
    "exp": r"\exp", "lim": r"\lim", "max": r"\max", "min": r"\min", "arg": r"\arg",
    "det": r"\det", "gcd": r"\gcd", "sup": r"\sup", "inf": r"\inf",
}


def _m_text(node) -> str:
    return "".join(t.text or "" for t in node.iter(M + "t"))


def _child(node, name):
    return node.find(M + name) if node is not None else None


def _omml(node) -> str:
    """递归把 OMML 节点转成 LaTeX。未知结构退化为子节点文本，保证不丢内容。"""
    if node is None:
        return ""
    tag = node.tag

    if tag in (M + "oMath", M + "oMathPara", M + "e", M + "num", M + "den",
               M + "sub", M + "sup", M + "deg", M + "fName", M + "lim", M + "groupChr"):
        return "".join(_omml(c) for c in node)

    if tag == M + "r":
        return _m_text(node)

    if tag == M + "f":  # 分式
        num = _omml(_child(node, "num"))
        den = _omml(_child(node, "den"))
        return r"\frac{%s}{%s}" % (num, den)

    if tag == M + "sSup":
        e = _omml(_child(node, "e"))
        sup = _omml(_child(node, "sup"))
        return "{%s}^{%s}" % (e, sup)

    if tag == M + "sSub":
        e = _omml(_child(node, "e"))
        sub = _omml(_child(node, "sub"))
        return "{%s}_{%s}" % (e, sub)

    if tag == M + "sSubSup":
        e = _omml(_child(node, "e"))
        sub = _omml(_child(node, "sub"))
        sup = _omml(_child(node, "sup"))
        return "{%s}_{%s}^{%s}" % (e, sub, sup)

    if tag == M + "sPre":
        sub = _omml(_child(node, "sub"))
        sup = _omml(_child(node, "sup"))
        e = _omml(_child(node, "e"))
        return "{}_{%s}^{%s}{%s}" % (sub, sup, e)

    if tag == M + "rad":  # 根式
        deg = _omml(_child(node, "deg"))
        e = _omml(_child(node, "e"))
        if deg.strip():
            return r"\sqrt[%s]{%s}" % (deg, e)
        return r"\sqrt{%s}" % e

    if tag == M + "d":  # 括号
        pr = _child(node, "dPr")
        beg, end = "(", ")"
        if pr is not None:
            b = pr.find(M + "begChr")
            e_ = pr.find(M + "endChr")
            if b is not None and b.get(M + "val") is not None:
                beg = b.get(M + "val")
            if e_ is not None and e_.get(M + "val") is not None:
                end = e_.get(M + "val")
        inner = _omml(_child(node, "e"))
        if beg in ("", "{"):
            beg_m = r"\{" if beg == "{" else ""
        else:
            beg_m = beg
        if end in ("", "}"):
            end_m = r"\}" if end == "}" else ""
        else:
            end_m = end
        return r"\left%s %s \right%s" % (beg_m, inner, end_m)

    if tag == M + "nary":  # 求和/积分/连乘
        pr = _child(node, "naryPr")
        chr_ = "∑"
        if pr is not None:
            c = pr.find(M + "chr")
            if c is not None and c.get(M + "val"):
                chr_ = c.get(M + "val")
        op = {"∑": r"\sum", "∏": r"\prod", "∫": r"\int", "∬": r"\iint",
              "∭": r"\iiint", "∮": r"\oint", "⋃": r"\bigcup", "⋂": r"\bigcap"}.get(chr_, chr_)
        sub = _omml(_child(node, "sub"))
        sup = _omml(_child(node, "sup"))
        e = _omml(_child(node, "e"))
        out = op
        if sub.strip():
            out += "_{%s}" % sub
        if sup.strip():
            out += "^{%s}" % sup
        return out + " " + e

    if tag == M + "func":
        fname = _omml(_child(node, "fName")).strip()
        e = _omml(_child(node, "e"))
        fn = _OMML_FUNCS.get(fname, fname)
        return "%s %s" % (fn, e)

    if tag == M + "limLow":
        e = _omml(_child(node, "e"))
        lim = _omml(_child(node, "lim"))
        return r"\underset{%s}{%s}" % (lim, e)

    if tag == M + "limUpp":
        e = _omml(_child(node, "e"))
        lim = _omml(_child(node, "lim"))
        return r"\overset{%s}{%s}" % (lim, e)

    if tag == M + "m":  # 矩阵
        rows = []
        for mr in node.findall(M + "mr"):
            cells = [_omml(_child(mr, "e")) for _ in node.iter(M + "e")]  # 兜底
            cells = [_omml(c) for c in mr.findall(M + "e")]
            rows.append(" & ".join(cells))
        return r"\begin{matrix} %s \end{matrix}" % r" \\ ".join(rows)

    if tag == M + "eqArr":  # 多行公式
        rows = [_omml(e) for e in node.findall(M + "e")]
        return r"\begin{aligned} %s \end{aligned}" % r" \\ ".join(rows)

    if tag == M + "bar":
        e = _omml(_child(node, "e"))
        return r"\overline{%s}" % e

    if tag == M + "acc":
        e = _omml(_child(node, "e"))
        return r"\hat{%s}" % e

    # 兜底：把子树文本拼起来
    return "".join(_omml(c) for c in node)


def _omml_blocks(el) -> list[tuple[str, str]]:
    """按出现顺序返回 [("text", "...") | ("math", "latex")]。"""
    out: list[tuple[str, str]] = []
    for child in el.iterchildren():
        tag = child.tag
        if tag == M + "oMath":
            out.append(("math", _omml(child)))
        elif tag == M + "oMathPara":
            for om in child.findall(M + "oMath"):
                out.append(("math", _omml(om)))
        elif tag.endswith("}r"):
            for t in child.iter(W + "t"):
                out.append(("text", t.text or ""))
            for blip in child.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip"):
                rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
                if rid:
                    out.append(("image", rid))
        elif tag.endswith("}hyperlink"):
            for t in child.iter(W + "t"):
                out.append(("text", t.text or ""))
    return out


# ---------------- docx ----------------

def _soffice_path() -> str | None:
    cand = [
        os.environ.get("SOFFICE_PATH"),
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    for c in cand:
        if c and Path(c).exists():
            return str(c)
    return None


def sniff_format(data: bytes) -> str:
    """按文件头判断真实格式，返回 docx / ole / html / mhtml / rtf / pdf / zip / text。

    扩展名不可靠的典型场景：
    - Word「另存为网页」存出的 .doc，实际是带 BOM 的 HTML
    - 期刊系统/投稿平台导出的 .docx，实际是 RTF 或 HTML
    - 邮件里下载的 .doc，实际是 MHTML（单个文件网页）
    """
    head = data[:4096]
    if head.startswith(_OLE_MAGIC):
        return "ole"
    if head.startswith(b"PK\x03\x04"):
        try:
            import io
            import zipfile
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
            if any(n == "word/document.xml" for n in names):
                return "docx"
            if any(n.startswith("xl/") for n in names):
                return "xlsx"
            if any(n.startswith("ppt/") for n in names):
                return "pptx"
            return "zip"
        except Exception:
            return "zip"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head[:5] == b"{\\rtf":
        return "rtf"
    if head.startswith(b"\x1f\x8b"):
        return "gzip"

    text = head
    for bom in (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff"):
        if text.startswith(bom):
            text = text[len(bom):]
            break
    low = text.lstrip()[:1024].lower()
    if low.startswith(b"mime-version") or b"mime-version:" in text[:2048].lower():
        return "mhtml"
    if b"<html" in low or low.startswith(b"<!doctype html") or low.startswith(b"<?xml"):
        if b"<html" in text[:4096].lower():
            return "html"
    return "text"


def _soffice_convert(data: bytes, target: str, src_ext: str) -> Path:
    """调 LibreOffice 做一次无头转换。

    target 必须带 filter 名（如 "docx:MS Word 2007 XML"）。只用裸扩展名时，
    LibreOffice 在部分平台上解析不到导出过滤器，会报 "no export filter ... found"。
    源文件写成 ASCII 短名，避免长中文名 + 破折号在 Windows 命令行上的问题。
    """
    soffice = _soffice_path()
    if not soffice:
        raise IngestError("本机未找到 LibreOffice")
    tmpdir = Path(tempfile.mkdtemp(prefix="acw_conv_"))
    src = tmpdir / ("input" + src_ext)
    src.write_bytes(data)
    profile = tmpdir / "profile"
    cmd = [
        soffice, "--headless", "--norestore", "--nolockcheck",
        f"-env:UserInstallation=file:///{profile.as_posix().lstrip('/')}",
        "--convert-to", target, "--outdir", str(tmpdir), str(src),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise IngestError("LibreOffice 转换超时（120 秒）")
    out_ext = target.split(":", 1)[0]
    out = tmpdir / ("input." + out_ext)
    if not out.exists() or out.stat().st_size == 0:
        msg = (r.stderr or b"") .decode("utf-8", "ignore") or (r.stdout or b"").decode("utf-8", "ignore")
        raise IngestError(msg.strip()[:300] or "LibreOffice 未产出文件")
    return out


def doc_to_docx(data: bytes, filename: str) -> Path:
    """老式 .doc（OLE 二进制）：用 LibreOffice 转 docx，独立 profile 不抢用户实例。"""
    if not _soffice_path():
        raise IngestError(
            "这是老式 .doc（二进制）格式，本机未找到 LibreOffice，无法解析。"
            "请在 Word 里「另存为 .docx」后重新上传。"
        )
    try:
        return _soffice_convert(data, "docx:MS Word 2007 XML", ".doc")
    except IngestError as e:
        raise IngestError(f"LibreOffice 未能转换该 .doc 文件：{e}")


def doc_to_text(data: bytes, src_ext: str = ".doc") -> str:
    """降级路径：只抽纯文本（表格结构、图片、公式会丢失，但正文不丢）。"""
    if not _soffice_path():
        raise IngestError("本机未找到 LibreOffice，无法读取该二进制文档")
    out = _soffice_convert(data, "txt:Text (encoded):UTF8", src_ext)
    raw = out.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def rtf_to_text(data: bytes) -> str:
    """轻量 RTF -> 纯文本（不依赖 LibreOffice 的兜底）。"""
    s = data.decode("latin-1", "ignore")
    s = re.sub(r"\{\\\*[^{}]*\}", "", s)              # 目标组：字体表、样式表等
    s = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes([int(m.group(1), 16)]).decode("latin-1"), s)
    s = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), s)
    s = s.replace("\\par", "\n").replace("\\line", "\n").replace("\\tab", "\t")
    s = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", s)          # 其余控制字
    s = s.replace("\\{", "{").replace("\\}", "}").replace("\\\\", "\\")
    s = re.sub(r"[{}]", "", s)
    s = re.sub(r"[ \t]+\n", "\n", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip() + "\n"


def mhtml_to_html(data: bytes) -> str:
    """Word「另存为单个文件网页」得到的 .doc 是 MHTML，取出其中的 text/html 部分。"""
    import email
    msg = email.message_from_bytes(data)
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True) or b""
            return payload.decode(part.get_content_charset() or "utf-8", "ignore")
    # 退化：整体按 quoted-printable 解一次再交给 HTML 解析
    import quopri
    body = data.split(b"\r\n\r\n", 1)[-1]
    return quopri.decodestring(body).decode("utf-8", "ignore")


def docx_to_markdown(path: Path | str) -> dict:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    path = Path(path)
    doc = Document(str(path))
    body = doc.element.body
    parts: list[str] = []
    images: list[str] = []
    warnings: list[str] = []

    def para_md(p: Paragraph) -> str:
        base = p.style.name if p.style is not None else ""
        level = 0
        m1 = re.match(r"(?:Heading|标题)\s*(\d)", base or "")
        if m1:
            level = min(int(m1.group(1)), 4)
        elif (base or "").lower() in ("title", "标题"):
            level = 1

        chunks: list[str] = []
        raw = _omml_blocks(p._p)
        # 段落内除公式外是否还有正文——决定公式按行内还是独立成段处理
        has_text = any(k == "text" and v.strip() for k, v in raw)
        for kind, val in raw:
            if kind == "text":
                chunks.append(val)
            elif kind == "math":
                tex = val.strip()
                if not tex:
                    continue
                # 整段只有公式 -> 独立成段（$$），否则行内（$）
                if not has_text or len(tex) >= 80 or "\n" in tex:
                    chunks.append(f"\n$$\n{tex}\n$$\n")
                else:
                    chunks.append(f"${tex}$")
            elif kind == "image":
                try:
                    part = doc.part.related_parts[val]
                    blob = part.blob
                    ext = "." + (getattr(part, "ext", None) or "png")
                    url = _save_bytes(blob, ext)
                    images.append(url)
                    chunks.append(f"\n![]({url})\n")
                except Exception:
                    warnings.append("有一张图片未能抽取")

        text = "".join(chunks)
        if not text.strip():
            return ""
        text = text.strip()
        if level:
            return "#" * level + " " + text
        style_l = (base or "").lower()
        if "list bullet" in style_l or "列表段落" in (base or ""):
            return "- " + text
        if "list number" in style_l:
            return "1. " + text
        if "quote" in style_l or "引用" in (base or ""):
            return "> " + text
        return text

    def table_md(t: Table) -> str:
        rows = []
        for row in t.rows:
            cells, seen = [], []
            for cell in row.cells:
                tc = cell._tc            # lxml 同一节点返回同一代理，用 is 判断合并单元格
                if any(tc is s for s in seen):
                    cells.append("")
                    continue
                seen.append(tc)
                cells.append(_md_escape_cell(cell.text))
            rows.append(cells)
        if not rows:
            return ""
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        head = "| " + " | ".join(rows[0]) + " |"
        sep = "| " + " | ".join(["---"] * width) + " |"
        body_rows = ["| " + " | ".join(r) + " |" for r in rows[1:]]
        return "\n".join([head, sep] + body_rows)

    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            md = para_md(Paragraph(child, doc))
            if md:
                parts.append(md)
        elif child.tag.endswith("}tbl"):
            md = table_md(Table(child, doc))
            if md:
                parts.append(md)

    # 段落间空行；标题前后留空行
    text = "\n\n".join(p for p in parts if p.strip())
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return {"markdown": text, "images": images, "warnings": warnings}


# ---------------- LaTeX ----------------

_TEX_SECTION_RE = re.compile(r"\\(chapter|section|subsection|subsubsection)\*?\{([^}]*)\}")


def tex_to_markdown(src: str) -> dict:
    """LaTeX 原样保留（模型读 LaTeX 无障碍），顶部附一份结构大纲便于定位章节。"""
    outline = []
    for m in _TEX_SECTION_RE.finditer(src):
        lvl = {"chapter": 1, "section": 2, "subsection": 3, "subsubsection": 4}[m.group(1)]
        outline.append("#" * lvl + " " + m.group(2).strip())
    head = ""
    if outline:
        head = ("<!-- 由 .tex 解析出的章节结构，正文保留 LaTeX 原文 -->\n"
                + "\n".join(outline) + "\n\n---\n\n")
    return {"markdown": head + src, "images": [], "warnings": [
        "已保留 LaTeX 原文：表格（tabular）与公式在预览中按源码显示，导出时可还原为 Word 表格与公式。"
    ]}


# ---------------- HTML（含 Word/网页剪贴板） ----------------

def html_to_markdown(html: str) -> dict:
    from lxml import html as LH

    html = html.lstrip("\ufeff").strip()
    try:
        tree = LH.fromstring(html)
    except Exception as e:
        raise IngestError(f"HTML 解析失败：{e}")

    for bad in tree.xpath("//script|//style|//meta|//link"):
        bad.getparent().remove(bad)

    images: list[str] = []

    def inner_html(el) -> str:
        """元素的内部内容（含自身 text 与各子节点的 tail）。"""
        parts = [el.text or ""]
        for c in el:
            parts.append(inline(c))
            parts.append(c.tail or "")
        return "".join(parts)

    def inline(el) -> str:
        tag = (el.tag or "").lower() if isinstance(el.tag, str) else ""
        if tag in ("strong", "b"):
            return f"**{inner_html(el)}**"
        if tag in ("em", "i"):
            return f"*{inner_html(el)}*"
        if tag == "br":
            return "\n"
        if tag == "sup":
            return "^" + (inner_html(el) or "")
        if tag == "sub":
            return "_" + (inner_html(el) or "")
        if tag == "a":
            txt = inner_html(el)
            href = el.get("href") or ""
            return f"[{txt}]({href})" if href else txt
        if tag == "code":
            return "`" + (el.text or "") + "`"
        if tag == "img":
            src = el.get("src") or ""
            alt = el.get("alt") or ""
            if src.startswith("data:image/"):
                try:
                    import base64
                    head, b64 = src.split(",", 1)
                    ext = "." + head.split("/")[1].split(";")[0]
                    url = _save_bytes(base64.b64decode(b64), ext)
                    images.append(url)
                    return f"\n![]({url})\n"
                except Exception:
                    return ""
            if src.startswith("file:") or src.startswith("blob:"):
                return f"\n![{alt}]\n"
            return f"\n![{alt}]({src})\n"
        return inner_html(el)

    def block(el, depth=0) -> list[str]:
        out: list[str] = []
        tag = (el.tag or "").lower() if isinstance(el.tag, str) else ""
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            lvl = int(tag[1])
            out.append("#" * min(lvl, 4) + " " + inline(el).strip())
        elif tag == "p":
            txt = inline(el).strip()
            if txt:
                out.append(txt)
        elif tag == "table":
            rows = []
            for tr in el.xpath(".//tr"):
                cells = []
                for td in tr.xpath("./td|./th"):
                    cells.append(_md_escape_cell(inline(td)))
                if cells:
                    rows.append(cells)
            if rows:
                w = max(len(r) for r in rows)
                rows = [r + [""] * (w - len(r)) for r in rows]
                # GFM 表格必须连续行，整张表作为单个块输出
                tbl = ["| " + " | ".join(rows[0]) + " |",
                       "| " + " | ".join(["---"] * w) + " |"]
                for r in rows[1:]:
                    tbl.append("| " + " | ".join(r) + " |")
                out.append("\n".join(tbl))
        elif tag in ("ul", "ol"):
            items = []
            for i, li in enumerate(el.xpath("./li"), 1):
                txt = inline(li).strip()
                prefix = (f"{i}. " if tag == "ol" else "- ")
                items.append("  " * depth + prefix + txt)
                for sub in li.xpath("./ul|./ol"):
                    items.extend(block(sub, depth + 1))
            if items:
                out.append("\n".join(items))
        elif tag == "pre":
            out.append("```\n" + ("".join(el.itertext()) or "").strip() + "\n```")
        elif tag == "blockquote":
            txt = " ".join(inline(el).split())
            if txt:
                out.append("> " + txt)
        else:
            for c in el:
                out.extend(block(c, depth))
            if tag in ("div", "section", "article", "body") and not len(el):
                txt = inline(el).strip()
                if txt:
                    out.append(txt)
        return out

    root = tree.body if tree.body is not None else tree
    lines: list[str] = []
    for c in root:
        try:
            lines.extend(block(c))
        except Exception:
            continue
    if not lines:
        txt = " ".join((root.text_content() or "").split())
        if txt:
            lines.append(txt)
    text = _dedupe_headings("\n\n".join(lines))
    return {"markdown": re.sub(r"\n{3,}", "\n\n", text).strip() + "\n",
            "images": images, "warnings": []}


def _dedupe_headings(md: str) -> str:
    """去掉紧邻的重复标题。

    Word「另存为网页」常见结构是 <h2>摘要</h2><h4>摘要</h4>，
    转出来会出现两级同名标题，正文其实只有一份。
    """
    out: list[str] = []
    for line in md.split("\n"):
        m = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if m:
            title = re.sub(r"^[0-9.、]+\s*", "", m.group(2)).strip()
            j = len(out) - 1
            while j >= 0 and not out[j].strip():      # 允许中间只隔空行
                j -= 1
            if j >= 0:
                pm = re.match(r"^(#{1,6})\s+(.*?)\s*$", out[j])
                if pm:
                    ptitle = re.sub(r"^[0-9.、]+\s*", "", pm.group(2)).strip()
                    if title and ptitle == title:
                        # 同名相邻：保留层级更高（# 更少）的一个
                        if len(m.group(1)) < len(pm.group(1)):
                            out[j] = line
                            del out[j + 1:]
                        continue
        out.append(line)
    return "\n".join(out)


# ---------------- PDF ----------------

def pdf_to_markdown(data: bytes) -> dict:
    try:
        import pymupdf  # 新版包名
    except Exception:
        try:
            import fitz as pymupdf
        except Exception:
            raise IngestError("未安装 PyMuPDF，无法解析 PDF。可改用 .docx / .md / .tex 上传。")
    doc = pymupdf.open(stream=data, filetype="pdf")
    pages = []
    for i, page in enumerate(doc):
        t = page.get_text("text") or ""
        if t.strip():
            pages.append(t.strip())
        # 页面图片（仅抽取位图，版式无法还原）
    doc.close()
    text = "\n\n".join(pages)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)      # 段内硬换行合并
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return {"markdown": text, "images": [], "warnings": [
        "PDF 仅提取文字层：表格结构、图片与公式版式无法还原。要求高保真请上传 .docx。"
    ]}


# ---------------- 统一入口 ----------------

def _decode_bytes(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", "ignore")
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "ignore")


def ingest(filename: str, data: bytes) -> dict:
    if not data:
        raise IngestError("文件为空")
    if len(data) > MAX_BYTES:
        raise IngestError("文件超过 25MB，请压缩或拆分后上传")

    ext = Path(filename or "").suffix.lower()
    real = sniff_format(data)
    warnings: list[str] = []

    # ---- 1) 真正的 Word（OOXML）：扩展名写错也按内容解析 ----
    if real == "docx":
        if ext and ext not in DOCX_EXT:
            warnings.append(f"文件扩展名是 {ext}，实际是 Word 文档（docx），已按 Word 解析")
        tmp = Path(tempfile.mkdtemp(prefix="acw_dx_")) / "input.docx"
        tmp.write_bytes(data)
        r = docx_to_markdown(tmp)
        r["format"] = "docx"
        r["warnings"] = r.get("warnings", []) + warnings
        return r

    # ---- 2) 老式二进制 .doc（OLE）----
    if real == "ole":
        try:
            converted = doc_to_docx(data, filename)
            r = docx_to_markdown(converted)
            r["format"] = "doc"
            r["warnings"] = r.get("warnings", []) + warnings + \
                ["已将 .doc 通过 LibreOffice 转换为 docx 解析"]
            return r
        except IngestError as e:
            try:
                txt = doc_to_text(data, ".doc")
            except IngestError:
                raise IngestError(
                    f"无法读取这个 .doc 文件：{e}。"
                    "请在 Word 中「另存为 .docx」后重新上传。"
                )
            warnings.append("Word 转换失败，已降级为纯文本提取：表格结构、图片与公式可能丢失")
            return {"markdown": txt, "images": [], "warnings": warnings, "format": "doc"}

    # ---- 3) HTML / MHTML：Word「另存为网页」存出的 .doc 就是这一类 ----
    if real in ("html", "mhtml"):
        if real == "mhtml":
            html = mhtml_to_html(data)
            warnings.append("文件实际是 MHTML 网页文档，已按网页内容解析")
        else:
            html = _decode_bytes(data)
            if ext in DOC_EXT or ext in DOCX_EXT:
                warnings.append(
                    f"这个文件的扩展名是 {ext}，但内容其实是 Word 导出的 HTML"
                    "（「另存为网页」的常见结果），已按网页文档解析；"
                    "表格与公式结构保留，页眉页脚与分页会丢失"
                )
            elif ext not in HTML_EXT and ext:
                warnings.append(f"文件实际是 HTML，已按网页文档解析（扩展名 {ext}）")
        r = html_to_markdown(html)
        r["format"] = "html"
        r["warnings"] = r.get("warnings", []) + warnings
        return r

    # ---- 4) PDF ----
    if real == "pdf":
        r = pdf_to_markdown(data)
        r["format"] = "pdf"
        r["warnings"] = r.get("warnings", []) + warnings
        return r

    # ---- 5) RTF：优先 LibreOffice，缺失时用轻量解析 ----
    if real == "rtf":
        try:
            txt = doc_to_text(data, ".rtf")
        except IngestError:
            txt = rtf_to_text(data)
        warnings.append("RTF 已转为纯文本，表格结构与公式可能被简化")
        return {"markdown": txt, "images": [], "warnings": warnings, "format": "rtf"}

    # ---- 6) 其他压缩容器：明确拒绝，不假装支持 ----
    if real in ("xlsx", "pptx", "zip", "gzip"):
        raise IngestError(
            "这个文件是 " + {"xlsx": "Excel 表格", "pptx": "PowerPoint 演示文稿",
                            "zip": "压缩包", "gzip": "gzip 压缩文件"}[real] +
            "，不是 Word 文档。请上传 .docx / .doc / .md / .tex / .pdf，"
            "或把表格内容直接粘贴到输入框。"
        )

    # ---- 7) 纯文本：按扩展名区分 LaTeX 与普通文本 ----
    text = _decode_bytes(data)
    if ext in TEX_EXT:
        r = tex_to_markdown(text)
        r["format"] = "tex"
        r["warnings"] = r.get("warnings", []) + warnings
        return r
    if ext and ext not in TEXT_EXT and ext not in HTML_EXT:
        warnings.append(f"按纯文本读取（扩展名 {ext}）")
    return {"markdown": text, "images": [], "warnings": warnings,
            "format": (ext.lstrip(".") or "txt")}


# ---------------- 给规则检测用的归一化 ----------------

def normalize_for_rules(text: str) -> str:
    r"""词面检测前归一化：公式/图片语法会干扰文本正则，替换为等长占位。

    - $$...$$ / $...$ / \[...\] / \(...\) -> 空格（保留位置，不算入词频）
    - ![](url) -> alt 文本（图片说明仍参与检测）
    - 表格分隔行 |---|---| -> 去掉（避免竖线被当成正文）
    纯文本 md 不受影响，保证改造前后词面检测结果一致。
    """
    if not text:
        return text
    t = re.sub(r"\$\$[\s\S]*?\$\$", " ", text)
    t = re.sub(r"\\\[[\s\S]*?\\\]", " ", t)
    t = re.sub(r"\\\([\s\S]*?\\\)", " ", t)
    t = re.sub(r"(?<!\\)\$[^\n$]{1,300}\$", " ", t)
    t = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^\s*\|[\s:|-]+\|\s*$", "", t, flags=re.MULTILINE)
    return t
