# -*- coding: utf-8 -*-
"""LLM 层：DeepSeek / Anthropic / Lumda AI 三家接入 + 六阶段工作流。

只接三家，各按各的协议：
- DeepSeek 官方：OpenAI 兼容（POST {base}/chat/completions）
- Anthropic 官方：原生 Messages API（POST {base}/v1/messages，x-api-key 头）
- Lumda AI：OpenAI 兼容（POST /api/v1/chat/completions），一个 key 转多模型

- deep_review: 对需人工判读的规则逐条判读，输出三层风险清单
- workflow: 选题/设计/初稿/引用/投稿返修 的引导
"""
import json
import re

import requests

import engine

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_MODEL_ANTHROPIC = "claude-sonnet-4-5"
DEFAULT_MODEL_LUMDA = "deepseek-v4-pro"

# ---------------------------------------------------------------- 服务商预设
#
# 只描述「接入地址 + 协议 + 常见模型 ID」，不涉及任何计费逻辑。前端设置面板读
# 这份数据渲染预设，后端 normalize_base_url 用它纠正粘贴错的地址。
# 刻意只保留三家：不设通用「自定义中转」入口，地址填错时由程序自动纠正。

PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek 官方",
        "protocol": "openai",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-chat", "deepseek-v4-pro", "deepseek-flash"],
        "note": "官方直连（OpenAI 兼容）：deepseek-chat 稳定别名，v4-pro 推理更强、flash 更快",
        "signup": "https://platform.deepseek.com/",
    },
    "anthropic": {
        "label": "Anthropic 官方",
        "protocol": "anthropic",
        "base_url": "https://api.anthropic.com",
        "models": ["claude-sonnet-4-5", "claude-haiku-4-5", "claude-opus-4-1"],
        "note": "原生 Messages API；地址只填到 api.anthropic.com（不带 /v1），key 在 console.anthropic.com 创建",
        "signup": "https://console.anthropic.com/",
    },
    "lumda": {
        "label": "Lumda AI",
        "protocol": "openai",
        "base_url": "https://api.lumdatech.com/api/v1",
        "models": ["deepseek-v4-pro", "deepseek-flash"],
        "note": "OpenAI 兼容，一个 key 可调 DeepSeek / Claude / GPT / Gemini；注册即送 5 元体验券，低至 6 折起，星际直连",
        "signup": ("https://www.lumdatech.com/?utm_source=academic-writing-agent"
                   "&utm_medium=referral&utm_campaign=settings"),
    },
}
PROVIDER_ORDER = ("deepseek", "anthropic", "lumda")

# 域名 → 规范 base。用户常把「官网域名」当 API 地址填，这里一次性纠正。
_HOST_ALIASES = {
    "lumdatech.com": "https://api.lumdatech.com/api/v1",
    "www.lumdatech.com": "https://api.lumdatech.com/api/v1",
    "api.lumdatech.com": "https://api.lumdatech.com/api/v1",
    "deepseek.com": "https://api.deepseek.com",
    "www.deepseek.com": "https://api.deepseek.com",
    "api.deepseek.com": "https://api.deepseek.com",
    "anthropic.com": "https://api.anthropic.com",
    "www.anthropic.com": "https://api.anthropic.com",
    "api.anthropic.com": "https://api.anthropic.com",
    "claude.ai": "https://api.anthropic.com",
}

# 用户可能连端点一起粘进来，这些尾巴要切掉
_ENDPOINT_SUFFIXES = (
    "/chat/completions", "/v1/chat/completions", "/api/v1/chat/completions",
    "/v1/messages", "/api/v1/messages", "/messages",
    "/v1/complete", "/api/v1/complete", "/completions", "/models",
)


def protocol_of(base: str | None) -> str:
    """按地址判断走哪套协议：Anthropic 原生，其余按 OpenAI 兼容。"""
    from urllib.parse import urlparse

    try:
        host = (urlparse(base or "").hostname or "").lower()
    except Exception:
        host = ""
    return "anthropic" if host.endswith("anthropic.com") else "openai"


def default_model_for(base: str | None) -> str:
    """按服务商给默认模型，避免拿 deepseek-chat 去打 Claude。"""
    proto = protocol_of(base)
    if proto == "anthropic":
        return DEFAULT_MODEL_ANTHROPIC
    if "lumdatech" in (base or ""):
        return DEFAULT_MODEL_LUMDA
    return DEFAULT_MODEL


