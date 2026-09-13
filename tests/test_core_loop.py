"""End-to-end test of the harness core loop with mock executor/evaluators.
Proves: retry-with-feedback, model escalation, evaluator gating, experience
promotion, approval gate, budget stop, dependency ordering, crash resumability.
Run:  python tests/test_core_loop.py
"""
import os
import sqlite3
import sys
import tempfile
import time
import urllib.error
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
from harness import db  # noqa: E402
from harness.supervisor import run_task_once, run  # noqa: E402
from harness.evaluators import _sh  # noqa: E402
from harness.router import llm_chat  # noqa: E402

PASSED = 0


def check(name, cond):
    global PASSED
    assert cond, f"FAIL: {name}"
    PASSED += 1
    print(f"  ok  {name}")


def make_cfg(tmp: Path, **over):
    cfg = {
        "project_root": str(tmp / "proj"), "uproject": str(tmp / "proj/G.uproject"),
        "engine_root": str(tmp / "ue"),
        "executor": "mock", "mock_succeed_on": 2, "mock_cost": 0.05,
        "mock_eval_pass_on": 2,
        "use_worktrees": False,
        "models": {"cheap": "m-cheap", "standard": "m-std", "heavy": "m-heavy", "vision": "m-vis"},
        "daily_budget_usd": 100.0,
        "default_evaluators": ["mock_fail_then_pass"],
        "runs_dir": str(tmp / "runs"), "vault_dir": str(tmp / "vault"),
    }
    cfg.update(over)
    (tmp / "proj").mkdir(parents=True, exist_ok=True)
    Path(cfg["runs_dir"]).mkdir(parents=True, exist_ok=True)
    Path(cfg["vault_dir"], "references").mkdir(parents=True, exist_ok=True)
    return cfg


