# -*- coding: utf-8 -*-
"""访问控制与 Key 策略 —— 只服务「部署到公网」这一个场景。

**桌面版必须零改动**：不设任何环境变量时，`mode()=="private"`，
所有检查直接放行，行为与 1.2.8 完全一致（本地 `127.0.0.1` 本来就只有自己能访问）。

三种模式（由 `PAPERMATE_ACCESS_TOKEN` 与 `PAPERMATE_ALLOW_SERVER_KEY` 共同决定）：

| 模式 | 触发条件 | 谁能访问 | 用谁的 Key |
|---|---|---|---|
| `private` | 未设 `ACCESS_TOKEN` | 本机（靠回环地址兜底） | 服务端 `.env`，也可前端自填 |
| `shared` | 设了 `ACCESS_TOKEN` | 持口令者 | 服务端 `.env`，或各人自填覆盖 |
| `byok` | 设了 `ACCESS_TOKEN` + `ALLOW_SERVER_KEY=0` | 持口令者 | **只能**各人自填，服务端 Key 一律不读 |

**为什么口令是签名 Cookie 而不是 Basic Auth**：浏览器弹窗式的 Basic Auth
在每个请求都重发密码，前端没法优雅地做「登录页 + 退出」；而纯前端 `localStorage`
存的 token 每次请求都要用户自己拼 header，改动面大。签名 Cookie 两边都省事：
后端下发 `HttpOnly` Cookie，前端只需要判断 401 然后展示登录框。

**为什么签名用 HMAC-SHA256 而不是 JWT**：只需要「服务端能验证自己发过」，
不需要跨服务、不需要过期后刷新、不需要公钥分发。标准库 `hmac` 足够，
少一个依赖（PyJWT 在精简镜像里经常因为 cryptography 编译失败）。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

COOKIE_NAME = "pm_session"
# 登录有效期：30 天。太短会让人天天重登，太长则口令泄露后收不回来。
# 但对内网/个人用途，30 天是合适的折中；要更严就改这个值。
SESSION_TTL = 30 * 24 * 3600


def _env(key: str, default: str = "") -> str:
    return (os.environ.get(key) or default).strip()


def access_token() -> str:
    """访问口令。空字符串表示不启用鉴权。"""
    return _env("PAPERMATE_ACCESS_TOKEN")


def allow_server_key() -> bool:
    """是否允许使用服务端 `.env` 里的 Key 替用户调用模型。

    默认 `1`（允许）——保持「管理员配一次，全组可用」的常见做法。
    显式设成 `0` 则退化为 BYOK：服务端 Key 绝不参与任何请求。
    """
    return _env("PAPERMATE_ALLOW_SERVER_KEY", "1").lower() not in ("0", "false", "no", "off")


def mode() -> str:
    """当前访问模式，供 `/api/settings` 告知前端该渲染哪个界面。"""
    if not access_token():
        return "private"
    return "shared" if allow_server_key() else "byok"


def secret() -> bytes:
    """签名密钥。

    优先 `PAPERMATE_SECRET`；没设就从访问口令派生——
    这样「改口令」会自动让所有旧 Cookie 失效，是个想要的行为。
    """
    raw = _env("PAPERMATE_SECRET")
    if raw:
        return raw.encode("utf-8")
    return hashlib.sha256(("papermate::" + access_token()).encode("utf-8")).digest()


def _sign(payload: str) -> str:
    return hmac.new(secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def issue() -> str:
    """签发一个会话 Cookie 值：`<过期时间戳>.<签名>`。"""
    exp = str(int(time.time()) + SESSION_TTL)
    return f"{exp}.{_sign(exp)}"


def verify(value: str | None) -> bool:
    """校验 Cookie 值。任何异常都当作未登录——不要因为一个畸形 Cookie 抛 500。"""
    if not value or "." not in value:
        return False
    exp, _, sig = value.partition(".")
    if not exp.isdigit() or int(exp) < time.time():
        return False
    expected = _sign(exp)
    # compare_digest 防时序侧信道；长度不等会抛 TypeError，先比长度
    return len(sig) == len(expected) and hmac.compare_digest(sig, expected)


def check_password(given: str) -> bool:
    """常量时间比对口令。明文存 `.env` 是合理的——这是运维自己设的一次性凭据。"""
    want = access_token()
    if not want:
        return True
    return hmac.compare_digest(given or "", want)


def new_secret_token(n: int = 32) -> str:
    """生成一个足够随机的口令，给部署脚本当默认值用。"""
    return secrets.token_urlsafe(n)