def normalize_base_url(raw: str | None) -> tuple[str, str]:
    """把用户填的地址收敛成可用的 base。

    返回 (base, note)。note 非空表示做过纠正，用于界面提示与错误说明。
    """
    s = (raw or "").strip()
    if not s:
        return DEFAULT_BASE_URL, ""

    note = ""
    if "://" not in s:
        s = "https://" + s
        note = "补全协议头"
    s = s.rstrip("/")

    # 切掉误贴的端点尾巴（可能重复多层，循环处理）
    changed = True
    while changed:
        changed = False
        low = s.lower()
        for suf in _ENDPOINT_SUFFIXES:
            if low.endswith(suf):
                s = s[: -len(suf)].rstrip("/")
                note = (note + "；" if note else "") + "去掉多余的接口路径"
                changed = True
                break

    from urllib.parse import urlparse

    u = urlparse(s)
    host = (u.hostname or "").lower().rstrip(".")
    canon = _HOST_ALIASES.get(host)

    if canon:
        path = (u.path or "").rstrip("/")
        # 空路径或只有 /v1、/api、/api/v1 这类通用前缀 → 直接用规范地址
        if path in ("", "/v1", "/api", "/api/v1"):
            if s != canon:
                note = (note + "；" if note else "") + f"按服务商规范纠正为 {canon}"
            return canon, note
        # 用户填了自定义反代路径（如 https://api.lumdatech.com/proxy/v1）→ 尊重原样
        if s != canon:
            note = (note + "；" if note else "") + "使用自定义路径，未套用服务商默认地址"
        return s, note

    return s, note


def base_candidates(base: str) -> list[str]:
    """同一个 base 的候选形式：原样 + 补/去 /v1，用于 404/405 自愈重试。"""
    b = base.rstrip("/")
    # 已知服务商的规范地址就是唯一正解，不要拿 /api 这种半截路径去试探
    from urllib.parse import urlparse

    host = (urlparse(b).hostname or "").lower()
    canon = _HOST_ALIASES.get(host)
    if canon and b == canon:
        return [b]

    out = [b]
    if b.endswith("/api/v1"):
        alt = b[: -len("/v1")]
    elif b.endswith("/v1"):
        alt = b[:-3]
    else:
        alt = b + "/v1"
    if alt and alt not in out:
        out.append(alt)
    return out


def explain_http_error(status: int, base: str, body, proto: str | None = None) -> str:
    """把 HTTP 状态码翻成「下一步该做什么」。proto 用于反代场景下仍按协议给提示。"""
    host = ""
    try:
        from urllib.parse import urlparse

        host = (urlparse(base).hostname or "").lower()
    except Exception:
        pass
    is_anthropic = proto == "anthropic" or "anthropic" in host

    detail = ""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            detail = str(err.get("message") or err.get("code") or "")
        elif err:
            detail = str(err)
        detail = detail or str(body.get("message") or body.get("detail") or "")
    else:
        detail = str(body or "")[:200]

    if status == 405:
        if "lumdatech" in host:
            return ("接口地址不对：这是 Lumda AI 的官网域名，不接受 API 请求。"
                    "请在设置里选「Lumda AI」预设，或把接口地址填成 "
                    "https://api.lumdatech.com/api/v1")
        if is_anthropic:
            return ("接口地址不对：Anthropic 走的是 /v1/messages，不是 /chat/completions。"
                    "地址只填 https://api.anthropic.com（不要带 /v1 或 /messages）")
        return (f"接口地址不对：{base} 不接受 POST /chat/completions（405）。"
                "请确认地址填到 /v1 为止，例如 https://api.deepseek.com 或 "
                "https://api.lumdatech.com/api/v1")
    if status == 404:
        if "lumdatech" in host:
            return ("接口不存在：Lumda AI 的 API 地址是 https://api.lumdatech.com/api/v1"
                    "（不是 www.lumdatech.com，也不要以 /chat/completions 结尾）")
        if is_anthropic:
            return ("接口不存在：Anthropic 只需填 https://api.anthropic.com；"
                    "不要把 /v1/messages 一起粘进地址，也不要用 claude.ai 的地址")
        return f"接口不存在（404）：{base} 可能缺少 /v1 前缀，或该中转站路径不同"
    if status == 401:
        if is_anthropic:
            return ("API Key 无效（401）：Anthropic 用的是 console.anthropic.com 创建的 "
                    "key（sk-ant- 开头），不是 claude.ai 的登录密码")
        return "API Key 无效或已过期（401），请重新复制 key，注意不要带空格或引号"
    if status == 403:
        if is_anthropic:
            return ("Key 无权限或当前网络地区不支持（403）。Anthropic 按账号地区开放，"
                    "可换用 Lumda AI 等中转通道，或检查 key 的额度与权限")
        return "Key 被禁用或权限不足（403），请到服务商控制台检查"
    if status == 402:
        return "账户余额不足（402），请先充值再试"
    if status == 429:
        return "请求过于频繁或并发超限（429），等几十秒再试"
    if status == 529:
        return "Anthropic 侧临时过载（529），等一会儿重试，或临时换成 claude-haiku-4-5"
    if status in (500, 502, 503, 504):
        return f"模型服务暂时不可用（{status}），通常是平台侧抖动，稍后重试；若持续，换个模型或服务商"
    return f"LLM 调用失败（{status}）" + (f"：{detail}" if detail else "")


def _post_chat(url: str, api_key: str, payload: dict, timeout: int):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    return requests.post(url, headers=headers, json=payload, timeout=timeout)


# ---------------- Anthropic 原生 Messages API ----------------
#
# 与 OpenAI 兼容格式的差别：key 走 x-api-key 头、必须带 anthropic-version、
# system 单独一个字段、messages 里只能有 user/assistant、max_tokens 必填。

ANTHROPIC_VERSION = "2023-06-01"


