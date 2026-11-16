# -*- coding: utf-8 -*-
"""导出：Markdown -> Word(.docx) / LaTeX(.tex)。

Word 导出要点：
- 表格生成真 Word 表格（Table Grid + 表头加粗 + 跨页重复表头）
- 公式由 LaTeX 子集转成 OMML（Word 原生公式，可双击编辑）
- 图片从 /media/<name> 读本地 uploads 文件内嵌，宽度按比例限制

LaTeX 导出要点：
- ctexart + amsmath + booktabs + graphicx，Overleaf 直接可编译
- 表格转 booktabs 三线表，公式原样保留（论文场景最需要保真的部分）
"""
from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

import paths

# 可写数据目录（打包后 = exe 同级 data/，源码运行 = 项目根）
BASE_DIR = paths.data_root()
UPLOAD_DIR = BASE_DIR / "uploads"


# =====================================================================
# 一、LaTeX 子集 -> OMML
# =====================================================================

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}

SYMBOLS = {
    "times": "×", "cdot": "⋅", "div": "÷", "pm": "±", "mp": "∓",
    "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "neq": "≠", "ne": "≠",
    "approx": "≈", "equiv": "≡", "sim": "∼", "propto": "∝", "infty": "∞",
    "partial": "∂", "nabla": "∇", "forall": "∀", "exists": "∃", "in": "∈",
    "notin": "∉", "subset": "⊂", "subseteq": "⊆", "cup": "∪", "cap": "∩",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "Rightarrow": "⇒",
    "Leftarrow": "⇐", "leftrightarrow": "↔", "mapsto": "↦",
    "ldots": "…", "cdots": "⋯", "vdots": "⋮", "ddots": "⋱",
    "angle": "∠", "perp": "⊥", "parallel": "∥", "degree": "°",
    "circ": "∘", "ast": "∗", "star": "⋆", "bullet": "∙",
    "ell": "ℓ", "hbar": "ℏ", "Re": "ℜ", "Im": "ℑ",
    "prime": "′", "emptyset": "∅", "therefore": "∴", "because": "∵",
}

FUNCS = {"sin", "cos", "tan", "cot", "sec", "csc", "log", "ln", "exp",
         "lim", "max", "min", "sup", "inf", "det", "arg", "gcd", "dim",
         "sinh", "cosh", "tanh", "mod", "bmod"}

NARY = {"sum": "∑", "prod": "∏", "int": "∫", "iint": "∬", "iiint": "∭",
        "oint": "∮", "bigcup": "⋃", "bigcap": "⋂", "bigoplus": "⨁"}

SPACES = {"quad", "qquad", " ", ",", ";", ":", "!", "enspace", "thinspace"}


class _P:
    def __init__(self, s: str):
        self.s = s
        self.i = 0

    def eof(self):
        return self.i >= len(self.s)

    def peek(self, n=1):
        return self.s[self.i:self.i + n]

    def take(self):
        c = self.s[self.i]
        self.i += 1
        return c

    def skip_ws(self):
        while not self.eof() and self.s[self.i] in " \t\n\r":
            self.i += 1

    def read_cmd(self) -> str:
        # 已消费反斜杠
        if self.eof():
            return ""
        if self.peek().isalpha():
            j = self.i
            while not self.eof() and self.s[self.i].isalpha():
                self.i += 1
            return self.s[j:self.i]
        return self.take()


def _parse_arg(p: _P):
    p.skip_ws()
    if p.eof():
        return ("run", "")
    c = p.peek()
    if c == "{":
        p.take()
        seq = _parse_seq(p, stop="}")
        if not p.eof() and p.peek() == "}":
            p.take()
        return ("seq", seq)
    if c == "\\":
        p.take()
        return _parse_cmd(p, p.read_cmd())
    return ("run", p.take())


def _parse_opt_arg(p: _P):
    p.skip_ws()
    if p.peek() != "[":
        return None
    p.take()
    depth = 1
    buf = []
    while not p.eof() and depth:
        c = p.take()
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                break
        buf.append(c)
    return "".join(buf)


