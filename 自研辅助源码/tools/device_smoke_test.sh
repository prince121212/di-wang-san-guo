#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APK="$ROOT/app/build/outputs/apk/debug/app-debug.apk"
PKG="com.example.dwpmclone"
ACTIVITY="${PKG}/.AssistantWebActivity"
OUT_DIR="$ROOT/reports/device_smoke_$(date +%Y%m%d_%H%M%S)"
ADB_BIN="${ADB_BIN:-adb}"
mkdir -p "$OUT_DIR"

echo "[1/6] Checking device"
"$ADB_BIN" devices -l | tee "$OUT_DIR/adb_devices.txt"
if ! "$ADB_BIN" get-state >/dev/null 2>&1; then
  echo "ERROR: no authorized adb device" >&2
  exit 2
fi
"$ADB_BIN" get-serialno | tee "$OUT_DIR/device.txt"
"$ADB_BIN" shell getprop ro.product.model | tee -a "$OUT_DIR/device.txt" || true
"$ADB_BIN" shell getprop ro.build.version.release | tee -a "$OUT_DIR/device.txt" || true

echo "[2/6] Installing with the required non-destructive replacement command"
"$ADB_BIN" install -r "$APK" | tee "$OUT_DIR/install.txt"

echo "[3/6] Launching the local WebView activity (no hosting/task action)"
"$ADB_BIN" logcat -c || true
"$ADB_BIN" shell am start -n "$ACTIVITY" | tee "$OUT_DIR/launch.txt"
sleep 3

echo "[4/6] Capturing UI and package state"
"$ADB_BIN" shell uiautomator dump /sdcard/dwpm_window.xml >/dev/null 2>&1 || true
"$ADB_BIN" pull /sdcard/dwpm_window.xml "$OUT_DIR/window.xml" >/dev/null 2>&1 || true
"$ADB_BIN" exec-out screencap -p > "$OUT_DIR/home.png" || true
"$ADB_BIN" shell dumpsys package "$PKG" > "$OUT_DIR/dumpsys_package.txt" || true
"$ADB_BIN" shell dumpsys activity activities > "$OUT_DIR/dumpsys_activities.txt" || true

echo "[5/6] Checking app-process crashes"
PID="$("$ADB_BIN" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')"
if [[ -n "$PID" ]]; then
  "$ADB_BIN" logcat -d -v time --pid "$PID" > "$OUT_DIR/logcat.txt" || true
else
  "$ADB_BIN" logcat -d -v time > "$OUT_DIR/logcat.txt" || true
fi
if rg -n "FATAL EXCEPTION|AndroidRuntime.*Process: ${PKG}|ANR in ${PKG}" "$OUT_DIR/logcat.txt"; then
  echo "ERROR: app crash/ANR detected" >&2
  exit 3
fi
if ! rg -q "${PKG}/\.AssistantWebActivity|${PKG}\.AssistantWebActivity" "$OUT_DIR/dumpsys_activities.txt"; then
  echo "ERROR: local activity is not visible in activity state" >&2
  exit 4
fi

echo "[6/6] Writing report"
cat > "$OUT_DIR/summary.md" <<EOF
# 手机本地 V1 安全烟测

- device: $("$ADB_BIN" get-serialno)
- apk: $APK
- package: $PKG
- activity: $ACTIVITY
- install: 仅使用 adb install -r
- hostingStarted: false
- gameActionSent: false
- crashOrAnr: false
- screenshot: home.png
- UI dump: window.xml
- logs: logcat.txt

本脚本不点击开始任务，不启动前台托管服务，不发送游戏动作。
EOF

echo "Smoke test artifacts: $OUT_DIR"