def _anthropic_headers(api_key: str) -> dict:
    return {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }


def _anthropic_payload(messages, model, temperature, max_tokens):
    system_parts = []
    conv = []
    for m in messages or []:
        role = m.get("role")
        content = m.get("content") or ""
        if role == "system":
            system_parts.append(content)
            continue
        if role not in ("user", "assistant"):
            continue
        # Anthropic 要求角色严格交替，相邻同角色合并
        if conv and conv[-1]["role"] == role:
            conv[-1]["content"] += "\n\n" + content
        else:
            conv.append({"role": role, "content": content})
    if not conv:
        conv = [{"role": "user", "content": "ping"}]
    if conv[0]["role"] != "user":
        conv.insert(0, {"role": "user", "content": "（对话开始）"})

    payload = {
        "model": model,
        "messages": conv,
        "max_tokens": int(max_tokens or 8192),
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    if temperature is not None:
        payload["temperature"] = max(0.0, min(1.0, float(temperature)))
    return payload


def _anthropic_text(data) -> str:
    if not isinstance(data, dict):
        return ""
    blocks = data.get("content") or []
    parts = [b.get("text") for b in blocks
             if isinstance(b, dict) and b.get("type") == "text"]
    return "".join(p for p in parts if p)


def chat(api_key, messages, base_url=None, model=None, temperature=0.2, timeout=600,
         max_tokens=None, protocol=None):
    """统一入口：按地址自动选协议（Anthropic 原生 / OpenAI 兼容）。"""
    base, _ = normalize_base_url(base_url)
    proto = protocol or protocol_of(base)
    model = model or default_model_for(base)

    last_err = None
    for cand in base_candidates(base):
        if proto == "anthropic":
            url = cand + "/v1/messages"
            payload = _anthropic_payload(messages, model, temperature, max_tokens)
            try:
                resp = requests.post(url, headers=_anthropic_headers(api_key),
                                     json=payload, timeout=timeout)
            except requests.RequestException as e:
                last_err = RuntimeError(
                    f"无法连接 {cand}：{type(e).__name__}。请检查网络/代理，或换一个服务商")
                continue

            if resp.status_code == 200:
                text = _anthropic_text(resp.json())
                if text:
                    return text
                raise RuntimeError("Anthropic 返回里没有文本块，可能是内容被安全策略拦截")

            body = _safe_json(resp)
            last_err = RuntimeError(explain_http_error(resp.status_code, cand, body, proto))
            if resp.status_code not in (404, 405):
                break
            continue

        url = cand + "/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        # 部分平台（如 Lumda AI）明确忽略 temperature；仍带上以兼容标准实现
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens:
            payload["max_tokens"] = int(max_tokens)

        try:
            resp = _post_chat(url, api_key, payload, timeout)
        except requests.RequestException as e:
            last_err = RuntimeError(
                f"无法连接 {cand}：{type(e).__name__}。请检查网络/代理，或换一个接口地址")
            continue

        if resp.status_code == 200:
            data = resp.json()
            try:
                return data["choices"][0]["message"]["content"]
            except Exception:
                # 兼容 /v1/complete 风格（无 choices，只有 output）
                if isinstance(data, dict) and isinstance(data.get("output"), str):
                    return data["output"]
                raise RuntimeError(f"返回格式无法解析：{str(data)[:200]}")

        last_err = RuntimeError(explain_http_error(resp.status_code, cand, _safe_json(resp), proto))

        # 只有「地址不对」才换候选重试；认证、限流、余额等问题重试无意义
        if resp.status_code not in (404, 405):
            break

    raise last_err or RuntimeError("LLM 调用失败：未知原因")


def test_connection(api_key: str, base_url: str | None = None, model: str | None = None,
                    timeout: int = 25, protocol: str | None = None) -> dict:
    """探活：优先 GET /models（不产生 token 费用），失败再发一个最小请求。"""
    import time

    base_in = (base_url or "").strip()
    base, note = normalize_base_url(base_in)
    proto = protocol or protocol_of(base)
    result = {
        "ok": False,
        "protocol": proto,
        "base_input": base_in,
        "base_used": base,
        "corrected": bool(note),
        "note": note,
        "model": model or default_model_for(base),
        "latency_ms": None,
        "models": [],
        "hint": "",
        "via": "",
    }

    if proto == "anthropic":
        headers = _anthropic_headers(api_key)
        models_path = "/v1/models"
        chat_path = "/v1/messages"
    else:
        headers = {"Authorization": f"Bearer {api_key}"}
        models_path = "/models"
        chat_path = "/chat/completions"

    t0 = time.time()
    for cand in base_candidates(base):
        try:
            r = requests.get(cand + models_path, headers=headers, timeout=timeout)
        except requests.RequestException as e:
            result["hint"] = f"无法连接 {cand}：{type(e).__name__}。检查网络或代理设置"
            continue

        result["latency_ms"] = int((time.time() - t0) * 1000)

        if r.status_code == 200:
            ids = []
            try:
                js = r.json()
                arr = js.get("models") or js.get("data") or []
                for it in arr:
                    if isinstance(it, dict) and it.get("id"):
                        ids.append(str(it["id"]))
                    elif isinstance(it, str):
                        ids.append(it)
            except Exception:
                pass
            result.update({"ok": True, "models": ids[:80], "base_used": cand,
                           "via": models_path})
            picked = result["model"]
            if picked and ids and picked not in ids:
                result["hint"] = (f"连接正常；服务端 /models 未列出「{picked}」"
                                  f"（可能是旧别名或需单独开通），可先按它试跑，"
                                  f"失败再换：{'、'.join(ids[:6])}")
            else:
                result["hint"] = "连接正常"
            return result

        if r.status_code in (401, 403):
            result.update({"base_used": cand, "via": models_path})
            result["hint"] = explain_http_error(r.status_code, cand, _safe_json(r), proto)
            return result

        if r.status_code in (404, 405):
            continue

        result["hint"] = explain_http_error(r.status_code, cand, _safe_json(r), proto)
        return result

    # /models 不可用 → 发最小请求探活
    for cand in base_candidates(base):
        try:
            if proto == "anthropic":
                payload = _anthropic_payload(
                    [{"role": "user", "content": "ping"}], result["model"], None, 1)
                r = requests.post(cand + chat_path, headers=headers, json=payload, timeout=timeout)
            else:
                payload = {"model": result["model"],
                           "messages": [{"role": "user", "content": "ping"}],
                           "max_tokens": 1, "stream": False}
                r = _post_chat(cand + chat_path, api_key, payload, timeout)
        except requests.RequestException as e:
            result["hint"] = f"无法连接 {cand}：{type(e).__name__}。检查网络或代理设置"
            continue
        result["latency_ms"] = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            result.update({"ok": True, "base_used": cand, "via": chat_path,
                           "hint": "连接正常（该服务未提供 /models，已用最小请求验证）"})
            return result
        if r.status_code in (404, 405):
            continue
        result.update({"base_used": cand, "via": chat_path})
        result["hint"] = explain_http_error(r.status_code, cand, _safe_json(r), proto)
        return result

    if not result["hint"]:
        result["hint"] = ("该地址既没有 /models 也不接受对话请求。"
                          "请确认填的是 API 地址而不是官网地址")
    return result


def _safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return resp.text


def extract_json(text):
    """从 LLM 输出中稳健提取 JSON（容忍 markdown 代码块包裹）。"""
    if not text:
        return []
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1)
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        return json.loads(text)
    except Exception:
        # 兜底：逐行找 { ... }
        objs = []
        for m in re.finditer(r"\{[^{}]*\}", text):
            try:
                objs.append(json.loads(m.group(0)))
            except Exception:
                continue
        return objs


