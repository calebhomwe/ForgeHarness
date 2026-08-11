"""Experience memory: error -> fix pairs. Doc-46 rule: only VERIFIED fixes get
injected into future prompts. A fix is verified when the task that used it
finally passes all evaluators (supervisor calls verify_fixes on success)."""
import re
from .. import db


def _sig(text: str) -> str:
    """Stable-ish signature: first compiler/test error line, trimmed of paths/numbers."""
    m = re.search(r"(error [A-Z]+\d+:.*|Error:.*|Assertion failed:.*)", text or "")
    line = (m.group(1) if m else (text or "")[:120]).strip()
    line = re.sub(r"[A-Za-z]:\\[^\s]+|/[^\s]+", "<path>", line)
    return re.sub(r"\d+", "<n>", line)[:200]


def remember_failure(con, task_id: int, failures: list[str], worker_output: str):
    for f in failures[:3]:
        con.execute(
            "INSERT INTO experience (error_sig, error_text, fix_text, task_id, verified, created_at)"
            " VALUES (?,?,?,?,0,?)",
            (_sig(f), f[:2000], (worker_output or "")[:2000], task_id, db.now()))
    con.commit()


def verify_fixes(con, task_id: int):
    """Task passed: its most recent error->fix pairs are now battle-tested."""
    con.execute("UPDATE experience SET verified=1 WHERE task_id=?", (task_id,))
    con.commit()


def relevant_fixes(con, error_text: str, limit: int = 5) -> list[dict]:
    if not error_text:
        return []
    sig = _sig(error_text)
    rows = con.execute(
        "SELECT error_sig, fix_text FROM experience WHERE verified=1 AND error_sig LIKE ? "
        "ORDER BY id DESC LIMIT ?", (f"%{sig[:60]}%", limit)).fetchall()
    return [dict(r) for r in rows]


def add_manual_fix(con, error_text: str, fix_text: str):
    con.execute(
        "INSERT INTO experience (error_sig, error_text, fix_text, task_id, verified, created_at)"
        " VALUES (?,?,?,NULL,1,?)", (_sig(error_text), error_text[:2000], fix_text[:2000], db.now()))
    con.commit()