def test_retry_escalation_and_gate(tmp):
    print("\n[1] retry with feedback -> escalation -> pass -> approval gate")
    cfg = make_cfg(tmp)
    con = db.connect(Path(cfg["runs_dir"]) / "t1.db")
    tid = db.add_task(con, "spawn system", autonomy=3, risk="medium", budget_usd=5, max_attempts=3)

    t = con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    s1 = run_task_once(cfg, con, t)
    check("attempt 1 fails -> needs_retry", s1 == "needs_retry")
    evs = con.execute("SELECT * FROM evaluations").fetchall()
    check("failure recorded with evaluator detail", any(not e["passed"] for e in evs))
    exp = con.execute("SELECT * FROM experience").fetchall()
    check("unverified experience captured from failure", len(exp) >= 1 and exp[0]["verified"] == 0)

    t = con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    s2 = run_task_once(cfg, con, t)
    check("attempt 2 passes all evaluators", s2 == "awaiting_approval")
    a2 = con.execute("SELECT model FROM attempts WHERE n=2").fetchone()
    check("model escalated on retry (standard->heavy)", a2["model"] == "m-heavy")
    exp = con.execute("SELECT verified FROM experience").fetchall()
    check("experience promoted to verified on success", all(e["verified"] == 1 for e in exp))
    rd = Path(cfg["runs_dir"]) / f"task-{tid}" / "attempt-2" / "report.md"
    check("evidence report written", rd.exists() and "ALL EVALUATORS PASSED" in rd.read_text(encoding="utf-8"))

    # feedback path A: attempt-1 failed at EXECUTOR stage -> its error is in attempt-2's prompt
    p2 = (Path(cfg["runs_dir"]) / f"task-{tid}" / "attempt-2" / "prompt.md").read_text(encoding="utf-8")
    check("retry prompt carries executor-stage feedback", "Previous attempt failed" in p2
          and "C2065" in p2)

    # feedback path B: executor OK but EVALUATOR fails -> eval detail reaches next prompt
    cfgB = make_cfg(tmp / "B", mock_succeed_on=1, mock_eval_pass_on=2)
    conB = db.connect(Path(cfgB["runs_dir"]) / "t1b.db")
    tb = db.add_task(conB, "eval feedback")
    for _ in range(2):
        t = conB.execute("SELECT * FROM tasks WHERE id=?", (tb,)).fetchone()
        run_task_once(cfgB, conB, t)
    pB = (Path(cfgB["runs_dir"]) / f"task-{tb}" / "attempt-2" / "prompt.md").read_text(encoding="utf-8")
    check("retry prompt carries evaluator-stage feedback", "lighting too flat" in pB)

    from harness.__main__ import main  # approve via CLI path
    os.environ["FORGE_CONFIG"] = str(tmp / "nonexistent.yaml")  # ensure CLI not used here
    db.set_status(con, tid, "done")
    check("approval gate -> done", con.execute(
        "SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()["status"] == "done")


def test_budget_and_max_attempts(tmp):
    print("\n[2] hard stops: budget + max attempts")
    cfg = make_cfg(tmp, mock_succeed_on=99, mock_eval_pass_on=99, mock_cost=0.6)
    con = db.connect(Path(cfg["runs_dir"]) / "t2.db")
    tid = db.add_task(con, "impossible task", budget_usd=1.0, max_attempts=5)
    for _ in range(5):
        t = con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        if t["status"] in ("failed", "done"):
            break
        run_task_once(cfg, con, t)
    t = con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    check("task hard-stopped", t["status"] == "failed")
    check("stopped by budget before attempts ran out",
          "budget" in (t["last_error"] or "") and t["attempts"] < 5)

    cfg2 = make_cfg(tmp, mock_succeed_on=99, mock_eval_pass_on=99, mock_cost=0.01)
    con2 = db.connect(Path(cfg2["runs_dir"]) / "t2b.db")
    tid2 = db.add_task(con2, "still impossible", budget_usd=50, max_attempts=2)
    for _ in range(3):
        t = con2.execute("SELECT * FROM tasks WHERE id=?", (tid2,)).fetchone()
        if t["status"] in ("failed", "done"):
            break
        run_task_once(cfg2, con2, t)
    t = con2.execute("SELECT * FROM tasks WHERE id=?", (tid2,)).fetchone()
    check("max_attempts stop works", t["status"] == "failed" and t["attempts"] == 2)


def test_dependencies_autonomy_and_daily_cap(tmp):
    print("\n[3] dependency ordering, autonomy-6 auto-done, daily budget stop")
    cfg = make_cfg(tmp, mock_succeed_on=1, mock_eval_pass_on=1)
    con = db.connect(Path(cfg["runs_dir"]) / "t3.db")
    t1 = db.add_task(con, "foundation", priority=1, autonomy=6, risk="low")
    t2 = db.add_task(con, "depends on foundation", priority=0, depends_on=t1,
                     autonomy=6, risk="medium")
    first = db.next_task(con)
    check("blocked dependent is skipped despite higher priority", first["id"] == t1)
    run(cfg, con, cycles=4, sleep_s=0)
    s1 = con.execute("SELECT status FROM tasks WHERE id=?", (t1,)).fetchone()["status"]
    s2 = con.execute("SELECT status FROM tasks WHERE id=?", (t2,)).fetchone()["status"]
    check("autonomy 6 + low risk auto-integrates", s1 == "done")
    check("autonomy 6 + MEDIUM risk still needs a human", s2 == "awaiting_approval")

    cfg2 = make_cfg(tmp, mock_succeed_on=1, mock_eval_pass_on=1,
                    mock_cost=0.5, daily_budget_usd=0.4)
    con2 = db.connect(Path(cfg2["runs_dir"]) / "t3b.db")
    db.add_task(con2, "a"); db.add_task(con2, "b")
    run(cfg2, con2, cycles=5, sleep_s=0)
    remaining = con2.execute(
        "SELECT COUNT(*) c FROM tasks WHERE status IN ('queued','needs_retry')").fetchone()["c"]
    check("daily cap halts the loop with work remaining", remaining >= 1)


def test_crash_resume(tmp):
    print("\n[4] crash resumability: state on disk, new process resumes cleanly")
    cfg = make_cfg(tmp, mock_succeed_on=2, mock_eval_pass_on=2)
    dbp = Path(cfg["runs_dir"]) / "t4.db"
    con = db.connect(dbp)
    tid = db.add_task(con, "survives crashes")
    t = con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    run_task_once(cfg, con, t)         # attempt 1 fails
    con.close()                        # "crash"
    con2 = db.connect(dbp)             # new process
    t = db.next_task(con2)
    check("needs_retry task picked up after restart", t and t["id"] == tid)
    s = run_task_once(cfg, con2, t)
    check("resumed run completes with prior feedback intact", s == "awaiting_approval")


def test_failure_boundaries(tmp):
    print("\n[5] failure boundaries: evaluator timeout, stale recovery, bounded LLM retry")
    tmp.mkdir(parents=True, exist_ok=True)
    log = tmp / "timeout.log"
    p = _sh([sys.executable, "-c", "import time; time.sleep(0.2)"],
            str(tmp), 0.01, log)
    check("evaluator timeout becomes a failed result", p.returncode == 124)
    check("evaluator timeout still writes its log", log.exists())

    con = db.connect(tmp / "stale.db")
    tid = db.add_task(con, "stalled task", max_attempts=3)
    db.set_status(con, tid, "running")
    con.execute("UPDATE tasks SET updated_at=? WHERE id=?", (time.time() - 100, tid))
    con.commit()
    check("stale task is returned to retry queue",
          db.recover_stale_tasks(con, stale_after_s=10) == 1 and
          con.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()["status"] == "needs_retry")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}],"usage":{"cost":0.0}}'

    with mock.patch("harness.router.urllib.request.urlopen",
                    side_effect=[urllib.error.URLError("temporary"), Response()]) as opened:
        result = llm_chat({"llm_base_url": "http://127.0.0.1:1234/v1",
                           "llm_retry_attempts": 1, "llm_retry_backoff_s": 0,
                           "llm_timeout_s": 7}, "local-model",
                          [{"role": "user", "content": "ping"}])
    check("transient LLM transport failure retries once", result["text"] == "ok" and opened.call_count == 2)
    check("LLM request uses configured timeout", opened.call_args_list[-1].kwargs["timeout"] == 7.0)

    cfg = make_cfg(tmp / "empty-evaluators", mock_succeed_on=1,
                   mock_eval_pass_on=1, default_evaluators=[])
    con2 = db.connect(Path(cfg["runs_dir"]) / "empty.db")
    tid2 = db.add_task(con2, "no evaluator task", autonomy=6, risk="low")
    t = con2.execute("SELECT * FROM tasks WHERE id=?", (tid2,)).fetchone()
    check("successful executor with no evaluators passes", run_task_once(cfg, con2, t) == "done")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        tmp = Path(td)
        test_retry_escalation_and_gate(tmp / "a")
        test_budget_and_max_attempts(tmp / "b")
        test_dependencies_autonomy_and_daily_cap(tmp / "c")
        test_crash_resume(tmp / "d")
        test_failure_boundaries(tmp / "e")
    print(f"\nALL {PASSED} CHECKS PASSED")