_SYSTEM_JUDGE = """你是学术论文写作审查专家。你的任务是根据给定的写作规则，逐条判断论文是否违反规则。

每条规则字段含义：
- id: 规则编号
- rule: 规则内容
- signal: 触发该规则的可判定信号（判读的主要依据）
- fix: 具体修改建议
- source: 规则出处（权威书目）

判读标准：
- defect: 论文违反了该规则（signal 命中，且确实存在）
- pass: 论文满足该规则
- na: 该规则不适用于这篇论文（如规则针对的要素在本文中根本不存在）

severity 分级（仅 verdict=defect 时给出）：
- must 硬伤: 方法有效性、数据诚信、伦理、引用基线问题，不改会被拒稿或无法复核
- should 建议: 规范性与可读性问题，不改会被要求大修
- nice 可选: 优良实践，领域内多数论文未做到

重要校准：
- 已发表论文平均仅约 1.5 处硬伤。若你对一篇正常论文报出 5 处以上硬伤，先怀疑自己判读有误，逐条复核 signal 是否真的命中。
- 只依据给定文本判读，不得臆测论文中未出现的内容。
- evidence 用中文简洁说明命中位置或理由。

只输出 JSON 数组，不要输出任何其他内容。格式：
[{"id":"规则id","verdict":"defect|pass|na","severity":"must|should|nice","evidence":"理由"}]"""


VALID_VERDICTS = ("defect", "pass", "na")
# 单次送模型的正文上限（字符）。DeepSeek/Claude 上下文足以容纳绝大多数整篇论文正文；
# 超过时按段落切块分别判读再合并，而不是像旧版那样直接截断 [:8000]。
JUDGE_CHUNK_CHARS = 60000


def _chunks(text, size=JUDGE_CHUNK_CHARS):
    if len(text) <= size:
        return [text]
    out, cur = [], ""
    for para in re.split(r"(\n\s*\n)", text):
        if len(cur) + len(para) > size and cur:
            out.append(cur)
            cur = ""
        cur += para
    if cur:
        out.append(cur)
    return out


def _merge_chunk_verdicts(per_chunk):
    """多块判读合并：任一块 pass（要素已出现）且另一块 defect → 交人工；
    否则 defect > pass > na。"""
    merged = {}
    for verdicts in per_chunk:
        for v in verdicts:
            merged.setdefault(v.get("id"), []).append(v)
    out = []
    for vid, vs in merged.items():
        kinds = {v.get("verdict") for v in vs}
        if "defect" in kinds and "pass" in kinds:
            base = next(v for v in vs if v.get("verdict") == "defect")
            out.append({**base, "verdict": "review",
                        "evidence": "分块判读结果冲突（部分块通过、部分块缺陷），需人工复核：" + str(base.get("evidence", ""))})
            continue
        for k in ("defect", "pass", "na"):
            hit = [v for v in vs if v.get("verdict") == k]
            if hit:
                out.append(hit[0])
                break
        else:
            out.append(vs[0])
    return out


