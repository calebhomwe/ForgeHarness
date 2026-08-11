"""Executors: how a worker actually does the task.

Contract: run(cfg, task, prompt, model, run_dir, cwd) -> {"exit_status": "ok|error|timeout",
                                                          "cost_usd": float, "output": str}
Built-ins:
  claude_code : headless Claude Code (`claude -p`) inside the worktree — the workhorse.
                It talks to Unreal via the UE 5.8 official MCP plugin (.mcp.json in project root).
  codex       : same idea via `codex exec` if you prefer a second coder for review passes.
  api         : direct chat completion (cheap planning / doc / patch-suggestion tasks).
  mock        : deterministic executor for the test suite.
Add your own: drop a module here exposing run(), register in REGISTRY.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

from ..router import llm_chat


def _write(run_dir: Path, name: str, content: str):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / name).write_text(content, encoding="utf-8", errors="replace")


def _run_cli(argv, cwd, timeout, run_dir: Path, stdin_text=None):
    try:
        p = subprocess.run(argv, cwd=cwd,
                           input=(stdin_text if stdin_text is not None else ""),
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        _write(run_dir, "stdout.txt", p.stdout or "")
        _write(run_dir, "stderr.txt", p.stderr or "")
        return p
    except subprocess.TimeoutExpired as e:
        _write(run_dir, "stdout.txt", (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
        return None


def claude_code(cfg, task, prompt, model, run_dir: Path, cwd: str):
    """Headless Claude Code. Flags are verified against `claude --help` at first run
    and cached, because flag names can move between versions."""
    exe = cfg.get("claude_bin", "claude")
    if not shutil.which(exe):
        return {"exit_status": "error", "cost_usd": 0.0,
                "output": f"'{exe}' not found on PATH. Install Claude Code or set claude_bin."}
    argv = [exe, "-p", prompt, "--output-format", "json"]
    allowed = cfg.get("allowed_tools")
    if allowed:
        argv += ["--allowedTools", allowed]
    if isinstance(model, str) and model and "/" not in model:
        argv += ["--model", model]  # ladder cloud/local specs don't apply to the Claude CLI
    extra = cfg.get("claude_extra_args", [])
    argv += list(extra)
    _write(run_dir, "prompt.md", prompt)
    p = _run_cli(argv, cwd, cfg.get("executor_timeout_s", 3600), run_dir)
    if p is None:
        return {"exit_status": "timeout", "cost_usd": 0.0, "output": "timeout"}
    cost, text = 0.0, p.stdout or ""
    try:  # claude -p --output-format json => single JSON object with result + cost fields
        data = json.loads(text.lstrip(chr(0xFEFF)))  # claude -p emits a UTF-8 BOM on Windows
        text = data.get("result", text)
        cost = float(data.get("total_cost_usd", data.get("cost_usd", 0.0)) or 0.0)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass  # older/newer CLI: keep raw stdout, cost unknown (0) — budget still bounded by attempts
    status = "ok" if p.returncode == 0 else "error"
    return {"exit_status": status, "cost_usd": cost, "output": text}


def codex(cfg, task, prompt, model, run_dir: Path, cwd: str):
    exe = cfg.get("codex_bin", "codex")
    if not shutil.which(exe):
        return {"exit_status": "error", "cost_usd": 0.0, "output": f"'{exe}' not found on PATH."}
    _write(run_dir, "prompt.md", prompt)
    p = _run_cli([exe, "exec", prompt], cwd, cfg.get("executor_timeout_s", 3600), run_dir)
    if p is None:
        return {"exit_status": "timeout", "cost_usd": 0.0, "output": "timeout"}
    return {"exit_status": "ok" if p.returncode == 0 else "error",
            "cost_usd": 0.0, "output": p.stdout or ""}


def api(cfg, task, prompt, model, run_dir: Path, cwd: str):
    """Single-shot chat completion. For planning, summaries, patch suggestions —
    output is written to run_dir for a human or a later task to apply."""
    _write(run_dir, "prompt.md", prompt)
    try:
        res = llm_chat(cfg, model, [{"role": "user", "content": prompt}])
    except Exception as e:  # noqa: BLE001 — network/provider errors become a failed attempt
        return {"exit_status": "error", "cost_usd": 0.0, "output": f"LLM error: {e}"}
    _write(run_dir, "output.md", res["text"])
    return {"exit_status": "ok", "cost_usd": res["cost_usd"], "output": res["text"]}


def mock(cfg, task, prompt, model, run_dir: Path, cwd: str):
    """Test executor: fails until attempt N (cfg mock_succeed_on), then succeeds."""
    n = task["attempts"]
    ok = n >= int(cfg.get("mock_succeed_on", 1))
    _write(run_dir, "prompt.md", prompt)
    _write(run_dir, "output.md", f"mock attempt {n} -> {'ok' if ok else 'error'}")
    return {"exit_status": "ok" if ok else "error",
            "cost_usd": float(cfg.get("mock_cost", 0.01)),
            "output": "mock success" if ok else "error C2065: 'Health': undeclared identifier"}


def opencode(cfg, task, prompt, model, run_dir: Path, cwd: str):
    """OpenCode headless runner — routes through YOUR opencode.json providers
    (OpenRouter and LM Studio both work; see opencode.json in the repo root).
    Model comes from the ladder: string specs pass through as `-m`."""
    exe = cfg.get("opencode_bin", "opencode")
    if not shutil.which(exe):
        return {"exit_status": "error", "cost_usd": 0.0,
                "output": f"'{exe}' not found on PATH. Install OpenCode or set opencode_bin."}
    from ..router import model_name
    argv = [exe, "run", "-m", model_name(model), prompt] if model else [exe, "run", prompt]
    _write(run_dir, "prompt.md", prompt)
    p = _run_cli(argv, cwd, cfg.get("executor_timeout_s", 3600), run_dir)
    if p is None:
        return {"exit_status": "timeout", "cost_usd": 0.0, "output": "timeout"}
    return {"exit_status": "ok" if p.returncode == 0 else "error",
            "cost_usd": 0.0, "output": p.stdout or ""}


REGISTRY = {"claude_code": claude_code, "codex": codex, "api": api,
            "opencode": opencode, "mock": mock}
