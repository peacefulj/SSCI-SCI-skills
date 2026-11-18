# -*- coding: utf-8 -*-
"""PaperMate（开源论文搭子）—— 独立 Web 应用后端。

FastAPI 服务：
- 静态前端
- /api/review/lexical  词面检测（复用 skill 原生脚本）
- /api/review/deep     LLM 逐条判读（需人工的规则）
- /api/workflow        六阶段工作流（选题/设计/初稿/引用/投稿返修）
- /api/chat            多轮追问
"""
import importlib.util
import json
import os
import re
import shutil
import socket
import sys
import threading
import urllib.request
import uuid
import webbrowser
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import auth
import dataset
import datasource
import engine
import export
import ingest
import llm
import oneshot
import state_store
import topic_trend

import paths

# 只读资源走 paths.resource_root()：打包后位于 _MEIPASS，源码运行即项目根。
# 可写数据（uploads/_oneshot/.env）走 paths.data_root()：打包后位于 exe 同级 data/。
BASE_DIR = paths.resource_root()
DATA_DIR = paths.data_root()
STATIC_DIR = BASE_DIR / "static"

VERSION = "1.3.1"
app = FastAPI(title="PaperMate", version=VERSION)

# 会话存储：内存 dict + 每次写入同步落盘（见 state_store）。
# 桌面版多写一个文件约 1ms，不值当为它分叉代码路径；换来的是容器重启后
# 追问上下文还在。启动时再由 `_restore_sessions()` 回填。
SESSIONS = {}


def _is_public(path: str) -> bool:
    """无需登录即可访问的路径。

    登录页、健康检查、静态资源必须放行：
    - `/api/health`：容器 healthcheck 与负载均衡探活，不能要求口令；
    - `/`、`/static/*`、favicon：登录页本身就在静态目录里，挡住就进不去；
    - `/api/auth/*`：登录/登出/查询状态。
    其余 `/api/*` 一律要口令。
    """
    if path in ("/api/health", "/api/auth/status", "/api/auth/login",
                "/api/auth/logout"):
        return True
    if path.startswith("/api/"):
        return False
    return True


@app.middleware("http")
async def _auth_guard(request: Request, call_next):
    """统一鉴权中间件。

    为什么用中间件而不是给每个路由加 `Depends`：本文件有 20+ 个路由，
    逐个加依赖一定会漏（尤其以后新加接口时）。中间件默认全拦、白名单放行，
    漏不出去。

    未启用口令时（`auth.mode()=="private"`）这里直接放行，桌面版零影响。
    """
    if auth.mode() == "private" or _is_public(request.url.path):
        return await call_next(request)

    if auth.verify(request.cookies.get(auth.COOKIE_NAME)):
        return await call_next(request)

    # 浏览器直接访问页面时 401 会显示一片 JSON，不如跳回登录页；
    # 而 XHR/fetch 必须拿到 401 才能由前端弹登录框。
    wants_html = "text/html" in (request.headers.get("accept") or "")
    if wants_html and request.method == "GET":
        return RedirectResponse("/login.html", status_code=303)
    return JSONResponse({"detail": "需要登录"}, status_code=401)


class LoginReq(BaseModel):
    password: str


@app.post("/api/auth/login")
def auth_login(req: LoginReq):
    if auth.mode() == "private":
        return {"ok": True, "mode": "private"}
    if not auth.check_password(req.password):
        # 不给「还剩几次」之类的提示，避免被拿来试探口令强度
        raise HTTPException(401, "口令不正确")
    tok = auth.issue()
    resp = JSONResponse({"ok": True, "mode": auth.mode()})
    resp.set_cookie(
        auth.COOKIE_NAME, tok,
        max_age=auth.SESSION_TTL,
        httponly=True,          # 前端脚本读不到，XSS 也偷不走
        samesite="lax",         # 防 CSRF；lax 不挡同站导航，登录后跳转正常
        # 只有走 HTTPS 时才加 Secure。内网 HTTP 部署很常见，硬加会导致
        # 浏览器直接丢弃 Cookie，表现为「登录成功但一直被踢回登录页」。
        secure=(os.environ.get("PAPERMATE_HTTPS", "").strip().lower()
                in ("1", "true", "yes", "on")),
        path="/",
    )
    return resp


@app.post("/api/auth/logout")
def auth_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE_NAME, path="/")
    return resp


@app.get("/api/auth/status")
def auth_status(request: Request):
    """前端启动时调一次，决定要不要渲染登录框、要不要显示 Key 输入。"""
    m = auth.mode()
    return {
        "mode": m,
        "need_login": m != "private",
        "logged_in": m == "private" or auth.verify(request.cookies.get(auth.COOKIE_NAME)),
        "allow_server_key": auth.allow_server_key(),
    }


