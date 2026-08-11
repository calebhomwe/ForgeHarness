# FORGE bootstrap for GENESIS — run once in PowerShell (as your user, not admin needed
# except for winget installs). From the forge-harness folder:  ./tools/bootstrap.ps1
$ErrorActionPreference = "Continue"
Set-Location "$PSScriptRoot\.."
Write-Host "== FORGE bootstrap for GENESIS ==" -ForegroundColor Cyan

function Need($cmd, $wingetId, $note) {
  if (Get-Command $cmd -ErrorAction SilentlyContinue) { Write-Host "[ok] $cmd found" }
  else { Write-Host "[..] installing $cmd via winget ($wingetId) $note";
         winget install --id $wingetId -e --accept-source-agreements --accept-package-agreements }
}
Need git    Git.Git ""
Need python Python.Python.3.12 ""
Need node   OpenJS.NodeJS.LTS ""

Write-Host "[..] Python deps";        py -3.12 -m pip install -r requirements.txt --quiet
Write-Host "[..] Claude Code CLI";    npm install -g @anthropic-ai/claude-code
Write-Host "[..] OpenCode CLI";       npm install -g opencode-ai
Write-Host "[..] LM Studio";          winget install --id ElementLabs.LMStudio -e --accept-source-agreements --accept-package-agreements
Write-Host "    -> open LM Studio once: download 'qwen2.5-coder-14b-instruct', then Developer tab -> Start Server (port 1234)"

if (-not (Test-Path ".env")) { Copy-Item .env.example .env
  Write-Host "[!!] EDIT .env — add your OPENROUTER_API_KEY" -ForegroundColor Yellow }

# knowledge sync: your repo -> vault
Write-Host "[..] syncing github.com/calebhomwe/genesis into vault/knowledge/genesis-repo"
if (Test-Path "vault/knowledge/genesis-repo") { git -C vault/knowledge/genesis-repo pull }
else { git clone https://github.com/calebhomwe/genesis vault/knowledge/genesis-repo }

py -3.12 -m harness init
Write-Host ""
Write-Host "== NEXT (manual, 10 min) ==" -ForegroundColor Cyan
Write-Host "1. Create/open the UE 5.8 project at the path in harness.config.yaml (Third Person, Blueprint)."
Write-Host "2. git init + commit the UE project. Non-negotiable."
Write-Host "3. Editor: enable 'Model Context Protocol' + 'AllToolsets' plugins -> restart."
Write-Host "4. Editor console:  ModelContextProtocol.GenerateClientConfig ClaudeCode"
Write-Host "5. Copy this forge-harness folder's contents INTO the UE project root (or run from here with project paths set)."
Write-Host "6. ./tools/seed_genesis.ps1   then   python -m harness run --cycles 20"