def _parse_cmd(p: _P, name: str):
    if name == "frac" or name == "dfrac" or name == "tfrac":
        return ("frac", _parse_arg(p), _parse_arg(p))
    if name == "sqrt":
        deg = _parse_opt_arg(p)
        body = _parse_arg(p)
        return ("sqrt", ("seq", [("run", deg)]) if deg else None, body)
    if name in GREEK:
        return ("run", GREEK[name])
    if name in SYMBOLS:
        return ("run", SYMBOLS[name])
    if name in NARY:
        return ("nary", NARY[name])
    if name in FUNCS:
        return ("func", name)
    if name in ("text", "mathrm", "textrm", "mbox"):
        arg = _parse_arg(p)
        return ("style", "p", arg)
    if name in ("mathbf", "textbf", "bm"):
        return ("style", "b", _parse_arg(p))
    if name in ("mathit", "textit", "emph"):
        return ("style", "i", _parse_arg(p))
    if name in ("mathbb", "mathcal", "mathfrak", "mathsf", "mathtt"):
        return _parse_arg(p)          # Word 无对应字体族，退化为普通文本
    if name in ("overline", "bar"):
        return ("bar", _parse_arg(p))
    if name in ("hat", "widehat", "tilde", "widetilde", "vec", "dot", "ddot"):
        return ("accent", _parse_arg(p))
    if name in ("left", "right", "big", "Big", "bigg", "Bigg", "displaystyle",
                "textstyle", "limits", "nolimits"):
        return ("run", "")            # 括号字符本身会作为普通 run 保留
    if name in SPACES:
        return ("run", " ")
    if name == "\\":
        return ("run", "\n")
    if name in ("%", "&", "_", "#", "$", "{", "}", "[", "]"):
        return ("run", name)
    if not name:
        return ("run", "")
    # 未知命令：保留可读文本，不丢内容也不报错
    return ("run", name)


def _parse_seq(p: _P, stop=None):
    atoms = []
    while not p.eof():
        p.skip_ws()
        if p.eof():
            break
        c = p.peek()
        if stop and c == stop:
            break
        if c in "^_":
            p.take()
            arg = _parse_arg(p)
            base = atoms.pop() if atoms else ("run", "")
            if c == "^":
                if base[0] == "sub":
                    atoms.append(("subsup", base[1], base[2], arg))
                elif base[0] == "nary":
                    # 求和/积分：保留已解析的下限，再补上限
                    atoms.append(("nary", base[1], base[2], arg))
                else:
                    atoms.append(("sup", base, arg))
            else:
                if base[0] == "sup":
                    atoms.append(("subsup", base[1], arg, base[2]))
                elif base[0] == "nary":
                    atoms.append(("nary", base[1], arg, None))
                else:
                    atoms.append(("sub", base, arg))
            continue
        if c == "{":
            atoms.append(_parse_arg(p))
            continue
        if c == "\\":
            p.take()
            atoms.append(_parse_cmd(p, p.read_cmd()))
            continue
        if c == "&":
            p.take()
            atoms.append(("run", "  "))
            continue
        atoms.append(("run", p.take()))
    return atoms


_XESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}


def _xesc(s: str) -> str:
    return "".join(_XESC.get(c, c) for c in s)


def _omml_run(text: str, style: str | None = None) -> str:
    if text == "":
        return ""
    pr = ""
    if style == "p":
        pr = '<m:rPr><m:sty m:val="p"/></m:rPr>'
    elif style == "b":
        pr = '<m:rPr><m:sty m:val="b"/></m:rPr>'
    elif style == "i":
        pr = '<m:rPr><m:sty m:val="i"/></m:rPr>'
    parts = text.split("\n")
    out = []
    for k, seg in enumerate(parts):
        if k:
            out.append("<m:br/>")
        if seg:
            out.append(f'<m:r>{pr}<m:t xml:space="preserve">{_xesc(seg)}</m:t></m:r>')
    return "".join(out)