def judge_batch(track, section_label, section_text, rules, api_key, base_url, model):
    """判读一批规则。正文超长时分块判读后合并（不再硬截断）。"""
    chunks = _chunks(section_text)
    if len(chunks) == 1:
        return _judge_once(track, section_label, chunks[0], rules, api_key, base_url, model)
    per = [_judge_once(track, f"{section_label}（第 {i + 1}/{len(chunks)} 块）", c,
                       rules, api_key, base_url, model) for i, c in enumerate(chunks)]
    return _merge_chunk_verdicts(per)


def _judge_once(track, section_label, section_text, rules, api_key, base_url, model):
    rules_block = [
        {
            "id": r["id"],
            "rule": r.get("rule", ""),
            "signal": r.get("signal", ""),
            "fix": r.get("fix", ""),
            "source": r.get("source", ""),
        }
        for r in rules
    ]
    user = (
        f"论文学科主线：{track}（{engine.TRACK_LABELS.get(track, track)}）\n\n"
        f"【论文正文 · {section_label} 章节】\n{section_text}\n\n"
        f"【待判读规则】{len(rules)} 条：\n"
        + json.dumps(rules_block, ensure_ascii=False, indent=2)
        + "\n\n请逐条判读并输出 JSON 数组。"
    )
    raw = chat(api_key, [{"role": "system", "content": _SYSTEM_JUDGE},
                         {"role": "user", "content": user}],
               base_url=base_url, model=model, temperature=0.1)
    return extract_json(raw)


def deep_review(text, track, api_key, base_url=None, model=None):
    """逐条判读需人工的规则，返回合并后的结构化结果。"""
    rules = engine.manual_rules(track)
    if not rules:
        return {"verdicts": [], "batches": 0, "summary": _summarize([], track)}

    # 按 section 分组，减少上下文切换
    groups = {}
    for r in rules:
        groups.setdefault(r.get("section", "general"), []).append(r)

    rules_by_id = engine.get_rules_by_id()
    verdicts = []
    batches = 0

    def _run(sec, batch):
        sec_text = engine._section_text_for_rule(text, batch[0])
        sec_label = engine.SECTION_LABELS.get(sec, sec)
        try:
            return judge_batch(track, sec_label, sec_text, batch, api_key, base_url, model)
        except Exception as e:  # 单批失败不拖垮整次判读，相关规则记为 unjudged
            return [{"id": r["id"], "verdict": "unjudged",
                     "evidence": f"本批调用失败：{type(e).__name__}"} for r in batch]

    pending = [(sec, group[i:i + 10]) for sec, group in groups.items()
               for i in range(0, len(group), 10)]
    for attempt in range(2):  # 第 2 轮只重试漏判的规则
        next_pending = []
        for sec, batch in pending:
            out = _run(sec, batch)
            batches += 1
            got = set()
            for v in out:
                vid = v.get("id")
                if vid not in {r["id"] for r in batch} or vid in got:
                    continue
                got.add(vid)
                verdicts.append(_make_verdict(v, rules_by_id.get(vid, {}), vid))
            missing = [r for r in batch if r["id"] not in got]
            if missing:
                next_pending.append((sec, missing))
        pending = next_pending
        if not pending:
            break

    # 重试后仍漏判：如实标为 unjudged，不再静默补 pass
    for sec, batch in pending:
        for r in batch:
            verdicts.append(_make_verdict(
                {"verdict": "unjudged", "evidence": "模型未返回该规则的判读（已重试一次）"}, r, r["id"]))

    return {"verdicts": verdicts, "batches": batches, "summary": _summarize(verdicts, track)}


def _make_verdict(v, rule, vid):
    verdict = v.get("verdict")
    if verdict not in VALID_VERDICTS + ("unjudged", "review"):
        # 修复：无效 verdict 不再转为 pass
        verdict = "unjudged"
    sev = v.get("severity", "should")
    if sev not in ("must", "should", "nice"):
        sev = rule.get("severity") if rule.get("severity") in ("must", "should", "nice") else "should"
    return {
        "id": vid,
        "verdict": verdict,
        "severity": sev if verdict in ("defect", "review") else None,
        "evidence": v.get("evidence", ""),
        "rule": rule.get("rule", ""),
        "signal": rule.get("signal", ""),
        "fix": rule.get("fix", ""),
        "source": rule.get("source", ""),
        "example_good": rule.get("example_good", ""),
        "section": rule.get("section", ""),
    }


