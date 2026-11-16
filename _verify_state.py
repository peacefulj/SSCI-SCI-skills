# -*- coding: utf-8 -*-
"""验证任务状态落盘与重启恢复（进程级，不是单元测试）。"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(ROOT), "_cloudtest2")
PORT = 8898
BASE = f"http://127.0.0.1:{PORT}"
fails = []


def check(n, c, e=""):
    print(("  [OK] " if c else "  [XX] ") + n + (f"   {e}" if e else ""))
    if not c:
        fails.append(n)


def start():
    env = dict(os.environ)
    env.update({"PAPERMATE_DATA_DIR": DATA, "PAPERMATE_HOST": "127.0.0.1",
                "PAPERMATE_PORT": str(PORT), "PAPERMATE_NO_BROWSER": "1",
                "PYTHONIOENCODING": "utf-8"})
    env.pop("PAPERMATE_ACCESS_TOKEN", None)
    log = open(os.path.join(os.path.dirname(DATA), "_cloudtest2.log"), "w",
               encoding="utf-8")
    p = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env,
                         stdout=log, stderr=subprocess.STDOUT)
    for _ in range(80):
        try:
            with urllib.request.urlopen(BASE + "/api/health", timeout=3) as r:
                if r.status == 200:
                    return p, log
        except Exception:
            pass
        time.sleep(0.5)
    p.kill()
    raise SystemExit("起不来")


def post(path, body):
    r = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"},
                               method="POST")
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def stop(p, log):
    p.terminate()
    try:
        p.wait(timeout=20)
    except subprocess.TimeoutExpired:
        p.kill()
    log.close()
    time.sleep(1)


def _can_rerun(mod, jid, step):
    """rerun 是否会因「正在运行」被拒。真起线程太重，只测状态判断这一层。"""
    job = mod.JOBS.get(jid) or {}
    if job.get("status") == "running":
        return False
    return True


def main():
    os.makedirs(DATA, exist_ok=True)

    print("\n=== A. 会话落盘 ===")
    p, log = start()
    try:
        # 私有模式（未设口令）：本地桌面行为必须完全不变
        with urllib.request.urlopen(BASE + "/api/meta", timeout=30) as r:
            m = json.loads(r.read())
        check("未设口令时无需登录即可访问（桌面版零影响）", True,
              (m.get("access") or {}).get("mode"))
        check("桌面兼容：access.mode=private",
              (m.get("access") or {}).get("mode") == "private")

        st, res = post("/api/workflow",
                       {"stage": 4, "params": {"track": "quant",
                                                "text": "x", "venue": "test"},
                        "api_key": ""})
        # 没 Key 会 400，但会话不建；改用直接验证 state_store
    finally:
        stop(p, log)

    import importlib
    os.environ["PAPERMATE_DATA_DIR"] = DATA
    sys.path.insert(0, ROOT)
    import state_store
    importlib.reload(state_store)

    print("\n=== B. state_store 会话读写 ===")
    state_store.save_session("abc123", {"kind": "review", "history": [{"role": "user"}]})
    f = os.path.join(DATA, "_sessions", "abc123.json")
    check("会话文件已写出", os.path.isfile(f), f)
    back = state_store.load_session("abc123")
    check("会话可读回", back and back.get("kind") == "review")
    check("读回带 _saved_at", "_saved_at" in (back or {}))

    # 原子写：不应该留下 .tmp 垃圾
    junk = [n for n in os.listdir(os.path.join(DATA, "_sessions"))
            if n.startswith(".tmp_")]
    check("原子写无临时文件残留", not junk, str(junk))

    # 坏文件不影响
    with open(os.path.join(DATA, "_sessions", "broken.json"), "w") as fp:
        fp.write("{not json")
    check("坏 JSON 返回 None 而不抛异常",
          state_store.load_session("broken") is None)

    print("\n=== C. oneshot 任务落盘与恢复 ===")
    import oneshot
    importlib.reload(oneshot)
    # 造一个假任务目录
    import uuid
    from pathlib import Path
    jid = uuid.uuid4().hex[:12]
    jd = Path(DATA) / "_oneshot" / jid
    jd.mkdir(parents=True, exist_ok=True)
    job = {
        "id": jid, "dir": str(jd), "status": "running", "current": 2,
        "cfg": {"title": "T"}, "plan": [], "log": ["a"], "artifacts": {},
        "steps": [{"key": "topic", "title": "选题", "status": "done"},
                  {"key": "draft", "title": "成稿", "status": "running"}],
        "manuscript": "x" * 100, "draft_sections": [],
        "data": {}, "llm": {"api_key": "sk-should-not-persist"},
    }
    oneshot._persist(job)

    sf = jd / "_state.json"
    check("_state.json 已写出", sf.is_file())
    raw = sf.read_text(encoding="utf-8")
    check("落盘不含 api_key（密钥不落磁盘）", "sk-should-not-persist" not in raw
          and "api_key" not in raw)

    n = oneshot.restore()
    check("restore 读到任务", n >= 1, f"n={n}")
    rj = oneshot.JOBS.get(jid)
    check("running 被改判 interrupted", rj and rj.get("status") == "interrupted",
          rj.get("status") if rj else "missing")
    check("进行中的步骤也被改判",
          rj and rj["steps"][1]["status"] == "interrupted",
          rj["steps"][1]["status"] if rj else "")
    check("已完成的步骤保持 done",
          rj and rj["steps"][0]["status"] == "done")
    check("恢复后无 llm 配置（需重跑时补）", rj and not rj.get("llm"))
    check("cancel 重置为 False", rj and rj.get("cancel") is False)

    # 重跑必须补 Key，否则会在第一次模型调用处炸
    print("\n=== D. 重启后重跑 ===")
    check("interrupted 任务允许重跑（不被当成 running）",
          _can_rerun(oneshot, jid, "draft"))

    try:
        oneshot.rerun_with_llm(jid, "draft",
                               {"api_key": "sk-x", "base_url": "", "model": ""})
        check("rerun_with_llm 能正常启动重跑", True)
    except Exception as e:
        check("rerun_with_llm 能正常启动重跑", False, str(e)[:100])
    oneshot.cancel(jid)

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