def _omml(node) -> str:
    if node is None:
        return ""
    kind = node[0]
    if kind == "run":
        return _omml_run(node[1])
    if kind == "seq":
        # 求和/积分符号后面紧跟的表达式要吸进 m:e，否则 Word 会显示空占位框
        items = node[1]
        out = []
        i = 0
        while i < len(items):
            it = items[i]
            if it[0] == "nary" and len(it) == 4 and i + 1 < len(items):
                body = items[i + 1]
                if body[0] not in ("run",) or (body[0] == "run" and body[1].strip()):
                    out.append(_omml(("nary", it[1], it[2], it[3], body)))
                    i += 2
                    continue
            out.append(_omml(it))
            i += 1
        return "".join(out)
    if kind == "func":
        return _omml_run(node[1], "p")
    if kind == "style":
        return f'<m:r><m:rPr><m:sty m:val="{node[1]}"/></m:rPr><m:t xml:space="preserve">{_xesc(_plain(node[2]))}</m:t></m:r>'
    if kind == "frac":
        return f"<m:f><m:num>{_omml(node[1])}</m:num><m:den>{_omml(node[2])}</m:den></m:f>"
    if kind == "sqrt":
        deg = node[1]
        if deg is None:
            return ('<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/>'
                    f"<m:e>{_omml(node[2])}</m:e></m:rad>")
        return f"<m:rad><m:deg>{_omml(deg)}</m:deg><m:e>{_omml(node[2])}</m:e></m:rad>"
    if kind == "sup":
        return f"<m:sSup><m:e>{_omml(node[1])}</m:e><m:sup>{_omml(node[2])}</m:sup></m:sSup>"
    if kind == "sub":
        return f"<m:sSub><m:e>{_omml(node[1])}</m:e><m:sub>{_omml(node[2])}</m:sub></m:sSub>"
    if kind == "subsup":
        return (f"<m:sSubSup><m:e>{_omml(node[1])}</m:e><m:sub>{_omml(node[2])}</m:sub>"
                f"<m:sup>{_omml(node[3])}</m:sup></m:sSubSup>")
    if kind == "nary":
        chr_ = node[1]
        sub = node[2]
        sup = node[3]
        body = node[4] if len(node) > 4 else None
        pr = f'<m:naryPr><m:chr m:val="{chr_}"/><m:limLoc m:val="undOvr"/>'
        if sub is None:
            pr += '<m:subHide m:val="1"/>'
        if sup is None:
            pr += '<m:supHide m:val="1"/>'
        pr += "</m:naryPr>"
        e = _omml(body) if body is not None else ""
        return (f"<m:nary>{pr}<m:sub>{_omml(sub) if sub else ''}</m:sub>"
                f"<m:sup>{_omml(sup) if sup else ''}</m:sup><m:e>{e}</m:e></m:nary>")
    if kind == "bar":
        return f"<m:bar><m:barPr><m:pos m:val=\"top\"/></m:barPr><m:e>{_omml(node[1])}</m:e></m:bar>"
    if kind == "accent":
        return f'<m:acc><m:accPr><m:chr m:val="̂"/></m:accPr><m:e>{_omml(node[1])}</m:e></m:acc>'
    if kind == "matrix":
        rows = node[2]
        body = "".join(
            "<m:mr>" + "".join(f"<m:e>{_omml(c)}</m:e>" for c in row) + "</m:mr>"
            for row in rows
        )
        return f"<m:m>{body}</m:m>"
    return ""


def _plain(node) -> str:
    """把节点树压平成纯文本（用于 \text{} 之类）。"""
    if node is None:
        return ""
    kind = node[0]
    if kind == "run":
        return node[1]
    if kind == "seq":
        return "".join(_plain(n) for n in node[1])
    if kind in ("style", "sqrt", "bar", "accent"):
        return _plain(node[-1])
    if kind == "frac":
        return _plain(node[1]) + "/" + _plain(node[2])
    if kind in ("sup", "sub"):
        return _plain(node[1])
    return ""


_MATRIX_ENVS = ("matrix", "pmatrix", "bmatrix", "vmatrix", "Vmatrix", "array", "cases")


def _split_matrix(body: str):
    """按 \\ 拆行、按 & 拆列。"""
    body = re.sub(r"\\begin\{[a-zA-Z*]+\}(?:\{[^}]*\})?", "", body)
    body = re.sub(r"\\end\{[a-zA-Z*]+\}", "", body)
    rows = re.split(r"\\\\", body)
    out = []
    for r in rows:
        r = r.strip()
        if not r:
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)&", r)]
        out.append([_parse_seq(_P(c)) for c in cells])
    return out


_TAG_RE = re.compile(r"\\tag\*?\s*\{([^{}]*)\}")
_SIZE_CMDS = ("biggl", "biggr", "Biggl", "Biggr", "bigl", "bigr", "Bigl", "Bigr")
_STAT_NOTE_RE = re.compile(r"\n(?:\s*---\s*\n+)?###\s*生成说明.*\Z", re.S)


def _strip_stat_note(md: str) -> str:
    """去掉稿件末尾的「生成说明」块：它是给人看的开发备注，不该进交付文档。"""
    return _STAT_NOTE_RE.sub("", str(md or "")).rstrip()


def _latex_fixups(tex: str) -> str:
    r"""把 Word/AMS 不认识的写法收敛成解析器能处理的形式。

    - \tag{1}  -> \qquad\text{(1)}：原来会变成字面量 "tag1"
    - \bigl( / \bigr) -> 去掉尺寸命令，括号本身保留（原来变成 "bigl("）
    - \boldsymbol{X} -> \mathbf{X}：原来变成 "boldsymbolθ"
    - \operatorname{X} -> \mathrm{X}
    """
    s = str(tex or "")

    def _tag(m):
        num = m.group(1).strip()
        return r"\qquad\text{(" + num + ")}" if num else ""

    s = _TAG_RE.sub(_tag, s)
    for c in _SIZE_CMDS:
        s = s.replace("\\" + c, "")
    s = s.replace("\\boldsymbol", "\\mathbf")
    s = re.sub(r"\\operatorname\*?\s*\{", r"\\mathrm{", s)
    s = re.sub(r"\\ensuremath\s*\{", "{", s)
    return s