def load_env():
    """读 .env。

    容错优先：用户多半是「复制 .env.example 再用记事本另存」，于是
    - UTF-8 with BOM 会让第一个 key 变成 `\\ufeffDEEPSEEK_API_KEY`，读不到；
    - ANSI/GBK（文件里有中文注释）会直接 UnicodeDecodeError，服务起不来。
    所以按 utf-8-sig → gb18030 → utf-16 依次试，最后兜底 errors=replace。
    也容忍 `export KEY=...` 这种从 shell 文档抄来的写法。
    """
    env = {}
    p = paths.env_path()
    if not p.exists():
        return env
    raw = p.read_bytes()
    text = None
    for enc in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def resolve_llm(body):
    """解析 API key/base_url/model：请求体优先，其次 .env，再次环境变量。

    base_url 一律经过 normalize_base_url 收敛：用户把官网域名（如
    www.lumdatech.com）当接口地址填的情况很常见，直接拼 /chat/completions 会
    被网关挡成 405。这里顺手纠正，并把「实际用的地址」带到错误信息里。

    **BYOK 模式**（`PAPERMATE_ALLOW_SERVER_KEY=0`）下只认请求体里的 Key，
    服务端 `.env` 与进程环境变量一律不看。多租户部署时这是防止「某个人
    拿公共 Key 刷额度」的唯一可靠办法——前端可以藏输入框，但接口挡不住。
    """
    env = load_env()
    fallback = auth.allow_server_key()
    key = body.get("api_key")
    if not key and fallback:
        key = env.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    raw_base = body.get("base_url")
    if not raw_base and fallback:
        raw_base = env.get("DEEPSEEK_BASE_URL") or os.environ.get("DEEPSEEK_BASE_URL")
    model = body.get("model")
    if not model and fallback:
        model = env.get("DEEPSEEK_MODEL") or os.environ.get("DEEPSEEK_MODEL")

    base, _note = llm.normalize_base_url(raw_base)
    if not model:
        # 按服务商给一个能跑通的默认模型（DeepSeek / Claude / 萤算各不同）
        model = llm.default_model_for(base)
    return key, base, model


# ---------------- 请求模型 ----------------

class LexicalReq(BaseModel):
    text: str
    track: str
    genre: str | None = None


class DeepReq(BaseModel):
    text: str
    track: str
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class CombinedReq(BaseModel):
    text: str
    track: str
    genre: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    votes: int = 3          # 复判投票次数（1–5）
    with_deep: bool = True  # 是否同时深审无检测器规则


class WorkflowReq(BaseModel):
    stage: int
    params: dict = {}
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class ChatReq(BaseModel):
    session_id: str | None = None
    message: str
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class TrendReq(BaseModel):
    topic: str


class ExportReq(BaseModel):
    markdown: str
    format: str = "docx"          # md | docx | tex
    title: str | None = None
    ai_generated: bool = False    # 一键成稿等 AI 产出：导出时强制嵌入水印警示


class OneShotGateReq(BaseModel):
    cfg: dict = {}


class OneShotStartReq(BaseModel):
    cfg: dict = {}
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class OneShotJobReq(BaseModel):
    job_id: str
    step: str | None = None
    # 重跑需要补 Key：重启后任务内存里没有 llm 配置（不落盘，见 oneshot._persist）
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


# ---------------- API ----------------

# 前端靠这份清单判断后端新旧：少一项就是没重启，直接提示重启，而不是让用户猜地址
FEATURES = ["llm_test", "title_translate", "dataset_profile", "oneshot_v2",
            "data_bundle", "data_autotrack", "data_gap", "data_sources", "data_find",
            "data_download", "data_demo",
            # 1.3.0 云部署：前端见到这四项才知道后端支持登录与状态恢复
            "cloud_auth", "persist_jobs", "byok", "server_mode"]

# 一次最多接收几份数据文件（主表 + 若干附表）
MAX_DATA_FILES = 8


