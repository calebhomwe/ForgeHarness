# Wiring the harness to Unreal 5.8

## 1. Official MCP plugin (the worker's hands)
Editor → Edit → Plugins → enable **Model Context Protocol** AND **AllToolsets** → restart.
Editor console: `ModelContextProtocol.GenerateClientConfig ClaudeCode`
This writes `.mcp.json` into the project root. The `claude_code` executor runs with
cwd = the task's worktree; each worktree is a full checkout, so the generated config
travels with it. Keep the editor OPEN during runs — the MCP server lives in the editor process.

## 2. Headless evaluators (the judge — no editor needed)
- build: `Engine/Build/BatchFiles/Build.bat <Project>Editor Win64 Development -project=...`
- tests: `UnrealEditor-Cmd.exe <uproject> -ExecCmds="Automation RunTests <filter>; Quit" -NullRHI -unattended`
- Write real Automation/Functional tests in your project; the contract's `test_filter`
  selects them. A feature without a test cannot pass the `tests` evaluator — by design.

## 3. Evidence the worker must produce
- Screenshots → `<worktree>/__forge_run__/shots/*.png` (visual evaluator input;
  capture via MCP viewport tools or `HighResShot 1920x1080`).
- Perf dump → `<worktree>/__forge_run__/perf.json` e.g. `{"frame_ms": 14.2, "memory_mb": 8200}`
  (write it from your soak/functional test).

## 4. Worktrees and large UE projects
Git worktrees share the object store but CHECK OUT Content/ per worktree. For a massive
project either (a) enable Git LFS + `git lfs dedup` (b) keep `use_worktrees: false` and
run tasks sequentially on branches, or (c) point DerivedDataCache to a shared location
so each worktree doesn't re-derive shaders:
`[InstalledDerivedDataBackendGraph] Local=(Type=FileSystem, Path="D:/SharedDDC")` in DefaultEngine.ini.

## 5. Unattended runs
- Commit before starting. Always.
- `claude_extra_args: ["--permission-mode", "acceptEdits"]` in harness.config.yaml for
  fewer prompts (verify flag names against your `claude --help`).
- The harness's own budgets/attempts are the real leash; Claude Code flags are belt+braces.