def latex_to_omml(latex: str, display: bool = False) -> str | None:
    """LaTeX -> <m:oMath>。解析失败返回 None（调用方降级为文本）。"""
    if not latex or not latex.strip():
        return None
    latex = _latex_fixups(latex)
    src = latex.strip()
    # 环境：矩阵 / cases 走专用拆分
    m = re.search(r"\\begin\{([a-zA-Z*]+)\}", src, re.M)
    if m and m.group(1).rstrip("*") in _MATRIX_ENVS:
        env = m.group(1).rstrip("*")
        rows = _split_matrix(src)
        if not rows:
            return None
        node = ("matrix", env, rows)
        return f'<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">{_omml(node)}</m:oMath>'
    if m:  # align/gather 等：按 \\ 拆成多行，用 eqArr 表达
        env = m.group(1).rstrip("*")
        body = re.sub(r"\\begin\{[a-zA-Z*]+\}", "", src)
        body = re.sub(r"\\end\{[a-zA-Z*]+\}", "", body)
        rows = [r for r in re.split(r"\\\\", body) if r.strip()]
        if not rows:
            return None
        inner = "".join(
            f"<m:e>{''.join(_omml(n) for n in _parse_seq(_P(r.replace('&', ' '))))}</m:e>"
            for r in rows
        )
        return ('<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
                f"<m:eqArr>{inner}</m:eqArr></m:oMath>")
    try:
        seq = _parse_seq(_P(src))
        inner = "".join(_omml(n) for n in seq)
    except Exception:
        return None
    if not inner.strip():
        return None
    return f'<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">{inner}</m:oMath>'


# =====================================================================
# 二、Markdown 块解析（docx / tex 共用）
# =====================================================================

_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def split_math(md: str):
    """抽取公式，返回 (含占位符的文本, [(tex, display), ...])。"""
    store = []

    def put(tex, display):
        store.append((tex, display))
        return f"\u0002MJ{len(store) - 1}\u0002"

    s = md or ""
    s = re.sub(r"\$\$([\s\S]+?)\$\$", lambda m: put(m.group(1), True), s)
    s = re.sub(r"\\\[([\s\S]+?)\\\]", lambda m: put(m.group(1), True), s)
    s = re.sub(
        r"\\begin\{(equation\*?|align\*?|gather\*?|multline\*?|eqnarray\*?|split|aligned|cases|matrix|pmatrix|bmatrix|array)\}([\s\S]+?)\\end\{\1\}",
        lambda m: put(f"\\begin{{{m.group(1)}}}{m.group(2)}\\end{{{m.group(1)}}}", True), s)
    s = re.sub(r"\\\(([\s\S]+?)\\\)", lambda m: put(m.group(1), False), s)
    s = re.sub(r"(?<!\\)\$([^\n$]{1,300}?)\$", lambda m: put(m.group(1), False), s)
    return s, store


