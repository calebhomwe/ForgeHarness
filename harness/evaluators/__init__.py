"""Evaluators. THE SYSTEM DECLARES SUCCESS, NOT THE AGENT.

Contract: run(cfg, task, contract, run_dir, cwd) -> {"passed": bool, "score": float|None,
                                                     "details": anything-json-able}
A task's acceptance contract lists which evaluators must pass (see contracts/*.yaml).
Unreal-facing evaluators shell out to UBT / UnrealEditor-Cmd (see harness/unreal/commands.py)
so they run identically for a human, Claude Code, or an overnight loop.
"""
import json
import re
import subprocess
from pathlib import Path

from ..router import llm_chat
from ..unreal import commands as ue


def _sh(argv, cwd, timeout, log_path: Path):
    p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    log_path.write_text((p.stdout or "") + "\n--- STDERR ---\n" + (p.stderr or ""),
                        encoding="utf-8", errors="replace")
    return p


def build(cfg, task, contract, run_dir: Path, cwd: str):
    """Compile the project. Pass = exit 0. Extracts first compiler errors for the retry prompt."""
    argv = ue.build_cmd(cfg)
    p = _sh(argv, cwd, cfg.get("build_timeout_s", 3600), run_dir / "build.log")
    errors = re.findall(r"^.*(?:error [A-Z]+\d+|Error:).*$",
                        (p.stdout or "") + (p.stderr or ""), re.MULTILINE)[:20]
    return {"passed": p.returncode == 0, "score": None,
            "details": {"returncode": p.returncode, "errors": errors}}


def tests(cfg, task, contract, run_dir: Path, cwd: str):
    """Run Unreal automation tests matching contract['test_filter'] (default project prefix)."""
    filt = (contract or {}).get("test_filter", cfg.get("test_filter", "Project"))
    argv = ue.automation_cmd(cfg, filt)
    p = _sh(argv, cwd, cfg.get("test_timeout_s", 3600), run_dir / "tests.log")
    out = (p.stdout or "") + (p.stderr or "")
    failed = re.findall(r"Test Completed?\. Result=\{?Fail", out) or re.findall(r"\bFailed\b", out)
    ran = bool(re.search(r"Automation Test", out)) or p.returncode == 0
    passed = p.returncode == 0 and not failed and ran
    return {"passed": passed, "score": None,
            "details": {"returncode": p.returncode, "fail_hits": len(failed)}}


def visual(cfg, task, contract, run_dir: Path, cwd: str):
    """Score screenshots in run_dir/shots (or contract['screenshots']) with a vision model
    against references in vault/references. Pass = overall >= threshold (default 7)."""
    import base64
    thresh = float((contract or {}).get("visual_threshold", cfg.get("visual_threshold", 7)))
    shots = sorted(Path(run_dir, "shots").glob("*.png")) or \
        [Path(p) for p in (contract or {}).get("screenshots", [])]
    if not shots:
        return {"passed": False, "score": 0,
                "details": "no screenshots produced — capture to <run_dir>/shots/*.png"}
    refs = sorted(Path(cfg["vault_dir"], "references").glob("*.*"))[:2]

    def b64(p: Path):
        ext = p.suffix.lstrip(".").replace("jpg", "jpeg")
        return {"type": "image_url", "image_url":
                {"url": f"data:image/{ext};base64," + base64.b64encode(p.read_bytes()).decode()}}

    content = [{"type": "text", "text":
                "You are a senior game art director. First image(s) are WIP Unreal screenshots"
                + ("; last image(s) are style references." if refs else ".")
                + ' Score 1-10 (composition, lighting, readability, style_match, overall) and give'
                ' up to 5 concrete fixes. Respond ONLY JSON: {"scores": {...}, "fixes": [...]}'}]
    content += [b64(s) for s in shots[:3]] + [b64(r) for r in refs]
    res = llm_chat(cfg, cfg["models"].get("vision", cfg["models"]["standard"]),
                   [{"role": "user", "content": content}])
    raw = res["text"].strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(raw)
        overall = float(data["scores"]["overall"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {"passed": False, "score": 0, "details": {"unparseable": raw[:500]}}
    (run_dir / "visual_eval.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"passed": overall >= thresh, "score": overall, "details": data}


def perf(cfg, task, contract, run_dir: Path, cwd: str):
    """Parse a stats dump (run_dir/perf.json written by a test, or contract['perf_file'])
    against thresholds: frame_ms_max, memory_mb_max."""
    src = Path((contract or {}).get("perf_file", run_dir / "perf.json"))
    limits = (contract or {}).get("perf_limits", cfg.get("perf_limits",
                                                         {"frame_ms_max": 22.2, "memory_mb_max": 12000}))
    if not src.exists():
        return {"passed": False, "score": None, "details": f"perf file missing: {src}"}
    data = json.loads(src.read_text(encoding="utf-8"))
    fails = {k: (data.get(k.replace("_max", "")), v) for k, v in limits.items()
             if data.get(k.replace("_max", ""), 0) > v}
    return {"passed": not fails, "score": None, "details": {"measured": data, "violations": fails}}


def docs(cfg, task, contract, run_dir: Path, cwd: str):
    """Format-gate for generated manual chapters (the Genesis pipeline).
    Checks: file exists, YAML frontmatter, required headings, >=1 mermaid block,
    wikilinks for integration, and no oversized verbatim code blocks (>60 lines)."""
    rel = (contract or {}).get("doc_path")
    if not rel:
        return {"passed": False, "score": None, "details": "contract missing doc_path"}
    path = Path(cwd) / rel
    if not path.exists():
        return {"passed": False, "score": None, "details": f"missing output file: {rel}"}
    text = path.read_text(encoding="utf-8", errors="replace")
    required = (contract or {}).get("required_sections", [
        "System Overview", "Design Philosophy", "Core Components",
        "Implementation Walkthrough", "Blueprint Node Reference",
        "Integration Points", "Deprecations & Version Notes", "Open Questions"])
    problems = [f"missing section heading: '{s}'" for s in required if f"## {s}" not in text]
    if not text.lstrip().startswith("---"):
        problems.append("missing YAML frontmatter block")
    if "```mermaid" not in text:
        problems.append("no mermaid diagram block")
    if "[[" not in text:
        problems.append("no [[wikilinks]] to related chapters")
    for block in re.findall(r"```(?:cpp|c\+\+|cs)?\n(.*?)```", text, re.DOTALL):
        if block.count("\n") > 60:
            problems.append("verbatim code block >60 lines — synthesize and link instead")
            break
    return {"passed": not problems, "score": None,
            "details": problems or f"chapter ok: {rel} ({len(text)} chars)"}


def mock_pass(cfg, task, contract, run_dir: Path, cwd: str):
    return {"passed": True, "score": 10, "details": "mock"}


def mock_fail_then_pass(cfg, task, contract, run_dir: Path, cwd: str):
    ok = task["attempts"] >= int(cfg.get("mock_eval_pass_on", 2))
    return {"passed": ok, "score": 8 if ok else 4,
            "details": "mock eval " + ("pass" if ok else "fail: lighting too flat")}


REGISTRY = {"build": build, "tests": tests, "visual": visual, "perf": perf, "docs": docs,
            "mock_pass": mock_pass, "mock_fail_then_pass": mock_fail_then_pass}