def _summarize(verdicts, track):
    defects = [v for v in verdicts if v.get("verdict") == "defect"]
    must = [v for v in defects if v.get("severity") == "must"]
    should = [v for v in defects if v.get("severity") == "should"]
    nice = [v for v in defects if v.get("severity") == "nice"]
    unjudged = [v for v in verdicts if v.get("verdict") == "unjudged"]
    review = [v for v in verdicts if v.get("verdict") == "review"]
    return {
        "track": track,
        "judged": len(verdicts) - len(unjudged),
        "total": len(verdicts),
        "defects": len(defects),
        "must": len(must),
        "should": len(should),
        "nice": len(nice),
        "na": sum(1 for v in verdicts if v.get("verdict") == "na"),
        "unjudged": len(unjudged),
        "review": len(review),
        "defect_ids": [v["id"] for v in defects],
        "unjudged_ids": [v["id"] for v in unjudged],
    }


# ---------------- 结合流程：脚本初筛 → 模型全文复判 ----------------
#
# 依据：40 篇真实论文、63 条脚本 must 命中的实测（对比测试/两方案结合必要性分析.md）：
#   脚本单独精确率 34%；送“章节 + 8000 字”复判保留真缺陷 10/17；
#   送“去参考文献全文”复判保留 17/17、剔除无缺陷/不适用 33/33；3 次多数票后误留 0。

RECHECK_VOTES = 3


def _recheck_once(track, body, rules, api_key, base_url, model):
    rb = [{"id": r["id"], "rule": r.get("rule", ""), "signal": r.get("signal", ""),
           "fix": r.get("fix", ""), "source": r.get("source", "")} for r in rules]
    user = (
        f"论文学科主线：{track}（{engine.TRACK_LABELS.get(track, track)}）\n\n"
        # 刻意用中性提示（与 40 篇验证中的 V2 一致）：曾提示"脚本常误判不适用/漏认写法"，
        # 结果模型偏向 na，真缺陷从 17/17 掉到 14/17（见 PaperMate改造说明.md 阶段 4）。
        f"【论文全文（已去参考文献）】\n{body}\n\n"
        f"【待判读规则】{len(rules)} 条：\n" + json.dumps(rb, ensure_ascii=False, indent=2)
        + "\n\n请逐条判读并输出 JSON 数组。"
    )
    raw = chat(api_key, [{"role": "system", "content": _SYSTEM_JUDGE},
                         {"role": "user", "content": user}],
               base_url=base_url, model=model, temperature=0.1)
    return {v.get("id"): v for v in extract_json(raw) if isinstance(v, dict)}


def recheck_lexical(text, track, lexical_defects, api_key, base_url=None, model=None,
                    votes=RECHECK_VOTES, severities=("must",)):
    """用模型读全文复判脚本命中的缺陷（默认只复判 must），多数票决定最终结论。

    返回每条：final ∈ confirmed / not_applicable / passed / review
      - confirmed：多数票 defect
      - not_applicable：多数票 na（规则不适用于本文设计）
      - passed：多数票 pass（要素存在，脚本漏认写法）
      - review：票数不过半或调用失败，交人工
    """
    rules_by_id = engine.get_rules_by_id()
    targets = [d for d in lexical_defects if d.get("severity") in severities]
    if not targets:
        return {"items": [], "calls": 0, "votes": votes,
                "summary": {"checked": 0, "confirmed": 0, "not_applicable": 0, "passed": 0, "review": 0}}
    rules = [rules_by_id[d["id"]] for d in targets if d["id"] in rules_by_id]
    body = engine.body_only(text)
    chunks = _chunks(body)

    ballots = []  # 每次投票：{id: verdict_dict}
    calls = 0
    for _ in range(max(1, votes)):
        merged = {}
        for c in chunks:
            try:
                out = _recheck_once(track, c, rules, api_key, base_url, model)
            except Exception:
                out = {}
            calls += 1
            for vid, v in out.items():
                prev = merged.get(vid)
                # 多块时：任一块 pass 即视为要素存在；否则 defect 优先于 na
                order = {"pass": 3, "defect": 2, "na": 1}
                if prev is None or order.get(v.get("verdict"), 0) > order.get(prev.get("verdict"), 0):
                    merged[vid] = v
        ballots.append(merged)

    items = []
    final_map = {"defect": "confirmed", "na": "not_applicable", "pass": "passed"}
    for d in targets:
        vs = [b.get(d["id"], {}).get("verdict") for b in ballots]
        valid = [v for v in vs if v in VALID_VERDICTS]
        top, n = (None, 0)
        if valid:
            from collections import Counter
            top, n = Counter(valid).most_common(1)[0]
        final = final_map[top] if top and n * 2 > len(vs) else "review"
        ev = next((b[d["id"]].get("evidence", "") for b in ballots
                   if d["id"] in b and b[d["id"]].get("verdict") == top), "")
        items.append({**d, "recheck": {"final": final, "votes": vs, "evidence": ev}})
    summary = {"checked": len(items)}
    for k in ("confirmed", "not_applicable", "passed", "review"):
        summary[k] = sum(1 for it in items if it["recheck"]["final"] == k)
    return {"items": items, "calls": calls, "votes": votes, "summary": summary}