def iter_blocks(md: str):
    """把 markdown 拆成块：(kind, payload)。"""
    lines = (md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        # 代码块
        if line.strip().startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            yield ("code", "\n".join(buf))
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            yield ("heading", (len(m.group(1)), m.group(2).strip()))
            i += 1
            continue

        # 分隔线
        if re.match(r"^\s*([-*_])\1{2,}\s*$", line):
            yield ("hr", None)
            i += 1
            continue

        # 表格
        if "|" in line and i + 1 < n and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*\s*$", lines[i + 1]):
            rows = []
            header = line
            i += 2
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(lines[i])
                i += 1
            yield ("table", (header, rows))
            continue

        # 引用
        if line.lstrip().startswith(">"):
            buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            yield ("quote", "\n".join(buf))
            continue

        # 列表
        m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", line)
        if m:
            items = []
            ordered = bool(re.match(r"\d", m.group(2)))
            while i < n:
                mm = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", lines[i])
                if not mm:
                    if lines[i].strip() and items and lines[i].startswith("  "):
                        items[-1] = items[-1] + " " + lines[i].strip()
                        i += 1
                        continue
                    break
                items.append((len(mm.group(1)), mm.group(3)))
                i += 1
            yield ("list", (ordered, items))
            continue

        # 独立图片行
        m = _IMG_RE.fullmatch(line.strip())
        if m:
            yield ("image", (m.group(1), m.group(2)))
            i += 1
            continue

        # 段落
        buf = []
        while i < n and lines[i].strip() and not re.match(
                r"^\s*(#{1,6}\s|```|>|\||([-*+]|\d+[.)])\s)", lines[i]):
            buf.append(lines[i].strip())
            i += 1
        if buf:
            yield ("para", " ".join(buf))


def parse_table(header: str, rows):
    def cells(line):
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|"):
            line = line[:-1]
        return [c.strip() for c in re.split(r"(?<!\\)\|", line)]

    head = cells(header)
    body = [cells(r) for r in rows]
    width = max([len(head)] + [len(r) for r in body]) if (head or body) else 0
    head += [""] * (width - len(head))
    body = [r + [""] * (width - len(r)) for r in body]
    return head, body


# =====================================================================
# 三、Markdown -> DOCX
# =====================================================================

def _omml_para(omml: str) -> str:
    """把 oMath 包成独占一行的显示公式（Word 里居中、可自动编号位置）。"""
    return ('<m:oMathPara xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
            '<m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr>'
            + omml + "</m:oMathPara>")


def _add_inline(p, text: str, math_store):
    """把一段含 **粗体** / *斜体* / `代码` / $公式$ / 链接 的文本写进段落。"""
    from docx.shared import Pt

    token = re.compile(
        r"(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`]+`|\u0002MJ\d+\u0002|!\[[^\]]*\]\([^)]+\)|\[[^\]]+\]\([^)]+\))")
    pos = 0
    for m in token.finditer(text):
        if m.start() > pos:
            p.add_run(text[pos:m.start()])
        seg = m.group(0)
        if seg.startswith("**"):
            r = p.add_run(seg[2:-2]); r.bold = True
        elif seg.startswith("`"):
            r = p.add_run(seg[1:-1]); r.font.name = "Consolas"; r.font.size = Pt(10)
        elif seg.startswith("*"):
            r = p.add_run(seg[1:-1]); r.italic = True
        elif seg.startswith("\u0002MJ"):
            idx = int(re.sub(r"\D", "", seg))
            tex, display = math_store[idx] if idx < len(math_store) else ("", False)
            omml = latex_to_omml(tex, display)
            if omml:
                from docx.oxml import parse_xml
                # 段落里还没有别的内容 => 这是独立公式，用 oMathPara 居中；
                # 否则保持行内，避免把公式从句子中间拆出去。
                p._p.append(parse_xml(_omml_para(omml) if (display and not p.runs) else omml))
            else:
                p.add_run("$" + tex + "$")
        elif seg.startswith("!["):
            mm = _IMG_RE.match(seg)
            if mm:
                _add_picture(p, mm.group(2), mm.group(1))
        else:
            mm = _LINK_RE.match(seg)
            if mm:
                p.add_run(mm.group(1))
        pos = m.end()
    if pos < len(text):
        p.add_run(text[pos:])


def _resolve_image(src: str):
    """图片路径解析：/media/、uploads/、绝对路径、相对项目根目录都试一遍。"""
    s = str(src or "").strip()
    if not s or s.startswith("http"):
        return None
    name = s.split("/")[-1]
    cands = []
    if s.startswith("/media/") or s.startswith("media/"):
        cands.append(UPLOAD_DIR / name)
    p = Path(s)
    if p.is_absolute():
        cands.append(p)
    root = paths.data_root()  # 图片相对路径按可写数据目录解析（打包后 = exe 同级 data/）
    cands += [UPLOAD_DIR / name, root / s.lstrip("/"), root / "uploads" / name, Path.cwd() / s.lstrip("/")]
    for c in cands:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def _add_picture(p, src: str, alt: str = ""):
    from docx.shared import Inches
    try:
        path = _resolve_image(src)
        if path:
            p.add_run().add_picture(str(path), width=Inches(5.6))
            return
        p.add_run(f"[图片未找到] {alt or src}")
    except Exception:
        p.add_run(f"[图片未找到] {alt or src}")


def _set_normal_style(doc):
    from docx.shared import Pt
    from docx.oxml.ns import qn

    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    st.paragraph_format.space_after = Pt(6)
    st.paragraph_format.line_spacing = 1.35


def _fit_table(table, head, body):
    """按内容长度分配列宽（总宽 16cm），避免定义列被挤成两行。"""
    from docx.shared import Cm

    def disp(s):
        return sum(2 if ord(ch) > 127 else 1 for ch in (s or ""))

    ncol = len(head)
    if not ncol:
        return
    raw = []
    for j in range(ncol):
        w = 0
        for row in [head] + body:
            if j < len(row):
                w = max(w, disp(row[j]))
        raw.append(max(w, 4))
    total_raw = sum(raw) or 1
    widths = [max(2.0, 16.0 * w / total_raw) for w in raw]
    scale = 16.0 / sum(widths)
    widths = [w * scale for w in widths]
    table.autofit = False
    # 同时写 tblGrid 与 tcW：Word 认 tcW，LibreOffice/WPS 认 gridCol，两边都要给
    from docx.oxml.ns import qn

    for row in table.rows:
        for j, cell in enumerate(row.cells):
            if j < len(widths):
                cell.width = Cm(widths[j])
    grid = table._tbl.tblGrid
    if grid is not None:
        for gc, w in zip(grid.findall(qn("w:gridCol")), widths):
            gc.set(qn("w:w"), str(int(w * 567)))


def markdown_to_docx(md: str, title: str | None = None) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement, parse_xml
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    md = _strip_stat_note(md)
    doc = Document()
    _set_normal_style(doc)

    if title:
        h = doc.add_heading(title, level=0)
        for r in h.runs:
            r.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)

    placeholder_md, store = split_math(md)

    for kind, payload in iter_blocks(placeholder_md):
        if kind == "heading":
            lvl, txt = payload
            h = doc.add_heading("", level=min(lvl, 4))
            _add_inline(h, txt, store)
            for r in h.runs:
                r.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)
        elif kind == "para":
            p = doc.add_paragraph()
            _add_inline(p, payload, store)
        elif kind == "list":
            ordered, items = payload
            for _, txt in items:
                p = doc.add_paragraph(style="List Number" if ordered else "List Bullet")
                _add_inline(p, txt, store)
        elif kind == "table":
            head, body = parse_table(*payload)
            if not head:
                continue
            t = doc.add_table(rows=1, cols=len(head))
            t.style = "Table Grid"
            t.autofit = True
            for j, c in enumerate(head):
                cell = t.rows[0].cells[j]
                cell.text = ""
                _add_inline(cell.paragraphs[0], c, store)
                for r in cell.paragraphs[0].runs:
                    r.bold = True
            # 跨页重复表头
            trPr = t.rows[0]._tr.get_or_add_trPr()
            th = OxmlElement("w:tblHeader")
            th.set(qn("w:val"), "true")
            trPr.append(th)
            for row in body:
                cells = t.add_row().cells
                for j, c in enumerate(row[:len(head)]):
                    cells[j].text = ""
                    _add_inline(cells[j].paragraphs[0], c, store)
            _fit_table(t, head, body)
            doc.add_paragraph()
        elif kind == "code":
            p = doc.add_paragraph()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:fill"), "F4F5F7")
            p._p.get_or_add_pPr().append(shd)
            r = p.add_run(payload)
            r.font.name = "Consolas"
            r.font.size = Pt(9.5)
        elif kind == "quote":
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Pt(18)
            for r in p.runs:
                r.italic = True
            _add_inline(p, payload, store)
        elif kind == "hr":
            p = doc.add_paragraph()
            pPr = p._p.get_or_add_pPr()
            pbdr = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "6")
            bottom.set(qn("w:color"), "CCCCCC")
            pbdr.append(bottom)
            pPr.append(pbdr)
        elif kind == "image":
            alt, src = payload
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _add_picture(p, src, alt)

    # 独立成段的块级公式（占位符独占段落）→ 居中显示
    for p in doc.paragraphs:
        if p.text.strip().startswith("\u0002MJ"):
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


