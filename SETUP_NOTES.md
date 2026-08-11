# FORGE Harness — Setup Notes (2026-07-11)

Set up and **verified operational** on this Windows 11 machine.

## Entry point (IMPORTANT)
The bare `python` on PATH is a stripped **Swift-bundled Python 3.10.1** with **no pip, no site-packages
on sys.path** — it cannot host the harness. Use the complete **Python 3.12** instead, via the launchers:

```powershell
.\forge.ps1 status            # PowerShell
forge.cmd status              # cmd / double-click
py -3.12 -m harness status    # raw equivalent (run from this folder)
```

`forge.cmd` / `forge.ps1` pin `py -3.12`, set `PYTHONUTF8=1`, and run from this folder so
relative contract paths resolve.

## What was configured
- `harness.config.yaml`: `project_root=C:/GenesisWork/Project`, `uproject=.../Genesis.uproject`,
  `engine_root=C:/Program Files/Epic Games/UE_5.8`. (Chose the **NVMe** clone `C:\GenesisWork`; the
  D: copy is the slow USB HDD. `.mcp.json` + `.uproject` live in `Project/`, so that is the executor cwd.)
- `.env`: `OPENROUTER_API_KEY` populated from the existing environment variable (UTF-8, no BOM).
- `pyyaml`: already present in Python 3.12 (6.0.3). Swift Python left untouched.
- Tool scripts (`tools/seed_genesis.ps1`, `tools/nightly.ps1`, `tools/bootstrap.ps1`) repointed
  `python` → `py -3.12`.

## Windows correctness fixes applied to the harness
The harness read text files with `read_text()` at the platform default (cp1252). The constitution
(`prompts/worker_system.md`) and **every contract** contain non-ASCII (em-dashes/curly quotes), so
`harness run` would have crashed with `UnicodeDecodeError` on first prompt build. Added
`encoding="utf-8"` to all runtime reads:
- `harness/__main__.py` (config + .env), `harness/supervisor.py` (contract + constitution),
  `harness/evaluators/__init__.py` (perf.json read + visual_eval.json write).
- Launchers also export `PYTHONUTF8=1` as belt-and-braces (also fixes console em-dash output).
- `tests/test_core_loop.py`: UTF-8 reads + `TemporaryDirectory(ignore_cleanup_errors=True)` for the
  Windows sqlite file-lock on temp cleanup.

## Unreal wiring — already in place (no action needed)
`C:\GenesisWork\Project\.mcp.json` points to the first-party Unreal MCP (`http://127.0.0.1:8000/mcp`).
`.uproject` already enables `ModelContextProtocol` + `AllToolsets` (and `UnrealMCP`). Keep the UE 5.8
**editor open** during any harness run that touches the engine — the MCP server lives in the editor process.

## Verification evidence
- `py -3.12 tests/test_core_loop.py` → **ALL 19 CHECKS PASSED** (retry+escalation, evaluator gating,
  experience promotion, budget/attempt stops, dependency ordering, autonomy gating, crash-resume).
- OpenRouter: live `google/gemini-2.5-flash` completion returned `OK` (key valid; cloud tiers work).
- `load_contract` + `build_prompt` on a real non-ASCII genesis contract → 2282-char prompt, no crash.
- Queue seeded: 6 GENESIS tasks (D1-2 … hostile playtest), dependency-chained, none executed yet.

## Next commands (you drive these)
```powershell
.\forge.ps1 status
# Open the UE 5.8 editor (Genesis) first for MCP-dependent tasks, then:
.\forge.ps1 run --cycles 20
.\forge.ps1 show 1          # -> path to runs\task-1\attempt-1\report.md (evidence)
.\forge.ps1 approve 1       # or: reject 1 "reason"
.\forge.ps1 spend
```
Not yet done (optional, cost/local-only): LM Studio local tier — install + load
`qwen2.5-coder-14b-instruct`, start server on :1234. The harness works without it (cheap cloud tier
takes over); it is purely a cost optimization.

## Validation run (2026-07-11) — plumbing PASS, one blocker remains
Ran one real cycle on task 1. The durable chain worked end-to-end: prompt built → headless
`claude -p --output-format json` invoked → JSON result+cost parsed → executor error detected →
`report.md` written → task transitioned to `needs_retry` on the live db. Task 1 has since been
reset to a clean `queued` (0 attempts).

Fixed along the way:
- **Workspace trust**: `C:/GenesisWork` had `hasTrustDialogAccepted=false`, so headless Claude Code
  ignored the project's 20 `permissions.allow` entries. Set to `true` in `C:\Users\caleb\.claude.json`
  (backup: `.claude.json.forge-bak`).
- **Executor BOM/encoding bug**: `claude -p --output-format json` emits a UTF-8 BOM on Windows, so
  `json.loads` failed and cost/result never parsed (always $0.00). Fixed in
  `harness/executors/__init__.py`: `text.lstrip(chr(0xFEFF))` before `json.loads`, and the executor
  subprocess now decodes stdout as UTF-8 (`encoding="utf-8"`) with empty stdin (kills the 3s
  "no stdin" wait). Verified against the real captured output.
- `executor_timeout_s` lowered 3600 → 1200 (20 min; 1h invited runaways).

**BLOCKER — you must do this (I can't; it needs your credentials):**
The `claude` CLI is **not logged in** for headless `-p` use (`"Not logged in · Please run /login"`),
even though `oauthAccount` is in `.claude.json` (token likely stale). Fix with EITHER:
- `claude login` (re-auth; uses your Claude subscription), **or**
- set `ANTHROPIC_API_KEY` (from console.anthropic.com) — most reliable for headless/CI; API billing.
Then confirm: from `C:\GenesisWork\Project`, `'' | claude -p "say READY" --output-format json`
should return `"READY"`, not "Not logged in".

Alternative executor (no Anthropic auth): set `executor: opencode` in `harness.config.yaml` — it routes
through your working OpenRouter key via `opencode.json`. (Needs `opencode` configured for OpenRouter.)

After auth: engine/visual tasks still need the **UE editor open** (MCP on :8000) and **reference
images in `vault/references/`** for the `visual` evaluator to pass. For deterministic C++ verification,
consider adding a `build` evaluator (UBT compile) — the project is C++ (`Source/`), not Blueprint-only.