@app.get("/api/health")
def health():
    """探活接口。容器 healthcheck 打的也是这个。

    注意：这里**不能**因为缺少 API Key 就返回非 200——容器编排会把
    「没配 Key」当成「服务挂了」反复重启。缺 Key 只体现在字段里。
    """
    env = load_env()
    has_key = bool(env.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY"))
    return {
        "ok": True,
        "version": VERSION,
        "has_default_key": has_key and auth.allow_server_key(),
        "access_mode": auth.mode(),
        "data_dir": str(DATA_DIR),
        "jobs": len(oneshot.JOBS),
    }


@app.get("/api/meta")
def meta():
    data = engine.meta()
    data["providers"] = llm.PROVIDERS
    data["llm_defaults"] = {"base_url": llm.DEFAULT_BASE_URL, "model": llm.DEFAULT_MODEL}
    # 前端据此决定要不要显示「尚未配置 API Key」：.env 里带 key 时不该再提示。
    # BYOK 模式下即使配了也不认，所以要和 allow_server_key() 一起判断。
    env = load_env()
    data["has_default_key"] = bool(
        env.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    ) and auth.allow_server_key()
    # 前端据此判断「我连的后端是不是旧版本」：旧进程没有这些接口，会以 405 报错
    data["features"] = list(FEATURES)
    # 部署形态：private（本机）/ shared（口令+公共 Key）/ byok（口令+自带 Key）
    data["access"] = {"mode": auth.mode(), "allow_server_key": auth.allow_server_key()}
    return data


class LLMTestReq(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


@app.post("/api/llm/test")
def llm_test(req: LLMTestReq):
    """模型连通性自检：不发正文、不改配置，只回答「这个地址+key 能不能用」。

    这里刻意不先归一化：把用户原样的输入交给 test_connection，才能在结果里
    告诉他「你填的是官网，已按服务商规范纠正为 ...」。
    """
    env = load_env()
    key = req.api_key or env.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    raw_base = req.base_url or env.get("DEEPSEEK_BASE_URL") or os.environ.get("DEEPSEEK_BASE_URL") or ""
    model = req.model or env.get("DEEPSEEK_MODEL") or os.environ.get("DEEPSEEK_MODEL") or ""
    if not key:
        raise HTTPException(400, "还没有填 API Key")

    normalized, _ = llm.normalize_base_url(raw_base)
    if not model:
        model = llm.default_model_for(normalized)
    try:
        return llm.test_connection(key, raw_base, model)
    except Exception as e:
        return {"ok": False, "base_input": raw_base, "base_used": normalized,
                "model": model, "note": "", "corrected": False, "latency_ms": None,
                "protocol": llm.protocol_of(normalized),
                "models": [], "via": "", "hint": f"自检异常：{e}"}


@app.get("/api/topic/venues")
def topic_venues(track: str = "quant"):
    return {"track": track, "venues": engine.venues_for_track(track)}


@app.post("/api/topic/trend")
def topic_trend_api(req: TrendReq):
    if not req.topic or not req.topic.strip():
        raise HTTPException(400, "研究主题不能为空")
    try:
        return topic_trend.get_trend(req.topic)
    except Exception as e:
        raise HTTPException(500, f"趋势获取失败：{e}")


# ---------------- 格式：摄取 / 图片 / 导出 ----------------

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}


@app.post("/api/ingest")
async def api_ingest(file: UploadFile = File(...)):
    """Word / Markdown / LaTeX / PDF / HTML -> Markdown（表格、图片、公式保留）。"""
    data = await file.read()
    try:
        result = await run_in_threadpool(ingest.ingest, file.filename or "", data)
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"文件解析失败：{e}")
    result["filename"] = file.filename or ""
    return result


@app.post("/api/ingest/html")
async def api_ingest_html(req: dict):
    """粘贴的 Word/网页剪贴板 HTML -> Markdown（前端拦截 paste 时调用）。"""
    html = (req or {}).get("html") or ""
    if not html.strip():
        raise HTTPException(400, "内容为空")
    try:
        result = await run_in_threadpool(ingest.html_to_markdown, html)
    except ingest.IngestError as e:
        raise HTTPException(400, str(e))
    return result


@app.post("/api/upload/image")
async def api_upload_image(file: UploadFile = File(...)):
    """粘贴/拖入的截图：存本地并返回可访问 URL，正文里插入 ![](url)。"""
    ext = Path(file.filename or "img.png").suffix.lower() or ".png"
    if ext not in ALLOWED_IMAGE_EXT:
        raise HTTPException(400, f"不支持的图片格式：{ext}")
    data = await file.read()
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(400, "图片超过 12MB")
    url = ingest._save_bytes(data, ext)
    return {"url": url}


def _safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", (name or "").strip())
    return (name[:60] or "academic-writing")


AI_WATERMARK_MD = """
> ⚠️ **AI 生成内容警示：本文件禁止直接用于投稿、交稿或发表。**
>
> 本文全部文本由 AI 生成，导出或转存的副本可能含可见或不可见的 AI 标记
> （水印 / 隐写标识 / 元数据）。带标记的稿件投稿会被期刊 AI 检测判为代写，
> 且隐写标记**无法通过转 PDF、截图、复制粘贴去除**。
>
> 正确用法：仅作写作骨架。逐段用自己的语言重写；`[TBD: ...]` 填真实数据；
> `[CITE: ...]` 换成可核实文献；最终稿必须是你自己重新写出的文本。

"""

AI_WATERMARK_TEX = """%% AI 生成内容警示：本文件禁止直接用于投稿、交稿或发表。
%% 本文全部文本由 AI 生成，可能含可见或不可见的 AI 标记（水印 / 隐写标识）。
%% 带标记的稿件投稿会被判为 AI 代写，且标记无法通过转 PDF、截图去除。
%% 仅作写作骨架：逐段用自己的语言重写，数据与文献全部换成真实可核实的。

"""