# =====================================================================
# 四、Markdown -> LaTeX
# =====================================================================

_UNI2TEX = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\epsilon",
    "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta", "ι": r"\iota", "κ": r"\kappa",
    "λ": r"\lambda", "μ": r"\mu", "ν": r"\nu", "ξ": r"\xi", "π": r"\pi",
    "ρ": r"\rho", "σ": r"\sigma", "τ": r"\tau", "υ": r"\upsilon", "φ": r"\phi",
    "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega", "Γ": r"\Gamma", "Δ": r"\Delta",
    "Θ": r"\Theta", "Λ": r"\Lambda", "Ξ": r"\Xi", "Π": r"\Pi", "Σ": r"\Sigma",
    "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega",
    "×": r"\times", "÷": r"\div", "±": r"\pm", "≤": r"\leq", "≥": r"\geq",
    "≠": r"\neq", "≈": r"\approx", "∞": r"\infty", "∂": r"\partial",
    "∇": r"\nabla", "∈": r"\in", "⊂": r"\subset", "⊆": r"\subseteq",
    "∪": r"\cup", "∩": r"\cap", "→": r"\rightarrow", "←": r"\leftarrow",
    "⇒": r"\Rightarrow", "⇐": r"\Leftarrow", "↔": r"\leftrightarrow",
    "∑": r"\sum", "∏": r"\prod", "∫": r"\int", "∮": r"\oint",
    "…": r"\ldots", "⋯": r"\cdots", "√": r"\sqrt", "∝": r"\propto",
    "≡": r"\equiv", "∼": r"\sim", "∠": r"\angle", "⊥": r"\perp",
    "°": r"^{\circ}", "−": "-", "∗": "*", "⋅": r"\cdot",
}

