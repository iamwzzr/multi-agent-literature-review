@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0.tools\node-v24.22.2-win-x64\node.exe" set "PATH=%~dp0.tools\node-v24.22.2-win-x64;%PATH%"
where node.exe >nul 2>nul
if errorlevel 1 (
  echo Node.js not found. Install Node.js 22.12+ or prepare the project-local Node 24 runtime.
  exit /b 1
)
node.exe -e "const [major,minor]=process.versions.node.split('.').map(Number); process.exit(major>22 || (major===22 && minor>=12) ? 0 : 1)"
if errorlevel 1 (
  echo Node.js is too old. This frontend requires Node.js 22.12 or newer.
  exit /b 1
)
where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo npm not found. Install the Node.js distribution including npm.
  exit /b 1
)
call npm.cmd %*