@app.post("/api/export")
def api_export(req: ExportReq):
    """把 Markdown 结果导出为 md / docx / tex。"""
    if not (req.markdown or "").strip():
        raise HTTPException(400, "内容为空，无法导出")
    fmt = (req.format or "docx").lower()
    base = _safe_filename(req.title or "PaperMate_导出")
    # AI 产出（一键成稿）导出的文件必须自带警示，否则文件一旦离开页面就失去了提醒
    md = (AI_WATERMARK_MD + req.markdown) if req.ai_generated else req.markdown

    if fmt == "md":
        data = md.encode("utf-8")
        media, ext = "text/markdown; charset=utf-8", ".md"
    elif fmt == "docx":
        try:
            data = export.markdown_to_docx(md, req.title)
        except Exception as e:
            raise HTTPException(500, f"Word 导出失败：{e}")
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = ".docx"
    elif fmt in ("tex", "latex"):
        try:
            tex = export.markdown_to_tex(md, req.title or "PaperMate 生成结果")
        except Exception as e:
            raise HTTPException(500, f"LaTeX 导出失败：{e}")
        if req.ai_generated:
            tex = AI_WATERMARK_TEX + tex

        # 正文含本地图片时打包成 Overleaf 可直接上传的 zip（main.tex + figures/）
        figures = []
        for rel in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", tex):
            src = ingest.UPLOAD_DIR / Path(rel).name
            if src.exists():
                figures.append((rel, src))
        if figures:
            buf = BytesIO()
            with ZipFile(buf, "w", ZIP_DEFLATED) as zf:
                zf.writestr("main.tex", tex)
                for rel, src in figures:
                    zf.write(src, rel)
                zf.writestr(
                    "README.txt",
                    "用法：Overleaf 新建项目 -> Upload -> 选择本 zip 解压后的全部文件。\n"
                    "中文文档建议把编译器设为 XeLaTeX（Menu -> Compiler -> XeLaTeX）。\n",
                )
            data, media, ext = buf.getvalue(), "application/zip", "_overleaf.zip"
        else:
            data, media, ext = tex.encode("utf-8"), "application/x-tex; charset=utf-8", ".tex"
    else:
        raise HTTPException(400, f"不支持的导出格式：{fmt}")

    fname = base + ext
    disp = "attachment; filename=\"export%s\"; filename*=UTF-8''%s" % (ext, quote(fname))
    return Response(content=data, media_type=media, headers={"Content-Disposition": disp})


# ---------------- 一键成稿（学术小白） ----------------

@app.post("/api/oneshot/gate")
def oneshot_gate(req: OneShotGateReq):
    """前置条件检查 + 章节计划（不调模型，纯本地判定）。"""
    try:
        return oneshot.gate_check(req.cfg)
    except Exception as e:
        raise HTTPException(500, f"前置检查失败：{e}")


@app.post("/api/oneshot/start")
def oneshot_start(req: OneShotStartReq):
    key, base, model = resolve_llm(req.model_dump())
    if not key:
        raise HTTPException(400, "未配置 API Key（DeepSeek / Anthropic / 萤算），请在设置中填写或写入 .env")
    try:
        jid = oneshot.start(req.cfg, {"api_key": key, "base_url": base, "model": model})
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"启动失败：{e}")
    return {"job_id": jid, "status": oneshot.status(jid)}


class TitleTranslateReq(BaseModel):
    title: str
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


@app.post("/api/oneshot/title/translate")
def oneshot_title_translate(req: TitleTranslateReq):
    """把中文题名译成学术英文题名（选题页复制过来的题目常是中文）。"""
    title = (req.title or "").strip()
    if not title:
        raise HTTPException(400, "题目为空")
    if not oneshot.has_cjk(title):
        return {"ok": True, "title_en": title, "original": title, "changed": False,
                "note": "已经是英文题名，无需翻译"}

    key, base, model = resolve_llm(req.model_dump())
    if not key:
        raise HTTPException(400, "未配置 API Key（DeepSeek / Anthropic / 萤算），请在设置中填写或写入 .env")

    try:
        en = oneshot.translate_title(title, {"api_key": key, "base_url": base, "model": model})
    except Exception as e:
        raise HTTPException(502, f"翻译失败：{e}")
    if not en:
        raise HTTPException(502, "模型没有返回可用的英文题名（可能仍含中文），请重试或手动改写成英文")
    return {"ok": True, "title_en": en, "original": title, "changed": en != title}


@app.get("/api/oneshot/status/{job_id}")
def oneshot_status(job_id: str):
    try:
        return oneshot.status(job_id)
    except KeyError:
        raise HTTPException(404, "任务不存在：可能是数据目录换了位置，或任务已被清理")


@app.post("/api/oneshot/cancel")
def oneshot_cancel(req: OneShotJobReq):
    if not oneshot.cancel(req.job_id):
        raise HTTPException(404, "任务不存在")
    return {"ok": True}