def combined_review(text, track, api_key, base_url=None, model=None, genre=None,
                    votes=RECHECK_VOTES, with_deep=True):
    """结合流程：脚本词面检测 → 模型全文复判脚本 must → （可选）模型深审无检测器规则。"""
    lex = engine.lexical_review(text, track, genre)
    rc = recheck_lexical(text, track, lex["defects"], api_key, base_url, model, votes=votes)
    rechecked = {i["id"]: i["recheck"] for i in rc["items"]}

    findings = []
    for d in lex["defects"]:
        r = rechecked.get(d["id"])
        if r is None:
            status = "script"  # 非 must 级，未复判，保留脚本结论
        else:
            status = r["final"]
        findings.append({**d, "origin": "script", "status": status, "recheck": r})

    deep = None
    if with_deep:
        deep = deep_review(text, track, api_key, base_url, model)
        for v in deep["verdicts"]:
            if v["verdict"] in ("defect", "review", "unjudged"):
                findings.append({**v, "origin": "model",
                                 "status": {"defect": "confirmed", "review": "review",
                                            "unjudged": "unjudged"}[v["verdict"]]})

    def cnt(s):
        return sum(1 for f in findings if f["status"] == s)

    return {
        "lexical": lex,
        "recheck": {"calls": rc["calls"], "votes": rc["votes"]},
        "deep": deep,
        "findings": findings,
        "summary": {
            "confirmed": cnt("confirmed"),
            "confirmed_must": sum(1 for f in findings if f["status"] == "confirmed" and f.get("severity") == "must"),
            "script_only": cnt("script"),
            "review": cnt("review"),
            "unjudged": cnt("unjudged"),
            "dismissed_not_applicable": cnt("not_applicable"),
            "dismissed_passed": cnt("passed"),
        },
    }


# ---------------- 六阶段工作流 ----------------

_GENRE_FILE = {
    "ei-conf": "genre-ei-conference.md",
    "ai-conf": "genre-ei-conference.md",
    "sci-journal": "genre-sci-journal.md",
    "quant": "genre-quant-empirical.md",
    "predictive": "genre-quant-empirical.md",
    "qualitative": "genre-qualitative.md",
    "basic-science": "genre-sci-journal.md",
    "clinical": "reporting-guidelines.md",
    "dissertation": "genre-dissertation.md",
    "ssci": "genre-ssci.md",
}

_SYSTEM_WORKFLOW = """你是「PaperMate」（开源论文搭子），一套规则驱动的学术论文写作决策与审查专家。

工作原则：
1. 每条建议必须可判定、可执行，给出具体改法，不说"注意逻辑清晰"这类空话。
2. 每条建议须能追溯到规则出处（source），优先引用规则库与参考文档里的规范。
3. 只做引导与审查，不代写整篇论文，不虚构。
4. 纯理论数理类论文（定义-定理-证明结构）不支持，遇到须明确说明。
5. 基础科学/临床两条线可信度较低，遇到领域表征标准（ACS/IUPAC/CIF）须提示用户外查目标期刊指南。
6. 回答用中文，结构化、分点清晰。"""


def _read_skill_file(relpath):
    p = engine.SKILL_ROOT / relpath
    if p.exists():
        return p.read_text(encoding="utf-8", errors="ignore")
    return ""


def _workflow_context(stage, params):
    """按阶段加载参考文档作为上下文。"""
    track = params.get("track", "quant")
    parts = []

    if stage in (1, 2, 6):
        gf = _GENRE_FILE.get(track, "genre-sci-journal.md")
        ref = _read_skill_file(f"references/{gf}")
        if ref:
            parts.append(f"【学科主线参考文档 {gf}】\n{ref}")

    # 可选增强·选题雷达：仅当 mode=radar 时叠加扩展包文档，常规选题引导不受影响
    if stage == 1 and params.get("mode") == "radar":
        ts = _read_skill_file("references/topic-selection.md")
        if ts:
            parts.append(f"【选题雷达·工作流规范】\n{ts}")
        sd = _read_skill_file("references/topic-scoring-dimensions.md")
        if sd:
            parts.append(f"【选题雷达·评分维度矩阵（6 范式 × 5 层级）】\n{sd}")
        tp = _read_skill_file("assets/topic-prompts.md")
        if tp:
            parts.append(f"【选题雷达·AI 评估提示词模板】\n{tp}")

    if stage == 2:
        ev = _read_skill_file("references/evidence-and-data.md")
        if ev:
            parts.append(f"【数据质量/效度/因果参考】\n{ev}")

    if stage == 3:
        sec = params.get("section", "introduction")
        sm = _read_skill_file(f"references/section-{sec}.md")
        if sm:
            parts.append(f"【{sec} 章节写作规范】\n{sm}")

    if stage == 4:
        style = params.get("style", "ieee")
        cm = _read_skill_file(f"assets/citation-{style}.md")
        if cm:
            parts.append(f"【引用格式规范 {style}】\n{cm}")

    if stage == 6 and params.get("mode") == "submit":
        rg = _read_skill_file("references/reporting-guidelines.md")
        if rg:
            parts.append(f"【报告规范】\n{rg}")

    return "\n\n".join(parts)