_TEX_ESC = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
            "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
            "^": r"\textasciicircum{}"}


def _tex_escape(s: str, unicode_map=True) -> str:
    out = []
    for c in s:
        if c in _TEX_ESC:
            out.append(_TEX_ESC[c])
        elif unicode_map and c in _UNI2TEX:
            v = _UNI2TEX[c]
            out.append(v if v.startswith("^") is False else "$" + v + "$")
        else:
            out.append(c)
    return "".join(out)


def _tex_inline(s: str, store) -> str:
    """行内 md -> LaTeX，公式占位符还原为 $...$。"""
    token = re.compile(r"(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`]+`|\u0002MJ\d+\u0002|\[[^\]]+\]\([^)]+\))")
    out = []
    pos = 0
    for m in token.finditer(s):
        if m.start() > pos:
            out.append(_tex_escape(s[pos:m.start()]))
        seg = m.group(0)
        if seg.startswith("**"):
            out.append(r"\textbf{" + _tex_escape(seg[2:-2]) + "}")
        elif seg.startswith("`"):
            out.append(r"\texttt{" + _tex_escape(seg[1:-1]) + "}")
        elif seg.startswith("*"):
            out.append(r"\emph{" + _tex_escape(seg[1:-1]) + "}")
        elif seg.startswith("\u0002MJ"):
            idx = int(re.sub(r"\D", "", seg))
            tex, display = store[idx] if idx < len(store) else ("", False)
            tex = _tex_math_unicode(tex.strip())
            if display:
                out.append("\n\\[\n" + tex + "\n\\]\n")
            else:
                out.append("$" + tex + "$")
        else:
            mm = _LINK_RE.match(seg)
            if mm:
                out.append(r"\href{" + mm.group(2) + "}{" + _tex_escape(mm.group(1)) + "}")
        pos = m.end()
    if pos < len(s):
        out.append(_tex_escape(s[pos:]))
    return "".join(out)


# 公式内的 Unicode 数学符号 -> LaTeX 命令（保证 pdfLaTeX 也能编译）
_MATH_UNI = {k: v for k, v in _UNI2TEX.items() if k not in ("√", "°", "−")}
_MATH_UNI["−"] = "-"
_MATH_UNI["°"] = r"^{\circ}"


def _tex_math_unicode(tex: str) -> str:
    """公式内 Unicode 符号转 LaTeX 命令；只在替换处补空格，不动原有命令。"""
    out = []
    for i, c in enumerate(tex):
        rep = _MATH_UNI.get(c)
        if rep is None:
            out.append(c)
            continue
        nxt = tex[i + 1] if i + 1 < len(tex) else ""
        # \Delta 紧跟变量名会拼成未定义命令 \DeltaY
        if rep and rep[-1].isalpha() and nxt.isalpha():
            rep = rep + " "
        out.append(rep)
    return "".join(out)


def _strip_heading_number(txt: str) -> str:
    """剥掉标题里手写的 "1" / "1.2" 编号，避免与 \\section 自动编号重复。"""
    return re.sub(r"^\s*\d+(?:\.\d+)*[.、]?\s+", "", txt)


def _tex_colspec(head, body) -> str:
    """中文长单元格用定宽列，避免 Overleaf 里表格溢出页面。"""
    longest = 0
    for row in [head] + body:
        for c in row:
            w = sum(2 if ord(ch) > 127 else 1 for ch in (c or ""))
            longest = max(longest, w)
    if longest > 24 and len(head) <= 5:
        w = round(0.88 / max(len(head), 1), 2)
        return "p{%.2f\\linewidth}" % w * len(head)
    return "l" * len(head)


def _same_heading(a: str, b: str) -> bool:
    norm = lambda x: re.sub(r"\s+", " ", str(x or "")).strip().lower()
    return bool(norm(a)) and norm(a) == norm(b)