@app.post("/api/oneshot/rerun")
def oneshot_rerun(req: OneShotJobReq):
    if not req.step:
        raise HTTPException(400, "缺少步骤名")
    # 重启后从磁盘恢复的任务内存里没有 llm 配置（含 Key），必须从本次请求补上，
    # 否则重跑会在第一次模型调用处失败。
    key, base, model = resolve_llm(req.model_dump())
    if not key:
        raise HTTPException(400, "未配置 API Key，无法重跑")
    try:
        return oneshot.rerun_with_llm(
            req.job_id, req.step, {"api_key": key, "base_url": base, "model": model})
    except KeyError:
        raise HTTPException(404, "任务不存在")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/oneshot/artifact/{job_id}/{name}")
def oneshot_artifact(job_id: str, name: str):
    """单步产物（Markdown 原文），用于时间轴上点开查看。"""
    try:
        p = oneshot.artifact(job_id, name)
    except KeyError:
        raise HTTPException(404, "任务不存在")
    except FileNotFoundError:
        raise HTTPException(404, "产物尚未生成")
    return {"name": p.name, "markdown": p.read_text(encoding="utf-8", errors="ignore")}


# ---------------- 数据文件画像（只读结构，不存原始行） ----------------

@app.post("/api/oneshot/data")
async def oneshot_data(file: list[UploadFile] = File(...)):
    """解析数据文件的列结构，返回 profile（多份文件合并成一个 bundle）。

    刻意不落原始文件：只把列名、类型、缺失率与汇总统计存成 JSON。作者点「移除」
    即删除该 JSON，原始数据从未离开本机。

    参数名保持 `file`（前端既有调用不变），类型是列表，因此一次传多份也能收全；
    旧实现用单个 UploadFile，多传的文件会被静默丢弃。
    """
    files = list(file or [])[:MAX_DATA_FILES]
    if not files:
        raise HTTPException(400, "没有收到文件")
    items = []
    for f in files:
        raw = await f.read()
        items.append((raw, f.filename or ""))
    try:
        prof = dataset.profile_files(items)
    except dataset.DatasetError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"解析失败：{e}")
    did = dataset.save_profile(prof, oneshot.JOB_DIR)
    prof["id"] = did
    prof["gap"] = dataset.gap_report(prof)
    return prof


@app.get("/api/oneshot/data/{did}")
def oneshot_data_get(did: str):
    prof = dataset.load_profile(did, oneshot.JOB_DIR)
    if not prof:
        raise HTTPException(404, "数据画像不存在或已移除")
    prof["gap"] = dataset.gap_report(prof)
    return prof


class DataSourcesReq(BaseModel):
    topic: str = ""
    need: list[str] = []
    dataset_id: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


@app.post("/api/oneshot/data/sources")
def oneshot_data_sources(req: DataSourcesReq):
    """按题目给出可公开获取的数据源线索。

    只返回链接、取数方式与引用格式：不下载、不解析、不写回画像。
    模型配置是可选的，仅用于把中文题目转成英文检索词（Zenodo/Dataverse 用）；
    没有 key 也能用，只是跳过在线检索、只给白名单入口。
    """
    prof = dataset.load_profile(req.dataset_id, oneshot.JOB_DIR) if req.dataset_id else None
    key, base, model = resolve_llm(req.model_dump())
    cfg = {"api_key": key, "base_url": base, "model": model} if key else None
    try:
        return datasource.suggest(req.topic, req.need, prof, cfg)
    except Exception as e:
        raise HTTPException(500, f"数据源检索失败：{e}")


class DataDownloadReq(BaseModel):
    items: list[dict]
    job_id: str = ""


@app.post("/api/oneshot/data/download")
def oneshot_data_download(req: DataDownloadReq):
    """代下载白名单公开源（世行 / Zenodo / Dataverse），落盘后不解析、不注入。

    只下载 datasource.download 允许的白名单来源；授权/付费/反爬站点一律拒绝并说明。
    返回 {downloaded, skipped, failed, notes}，任何单条失败不影响其余条目。
    """
    if not req.items:
        raise HTTPException(400, "没有要下载的来源")
    outdir = (oneshot.JOB_DIR / req.job_id / "_sources") if req.job_id \
        else (oneshot.JOB_DIR / "_downloads")
    try:
        return datasource.download(req.items, str(outdir))
    except Exception as e:
        raise HTTPException(500, f"代下载失败：{e}")


class DatasetIdReq(BaseModel):
    id: str


@app.post("/api/oneshot/data/delete")
def oneshot_data_delete(req: DatasetIdReq):
    return {"ok": dataset.delete_profile(req.id, oneshot.JOB_DIR)}


# ---------------- 词面检测 / 深度判读 ----------------

@app.post("/api/review/lexical")
def review_lexical(req: LexicalReq):
    if not req.text or not req.text.strip():
        raise HTTPException(400, "稿件正文不能为空")
    if req.track not in engine.TRACKS:
        raise HTTPException(400, f"未知学科主线：{req.track}")
    try:
        # 公式/图片语法会干扰文本正则，检测前归一化（纯文本 md 不受影响）
        return engine.lexical_review(ingest.normalize_for_rules(req.text), req.track, req.genre)
    except Exception as e:
        raise HTTPException(500, f"词面检测失败：{e}")