def _workflow_task(stage, params):
    track = params.get("track", "quant")
    tlabel = engine.TRACK_LABELS.get(track, track)
    if stage == 1:
        # 默认路径：原版选题定位（研究问题 + gap 论证），行为与挂载扩展前完全一致
        if params.get("mode") != "radar":
            return (
                f"请帮我做【选题定位】。学科主线：{tlabel}。\n"
                f"研究方向：{params.get('dir', '')}\n"
                f"目标期刊/会议：{params.get('venue', '')}\n\n"
                "请产出：1) 可回答、可证伪、有变量的研究问题；2) gap 论证"
                "（现有文献缺什么、为什么现在能做）。"
            )
        # 可选路径：选题雷达（OpenAlex 趋势 + 三维评估）
        venue = params.get("venue", "")
        trend = params.get("trend", "")  # 前端跑趋势后传来的 "年份:篇数" 字符串
        level = params.get("level", "journal")  # 层级（本科/硕士/博士/期刊/一般）
        query = params.get("query", "")  # OpenAlex 检索词（可能与研究方向不同）
        stale = params.get("trend_stale", "")
        venue_line = f"\n目标期刊/会议：{venue}" if venue else ""
        query_line = f"\nOpenAlex 检索词：{query}" if query and query != params.get("dir", "") else ""
        trend_line = f"\n全球发文趋势（年份:篇数）：{trend}" if trend else "\n全球发文趋势（年份:篇数）：未跑趋势"
        stale_line = (
            f"\n注意：用户已把题目改成上面的方向，但趋势数据还是旧检索词「{stale}」的，"
            "本次不引用该趋势，请按“未跑趋势”处理，并提示用户重新跑趋势。"
            if stale else ""
        )
        return (
            f"请帮我做【选题定位 · 选题雷达】。学科主线：{tlabel}。\n"
            f"研究方向：{params.get('dir', '')}{query_line}\n"
            f"用户层级：{level}{venue_line}{trend_line}{stale_line}\n\n"
            "请严格按选题雷达的规范输出一份选题评估报告，包含：\n"
            "一、三个候选题目（每题一句话说明研究角度与创新点，编号 1-3）\n"
            "二、每个题目三维打分：新颖性(1-10)、可行性(1-10)、数据/材料可得性(1-10)，各一句理由（理由须回扣该范式的评价关切，见评分维度矩阵）\n"
            "三、数据与文献可得性清单：需要什么数据或材料、核心文献大概在哪些库\n"
            "四、主要风险与规避建议（2-3 条）\n"
            "五、gap 论证（现有文献缺什么、为什么现在能做）\n"
            "若已提供全球发文趋势，须结合趋势判读（升温/平稳/回落）给出选题必要性的判断。"
        )
    if stage == 2:
        return (
            f"请帮我做【研究设计评审】。学科主线：{tlabel}。\n"
            f"研究设计描述：{params.get('design', '')}\n\n"
            "请按该主线校验：识别策略是否成立、内生性来源、抽样与样本量、"
            "对照组、数据可复现性，并给出设计缺陷清单与修正方向。"
        )
    if stage == 3:
        sec = params.get("section", "introduction")
        slabel = engine.SECTION_LABELS.get(sec, sec)
        draft = params.get("draft", "")
        d = f"\n已有草稿：{draft}" if draft else ""
        return (
            f"请帮我做【初稿写作引导】。学科主线：{tlabel}。\n"
            f"要写的章节：{slabel}（{sec}）。{d}\n\n"
            "请按该章节的写作规范逐段给出框架，并给出正反例句作为改写范本。"
        )
    if stage == 4:
        style = params.get("style", "ieee")
        refs = params.get("refs", "")
        r = f"\n参考文献/正文：{refs}" if refs else ""
        return (
            f"请帮我做【引用格式检查】。目标体系：{style}。{r}\n\n"
            "请按该引用体系逐条检查，重点看体系一致性、编号顺序、"
            "文献类型标识与引用日期，并给出具体改法。"
        )
    if stage == 6:
        mode = params.get("mode", "submit")
        if mode == "submit":
            return (
                f"请帮我做【投稿准备】。学科主线：{tlabel}。\n\n"
                "请产出投稿包清单：cover letter、标题页、图表、伦理声明、"
                "数据可用性声明、报告规范清单（临床类按 CONSORT/STROBE/PRISMA/STARD 选型）。"
            )
        comments = params.get("comments", "")
        return (
            f"请帮我做【返修 rebuttal】。学科主线：{tlabel}。\n"
            f"审稿意见：{comments}\n\n"
            "请产出 rebuttal 结构：逐条回应 + 改动定位 + 不改的理由。"
        )
    return ""


def workflow(stage, params, api_key, base_url=None, model=None, history=None):
    """六阶段工作流（阶段 5 审查走 deep_review，不走这里）。"""
    context = _workflow_context(stage, params)
    task = _workflow_task(stage, params)

    messages = [{"role": "system", "content": _SYSTEM_WORKFLOW}]
    for h in (history or []):
        messages.append(h)
    user = task
    if context:
        user += "\n\n【参考文档（请据此给出可追溯的建议）】\n" + context[:15000]
    messages.append({"role": "user", "content": user})

    answer = chat(api_key, messages, base_url=base_url, model=model, temperature=0.3)
    return answer
