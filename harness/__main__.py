"""FORGE Harness CLI.

  python -m harness init                         # create db/dirs from config
  python -m harness add "title" [--contract c.yaml] [--priority N] [--risk r]
                         [--autonomy N] [--budget USD] [--attempts N] [--after TASKID]
  python -m harness run [--cycles N]             # the autonomous loop (resumable)
  python -m harness status                       # queue overview
  python -m harness show ID                      # task detail + last report path
  python -m harness approve ID / reject ID "why"
  python -m harness fix "error text" "fix text"  # seed verified experience memory
  python -m harness spend                        # today's cost
"""
import argparse
import os
import sys
from pathlib import Path

import yaml

from . import db
from .memory.experience import add_manual_fix
from .supervisor import run as run_loop

ROOT = Path(__file__).resolve().parent.parent


def load_cfg():
    cfg_path = Path(os.getenv("FORGE_CONFIG", ROOT / "harness.config.yaml"))
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    # load .env sitting next to the config, if present (KEY=VALUE lines)
    env = cfg_path.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    for key in ("runs_dir", "vault_dir"):
        cfg[key] = str((cfg_path.parent / cfg[key]).resolve())
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(prog="harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    a = sub.add_parser("add")
    a.add_argument("title")
    a.add_argument("--contract")
    a.add_argument("--priority", type=int, default=2)
    a.add_argument("--risk", default="medium", choices=["low", "medium", "high"])
    a.add_argument("--autonomy", type=int, default=3)
    a.add_argument("--budget", type=float, default=5.0)
    a.add_argument("--attempts", type=int, default=3)
    a.add_argument("--after", type=int, default=None)
    r = sub.add_parser("run")
    r.add_argument("--cycles", type=int, default=20)
    sub.add_parser("status")
    s = sub.add_parser("show"); s.add_argument("id", type=int)
    ap_ = sub.add_parser("approve"); ap_.add_argument("id", type=int)
    rj = sub.add_parser("reject"); rj.add_argument("id", type=int); rj.add_argument("reason")
    fx = sub.add_parser("fix"); fx.add_argument("error"); fx.add_argument("fixtext")
    sub.add_parser("spend")
    args = ap.parse_args(argv)

    cfg = load_cfg()
    Path(cfg["runs_dir"]).mkdir(parents=True, exist_ok=True)
    Path(cfg["vault_dir"], "references").mkdir(parents=True, exist_ok=True)
    con = db.connect(Path(cfg["runs_dir"]) / "forge.db")

    if args.cmd == "init":
        print(f"initialized: db + dirs under {cfg['runs_dir']}")
    elif args.cmd == "add":
        tid = db.add_task(con, args.title, args.contract, args.priority, args.risk,
                          args.autonomy, args.budget, args.attempts, args.after)
        print(f"task {tid} queued: {args.title}")
    elif args.cmd == "run":
        run_loop(cfg, con, cycles=args.cycles)
    elif args.cmd == "status":
        rows = con.execute(
            "SELECT id,status,priority,risk,autonomy,attempts,max_attempts,"
            "printf('%.2f',spent_usd) spent,title FROM tasks ORDER BY status, priority, id").fetchall()
        for r_ in rows:
            print(f"[{r_['id']:>3}] {r_['status']:<18} p{r_['priority']} {r_['risk']:<6} "
                  f"auto{r_['autonomy']} {r_['attempts']}/{r_['max_attempts']} "
                  f"${r_['spent']:<7} {r_['title']}")
        if not rows:
            print("(no tasks)")
    elif args.cmd == "show":
        t = con.execute("SELECT * FROM tasks WHERE id=?", (args.id,)).fetchone()
        if not t:
            sys.exit("no such task")
        for k in t.keys():
            print(f"{k:>14}: {t[k]}")
        last = con.execute("SELECT run_dir FROM attempts WHERE task_id=? ORDER BY id DESC LIMIT 1",
                           (args.id,)).fetchone()
        if last:
            print(f"{'last report':>14}: {last['run_dir']}/report.md")
    elif args.cmd == "approve":
        db.set_status(con, args.id, "done")
        print(f"task {args.id} approved -> done. Merge per the report's integration section.")
    elif args.cmd == "reject":
        db.set_status(con, args.id, "needs_retry", last_error=f"human rejection: {args.reason}")
        print(f"task {args.id} sent back with your feedback.")
    elif args.cmd == "fix":
        add_manual_fix(con, args.error, args.fixtext)
        print("verified fix stored.")
    elif args.cmd == "spend":
        print(f"spent today: ${db.spent_today(con):.2f} "
              f"(daily cap ${cfg.get('daily_budget_usd', 25)})")


if __name__ == "__main__":
    main()
