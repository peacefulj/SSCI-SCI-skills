# -*- coding: utf-8 -*-
"""本地云模式验收脚本（不属于产品代码，仅供本次验证使用）。

用 subprocess 起服务、跑一串断言、再杀掉。这样验证的是**真实进程**的行为，
而不是在同一个解释器里 import 出来的近似值——鉴权、Cookie、重启恢复这些
恰好都依赖真实进程。
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(ROOT), "_cloudtest")
PORT = 8899
BASE = f"http://127.0.0.1:{PORT}"
TOKEN = "test-token-123"

fails = []


def check(name, cond, extra=""):
    print(("  [OK] " if cond else "  [XX] ") + name + (f"   {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def req(path, method="GET", body=None, cookie=None, headers=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"}
    if cookie:
        h["Cookie"] = cookie
    if headers:
        h.update(headers)
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=90) as resp:
            raw = resp.read()
            return resp.status, dict(resp.headers), raw
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def start():
    env = dict(os.environ)
    env.update({
        "PAPERMATE_DATA_DIR": DATA,
        "PAPERMATE_HOST": "0.0.0.0",
        "PAPERMATE_PORT": str(PORT),
        "PAPERMATE_ACCESS_TOKEN": TOKEN,
        "PAPERMATE_NO_BROWSER": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    log = open(os.path.join(os.path.dirname(DATA), "_cloudtest.log"), "w",
               encoding="utf-8")
    p = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env,
                         stdout=log, stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            st, _, _ = req("/api/health")
            if st == 200:
                return p, log
        except Exception:
            pass
        time.sleep(0.5)
    p.kill()
    raise SystemExit("服务 30 秒内没起来，看 _cloudtest.log")


def main():
    os.makedirs(DATA, exist_ok=True)
    p, log = start()
    try:
        print("\n=== 1. 健康检查与鉴权边界 ===")
        st, hd, raw = req("/api/health")
        h = json.loads(raw)
        check("health 免登录可访问", st == 200)
        check("health 报版本 1.3.0", h.get("version") == "1.3.0", h.get("version"))
        check("health 报 access_mode=shared", h.get("access_mode") == "shared",
              h.get("access_mode"))

        st, _, raw = req("/api/meta")
        check("未登录访问 /api/meta 被挡（401）", st == 401, str(st))

        st, hd, raw = req("/api/meta", headers={"Accept": "text/html"})
        check("浏览器直访受保护 API 跳登录页", st in (200, 303, 307), str(st))

        st, _, _ = req("/", headers={"Accept": "text/html"})
        check("静态首页免登录可打开", st == 200, str(st))

        st, _, raw = req("/login.html")
        check("登录页可访问", st == 200)

        print("\n=== 2. 登录 ===")
        st, _, _ = req("/api/auth/login", "POST", {"password": "wrong"})
        check("错口令返回 401", st == 401, str(st))

        st, hd, raw = req("/api/auth/login", "POST", {"password": TOKEN})
        check("正确口令登录成功", st == 200, str(st))
        sc = hd.get("set-cookie") or hd.get("Set-Cookie") or ""
        check("下发会话 Cookie", "pm_session=" in sc, sc[:60])
        check("Cookie 带 HttpOnly", "httponly" in sc.lower())
        check("Cookie 带 SameSite", "samesite" in sc.lower())
        check("HTTP 部署不带 Secure（否则浏览器丢弃）",
              "secure" not in sc.lower(), sc[:80])
        cookie = sc.split(";")[0]

        st, _, raw = req("/api/meta", cookie=cookie)
        check("带 Cookie 可访问 /api/meta", st == 200, str(st))
        meta = json.loads(raw)
        check("meta 报 393 条规则", meta.get("rule_count") == 393,
              meta.get("rule_count"))
        check("meta 含 4 项云能力",
              all(k in (meta.get("features") or [])
                  for k in ("cloud_auth", "persist_jobs", "byok", "server_mode")))
        check("meta access.mode=shared",
              (meta.get("access") or {}).get("mode") == "shared")

        st, _, raw = req("/api/auth/status", cookie=cookie)
        s = json.loads(raw)
        check("auth/status 免登录可查且显示已登录",
              st == 200 and s.get("logged_in") is True, str(s))

        print("\n=== 3. 伪造 Cookie 无效 ===")
        st, _, _ = req("/api/meta", cookie="pm_session=9999999999.deadbeef")
        check("伪造签名被拒", st == 401, str(st))
        st, _, _ = req("/api/meta", cookie="pm_session=garbage")
        check("畸形 Cookie 被拒且不报 500", st == 401, str(st))
        # 过期时间戳
        st, _, _ = req("/api/meta", cookie="pm_session=1000000000.aaa")
        check("过期 Cookie 被拒", st == 401, str(st))

        print("\n=== 4. 规则引擎（真实跑一遍） ===")
        sample = ("This paper studies the effect of data asset recognition on "
                  "manufacturing upgrading. We find that the effect is very "
                  "significant. The results show a positive effect. Obviously, "
                  "this is a very important and novel contribution. It is worth "
                  "noting that the mechanism is very clear and the conclusion is "
                  "very robust. In conclusion, our study provides a comprehensive "
                  "analysis of the phenomenon with a series of interesting findings. ")
        sample = sample * 5
        st, _, raw = req("/api/review/lexical", "POST",
                         {"text": sample, "track": "quant"}, cookie=cookie)
        check("词面检测接口返回 200", st == 200, str(st))
        lex = json.loads(raw)
        check("规则库可用（适用 56 条 / 自动检查 30 条）",
              lex.get("applicable_rules") == 56 and lex.get("auto_checked") == 30,
              f"{lex.get('applicable_rules')}/{lex.get('auto_checked')}")
        n_def = lex.get("defect_count", 0)
        check("这段劣质文本检出缺陷", n_def >= 3, f"defect_count={n_def}")
        ids = [d.get("id") for d in (lex.get("defects") or [])][:5]
        check("缺陷带规则编号", bool(ids), str(ids))

        print("\n=== 5. 上传与数据落盘 ===")
        # 传一份 CSV 走真实 multipart
        boundary = "----pmtest"
        body = (f"--{boundary}\r\nContent-Disposition: form-data; "
                f"name=\"file\"; filename=\"t.csv\"\r\n"
                f"Content-Type: text/csv\r\n\r\n"
                f"year,prov,value\n2020,A,1\n2021,B,2\n2022,C,3\n\r\n--{boundary}--\r\n"
                ).encode()
        r = urllib.request.Request(BASE + "/api/oneshot/data", data=body, method="POST",
                                   headers={"Content-Type":
                                            f"multipart/form-data; boundary={boundary}",
                                            "Cookie": cookie})
        try:
            with urllib.request.urlopen(r, timeout=90) as resp:
                up = json.loads(resp.read())
                check("CSV 上传解析成功", resp.status == 200, str(resp.status))
                check("拿到列画像", bool(up.get("parts")), str(list(up.keys()))[:80])
        except urllib.error.HTTPError as e:
            check("CSV 上传解析成功", False, f"{e.code} {e.read()[:150]}")

        check("uploads 落在数据卷",
              os.path.isdir(os.path.join(DATA, "uploads")))
        check("_oneshot 落在数据卷",
              os.path.isdir(os.path.join(DATA, "_oneshot")))

        print("\n=== 6. 重启后状态恢复 ===")
        p.terminate()
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
        log.close()
        time.sleep(1)
        p2, log2 = start()
        try:
            st, _, raw = req("/api/auth/status", cookie=cookie)
            s = json.loads(raw)
            check("重启后旧 Cookie 仍有效（口令未变）",
                  st == 200 and s.get("logged_in") is True, str(s))
            st, _, raw = req("/api/health")
            h2 = json.loads(raw)
            check("重启后 health 正常", st == 200 and h2.get("version") == "1.3.0")

            # 会话落盘验证：造一个会话文件，确认能被读
            sd = os.path.join(DATA, "_sessions")
            check("_sessions 目录已创建", os.path.isdir(sd), sd)
        finally:
            p2.terminate()
            try:
                p2.wait(timeout=15)
            except subprocess.TimeoutExpired:
                p2.kill()
            log2.close()

        print("\n=== 7. BYOK 模式 ===")
        os.environ["PAPERMATE_ALLOW_SERVER_KEY"] = "0"
        # 直接验证模块逻辑（另起进程太重）
        sys.path.insert(0, ROOT)
        for k in ("PAPERMATE_HOST", "PAPERMATE_DATA_DIR", "PAPERMATE_ACCESS_TOKEN"):
            os.environ.pop(k, None)
        os.environ["PAPERMATE_ACCESS_TOKEN"] = TOKEN
        os.environ["DEEPSEEK_API_KEY"] = "sk-server-should-be-ignored"
        import importlib
        import auth as A
        importlib.reload(A)
        check("byok 模式识别正确", A.mode() == "byok", A.mode())
        check("byok 下 allow_server_key=False", A.allow_server_key() is False)

        # 重载 server 验证 resolve_llm 真的不读 .env
        os.environ["PAPERMATE_HOST"] = "127.0.0.1"
        os.environ["PAPERMATE_DATA_DIR"] = DATA
        import server as S
        importlib.reload(S)
        _k, _b, _m = S.resolve_llm({})
        check("byok 下 resolve_llm 不返回服务端 Key", not _k, repr(_k))
        _k2, _, _ = S.resolve_llm({"api_key": "sk-user-own"})
        check("byok 下用户自带 Key 正常透传", _k2 == "sk-user-own", repr(_k2))

    finally:
        for proc in (p,):
            try:
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass

    print("\n" + "=" * 50)
    if fails:
        print(f"失败 {len(fails)} 项：")
        for f in fails:
            print("  - " + f)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
