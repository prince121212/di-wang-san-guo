@echo off
chcp 65001 >nul
title 关闭帝王三国电脑版辅助
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { Invoke-WebRequest -UseBasicParsing -Method Post -Uri 'http://127.0.0.1:17351/api/server/shutdown' -ContentType 'application/json' -Body '{}' -TimeoutSec 3 | Out-Null; exit 0 } catch { exit 1 }"

if errorlevel 1 (
  echo 未检测到正在运行的电脑版辅助。
) else (
  echo 已发送关闭指令，正在等待程序保存数据并退出...
  timeout /t 3 /nobreak >nul
)
pause
