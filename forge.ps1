# FORGE launcher (PowerShell) — pins the harness to the complete Python 3.12 interpreter.
# The bare `python` on PATH is a stripped Swift runtime with no pip/pyyaml, so we use `py -3.12`.
# Usage:  .\forge.ps1 status   |   .\forge.ps1 run --cycles 20
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $here
$env:PYTHONUTF8 = '1'
try { & py -3.12 -m harness @args } finally { Pop-Location }