def _tex_heading_base(md: str, title: str) -> int:
    """判断稿件开头的一级标题是「文章标题」还是「章节」。

    生成稿的结构是 `# 文章标题` + 若干 `## 章节`。若直接按层级映射，
    整篇会变成「一个 section + 若干 subsection」，编号与目录全错。

    判定规则：全文只有一个 H1、且后面出现过 H2、并且它长得像标题（或与传入 title 相同）
    -> 视为文章标题，正文层级整体上移一级。多个 H1 时按章节处理，不做上移。
    """
    levels, first = [], None
    for kind, payload in iter_blocks(md):
        if kind != "heading":
            continue
        lvl, txt = payload
        if first is None:
            first = (lvl, txt)
        levels.append(lvl)
    if not levels or levels[0] != 1:
        return 0
    if levels.count(1) != 1 or 2 not in levels:
        return 0
    if _same_heading(first[1], title):
        return 1
    # 后面所有标题都更深，且首行不是「1. Introduction」这类章节编号开头
    return 0 if re.match(r"^\s*\d+[.、)]\s", str(first[1])) else 1


def markdown_to_tex(md: str, title: str = "PaperMate 生成结果") -> str:
    md = _strip_stat_note(md)
    body_md, store = split_math(md)
    base = _tex_heading_base(md, title)
    title_skipped = False
    lines: list[str] = []
    for kind, payload in iter_blocks(body_md):
        if kind == "heading":
            lvl, txt = payload
            text_out = _tex_inline(_strip_heading_number(txt), store)
            if lvl == 1 and base == 1 and not title_skipped:
                title_skipped = True          # 第一个 H1 是文章标题，已由 maketitle 输出
                continue
            if re.match(r"^(references|bibliography|参考文献)$", str(txt).strip(), re.I):
                lines.append("\\section*{%s}" % text_out)
                lines.append("\\addcontentsline{toc}{section}{%s}" % text_out)
                continue
            idx = max(1, min(lvl - base, 4))
            cmd = ["section", "subsection", "subsubsection", "paragraph"][idx - 1]
            lines.append("\\%s{%s}" % (cmd, text_out))
        elif kind == "para":
            lines.append(_tex_inline(payload, store) + "\n")
        elif kind == "list":
            ordered, items = payload
            env = "enumerate" if ordered else "itemize"
            lines.append("\\begin{%s}" % env)
            for _, txt in items:
                lines.append("  \\item " + _tex_inline(txt, store))
            lines.append("\\end{%s}" % env)
        elif kind == "table":
            head, body = parse_table(*payload)
            if not head:
                continue
            lines.append("\\begin{table}[htbp]")
            lines.append("  \\centering")
            lines.append("  \\begin{tabular}{%s}" % _tex_colspec(head, body))
            lines.append("    \\toprule")
            lines.append("    " + " & ".join(_tex_inline(c, store) for c in head) + r" \\")
            lines.append("    \\midrule")
            for row in body:
                lines.append("    " + " & ".join(_tex_inline(c, store) for c in row[:len(head)]) + r" \\")
            lines.append("    \\bottomrule")
            lines.append("  \\end{tabular}")
            lines.append("\\end{table}")
        elif kind == "code":
            lines.append("\\begin{verbatim}")
            lines.append(payload)
            lines.append("\\end{verbatim}")
        elif kind == "quote":
            lines.append("\\begin{quote}")
            lines.append(_tex_inline(payload, store))
            lines.append("\\end{quote}")
        elif kind == "hr":
            lines.append("\\par\\noindent\\rule{\\linewidth}{0.4pt}\\par")
        elif kind == "image":
            alt, src = payload
            local = src
            if src.startswith("/media/"):
                local = "figures/" + src.split("/")[-1]
            lines.append("\\begin{figure}[htbp]")
            lines.append("  \\centering")
            lines.append("  \\includegraphics[width=0.85\\linewidth]{%s}" % local)
            lines.append("  \\caption{%s}" % _tex_escape(alt or "figure"))
            lines.append("  \\label{fig:%s}" % re.sub(r"\W+", "", (alt or "fig"))[:20])
            lines.append("\\end{figure}")

    head = [
        r"\documentclass[UTF8,a4paper,12pt]{ctexart}",
        r"\usepackage{amsmath,amssymb,amsthm}",
        r"\usepackage{graphicx}",
        r"\usepackage{booktabs}",
        r"\usepackage{geometry}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\geometry{margin=2.5cm}",
        r"\title{" + _tex_escape(title) + "}",
        r"\author{PaperMate}",
        r"\date{\today}",
        r"\begin{document}",
        r"\maketitle",
        "",
    ]
    tail = ["", r"\end{document}", ""]
    return "\n".join(head + lines + tail)
