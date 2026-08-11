"""Evidence report per attempt: what ran, what the evaluators said, what to review."""
import json
from pathlib import Path
from .unreal import worktree


def write_report(cfg, con, task, attempt_id, run_dir: Path, verdicts, result, all_passed):
    lines = [f"# Task {task['id']}: {task['title']}",
             f"Attempt dir: {run_dir}",
             f"Executor status: {result['exit_status']}  |  cost: ${result['cost_usd']:.4f}",
             f"Overall: {'ALL EVALUATORS PASSED' if all_passed else 'FAILED'}", ""]
    for name, v in (verdicts or {}).items():
        lines.append(f"## {name}: {'PASS' if v['passed'] else 'FAIL'}"
                     + (f" (score {v['score']})" if v.get("score") is not None else ""))
        lines.append("```json\n" + json.dumps(v.get("details"), indent=2, default=str)[:3000] + "\n```")
    shots = sorted(run_dir.glob("shots/*.png"))
    if shots:
        lines.append("## Evidence screenshots\n" + "\n".join(f"- {s}" for s in shots))
    if all_passed and task["autonomy"] < 6:
        lines.append("\n## Integration (after your approval)\n"
                     + worktree.merge_instructions(cfg, task["id"]))
    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return run_dir / "report.md"
