"""Git worktree isolation: every task runs in its own branch+worktree so
parallel/overnight work can't corrupt main. Level >=2 on the autonomy ladder."""
import subprocess
from pathlib import Path


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=False)


def create(cfg, task_id: int) -> str:
    repo = Path(cfg["project_root"])
    if not cfg.get("use_worktrees", True):
        return str(repo)
    base = Path(cfg.get("worktrees_dir", repo.parent / "forge-worktrees"))
    base.mkdir(parents=True, exist_ok=True)
    branch, path = f"forge/task-{task_id}", base / f"task-{task_id}"
    if path.exists():
        return str(path)
    r = _git(repo, "worktree", "add", "-b", branch, str(path))
    if r.returncode != 0:  # branch may exist from a crashed run
        r = _git(repo, "worktree", "add", str(path), branch)
    return str(path) if r.returncode == 0 else str(repo)


def merge_instructions(cfg, task_id: int) -> str:
    return (f"Review then integrate:\n  git -C {cfg['project_root']} merge --no-ff forge/task-{task_id}\n"
            f"  git -C {cfg['project_root']} worktree remove <worktree-path>")
