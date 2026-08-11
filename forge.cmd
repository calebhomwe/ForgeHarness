@echo off
setlocal
REM FORGE launcher - pins the harness to the complete Python 3.12 interpreter.
REM The bare "python" on PATH is a stripped Swift runtime with no pip or pyyaml.
REM Runs from the harness folder so "-m harness" and relative config/contract paths resolve.
pushd "%~dp0"
set PYTHONUTF8=1
py -3.12 -m harness %*
set "FORGE_EXIT=%ERRORLEVEL%"
popd
exit /b %FORGE_EXIT%
