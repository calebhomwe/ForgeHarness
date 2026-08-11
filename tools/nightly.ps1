# Doc-50 §13: nightly automation via Windows Task Scheduler (no n8n needed yet).
# Register:  schtasks /Create /SC DAILY /ST 02:00 /TN ForgeNightly /TR "powershell -File D:\forge-harness\tools\nightly.ps1"
Set-Location $PSScriptRoot\..
git -C (Get-Content harness.config.yaml | Select-String 'project_root' | ForEach-Object { ($_ -split '"')[1] }) add -A 2>$null
py -3.12 -m harness add "Nightly asset audit" --contract contracts/library/asset_audit.yaml --risk low --autonomy 6 --budget 1
py -3.12 -m harness add "Nightly hostile playtest of main map" --contract contracts/library/playtest_sim.yaml --risk low --autonomy 6 --budget 2
py -3.12 -m harness run --cycles 20 *>> runs\nightly.log
py -3.12 -m harness status *>> runs\nightly.log   # your morning summary lives in runs\nightly.log + report.md files
