"""Supervisor: pick task -> route model -> execute -> evaluate -> gate -> record.

The doc-46 loop, made durable:
  choose task -> isolate worktree -> retrieve experience -> execute with budget
  -> run acceptance evaluators -> retry with error feedback (escalating models)
  -> evidence report -> approval gate (autonomy ladder decides).
Crash-safe: every transition is a committed SQLite row; rerun `harness run` to resume.
"""
from __future__ import annotations

import time
from pathlib import Path

import yaml

from . import db
from .executors import REGISTRY as EXECUTORS
from .evaluators import REGISTRY as EVALUATORS
from .memory.experience import relevant_fixes, remember_failure, verify_fixes
from .report import write_report
from .router import pick_model, model_name
from .unreal import worktree

CONSTITUTION = Path(__file__).resolve().parent.parent / "prompts" / "worker_system.md"


def load_contract(path: str | None) -> dict:
    if not path or not Path(path).exists():
        return {}
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def build_prompt(cfg, task, contract, prior_failures: list[str], fixes: list[dict]) -> str:
    parts = [CONSTITUTION.read_text(encoding="utf-8") if CONSTITUTION.exists() else "",
             f"\n# TASK {task['id']}: {task['title']}\n"]
    if contract:
        parts.append("## Acceptance contract (the evaluators WILL check these)\n"
                     + yaml.safe_dump(contract, sort_keys=False))
    if fixes:
        parts.append("## Verified fixes from project memory (apply if the same error appears)\n")
        parts += [f"- ERROR: {f['error_sig']}\n  FIX: {f['fix_text']}\n" for f in fixes[:5]]
    if prior_failures:
        parts.append("## Previous attempt failed. Evaluator feedback (fix THIS first):\n")
        parts += [f"- {f}\n" for f in prior_failures[-8:]]
    parts.append("\nWork inside the current directory only. When done, ensure evidence exists "
                 "(screenshots in ./__forge_run__/shots if the contract has a visual check). "
                 "Do not claim success — the evaluators decide.")
    return "".join(parts)


def _autonomy_gate(task, all_passed: bool) -> str:
    """Ladder: <5 or medium/high risk => human approval; 6+low risk => auto-done."""
    if not all_passed:
        return "needs_retry"
    if task["autonomy"] >= 6 and task["risk"] == "low":
        return "done"
    return "awaiting_approval"


def run_task_once(cfg, con, task) -> str:
    tid = task["id"]
    contract = load_contract(task["contract_path"])
    cwd = task["worktree"] or worktree.create(cfg, tid)
    if not task["worktree"]:
        db.set_status(con, tid, "running", worktree=cwd)

    n = task["attempts"] + 1
    task = dict(task) | {"attempts": n}  # one consistent view for executor + evaluators
    run_dir = Path(cfg["runs_dir"]) / f"task-{tid}" / f"attempt-{n}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (Path(cwd) / "__forge_run__").mkdir(exist_ok=True)  # where workers drop shots/perf

    prior = [e for (e,) in con.execute(
        """SELECT details FROM evaluations ev JOIN attempts a ON ev.attempt_id=a.id
           WHERE a.task_id=? AND ev.passed=0 ORDER BY ev.id""", (tid,)).fetchall()]
    fixes = relevant_fixes(con, task["last_error"] or "")
    prompt = build_prompt(cfg, task, contract, prior, fixes)

    complexity = contract.get("complexity", "standard")
    model = pick_model(cfg, complexity, n)
    executor_name = contract.get("executor", cfg.get("executor", "claude_code"))
    executor = EXECUTORS[executor_name]

    att_id = db.start_attempt(con, tid, n, executor_name, model_name(model), run_dir)
    db.set_status(con, tid, "running")
    result = executor(cfg, task, prompt, model, run_dir, cwd)
    db.finish_attempt(con, att_id, result["exit_status"], result["cost_usd"])

    # ---- evaluate (system declares success, not the agent) ----
    db.set_status(con, tid, "evaluating")
    # move worker-produced evidence into the attempt dir
    src = Path(cwd) / "__forge_run__"
    if src.exists():
        import shutil
        for p in src.rglob("*"):
            if p.is_file():
                dest = run_dir / p.relative_to(src)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)

    verdicts, failures = {}, []
    if result["exit_status"] != "ok":
        failures.append(f"executor:{result['exit_status']}: {result['output'][:300]}")
        db.record_eval(con, att_id, "executor", False, details=result["output"][:1000])
    else:
        for name in contract.get("evaluators", cfg.get("default_evaluators", ["build"])):
            v = EVALUATORS[name](cfg, task, contract, run_dir, cwd)
            verdicts[name] = v
            db.record_eval(con, att_id, name, v["passed"], v.get("score"), v.get("details"))
            if not v["passed"]:
                failures.append(f"{name}: {str(v.get('details'))[:400]}")

    all_passed = result["exit_status"] == "ok" and all(
        v["passed"] for v in verdicts.values())
    write_report(cfg, con, task, att_id, run_dir, verdicts, result, all_passed)

    if all_passed:
        verify_fixes(con, tid)  # promote experience: this task's error->fix pairs are now proven
        status = _autonomy_gate(task, True)
        db.set_status(con, tid, status)
        return status

    remember_failure(con, tid, failures, result["output"])
    if n >= task["max_attempts"]:
        db.set_status(con, tid, "failed", last_error="; ".join(failures)[:1000])
        return "failed"
    if task["spent_usd"] + result["cost_usd"] >= task["budget_usd"]:
        db.set_status(con, tid, "failed", last_error="budget exhausted")
        return "failed"
    db.set_status(con, tid, "needs_retry", last_error="; ".join(failures)[:1000])
    return "needs_retry"


def run(cfg, con, cycles: int = 20, sleep_s: float = 1.0) -> None:
    recovered = db.recover_stale_tasks(con, cfg.get("stale_task_timeout_s", 7200))
    if recovered:
        print(f"[supervisor] recovered {recovered} stale task(s) for retry.")
    for i in range(cycles):
        if db.spent_today(con) >= cfg.get("daily_budget_usd", 25.0):
            print("[supervisor] daily budget reached — stopping cleanly.")
            return
        task = db.next_task(con)
        if not task:
            print("[supervisor] queue empty (or all tasks gated/blocked).")
            return
        print(f"[supervisor] cycle {i+1}/{cycles}: task {task['id']} "
              f"'{task['title']}' attempt {task['attempts']+1}/{task['max_attempts']}")
        status = run_task_once(cfg, con, task)
        print(f"[supervisor]   -> {status}")
        time.sleep(sleep_s)
