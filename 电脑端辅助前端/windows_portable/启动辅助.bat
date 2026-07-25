@echo off
chcp 65001 >nul
title 帝王三国电脑版辅助
cd /d "%~dp0"

if not exist "runtime\python.exe" (
  echo [错误] 缺少 runtime\python.exe，请重新完整解压便携版。
  pause
  exit /b 1
)
if not exist "proxy\mihomo.exe" (
  echo [错误] 缺少 proxy\mihomo.exe，可能被安全软件隔离。
  pause
  exit /b 1
)
if not exist "proxy\顶级机场-完整便携版.yaml" (
  echo [错误] 缺少代理配置文件，请重新完整解压便携版。
  pause
  exit /b 1
)

if "%LOCALAPPDATA%"=="" (
  set "DWPM_USER_HOME=%USERPROFILE%\AppData\Local\DWPMDesktop"
) else (
  set "DWPM_USER_HOME=%LOCALAPPDATA%\DWPMDesktop"
)
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "DWPM_DATA_DIR=%DWPM_USER_HOME%\data"
set "DWPM_LEGACY_DATA_DIR=%CD%\data"
set "DWPM_ASSET_DIR=%CD%\app\assets"
set "DWPM_CLASH_SOURCE_DIR=%CD%\proxy"
set "DWPM_CLASH_SOURCE_CONFIG=%CD%\proxy\顶级机场-完整便携版.yaml"
set "DWPM_CLASH_CORE_BINARY=%CD%\proxy\mihomo.exe"

echo 正在启动，浏览器将自动打开...
"runtime\python.exe" "portable_launcher.py"

echo.
echo 电脑版辅助已经停止。
pause
