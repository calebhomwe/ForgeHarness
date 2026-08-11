"""Durable state layer. SQLite = crash-safe task queue + audit trail + memory.
Every supervisor transition is a committed row, so a crash costs nothing.
Swap for Postgres later by reimplementing this module only (see docs/SCALING.md).
"""
import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  contract_path TEXT,
  status TEXT NOT NULL DEFAULT 'queued',
  -- queued|running|evaluating|awaiting_approval|approved|rejected|needs_retry|failed|done
  priority INTEGER DEFAULT 2,          -- 0 highest
  risk TEXT DEFAULT 'medium',          -- low|medium|high
  autonomy INTEGER DEFAULT 3,          -- 0..6 ladder
  depends_on INTEGER,                  -- task id or NULL
  attempts INTEGER DEFAULT 0,
  max_attempts INTEGER DEFAULT 3,
  budget_usd REAL DEFAULT 5.0,
  spent_usd REAL DEFAULT 0.0,
  worktree TEXT,
  last_error TEXT,
  created_at REAL, updated_at REAL
);
CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  n INTEGER NOT NULL,
  executor TEXT, model TEXT,
  started REAL, finished REAL,
  cost_usd REAL DEFAULT 0.0,
  exit_status TEXT,                    -- ok|error|timeout
  run_dir TEXT
);
CREATE TABLE IF NOT EXISTS evaluations (
  id INTEGER PRIMARY KEY,
  attempt_id INTEGER NOT NULL,
  evaluator TEXT NOT NULL,
  passed INTEGER NOT NULL,
  score REAL,
  details TEXT
);
CREATE TABLE IF NOT EXISTS experience (
  id INTEGER PRIMARY KEY,
  error_sig TEXT,                      -- short signature for lookup
  error_text TEXT,
  fix_text TEXT,
  task_id INTEGER,
  verified INTEGER DEFAULT 0,          -- only verified fixes are injected into prompts
  created_at REAL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  ts REAL, task_id INTEGER, kind TEXT, detail TEXT
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def now() -> float:
    return time.time()


def log_event(con, task_id, kind, detail=""):
    con.execute(
        "INSERT INTO events (ts, task_id, kind, detail) VALUES (?,?,?,?)",
        (now(), task_id, kind, str(detail)[:4000]),
    )
    con.commit()


def add_task(con, title, contract_path=None, priority=2, risk="medium",
             autonomy=3, budget_usd=5.0, max_attempts=3, depends_on=None):
    cur = con.execute(
        """INSERT INTO tasks (title, contract_path, priority, risk, autonomy,
           budget_usd, max_attempts, depends_on, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (title, contract_path, priority, risk, autonomy, budget_usd,
         max_attempts, depends_on, now(), now()),
    )
    con.commit()
    log_event(con, cur.lastrowid, "created", title)
    return cur.lastrowid


def set_status(con, task_id, status, **fields):
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values())
    q = f"UPDATE tasks SET status=?, updated_at=?{', ' + sets if sets else ''} WHERE id=?"
    con.execute(q, [status, now(), *vals, task_id])
    con.commit()
    log_event(con, task_id, "status", status)


def next_task(con):
    """Highest-priority queued/needs_retry task whose dependency (if any) is done."""
    return con.execute(
        """SELECT t.* FROM tasks t
           LEFT JOIN tasks d ON t.depends_on = d.id
           WHERE t.status IN ('queued','needs_retry')
             AND (t.depends_on IS NULL OR d.status='done')
           ORDER BY t.priority ASC, t.id ASC LIMIT 1"""
    ).fetchone()


def start_attempt(con, task_id, n, executor, model, run_dir):
    cur = con.execute(
        """INSERT INTO attempts (task_id, n, executor, model, started, run_dir)
           VALUES (?,?,?,?,?,?)""",
        (task_id, n, executor, model, now(), str(run_dir)),
    )
    con.execute("UPDATE tasks SET attempts=?, updated_at=? WHERE id=?", (n, now(), task_id))
    con.commit()
    return cur.lastrowid


def finish_attempt(con, attempt_id, exit_status, cost_usd):
    con.execute(
        "UPDATE attempts SET finished=?, exit_status=?, cost_usd=? WHERE id=?",
        (now(), exit_status, cost_usd, attempt_id),
    )
    row = con.execute("SELECT task_id FROM attempts WHERE id=?", (attempt_id,)).fetchone()
    con.execute("UPDATE tasks SET spent_usd = spent_usd + ? WHERE id=?", (cost_usd, row["task_id"]))
    con.commit()


def record_eval(con, attempt_id, evaluator, passed, score=None, details=""):
    con.execute(
        "INSERT INTO evaluations (attempt_id, evaluator, passed, score, details) VALUES (?,?,?,?,?)",
        (attempt_id, evaluator, int(passed), score, json.dumps(details)[:8000]),
    )
    con.commit()


def spent_today(con) -> float:
    day_start = time.time() - (time.time() % 86400)
    row = con.execute(
        "SELECT COALESCE(SUM(cost_usd),0) s FROM attempts WHERE started >= ?", (day_start,)
    ).fetchone()
    return float(row["s"])
