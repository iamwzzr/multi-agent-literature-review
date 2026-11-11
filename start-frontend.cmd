@echo off
setlocal
cd /d "%~dp0"
if not exist "node_modules\vite" (
  call "%~dp0frontend.cmd" ci
  if errorlevel 1 exit /b 1
)
call "%~dp0frontend.cmd" run dev -- --host 127.0.0.1 --port 5173 --strictPort