@app.post("/api/review/deep")
def review_deep(req: DeepReq):
    key, base, model = resolve_llm(req.model_dump())
    if not key:
        raise HTTPException(400, "未配置 API Key（DeepSeek / Anthropic / 萤算），请在设置中填写或写入 .env")
    if not req.text or not req.text.strip():
        raise HTTPException(400, "稿件正文不能为空")
    try:
        result = llm.deep_review(req.text, req.track, key, base, model)
    except Exception as e:
        raise HTTPException(500, f"深度判读失败：{e}")

    # 建立会话，支持后续追问
    sid = uuid.uuid4().hex[:12]
    defects = [v for v in result["verdicts"] if v.get("verdict") == "defect"]
    ctx_lines = [f"- {v['id']}（{v.get('severity','should')}）：{v.get('evidence','')}"
                 for v in defects]
    SESSIONS[sid] = {
        "kind": "review",
        "track": req.track,
        "text": req.text[:15000],
        "context": "此前审查判读出的缺陷：\n" + "\n".join(ctx_lines),
        "history": [],
    }
    state_store.save_session(sid, SESSIONS[sid])
    result["session_id"] = sid
    return result


@app.post("/api/review/combined")
def review_combined(req: CombinedReq):
    """结合审查：脚本词面检测 → 模型读全文复判脚本 must（多数票）→ 模型深审无检测器规则。"""
    key, base, model = resolve_llm(req.model_dump())
    if not key:
        raise HTTPException(400, "未配置 API Key（DeepSeek / Anthropic / 萤算），请在设置中填写或写入 .env")
    if not req.text or not req.text.strip():
        raise HTTPException(400, "稿件正文不能为空")
    if req.track not in engine.TRACKS:
        raise HTTPException(400, f"未知学科主线：{req.track}")
    votes = max(1, min(5, req.votes))
    try:
        return llm.combined_review(ingest.normalize_for_rules(req.text), req.track, key, base, model,
                                   genre=req.genre, votes=votes, with_deep=req.with_deep)
    except Exception as e:
        raise HTTPException(500, f"结合审查失败：{e}")


@app.post("/api/workflow")
def do_workflow(req: WorkflowReq):
    key, base, model = resolve_llm(req.model_dump())
    if not key:
        raise HTTPException(400, "未配置 API Key（DeepSeek / Anthropic / 萤算），请在设置中填写或写入 .env")
    if req.stage not in (1, 2, 3, 4, 6):
        raise HTTPException(400, "该阶段请走审查接口")
    try:
        answer = llm.workflow(req.stage, req.params, key, base, model)
    except Exception as e:
        raise HTTPException(500, f"工作流执行失败：{e}")

    sid = uuid.uuid4().hex[:12]
    SESSIONS[sid] = {
        "kind": "workflow",
        "stage": req.stage,
        "params": req.params,
        "context": "",
        "history": [
            {"role": "user", "content": llm._workflow_task(req.stage, req.params)},
            {"role": "assistant", "content": answer},
        ],
    }
    state_store.save_session(sid, SESSIONS[sid])
    return {"answer": answer, "session_id": sid}


@app.post("/api/chat")
def do_chat(req: ChatReq):
    key, base, model = resolve_llm(req.model_dump())
    if not key:
        raise HTTPException(400, "未配置 API Key（DeepSeek / Anthropic / 萤算）")
    if not req.message or not req.message.strip():
        raise HTTPException(400, "消息不能为空")

    # 先查内存，未命中再查磁盘——容器重启后内存是空的，
    # 但用户浏览器里还留着 session_id，追问必须能接上。
    sess = SESSIONS.get(req.session_id) if req.session_id else None
    if sess is None and req.session_id:
        sess = state_store.load_session(req.session_id)
        if sess is not None:
            sess.pop("_saved_at", None)
            SESSIONS[req.session_id] = sess

    if sess and sess.get("kind") == "review":
        system = (
            llm._SYSTEM_WORKFLOW
            + "\n\n【审查上下文】\n学科主线："
            + engine.TRACK_LABELS.get(sess["track"], sess["track"])
            + "\n" + sess["context"]
            + "\n\n论文正文（前段）：\n" + sess["text"]
            + "\n\n请基于以上上下文，回答用户对审查结果的追问。"
        )
    elif sess:
        system = llm._SYSTEM_WORKFLOW
    else:
        system = llm._SYSTEM_WORKFLOW

    messages = [{"role": "system", "content": system}]
    messages.extend(sess["history"] if sess else [])
    messages.append({"role": "user", "content": req.message})

    try:
        answer = llm.chat(key, messages, base_url=base, model=model, temperature=0.3)
    except Exception as e:
        raise HTTPException(500, f"对话失败：{e}")

    if sess:
        sess["history"].append({"role": "user", "content": req.message})
        sess["history"].append({"role": "assistant", "content": answer})
        # 限制历史长度，避免超长
        sess["history"] = sess["history"][-20:]
        state_store.save_session(req.session_id, sess)

    return {"answer": answer, "session_id": req.session_id or ""}


