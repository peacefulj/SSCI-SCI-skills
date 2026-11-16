# -*- coding: utf-8 -*-
"""桌面版回归：不设任何新增环境变量时，行为必须与 1.2.8 一致。"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(ROOT), "_deskreg")
PORT = 8897
BASE = f"http://127.0.0.1:{PORT}"
fails = []


def check(n, c, e=""):
    print(("  [OK] " if c else "  [XX] ") + n + (f"   {e}" if e else ""))
    if not c:
        fails.append(n)


def main():
    env = dict(os.environ)
    for k in ("PAPERMATE_HOST", "PAPERMATE_ACCESS_TOKEN", "PAPERMATE_ALLOW_SERVER_KEY",
              "PAPERMATE_HTTPS", "PAPERMATE_DATA_DIR"):
        env.pop(k, None)
    env["PAPERMATE_PORT"] = str(PORT)
    env["PAPERMATE_NO_BROWSER"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    log = open(os.path.join(os.path.dirname(DATA), "_deskreg.log"), "w",
               encoding="utf-8")
    p = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env,
                         stdout=log, stderr=subprocess.STDOUT)
    try:
        ok = False
        for _ in range(80):
            try:
                with urllib.request.urlopen(BASE + "/api/health", timeout=3) as r:
                    if r.status == 200:
                        ok = True
                        break
            except Exception:
                pass
            time.sleep(0.5)
        check("桌面模式启动成功", ok)
        if not ok:
            return 1

        print("\n=== 桌面行为不变 ===")
        with urllib.request.urlopen(BASE + "/api/meta", timeout=30) as r:
            m = json.loads(r.read())
        check("无需登录即访问 /api/meta", True)
        check("access.mode = private", (m.get("access") or {}).get("mode") == "private")
        check("规则数仍 393", m.get("rule_count") == 393, m.get("rule_count"))
        check("版本 1.3.0", m.get("version") == "1.3.0", m.get("version"))

        with urllib.request.urlopen(BASE + "/api/health", timeout=10) as r:
            h = json.loads(r.read())
        check("health access_mode=private", h.get("access_mode") == "private")
        check("health 报数据目录（源码运行=项目根）",
              os.path.normcase(h.get("data_dir", "")) == os.path.normcase(ROOT),
              h.get("data_dir"))

        with urllib.request.urlopen(BASE + "/api/auth/status", timeout=10) as r:
            s = json.loads(r.read())
        check("auth/status 在 private 下 logged_in=True",
              s.get("logged_in") is True and s.get("need_login") is False, str(s))

        # 登录接口在 private 下应直接成功（不报错），避免前端逻辑分叉
        rq = urllib.request.Request(BASE + "/api/auth/login",
                                    data=b'{"password":"whatever"}',
                                    headers={"Content-Type": "application/json"},
                                    method="POST")
        with urllib.request.urlopen(rq, timeout=10) as r:
            lr = json.loads(r.read())
        check("private 下 login 直接返回 ok", lr.get("ok") is True)

        # 词面检测仍然可用且无鉴权
        body = json.dumps({"text": "We find that the effect is very significant. " * 20,
                           "track": "quant"}).encode()
        rq = urllib.request.Request(BASE + "/api/review/lexical", data=body,
                                    headers={"Content-Type": "application/json"},
                                    method="POST")
        with urllib.request.urlopen(rq, timeout=60) as r:
            lex = json.loads(r.read())
        check("词面检测可用", lex.get("applicable_rules") == 56,
              lex.get("applicable_rules"))

        print("\n=== 静态资源 ===")
        for path in ("/", "/login.html", "/app.js", "/style.css", "/render.js"):
            try:
                with urllib.request.urlopen(BASE + path, timeout=10) as r:
                    check(f"{path} 可访问", r.status == 200, str(r.status))
            except urllib.error.HTTPError as e:
                check(f"{path} 可访问", False, str(e.code))

        # 版本号已更新到前端
        with urllib.request.urlopen(BASE + "/", timeout=10) as r:
            html = r.read().decode("utf-8", "replace")
        check("首页显示 v1.3.0", "v1.3.0" in html)
        check("首页有退出按钮（默认隐藏）", 'id="btnLogout"' in html)

    finally:
        p.terminate()
        try:
            p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            p.kill()
        log.close()

    print("\n" + "=" * 50)
    if fails:
        print(f"失败 {len(fails)} 项：")
        for x in fails:
            print("  - " + x)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
