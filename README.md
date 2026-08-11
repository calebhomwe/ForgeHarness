# FORGE Harness — Autonomous Unreal Development Harness

Orchestrator → workers → evaluators, with durable execution, budgets, experience
memory, and human approval gates. The agent never grades its own homework:
**the test system declares success, not the worker.**

Core loop is fully tested (`tests/test_core_loop.py`, 19 checks): retry-with-feedback,
model escalation, evaluator gating, experience promotion, budget hard-stops,
dependency ordering, autonomy gating, crash-resume.

```
you ──► harness CLI ──► SUPERVISOR (durable, SQLite-backed)
                          │ pick task (priority + deps) ── daily/task budgets
                          │ isolate git worktree
                          │ build prompt: constitution + contract
                          │              + verified fixes + last failures
                          │ route model (cheap→standard→heavy, escalates per retry)
                          ▼
                        EXECUTOR   claude_code (headless, drives UE via the
                          │        official 5.8 MCP plugin) | codex | api
                          ▼
                        EVALUATORS build (UBT) · tests (Automation) ·
                          │        visual (vision model vs references) · perf
                          ▼
              all pass ──┴── any fail
                 │              └► feedback into next attempt (max_attempts, budget)
        autonomy≥6 & low risk?         failures stored as experience;
           yes → done                  promoted to VERIFIED on eventual success
           no  → awaiting_approval → you review report.md → approve/reject
```

## Install (Windows, PowerShell)
```powershell
pip install -r requirements.txt
copy .env.example .env          # add OPENROUTER_API_KEY (visual evaluator + api executor)
# edit harness.config.yaml: project_root, uproject, engine_root
```
One-time in your UE project (see docs/UNREAL_SETUP.md):
enable **Model Context Protocol** + **AllToolsets** plugins, then in the editor console:
`ModelContextProtocol.GenerateClientConfig ClaudeCode` — this is how the claude_code
executor reaches the live editor.

## Use
```powershell
python -m harness init
python -m harness add "Village NPC spawn system" --contract contracts/example_npc_spawn.yaml --priority 1 --budget 8
python -m harness add "Lighting pass on village" --after 1 --risk low
python -m harness run --cycles 30        # go make coffee / sleep — it's resumable
python -m harness status
python -m harness show 1                 # → path to evidence report.md
python -m harness approve 1              # or: reject 1 "camera clips through wall"
python -m harness fix "error LNK2019 ..." "add module to Build.cs"   # seed memory
python -m harness spend
```

## The pieces (what each file is FOR)
| Path | Purpose |
|---|---|
| `harness/supervisor.py` | The loop. Doc-46's workflow made durable and crash-safe. |
| `harness/db.py` | SQLite state: tasks, attempts, evaluations, experience, audit events. |
| `harness/router.py` | Model ladder + escalation + OpenAI-compatible LLM client (OpenRouter or a LiteLLM proxy — just change `llm_base_url`). |
| `harness/executors/` | How work happens: `claude_code` (headless, MCP→Unreal), `codex`, `api`, `mock`. Add your own in one function. |
| `harness/evaluators/` | How success is decided: `build`, `tests`, `visual`, `perf`. Contracts pick which apply. |
| `harness/unreal/commands.py` | The only place engine paths/commands live (UBT, UnrealEditor-Cmd, screenshots). |
| `harness/unreal/worktree.py` | Git worktree isolation per task — autonomy level 2+ safety. |
| `harness/memory/experience.py` | Error→fix pairs; only VERIFIED fixes are injected into prompts. |
| `contracts/*.yaml` | Acceptance contracts: requirements, evaluators, thresholds, evidence. |
| `prompts/worker_system.md` | The worker constitution (no placeholders, evidence mandatory, etc.). |
| `vault/` | Human knowledge: references/ images feed the visual evaluator; DECISIONS.md. |
| `runs/` | Every attempt's prompt, logs, screenshots, evaluator verdicts, report.md. |

## Autonomy ladder (per task: `--autonomy N`)
0–1 read/plan only (use `api` executor) · 2–3 sandboxed worktree edits (default) ·
4–5 unattended feature branches, human approves integration ·
6 auto-integrate **only if risk=low and every evaluator passed**.
High-risk operations (deletes, engine/plugin changes, main-branch merges, spending)
stay behind a human regardless — the harness only ever *proposes* merges via report.md.

## Scaling path
This is deliberately SQLite + stdlib so it runs today. When (and only when) you hit the
limits, `docs/SCALING.md` maps each module to its heavyweight replacement:
Postgres, Qdrant retrieval, LangGraph supervisor, Temporal durability, HF trajectory datasets.
