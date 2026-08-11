"""Command builders for Unreal on Windows. Paths come from harness.config.yaml.
These are the ONLY places engine paths live; evaluators and tools reuse them.
"""
from pathlib import Path


def _engine(cfg) -> Path:
    return Path(cfg["engine_root"])  # e.g. C:/Program Files/Epic Games/UE_5.8


def _uproject(cfg) -> Path:
    return Path(cfg["uproject"])     # e.g. D:/Dev/MyGame/MyGame.uproject


def build_cmd(cfg):
    """UnrealBuildTool: compile <Project>Editor Win64 Development."""
    ubt = _engine(cfg) / "Engine/Build/BatchFiles/Build.bat"
    target = cfg.get("build_target") or (_uproject(cfg).stem + "Editor")
    return [str(ubt), target, "Win64", "Development",
            f"-project={_uproject(cfg)}", "-WaitMutex"]


def automation_cmd(cfg, test_filter: str):
    """Headless automation tests via UnrealEditor-Cmd."""
    ed = _engine(cfg) / "Engine/Binaries/Win64/UnrealEditor-Cmd.exe"
    return [str(ed), str(_uproject(cfg)),
            f'-ExecCmds=Automation RunTests {test_filter}; Quit',
            "-unattended", "-nop4", "-nosplash", "-NullRHI", "-log"]


def screenshot_cmd(cfg, map_name: str, out_png: str, res="1920x1080"):
    """Load a map headless-with-RHI and take a high-res screenshot, then quit.
    For richer capture (specific cameras), prefer an in-project automation test
    or the MCP viewport tools; this is the dumb reliable fallback."""
    ed = _engine(cfg) / "Engine/Binaries/Win64/UnrealEditor-Cmd.exe"
    return [str(ed), str(_uproject(cfg)), map_name,
            f'-ExecCmds=HighResShot {res}; Quit',
            "-game", "-windowed", "-resx=1920", "-resy=1080", "-log"]
