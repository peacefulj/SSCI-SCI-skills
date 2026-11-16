# -*- coding: utf-8 -*-
"""数据文件结构画像（dataset profiling）。

只回答「这份数据长什么样」，不保存、不外传原始行：
- 列名、类型（数值 / 二值 / 年份 / 日期 / 文本 / 长文本 / ID）、缺失率、唯一值数
- 数值列的 min / max / mean / sd；二值列只报 1 的占比
- 每列最多 3 个示例值（疑似身份列自动脱敏）
- 数据结构判定（面板 / 时序 / 截面 / 文语料）与方法族信号（DiD / IV / RDD / 生存…）
- 由结构反推学科主线建议（只建议，不改用户选择）

支持的格式：
- csv / tsv / txt：自动嗅探分隔符与编码（utf-8-sig / utf-8 / gb18030）
- xlsx / xlsm：多工作表自动挑「最像数据表」的一页
- xls / ods：本机有 LibreOffice 时转 xlsx 再读（不引入新依赖）
- json：记录数组 / 二维数组 / {"data": [...]}
- dta / sav / parquet：本机恰好装了 pandas 才能读，否则给出「另存为 csv」的明确指引

设计约束：
1. 不依赖 pandas（本地环境常常装不上，装不上就起不来）——只在 pandas 恰好存在时借用。
2. 大文件只扫描前 MAX_ROWS_SCAN 行，并如实标注 truncated 与总行数。
3. 存盘只存 profile（JSON），不存原始文件——用户在界面上「移除」即彻底消失。
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

MAX_ROWS_SCAN = 20000
MAX_COLS = 200
MAX_FILE_BYTES = 32 * 1024 * 1024

_ID_HINTS = (
    "id", "code", "代码", "编号", "序号", "index", "no", "stkcd", "gvkey", "permno",
    "cusip", "ticker", "isin", "firm", "company", "entity", "企业", "公司", "证券", "机构",
)
# 强 ID 命名：命中即认作实体标识（不受唯一率影响——面板里同一实体本来就重复）
_ID_STRONG_RE = re.compile(
    r"(^id$|(^|_)id($|_)|代码|编号|序号|^stkcd|^gvkey$|^permno$|^cusip$|^ticker$|^isin$"
    r"|^firm_?id$|^company_?id$|^entity_?id$|^机构代码$)", re.I)
# 弱 ID 命名：只有「几乎不重复」时才认（index/code/no 这类容易误伤业务变量）
_ID_WEAK = ("index", "code", "no")
_TIME_HINTS = (
    "year", "yr", "年份", "年度", "date", "日期", "month", "月份", "quarter", "季度",
    "week", "week", "period", "期间", "time",
)
_TREAT_HINTS = ("treat", "treated", "处理", "政策", "did", "干预", "intervention", "policy", "reform")
_POST_HINTS = ("post", "after", "afterward", "_after", "政策后")
_IV_HINTS = ("iv", "instrument", "工具变量", "z_", "_z", "bartik", "shift_share")
_RD_HINTS = ("score", "running", "cutoff", "threshold", "评分", "得分", "临界")
_DUR_HINTS = ("duration", "time_to", "surv", "spell", "持续期", "存活", "hazard")
_EVENT_HINTS = ("event", "dead", "death", "default", "fail", "censored", "违约", "事件", "死亡")
_MED_HINTS = ("patient", "age", "sex", "gender", "bmi", "dose", "cohort", "arm", "placebo",
              "患者", "年龄", "性别", "剂量", "组别", "临床")
_ML_HINTS = ("accuracy", "precision", "recall", "f1", "auc", "epoch", "loss", "rmse", "mae",
             "准确率", "召回率", "轮次")
_PII_HINTS = ("name", "姓名", "名字", "phone", "mobile", "手机", "电话", "email", "邮箱",
              "mail", "身份证", "idcard", "id_card", "passport", "passport_no", "address",
              "地址", "联系人", "contact")

_TRACK_GENRE = {
    "quant": "quant", "predictive": "predictive", "qualitative": "qualitative",
    "basic-science": "sci-journal", "clinical": "clinical", "reporting": "sci-journal",
    "ei-conf": "ei-conf", "ai-conf": "ai-conf", "sci-journal": "sci-journal",
    "ssci": "ssci", "dissertation": "dissertation",
}

_MISSING = {"", "na", "n/a", "nan", "null", "none", ".", "-", "--", "缺失", "n.a."}
_DATE_RE = re.compile(r"^\d{4}[-/]\d{1,2}([-/]\d{1,2})?$")
_EXCEL_EXT = {".xlsx", ".xlsm", ".xls", ".ods"}
_NEED_CONVERT = {".xls", ".ods"}


class DatasetError(ValueError):
    pass


# ---------------------------------------------------------------- 基础工具


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _sniff_delim(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except Exception:
        counts = {d: sample.count(d) for d in ("\t", ",", ";", "|")}
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else ","


def _num(v) -> float | None:
    s = str(v or "").strip().replace(",", "").replace("，", "")
    if s.lower() in _MISSING:
        return None
    try:
        f = float(s)
    except Exception:
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _is_num_str(v) -> bool:
    return _num(v) is not None


def _fmt(x: float) -> str:
    if x is None:
        return "—"
    if abs(x) >= 10000 or (abs(x) < 0.01 and x != 0):
        return f"{x:.3g}"
    return f"{x:.3f}".rstrip("0").rstrip(".")


def _hit(name: str, hints: tuple[str, ...]) -> bool:
    low = str(name or "").lower()
    return any(h in low for h in hints)


# ---------------------------------------------------------------- 表头


def _looks_like_header(row: list[str], next_row: list[str] | None) -> bool:
    """首行是不是表头。

    判据：非空单元格里「不像数字」的占比高，且下一行至少有一个数字。
    纯数字首行（常见的无表头 csv）会被判成数据行。
    """
    cells = [str(c or "").strip() for c in row if str(c or "").strip()]
    if not cells:
        return False
    textish = sum(1 for c in cells if not _is_num_str(c))
    if textish / len(cells) < 0.6:
        return False
    if next_row is None:
        return True
    nxt = [str(c or "").strip() for c in next_row if str(c or "").strip()]
    return any(_is_num_str(c) for c in nxt) or not nxt


def _clean_header(cells: list[str], synthesized: bool = False) -> list[str]:
    raw = [re.sub(r"\s+", " ", str(c or "").replace("\ufeff", "")).strip().replace("|", "／")
           for c in cells[:MAX_COLS]]
    if synthesized:
        return [f"col_{i + 1}" for i in range(max(len(raw), 1))]
    out: list[str] = []
    seen: dict[str, int] = {}
    for i, name in enumerate(raw):
        name = name[:60] or f"col_{i + 1}"
        key = name.lower()
        if key in seen:
            seen[key] += 1
            name = f"{name}_{seen[key]}"
        else:
            seen[key] = 1
        out.append(name)
    if not out:
        raise DatasetError("第一行没有表头")
    return out


# ---------------------------------------------------------------- 各格式解析


def parse_csv(raw: bytes) -> tuple[list[str], list[list[str]], dict]:
    text = _decode(raw)
    if not text.strip():
        raise DatasetError("文件是空的")
    lines = text.splitlines()
    delim = _sniff_delim("\n".join(lines[:20]))
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    rows = [r for r in rows if any((c or "").strip() for c in r)]
    if not rows:
        raise DatasetError("没有解析出任何行")
    has_header = _looks_like_header(rows[0], rows[1] if len(rows) > 1 else None)
    header = _clean_header(rows[0], synthesized=not has_header)
    body = rows[1:] if has_header else rows
    meta = {"delimiter": delim, "encoding_ok": True, "header_synthesized": not has_header,
            "delimiter_label": {",": "逗号", "\t": "制表符", ";": "分号", "|": "竖线"}.get(delim, delim)}
    return header, body, meta


def _xlsx_sheet_sample(ws, limit: int = 12) -> list[list[str]]:
    out: list[list[str]] = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i >= limit:
            break
        out.append(["" if v is None else str(v) for v in row])
    return out


def _sheet_score(sample: list[list[str]]) -> float:
    """给工作表打分：宽、有数据、首行像表头、下面有数字。"""
    if not sample:
        return -1.0
    width = max(len(r) for r in sample)
    filled = sum(1 for r in sample for c in r if str(c).strip())
    numeric = sum(1 for r in sample[1:] for c in r if _is_num_str(c))
    head = sum(1 for c in sample[0] if str(c).strip() and not _is_num_str(c))
    return min(width, 20) * 2 + min(filled, 200) * 0.1 + min(numeric, 50) * 0.5 + min(head, 10)


def parse_xlsx(raw: bytes, sheet: str | None = None) -> tuple[list[str], list[list[str]], dict]:
    try:
        from openpyxl import load_workbook
    except Exception:
        raise DatasetError("缺少 openpyxl，无法读 xlsx；可另存为 csv 再上传")
    try:
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as e:
        raise DatasetError(f"xlsx 打开失败：{e}")

    names = list(wb.sheetnames)
    if not names:
        raise DatasetError("工作簿里没有工作表")

    # 多工作表：默认挑「最像数据表」的一页，而不是盲取第一页
    # （实证数据常把「变量说明」放第一页，盲取会读出 1 行说明文字）
    pick, scores = names[0], {}
    if sheet and sheet in names:
        pick = sheet
    elif len(names) > 1:
        best = -1e9
        for nm in names:
            try:
                sc = _sheet_score(_xlsx_sheet_sample(wb[nm]))
            except Exception:
                sc = -1.0
            if any(k in nm.lower() for k in ("data", "main", "数据", "主要", "样本")):
                sc += 3
            scores[nm] = round(sc, 1)
            if sc > best:
                best, pick = sc, nm

    ws = wb[pick]
    rows: list[list[str]] = []
    total = 0
    # read_only 模式下 max_row 在迭代前是 None（工作表未 sized），
    # 所以一边流式读一边计数：只把前 MAX_ROWS_SCAN 行留在内存，其余只数行数。
    # 旧实现读到上限就 break，导致 3 万行的表报「20000 行、未截断」。
    try:
        for row in ws.iter_rows(values_only=True):
            vals = ["" if v is None else str(v) for v in row]
            if not any(v.strip() for v in vals):
                continue
            total += 1
            if total <= MAX_ROWS_SCAN + 1:      # 表头 1 行 + MAX_ROWS_SCAN 行数据
                rows.append(vals)
    except Exception:
        pass
    try:
        wb.close()
    except Exception:
        pass
    if not rows:
        raise DatasetError(f"工作表「{pick}」是空的")

    has_header = _looks_like_header(rows[0], rows[1] if len(rows) > 1 else None)
    header = _clean_header(rows[0], synthesized=not has_header)
    body = rows[1:] if has_header else rows
    meta = {
        "sheet": pick,
        "sheets": names,
        "sheet_scores": scores,
        "header_synthesized": not has_header,
        "total_rows": max(total - (1 if has_header else 0), 0),
    }
    return header, body, meta


def parse_json(raw: bytes) -> tuple[list[str], list[list[str]], dict]:
    text = _decode(raw).strip()
    if not text:
        raise DatasetError("文件是空的")
    try:
        obj = json.loads(text)
    except Exception as e:
        raise DatasetError(f"JSON 解析失败：{e}")

    for key in ("data", "records", "rows", "items", "result"):
        if isinstance(obj, dict) and isinstance(obj.get(key), list):
            obj = obj[key]
            break
    if not isinstance(obj, list) or not obj:
        raise DatasetError("JSON 需要是记录数组，如 [{\"firm_id\": 1, \"roa\": 0.1}]")
    if all(isinstance(x, dict) for x in obj):
        keys: list[str] = []
        for rec in obj[:MAX_ROWS_SCAN]:
            for k in rec.keys():
                if k not in keys:
                    keys.append(k)
        header = _clean_header([str(k) for k in keys])
        body = [["" if rec.get(k) is None else str(rec.get(k)) for k in keys] for rec in obj]
        return header, body, {"format": "records", "header_synthesized": False}
    if all(isinstance(x, (list, tuple)) for x in obj):
        rows = [["" if v is None else str(v) for v in r] for r in obj]
        has_header = _looks_like_header(rows[0], rows[1] if len(rows) > 1 else None)
        return (_clean_header(rows[0], synthesized=not has_header),
                rows[1:] if has_header else rows,
                {"format": "matrix", "header_synthesized": not has_header})
    raise DatasetError("JSON 里需要是同构对象数组或二维数组")


def _soffice_path() -> str | None:
    for c in (os.environ.get("SOFFICE_PATH"), shutil.which("soffice"), shutil.which("libreoffice"),
              r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if c and Path(c).exists():
            return str(c)
    return None


def _convert_to_xlsx(raw: bytes, src_ext: str) -> bytes:
    """用本机 LibreOffice 把 xls/ods 转成 xlsx（不引入新依赖）。"""
    soffice = _soffice_path()
    if not soffice:
        raise DatasetError(
            f"这是 {src_ext} 格式，本机未找到 LibreOffice，无法直接读；"
            "请在 Excel/WPS 里「另存为 .xlsx」或 .csv 后重新上传")
    tmpdir = Path(tempfile.mkdtemp(prefix="acw_data_"))
    src = tmpdir / ("input" + src_ext)
    src.write_bytes(raw)
    cmd = [soffice, "--headless", "--norestore", "--nolockcheck",
           f"-env:UserInstallation=file:///{(tmpdir / 'profile').as_posix().lstrip('/')}",
           "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", str(tmpdir), str(src)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise DatasetError("LibreOffice 转换超时（180 秒）")
    out = tmpdir / "input.xlsx"
    if not out.exists() or out.stat().st_size == 0:
        msg = ((r.stderr or b"").decode("utf-8", "ignore")
               or (r.stdout or b"").decode("utf-8", "ignore")).strip()
        raise DatasetError(f"LibreOffice 转换失败：{msg[:200] or '未产出文件'}")
    return out.read_bytes()


def _via_pandas(raw: bytes, ext: str):
    """dta/sav/parquet：本机恰好装了 pandas 才借用，否则给明确指引。"""
    try:
        import pandas as pd  # noqa: F401
    except Exception:
        raise DatasetError(
            f"暂不支持 {ext}（需要 pandas，本机未安装）；"
            "请在 Stata/SPSS 里导出为 csv 或 xlsx 后重新上传")
    try:
        import io as _io
        if ext == ".dta":
            df = pd.read_stata(_io.BytesIO(raw))
        elif ext == ".sav":
            df = pd.read_spss(_io.BytesIO(raw))
        else:
            df = pd.read_parquet(_io.BytesIO(raw))
    except Exception as e:
        raise DatasetError(f"{ext} 读取失败：{e}")
    header = _clean_header([str(c) for c in df.columns])
    body = [["" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v)
             for v in row] for row in df.itertuples(index=False, name=None)]
    return header, body, {"format": ext.lstrip("."), "header_synthesized": False, "via": "pandas"}


# ---------------------------------------------------------------- 画像


def profile_rows(header: list[str], rows: list[list[str]], meta: dict | None = None,
                 total_rows: int | None = None) -> dict:
    n_scan = len(rows[:MAX_ROWS_SCAN])
    scan = rows[:MAX_ROWS_SCAN]
    meta = dict(meta or {})
    cols_total = max([len(header)] + [len(r) for r in scan[:50]]) if (header or scan) else 0

    cols = []
    for ci, name in enumerate(header):
        vals = [(r[ci] if ci < len(r) else "") for r in scan]
        non_empty = [v for v in vals if str(v or "").strip().lower() not in _MISSING]
        missing = (len(vals) - len(non_empty)) / len(vals) if vals else 0.0

        nums = [x for x in (_num(v) for v in non_empty) if x is not None]
        ratio = (len(nums) / len(non_empty)) if non_empty else 0.0
        is_num = len(nums) >= 2 and ratio >= 0.9
        uniq_vals = [str(v).strip() for v in non_empty]
        uniq = len(set(uniq_vals))
        is_date = (not is_num) and bool(non_empty) and all(_DATE_RE.match(v) for v in uniq_vals[:50])

        ctype = "numeric" if is_num else ("date" if is_date else "text")
        if is_num and nums and uniq <= 2 and all(x in (0.0, 1.0) for x in nums):
            ctype = "binary"
        if is_num and re.fullmatch(r"(year|yr|fyear|年份|年度)", name.lower()) \
                and nums and all(1900 <= x <= 2100 for x in nums):
            ctype = "year"

        col = {"name": name, "type": ctype, "missing": round(missing, 4), "unique": uniq}
        if ctype == "text":
            lens = [len(v) for v in uniq_vals]
            col["avg_len"] = int(sum(lens) / len(lens)) if lens else 0
            if _hit(name, _PII_HINTS):
                col["examples"] = ["（已脱敏）"]
                col["masked"] = True
            else:
                col["examples"] = [v[:40] for v in uniq_vals[:3]]
            if col.get("avg_len", 0) >= 160:
                col["type"] = "text-long"
        if is_num and nums:
            m = sum(nums) / len(nums)
            sd = math.sqrt(sum((x - m) ** 2 for x in nums) / len(nums)) if len(nums) > 1 else 0.0
            col.update({"min": _fmt(min(nums)), "max": _fmt(max(nums))})
            if ctype == "binary":
                col["share"] = round(m, 4)
            elif ctype == "numeric":
                col.update({"mean": _fmt(m), "sd": _fmt(sd)})
        cols.append(col)

    n_rows_total = int(total_rows) if (total_rows and total_rows > 0) else len(rows)
    out = {
        "rows": n_rows_total,
        "cols": max(cols_total, len(header)),
        "cols_profiled": len(header),
        "cols_dropped": max(cols_total - len(header), 0),
        "scanned": n_scan,
        "truncated": n_rows_total > n_scan,
        "columns": cols,
        "meta": meta,
    }
    _mark_ids(out, n_scan)
    out["structure"] = _structure(out)
    out["signals"] = _signals(out)
    out["suggest"] = _suggest(out)
    out["warnings"] = _warnings(out)
    out["summary_md"] = summary_table(out)
    return out


def _int_like(c: dict) -> bool:
    try:
        return float(c.get("min")).is_integer() and float(c.get("max")).is_integer()
    except Exception:
        return False


def _mark_ids(p: dict, n_scan: int) -> None:
    """标出 ID 列。

    旧实现有两个毛病：要求 `type == "text"`（firm_id 这类数值 ID 全被当成连续变量，
    摘要里给均值 SD，模型会把它写进控制变量）；名字命中 "index" 就算 ID
    （dfi_index 这种指标被误伤）。现在分三档：
      强命名（_id / 代码 / 编号 / stkcd…）→ 直接认定
      弱命名（index / code / no）+ 几乎不重复 → 认定
      形状（整数、唯一率 ≥95%、量级 ≥100）→ 认定
    """
    ids = []
    for c in p.get("columns") or []:
        if c.get("type") in ("binary", "date", "text-long", "year"):
            continue
        low = str(c["name"]).lower()
        ratio = (c.get("unique", 0) / n_scan) if n_scan else 0.0
        strong = bool(_ID_STRONG_RE.search(low))
        weak = _hit(low, _ID_WEAK) and ratio >= 0.9
        shape = (c.get("type") == "numeric" and ratio >= 0.95 and _int_like(c)
                 and (float(c.get("max") or 0) >= 100))
        if strong or weak or shape:
            c["role"] = "id"
            c["type"] = "id"
            for k in ("mean", "sd"):
                c.pop(k, None)
            ids.append(c["name"])
    p["id_like"] = ids


def _col(p: dict, name: str) -> dict | None:
    for c in p.get("columns") or []:
        if c["name"] == name:
            return c
    return None


def _time_col(p: dict) -> dict | None:
    for c in p.get("columns") or []:
        if c.get("type") in ("year", "date"):
            return c
    for c in p.get("columns") or []:
        if _hit(c["name"], _TIME_HINTS) and c.get("type") in ("numeric", "text"):
            return c
    return None


def _structure(p: dict) -> dict:
    rows = p.get("rows") or 0
    cols = p.get("columns") or []
    ids = p.get("id_like") or []
    t = _time_col(p)
    long_text = [c["name"] for c in cols if c.get("type") == "text-long"]

    entity = ids[0] if ids else None
    n_entities = (_col(p, entity) or {}).get("unique", 0) if entity else 0
    n_periods = (t or {}).get("unique", 0)

    layout = "table"
    if long_text and (not t or n_entities <= max(50, rows * 0.2)):
        layout = "text-corpus"
    elif entity and t and n_entities >= 2 and n_periods >= 2 and rows >= 8:
        layout = "panel"
    elif t and not entity and n_periods >= 5:
        layout = "time-series"
    elif entity and n_entities >= max(3, int(rows * 0.9)):
        layout = "cross-section"
    elif rows >= 200:
        layout = "table"

    balanced = None
    if layout == "panel" and n_entities and n_periods:
        balanced = (n_entities * n_periods == rows)
    return {
        "layout": layout,
        "entity": entity, "time": (t or {}).get("name"),
        "n_entities": n_entities, "n_periods": n_periods,
        "balanced": balanced,
        "long_text_cols": long_text[:3],
    }


def _signals(p: dict) -> list[dict]:
    cols = p.get("columns") or []
    st = p.get("structure") or {}
    sig: list[dict] = []

    def add(key, label, evidence, conf="medium"):
        sig.append({"key": key, "label": label, "evidence": evidence, "confidence": conf})

    bin_cols = [c for c in cols if c.get("type") == "binary"]
    num_cols = [c for c in cols if c.get("type") in ("numeric", "year")]

    if st.get("layout") == "panel":
        add("panel", "面板数据",
            f"{st['entity']} × {st['time']}：{st['n_entities']} 个实体 × {st['n_periods']} 期，"
            f"共 {p.get('rows')} 行" + ("（平衡面板）" if st.get("balanced") else ""), "high")
    if st.get("layout") == "time-series":
        add("timeseries", "时间序列", f"{st['time']} 共 {st['n_periods']} 期，无实体维度", "high")
    if st.get("layout") == "text-corpus":
        add("text", "文本语料",
            f"长文本列 {st['long_text_cols']}（平均长度 "
            f"{( _col(p, st['long_text_cols'][0]) or {}).get('avg_len', 0)} 字）", "high")

    treat = next((c for c in bin_cols if _hit(c["name"], _TREAT_HINTS)), None)
    post = next((c for c in bin_cols if _hit(c["name"], _POST_HINTS)), None)
    if treat and post:
        add("did", "双重差分（DiD）", f"处理变量 {treat['name']} 与时期变量 {post['name']} 同时存在", "high")
    iv = next((c for c in cols if _hit(c["name"], _IV_HINTS)), None)
    if iv:
        add("iv", "工具变量（IV）", f"列名命中工具变量命名：{iv['name']}", "medium")
    rd = next((c for c in cols if _hit(c["name"], _RD_HINTS)), None)
    if rd and bin_cols:
        add("rdd", "断点回归（RDD）", f"{rd['name']} 可作为驱动变量，配合 {bin_cols[0]['name']} 的断点", "low")
    dur = next((c for c in num_cols if _hit(c["name"], _DUR_HINTS)), None)
    ev = next((c for c in bin_cols if _hit(c["name"], _EVENT_HINTS)), None)
    if dur and ev:
        add("survival", "生存/久期分析", f"持续期 {dur['name']} + 事件 {ev['name']}", "high")

    if bin_cols and len(num_cols) >= 4 and st.get("layout") in ("table", "cross-section"):
        add("classification", "二分类/预测建模",
            f"二值结果 {bin_cols[0]['name']} + {len(num_cols)} 个数值特征", "medium")
    if any(_hit(c["name"], ("group", "arm", "组别", "分组")) for c in cols) and bin_cols:
        add("experiment", "实验/分组对照", "存在分组变量与二值结果", "medium")
    if any(_hit(c["name"], _ML_HINTS) for c in cols):
        add("ml-eval", "模型评测指标", "命中 accuracy/F1/AUC 等评测列名", "medium")
    if any(_hit(c["name"], _MED_HINTS) for c in cols) and st.get("layout") != "panel":
        add("medical", "医学/临床变量", "命中 age/sex/bmi/组别 等临床列名", "medium")

    return sig


def _suggest(p: dict) -> dict:
    """由数据结构反推学科主线（只建议，不覆盖用户选择）。"""
    st = p.get("structure") or {}
    sigs = {s["key"]: s for s in (p.get("signals") or [])}
    layout = st.get("layout")
    reasons: list[str] = []
    track, conf = "", "low"

    if "text" in sigs:
        track, conf = "qualitative", "high"
        reasons.append(sigs["text"]["evidence"])
        reasons.append("长文本语料按质性编码处理，规则走质性研究线（41 条）")
    elif "ml-eval" in sigs and layout in ("table", "cross-section"):
        track, conf = "ai-conf", "medium"
        reasons.append(sigs["ml-eval"]["evidence"])
    elif "classification" in sigs:
        track, conf = "predictive", "medium"
        reasons.append(sigs["classification"]["evidence"])
        reasons.append("结果是二值/类别变量，走预测建模线（25 条）而不是因果识别线")
    elif "medical" in sigs and "panel" not in sigs:
        track, conf = "clinical", "medium"
        reasons.append(sigs["medical"]["evidence"])
    elif "panel" in sigs or "did" in sigs or "iv" in sigs or "rdd" in sigs:
        track, conf = "quant", "high"
        for k in ("did", "iv", "rdd", "panel"):
            if k in sigs:
                reasons.append(sigs[k]["evidence"])
                break
        reasons.append("识别策略类结构（面板/DiD/IV/RDD）走定量实证线（56 条）")
    elif "survival" in sigs:
        track, conf = "quant", "medium"
        reasons.append(sigs["survival"]["evidence"])
    elif layout in ("time-series", "cross-section", "table") and any(
            c.get("type") == "numeric" for c in (p.get("columns") or [])):
        track, conf = "quant", "low"
        reasons.append(f"{layout} 结构 + 数值型变量，按定量实证处理（也可自行改为其他主线）")

    return {"track": track, "genre": _TRACK_GENRE.get(track, ""),
            "reasons": reasons[:4], "confidence": conf}


def _warnings(p: dict) -> list[str]:
    out: list[str] = []
    meta = p.get("meta") or {}
    if meta.get("header_synthesized"):
        out.append("首行看起来不是表头（多为数字），已按无表头处理，列名用 col_1…col_n")
    if p.get("cols_dropped"):
        out.append(f"共 {p.get('cols')} 列，只分析前 {p.get('cols_profiled')} 列"
                   f"（其余 {p['cols_dropped']} 列未纳入画像）")
    if p.get("truncated"):
        out.append(f"共 {p.get('rows')} 行，只扫描前 {p.get('scanned')} 行做统计")
    if meta.get("sheets") and len(meta["sheets"]) > 1:
        others = [s for s in meta["sheets"] if s != meta.get("sheet")]
        out.append(f"工作簿有 {len(meta['sheets'])} 页，已选数据最多的一页「{meta.get('sheet')}」；"
                   f"未使用：{'、'.join(others[:5])}")
    if meta.get("converted_from"):
        out.append(f"已用 LibreOffice 把 {meta['converted_from']} 转为 xlsx 后解析")
    dup = [c["name"] for c in (p.get("columns") or [])
           if not (p.get("meta") or {}).get("header_synthesized") and re.search(r"_\d+$", c["name"])]
    if dup:
        out.append(f"原始表头有重名，已自动加后缀区分：{'、'.join(dup[:4])}")
    return out


# ---------------------------------------------------------------- 数据体检
# 「数据不全」有三种，处置完全不同，必须先分开再谈补：
#   ① 缺列：某个变量根本没采（如做 DiD 却没有 treat 列）——只有外部数据源可能有，
#      但口径是否可比要作者判断，机器不能替他决定，本模块只报「做不了什么」；
#   ② 单元格缺失：变量在、值是空的——技术上可插补，但需要原始行与方法学声明；
#      本系统只存画像、不留行（server.py 上传接口刻意不落原始文件），故不做插补；
#   ③ 样本期/样本量不足：补不回来，只能改研究设计。
# 所以体检的产出是「按现有数据哪些分析做不了」，不是「把数据补全」。
# 硬约束：这里只读画像里的结构事实，不猜数值、不生成任何模拟值。

_GAP_MIN_ROWS = 30          # 低于此，任何显著性检验都不成立
_GAP_MIN_ANALYSIS = 2       # 少于 2 个可分析变量，做不了多元回归
_GAP_MISS_RISK = 0.40       # 分析变量缺失超过此比例，估计量基本不可用
_GAP_MISS_WARN = 0.15
_GAP_MIN_PERIODS = 3        # 面板少于 3 期，双向固定效应/DiD 差分后自由度不够
_GAP_MIN_TS = 20            # 时序短于此，单位根/协整与滞后项都吃紧


def gap_report(p: dict | None) -> dict:
    """对画像做「够不够做实证」的体检。只出结构判断，不出数据。

    返回 {level, items[], counts, summary_md}；level ∈ ok / warn / risk / none。
    items[].status ∈ pass / warn / risk，risk 表示该项分析按现有数据做不了。
    """
    if not p:
        return {"level": "none", "items": [],
                "counts": {"risk": 0, "warn": 0, "pass": 0},
                "summary_md": "_未上传数据文件，无法体检。_"}
    cols = p.get("columns") or []
    st = p.get("structure") or {}
    lay = st.get("layout") or "table"
    rows = int(p.get("rows") or 0)
    items: list[dict] = []

    def add(key: str, label: str, status: str, detail: str, fix: str = "") -> None:
        items.append({"key": key, "label": label, "status": status,
                      "detail": detail, "fix": fix})

    def names(cs: list[dict], n: int = 5) -> str:
        return "、".join(c["name"] for c in cs[:n]) + ("…" if len(cs) > n else "")

    # 1 样本量
    if rows <= 0:
        add("rows", "样本量", "risk", "未读出有效数据行", "确认文件除表头外还有数据行")
    elif rows < _GAP_MIN_ROWS:
        add("rows", "样本量", "risk",
            f"{rows} 行，低于 {_GAP_MIN_ROWS} 行：任何显著性检验都不可靠",
            "补样本，或把设计改成案例/定性研究，正文里不要报 p 值与显著性星号")
    elif rows < 100:
        add("rows", "样本量", "warn",
            f"{rows} 行：小样本，估计量方差大",
            "补样本，或减少控制变量以节省自由度，并在方法里说明抽样与稳健性")
    else:
        add("rows", "样本量", "pass", f"{rows} 行")

    # 2 可分析变量（排除 ID 列：ID 不进回归、不算均值）
    analysis = [c for c in cols
                if c.get("type") in ("numeric", "binary") and c.get("role") != "id"]
    if lay == "text-corpus":
        lt = st.get("long_text_cols") or []
        add("vars", "可分析变量", "pass" if lt else "warn",
            f"文本语料型：长文本列 {'、'.join(lt[:3]) or '未识别'}"
            if lt else "识别为文本语料，但没找到长文本列",
            "" if lt else "确认文本列是否被拆成短字段，或改用表格型数据")
    elif not analysis:
        add("vars", "可分析变量", "risk",
            "没有任何数值/二值列，定量分析无从下手",
            "把关键变量整理成数值列（比率、计数、0/1 虚拟变量）后重新上传")
    elif len(analysis) < _GAP_MIN_ANALYSIS:
        add("vars", "可分析变量", "warn",
            f"只有 1 个可分析变量（{analysis[0]['name']}），做不了多元回归",
            "至少再补 1 个解释变量；否则只能做描述统计")
    else:
        add("vars", "可分析变量", "pass",
            f"{len(analysis)} 个数值/二值变量：{names(analysis)}")

    # 3 关键变量缺失率（只对分析变量判，ID 列缺失无意义）
    miss_risk = sorted([c for c in analysis if (c.get("missing") or 0) > _GAP_MISS_RISK],
                       key=lambda c: -(c.get("missing") or 0))
    miss_warn = [c for c in analysis
                 if _GAP_MISS_WARN < (c.get("missing") or 0) <= _GAP_MISS_RISK]
    if miss_risk:
        add("missing", "关键变量缺失", "risk",
            f"{len(miss_risk)} 个分析变量缺失超过 {_GAP_MISS_RISK:.0%}："
            + "、".join(f"{c['name']}（{c['missing']:.0%}）" for c in miss_risk[:3]),
            "补数据源，或弃用该变量。若必须保留，须在方法里写明缺失机制与处理方式，"
            "并按处理后样本报 N——本系统不替你插补")
    elif miss_warn:
        add("missing", "关键变量缺失", "warn",
            f"{len(miss_warn)} 个分析变量缺失在 {_GAP_MISS_WARN:.0%}–{_GAP_MISS_RISK:.0%}："
            + "、".join(f"{c['name']}（{c['missing']:.0%}）" for c in miss_warn[:3]),
            "在方法里说明缺失比例与处理方式（删除/插补），并做缺失样本的稳健性检验")
    else:
        add("missing", "关键变量缺失", "pass", "分析变量缺失率均在 15% 以内")

    # 4 面板深度 / 时序长度
    if lay == "panel":
        np_ = int(st.get("n_periods") or 0)
        ne = int(st.get("n_entities") or 0)
        if np_ and np_ < _GAP_MIN_PERIODS:
            add("depth", "面板深度", "risk",
                f"{np_} 期：少于 {_GAP_MIN_PERIODS} 期，双向固定效应与 DiD 差分后自由度不够",
                "补到 3 期以上，或改用截面/混合方法并说明")
        elif ne and ne < 30:
            add("depth", "面板深度", "warn",
                f"{ne} 个个体 × {np_} 期：个体数偏少，聚类稳健标准误不可靠",
                "补个体，或改用不带聚类的标准误并在局限里说明")
        else:
            add("depth", "面板深度", "pass",
                f"{ne} 个个体 × {np_} 期" + ("" if st.get("balanced") is not False else "（非平衡）"))
    elif lay == "time-series":
        np_ = int(st.get("n_periods") or 0)
        if np_ and np_ < _GAP_MIN_TS:
            add("depth", "时序长度", "warn",
                f"仅 {np_} 期：单位根/协整检验与滞后项估计都吃紧",
                "补到 20 期以上，或改用不依赖长时序的方法并说明")
        else:
            add("depth", "时序长度", "pass", f"{np_} 期")

    # 5 取值退化（数值列几乎无变异，回归系数不可识别）
    flat = [c for c in analysis
            if c.get("type") == "numeric" and (c.get("unique") or 0) <= 2]
    if flat:
        add("variance", "变量变异", "warn",
            f"{names(flat)} 只有 2 个不同取值，按数值列放进回归没有意义",
            "确认是否该按 0/1 虚拟变量处理，或该变量实为分组标签")

    # 6 多表可连接性（附表连不上主表，就只能各写各的）
    parts = p.get("parts") or []
    if len(parts) > 1:
        pi = int(p.get("primary") or 0)
        main_keys = {str(c.get("name") or "").strip().lower()
                     for c in (parts[pi].get("columns") or [])}
        orphans, time_only = [], []
        for i, part in enumerate(parts):
            if i == pi:
                continue
            inter = main_keys & {str(c.get("name") or "").strip().lower()
                                 for c in (part.get("columns") or [])}
            tag = part.get("filename") or part.get("role") or f"附表{i}"
            if not inter:
                orphans.append(tag)
            elif not [k for k in inter if not _hit(k, _TIME_HINTS)]:
                time_only.append(tag)
        if orphans:
            add("join", "多表连接", "warn",
                f"{'、'.join(orphans[:3])} 与主表没有同名键列，无法按行合并",
                "确认附表靠什么连接（实体 ID/年份），或在正文里各自单独描述")
        elif time_only:
            add("join", "多表连接", "warn",
                f"{'、'.join(time_only[:3])} 只能按时间列对齐，缺实体键",
                "补实体 ID 后再合并；只按年份对齐会把不同个体错配")
        else:
            add("join", "多表连接", "pass", "附表与主表存在同名实体键，可合并")

    risk = sum(1 for i in items if i["status"] == "risk")
    warn = sum(1 for i in items if i["status"] == "warn")
    level = "risk" if risk else ("warn" if warn else "ok")
    rep = {"level": level, "items": items,
           "counts": {"risk": risk, "warn": warn, "pass": len(items) - risk - warn}}
    rep["summary_md"] = gap_md(rep)
    return rep


def gap_md(rep: dict) -> str:
    """体检结果 → Markdown 表（进 05_check.md，也用于前端提示）。"""
    tag = {"pass": "通过", "warn": "注意", "risk": "阻断"}
    lines = ["| 体检项 | 结果 | 说明 | 建议 |", "| --- | --- | --- | --- |"]
    for it in rep.get("items") or []:
        det = str(it.get("detail") or "").replace("|", "／").replace("\n", " ")
        fix = str(it.get("fix") or "—").replace("|", "／").replace("\n", " ")
        lines.append(f"| {it.get('label')} | {tag.get(it.get('status'), '—')} | {det} | {fix} |")
    if not rep.get("items"):
        lines.append("| — | — | 未上传数据，未做体检 | — |")
    return "\n".join(lines)


def summary_table(p: dict) -> str:
    lines = []
    st = p.get("structure") or {}
    if st:
        bits = [f"结构：{ {'panel':'面板','time-series':'时间序列','cross-section':'截面',
                              'text-corpus':'文本语料','table':'普通表格'}.get(st.get('layout'), st.get('layout')) }"]
        if st.get("entity"):
            bits.append(f"实体列 {st['entity']}（{st.get('n_entities')} 个）")
        if st.get("time"):
            bits.append(f"时间列 {st['time']}（{st.get('n_periods')} 期）")
        if st.get("balanced") is not None:
            bits.append("平衡面板" if st.get("balanced") else "非平衡面板")
        lines.append("；".join(bits))
        lines.append("")
    lines += ["| 变量 | 类型 | 缺失率 | 取值 / 分布 |", "| --- | --- | --- | --- |"]
    for c in (p.get("columns") or [])[:40]:
        t = c["type"]
        if t == "id":
            desc = "ID 列（实体标识，不是分析变量，勿计入描述统计）"
            tlabel = "ID"
        elif t == "binary":
            desc = f"0/1 变量，1 占 {c.get('share', 0):.0%}"
            tlabel = "二值"
        elif t == "numeric":
            desc = f"均值 {c.get('mean')}，SD {c.get('sd')}，范围 {c.get('min')} ~ {c.get('max')}"
            tlabel = "数值"
        elif t == "year":
            desc = f"年份范围 {c.get('min')} ~ {c.get('max')}"
            tlabel = "年份"
        elif t == "date":
            desc = f"{c['unique']} 个不同日期"
            tlabel = "日期"
        elif t == "text-long":
            desc = f"长文本，平均 {c.get('avg_len', 0)} 字，{c['unique']} 条不同文本"
            tlabel = "长文本"
        else:
            ex = "、".join(c.get("examples") or []) or "—"
            desc = f"{c['unique']} 个不同取值，如 {ex}"
            tlabel = "文本"
        lines.append(f"| {c['name']} | {tlabel} | {c['missing']:.1%} | {desc} |")
    if p.get("cols_profiled", 0) > 40:
        lines.append(f"| … | | | 其余 {p['cols_profiled'] - 40} 列未列出 |")
    if p.get("cols_dropped"):
        lines.append(f"| … | | | 另有 {p['cols_dropped']} 列超出自画像上限，未分析 |")
    return "\n".join(lines)


def profile_file(raw: bytes, filename: str) -> dict:
    if not raw:
        raise DatasetError("文件为空")
    if len(raw) > MAX_FILE_BYTES:
        raise DatasetError(f"文件超过 {MAX_FILE_BYTES // 1024 // 1024} MB，请先抽样或另存为较小的 csv")

    name = Path(filename or "").name
    ext = Path(name).suffix.lower()

    if ext in (".xlsx", ".xlsm"):
        header, rows, meta = parse_xlsx(raw)
        kind = "xlsx"
    elif ext in _NEED_CONVERT:
        xlsx = _convert_to_xlsx(raw, ext)
        header, rows, meta = parse_xlsx(xlsx)
        meta["converted_from"] = ext
        kind = ext.lstrip(".")
    elif ext in (".csv", ".tsv", ".txt", ""):
        header, rows, meta = parse_csv(raw)
        kind = "csv"
    elif ext == ".json":
        header, rows, meta = parse_json(raw)
        kind = "json"
    elif ext in (".dta", ".sav", ".parquet"):
        header, rows, meta = _via_pandas(raw, ext)
        kind = ext.lstrip(".")
    elif ext in (".zip", ".rar", ".7z"):
        raise DatasetError("不支持压缩包；请解压后逐个上传（可一次选多个文件）")
    else:
        raise DatasetError(f"不支持的格式 {ext or '(无扩展名)'}；"
                           "支持 csv / tsv / txt / xlsx / xlsm / xls / ods / json")

    p = profile_rows(header, rows, meta, total_rows=meta.get("total_rows"))
    p["kind"] = kind
    p["filename"] = name[:80]
    p["bytes"] = len(raw)
    return p


def profile_files(items: list[tuple[bytes, str]]) -> dict:
    """一份或多份数据文件 → 一个 bundle。

    多文件时保留各自的画像（parts），主表取「行×列」最大的那份；
    提示词会把每一份都列出来，避免「只用了附表、主表被丢掉」。
    """
    if not items:
        raise DatasetError("没有收到文件")
    parts = []
    for raw, name in items:
        if not raw:
            continue
        try:
            parts.append(profile_file(raw, name))
        except DatasetError as e:
            raise DatasetError(f"{Path(name or '').name or '文件'}：{e}")
    if not parts:
        raise DatasetError("文件都是空的")
    if len(parts) == 1:
        one = dict(parts[0])
        one["parts"] = [dict(parts[0], primary=True)]
        one["primary"] = 0
        one["summary_md"] = _bundle_summary(one["parts"])
        return one

    primary = max(range(len(parts)), key=lambda i: (parts[i].get("rows", 0) * parts[i].get("cols", 0)))
    for i, part in enumerate(parts):
        part["primary"] = (i == primary)
        part["role"] = "主表" if i == primary else f"附表 {i + 1 if i < primary else i}"

    sigs: list[dict] = []
    seen = set()
    for part in parts:
        for s in part.get("signals") or []:
            if s["key"] in seen:
                continue
            seen.add(s["key"])
            sigs.append(s)

    merged = {
        "kind": "bundle",
        "filename": " + ".join(p["filename"] for p in parts)[:120],
        "parts": parts,
        "primary": primary,
        "rows": sum(p.get("rows", 0) for p in parts),
        "cols": max(p.get("cols", 0) for p in parts),
        "cols_profiled": max(p.get("cols_profiled", 0) for p in parts),
        "cols_dropped": max(p.get("cols_dropped", 0) for p in parts),
        "scanned": sum(p.get("scanned", 0) for p in parts),
        "truncated": any(p.get("truncated") for p in parts),
        "bytes": sum(p.get("bytes", 0) for p in parts),
        "columns": parts[primary].get("columns") or [],
        "id_like": parts[primary].get("id_like") or [],
        "structure": parts[primary].get("structure") or {},
        "signals": sigs,
        "suggest": parts[primary].get("suggest") or {},
        "meta": {"files": [{"filename": p["filename"], "kind": p["kind"],
                            "rows": p.get("rows"), "cols": p.get("cols")} for p in parts]},
        "warnings": [f"{p['filename']}：{w}" for p in parts for w in (p.get("warnings") or [])],
    }
    merged["summary_md"] = _bundle_summary(parts)
    return merged


def _bundle_summary(parts: list[dict]) -> str:
    if len(parts) == 1:
        p = parts[0]
        head = f"数据文件：{p.get('filename')}（{p.get('rows')} 行 × {p.get('cols')} 列"
        head += f"，{p.get('kind')}）" if p.get("kind") else "）"
        return head + "\n\n" + (p.get("summary_md") or "")
    out = []
    for i, p in enumerate(parts, 1):
        tag = p.get("role") or ("主表" if p.get("primary") else f"附表 {i}")
        out.append(f"【{tag}】{p.get('filename')}（{p.get('rows')} 行 × {p.get('cols')} 列"
                   f"，{p.get('kind')}）")
        out.append(p.get("summary_md") or "")
        out.append("")
    return "\n".join(out).strip()


# ---------------------------------------------------------------- 存取
#
# 只存 profile，不存原始数据。目录：_oneshot/_datasets/<id>.json


def datasets_dir(base: Path) -> Path:
    d = base / "_datasets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_profile(profile: dict, base: Path) -> str:
    did = uuid.uuid4().hex[:12]
    profile = dict(profile)
    profile["id"] = did
    datasets_dir(base).joinpath(f"{did}.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=1), encoding="utf-8")
    return did


def load_profile(did: str, base: Path) -> dict | None:
    if not did or not re.fullmatch(r"[0-9a-f]{6,32}", did or ""):
        return None
    p = datasets_dir(base) / f"{did}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def delete_profile(did: str, base: Path) -> bool:
    if not did or not re.fullmatch(r"[0-9a-f]{6,32}", did or ""):
        return False
    p = datasets_dir(base) / f"{did}.json"
    if p.exists():
        p.unlink()
        return True
    return False