# 上传的图片等静态资源（须在 "/" 之前挂载，否则会被前端静态目录吞掉）
app.mount("/media", StaticFiles(directory=str(ingest.UPLOAD_DIR)), name="media")

# 静态文件（前端）最后挂载，避免覆盖 /api 路由
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


# ---------------------------------------------------------------- 启动

DEFAULT_PORT = 8000
DEFAULT_HOST = "127.0.0.1"
PORT_SPAN = 20


def bind_host() -> str:
    """监听地址。

    默认 `127.0.0.1`（桌面版，只有本机连得上）。
    容器/云主机必须设 `PAPERMATE_HOST=0.0.0.0`，否则外面永远连不进来——
    这是把本地应用搬上云时最容易忽略的一处。
    """
    return (os.environ.get("PAPERMATE_HOST") or DEFAULT_HOST).strip() or DEFAULT_HOST


def _port_free(port: int, host: str = DEFAULT_HOST) -> bool:
    """端口能不能绑上（只测一次 bind，不真监听）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def _papermate_alive(port: int) -> bool:
    """该端口上是否已经跑着一个健康的 PaperMate。"""
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/health", timeout=1.5) as r:
            return bool(json.loads(r.read().decode("utf-8")).get("ok"))
    except Exception:
        return False


def _pick_port(preferred: int, host: str = DEFAULT_HOST) -> tuple[int, bool]:
    """返回 (端口, 是否被别的程序占过)。

    过去端口占用会让 uvicorn 抛 `[Errno 10048]` 直接退出，用户只看到一屏
    看不懂的英文。现在自动顺延到下一个可用端口，并把实际地址打出来。

    **服务端模式不做顺延**：容器/云主机上端口是对外契约，反代、防火墙、
    健康检查都按固定端口配。悄悄换到 8001 只会让一切都不通，还查不出原因。
    这里宁可让 uvicorn 报错退出、由编排系统拉起并暴露问题。
    """
    if paths.is_server():
        return preferred, False
    if _port_free(preferred, host):
        return preferred, False
    for p in range(preferred + 1, preferred + PORT_SPAN + 1):
        if _port_free(p, host):
            return p, True
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1]), True


def _have(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def _soffice() -> str | None:
    for c in (os.environ.get("SOFFICE_PATH"), shutil.which("soffice"),
              shutil.which("libreoffice"),
              r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if c and Path(c).exists():
            return c
    return None


def _banner(port: int, moved: bool, host: str = DEFAULT_HOST) -> None:
    """启动横幅 + 环境自检。用户「起不来」时第一眼就能看到缺什么。"""
    server_mode = paths.is_server()
    # 服务端模式下 127.0.0.1 这个地址对用户毫无意义（他在自己电脑上），
    # 打出来反而误导，所以只报端口和监听地址。
    if server_mode:
        url = f"http://{host}:{port}"
    else:
        url = f"http://127.0.0.1:{port}"
    bits = "64 位" if sys.maxsize > 2 ** 32 else "32 位"
    print("")
    print("=" * 62)
    print(f"  PaperMate {app.version}   ->  {url}")
    print("=" * 62)
    if moved:
        print(f"  注意：{DEFAULT_PORT} 端口已被其他程序占用，已自动改用 {port}。")
        print(f"        浏览器请开 {url}（不是 8000）。")
    if server_mode:
        print(f"  模式     服务端（监听 {host}）")
    print(f"  Python   {sys.version.split()[0]}  ({bits})")

    # 必需依赖
    need = [("fastapi", "FastAPI"), ("uvicorn", "uvicorn"), ("yaml", "PyYAML"),
            ("requests", "requests"), ("multipart", "python-multipart"),
            ("docx", "python-docx"), ("lxml", "lxml")]
    miss = [label for mod, label in need if not _have(mod)]
    if miss:
        print(f"  [缺] 依赖缺失：{', '.join(miss)}")
        print("       请运行：python -m pip install -r requirements.txt")
    else:
        print("  [OK] 必需依赖齐全")

    # 可选能力
    opt = []
    opt.append("[OK] xlsx 数据" if _have("openpyxl") else "[缺] xlsx 数据（装 openpyxl）")
    opt.append("[OK] PDF 上传" if (_have("pymupdf") or _have("fitz"))
               else "[缺] PDF 上传（装 PyMuPDF）")
    opt.append("[OK] dta/sav/parquet" if _have("pandas") else "[--] dta/sav/parquet（可选 pandas）")
    opt.append("[OK] LibreOffice" if _soffice() else "[--] .doc/.xls/.ods（可选 LibreOffice）")
    print("  可选：" + "  ".join(opt))

    # API Key 与访问控制
    env = load_env()
    key = (env.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    m = auth.mode()
    if m == "byok":
        print("  [OK] 访问模式：BYOK（用户自带 Key，服务端 Key 不参与）")
        if key:
            print("       .env 里有 DEEPSEEK_API_KEY，但 ALLOW_SERVER_KEY=0，已忽略")
    else:
        if key:
            print("  [OK] API Key 已配置" + ("（口令保护）" if m == "shared" else ""))
        else:
            print("  [--] 未配置 API Key：启动后在网页右上角「设置」里填，")
            print("       或把 .env.example 复制成 .env 再填 DEEPSEEK_API_KEY")
        if m == "shared":
            print("  [OK] 访问口令已启用（shared 模式）")

    if server_mode and m == "private":
        # 这是最容易出事的组合：0.0.0.0 监听 + 无口令 = 整个公网都能用你的 Key
        print("  [!!] 警告：监听在非回环地址，但没设 PAPERMATE_ACCESS_TOKEN。")
        print("       只要能连到这个端口的人都能用你的 API Key。")
        print("       公网部署请务必设置访问口令（见 deploy/DEPLOY.md）。")

    # 目录可写
    try:
        ingest.UPLOAD_DIR.mkdir(exist_ok=True)
        probe = ingest.UPLOAD_DIR / f".probe_{uuid.uuid4().hex[:6]}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        print(f"  [OK] 数据目录可写：{ingest.UPLOAD_DIR}")
    except Exception as e:
        print(f"  [缺] 数据目录不可写：{ingest.UPLOAD_DIR}（{e}）")
        print("       请把整个文件夹解压到「文档」或桌面这类有写权限的位置，")
        print("       不要放在 Program Files、只读盘或压缩包里直接运行。")
        if server_mode:
            print("       容器里请确认卷已挂到 PAPERMATE_DATA_DIR，且属主是运行用户。")

    print("=" * 62)
    print("  停止服务：Ctrl+C（或直接关掉这个窗口）" if not server_mode
          else "  停止服务：docker stop / systemctl stop papermate")
    print("")


def _open_browser(url: str) -> None:
    """自动开浏览器。服务端模式、无 DISPLAY 时一律不试。

    容器里 `webbrowser.open` 找不到浏览器，某些发行版还会因为等 xdg-open
    超时卡住几秒；以前这个调用包在 try 里不会崩，但会拖慢启动。
    """
    if paths.is_server() or os.environ.get("PAPERMATE_NO_BROWSER"):
        return
    if os.name != "nt" and not os.environ.get("DISPLAY") \
            and not os.environ.get("WAYLAND_DISPLAY"):
        return
    try:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    except Exception:
        pass


def _restore_sessions() -> None:
    """启动时清理过期会话、恢复历史任务索引。

    只恢复索引，不重跑任务：中断在「生成中」的任务保持中断状态，界面上
    显示为失败/未完成，用户可以点重跑。假装它还在跑只会让人白等。
    """
    try:
        n = state_store.prune_sessions()
        if n:
            print(f"  [OK] 清理过期会话 {n} 条")
    except Exception:
        pass
    try:
        jobs = oneshot.restore()
        if jobs:
            print(f"  [OK] 恢复历史任务 {jobs} 条")
    except Exception as e:  # noqa: BLE001
        print(f"  [--] 任务恢复跳过：{e}")


def main() -> int:
    try:
        # 输出重定向到文件/管道时默认是块缓冲，横幅会迟迟不出现；
        # 改成逐行刷新，用户双击后立刻能看到自检结果。
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

    try:
        preferred = int(os.environ.get("PAPERMATE_PORT") or DEFAULT_PORT)
    except ValueError:
        preferred = DEFAULT_PORT

    host = bind_host()

    # 已经在跑：不要再起第二个实例（内存里的任务不共享，用户会以为「没反应」）。
    # 服务端模式下这个检测有害：容器里本机探测永远成功会直接退出，
    # 让编排系统误以为只是短暂重启。单实例交给编排去管。
    if not paths.is_server() and _papermate_alive(preferred):
        url = f"http://127.0.0.1:{preferred}"
        print(f"\n  PaperMate 已经在运行：{url}")
        print("  直接打开浏览器即可；这个窗口可以关掉。\n")
        _open_browser(url)
        return 0

    _restore_sessions()
    port, moved = _pick_port(preferred, host)
    _banner(port, moved, host)
    _open_browser(f"http://127.0.0.1:{port}")

    import uvicorn
    if paths.is_server():
        # 服务端模式：日志走 stdout（容器日志采集靠它），不写文件；
        # proxy_headers 让 Nginx 的 X-Forwarded-For 生效，access log 里
        # 才是真实客户端 IP，排查「谁在刷接口」时必需。
        uvicorn.run(app, host=host, port=port, log_level="info",
                    proxy_headers=True,
                    forwarded_allow_ips=os.environ.get("PAPERMATE_TRUSTED_PROXIES",
                                                      "127.0.0.1"))
    else:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())

