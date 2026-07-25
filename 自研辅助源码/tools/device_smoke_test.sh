#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APK="$ROOT/app/build/outputs/apk/debug/app-debug.apk"
PKG="com.example.dwpmclone"
ACTIVITY="${PKG}/.MainActivity"
SERVICE="${PKG}/.service.AssistantForegroundService"
OUT_DIR="$ROOT/reports/device_smoke_$(date +%Y%m%d_%H%M%S)"
ADB_BIN="${ADB_BIN:-adb}"
mkdir -p "$OUT_DIR"

export PATH="/opt/homebrew/bin:$PATH"

tap_text_or_fallback() {
  local label="$1"
  local fallback_x="$2"
  local fallback_y="$3"
  local tag="$4"
  local xml_path="$OUT_DIR/${tag}_window.xml"
  local tap_log="$OUT_DIR/${tag}_tap.txt"

  "$ADB_BIN" shell uiautomator dump /sdcard/window.xml >/dev/null 2>&1 || true
  "$ADB_BIN" pull /sdcard/window.xml "$xml_path" >/dev/null 2>&1 || true
  coords="$(python3 - "$xml_path" "$label" <<'PY' || true
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

xml_path = Path(sys.argv[1])
label = sys.argv[2]
if not xml_path.exists():
    sys.exit(1)
try:
    root = ET.parse(xml_path).getroot()
except Exception:
    sys.exit(1)
for node in root.iter("node"):
    text = (node.attrib.get("text") or "") + " " + (node.attrib.get("content-desc") or "")
    if label not in text:
        continue
    bounds = node.attrib.get("bounds") or ""
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if match:
        left, top, right, bottom = map(int, match.groups())
        print(f"{(left + right) // 2} {(top + bottom) // 2}")
        sys.exit(0)
sys.exit(1)
PY
)"
  if [[ -n "${coords:-}" ]]; then
    read -r tap_x tap_y <<< "$coords"
    echo "tap label='$label' at $tap_x,$tap_y from $xml_path" | tee "$tap_log"
    "$ADB_BIN" shell input tap "$tap_x" "$tap_y"
  else
    echo "fallback tap label='$label' at $fallback_x,$fallback_y; UI xml=$xml_path" | tee "$tap_log"
    "$ADB_BIN" shell input tap "$fallback_x" "$fallback_y"
  fi
}

echo "[1/8] Checking adb devices..."
"$ADB_BIN" devices -l | tee "$OUT_DIR/adb_devices.txt"
if ! "$ADB_BIN" get-state >/dev/null 2>&1; then
  echo "ERROR: no adb device detected. Unlock phone, enable USB debugging, authorize RSA prompt, and select File Transfer/MTP." >&2
  exit 2
fi

SERIAL="$("$ADB_BIN" get-serialno)"
echo "device=$SERIAL" | tee "$OUT_DIR/device.txt"
"$ADB_BIN" shell getprop ro.product.manufacturer | tee -a "$OUT_DIR/device.txt" || true
"$ADB_BIN" shell getprop ro.product.model | tee -a "$OUT_DIR/device.txt" || true
"$ADB_BIN" shell getprop ro.build.version.release | tee -a "$OUT_DIR/device.txt" || true

echo "[2/8] Installing APK: $APK"
"$ADB_BIN" install -r -d "$APK" | tee "$OUT_DIR/install.txt"

echo "[3/8] Clearing logcat and launching app"
"$ADB_BIN" logcat -c || true
"$ADB_BIN" shell am force-stop "$PKG" || true
"$ADB_BIN" shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 | tee "$OUT_DIR/launch.txt"
sleep 3

echo "[4/8] Capturing current UI"
"$ADB_BIN" shell uiautomator dump /sdcard/window.xml >/dev/null 2>&1 || true
"$ADB_BIN" pull /sdcard/window.xml "$OUT_DIR/window.xml" >/dev/null 2>&1 || true
"$ADB_BIN" exec-out screencap -p > "$OUT_DIR/home.png" || true

echo "[5/8] Granting notification permission where supported"
"$ADB_BIN" shell pm grant "$PKG" android.permission.POST_NOTIFICATIONS >/dev/null 2>&1 || true

echo "[6/8] Starting foreground local scheduling service through UI button"
# The service is intentionally android:exported="false". Start it the same way users do:
# prefer uiautomator text bounds for "启动后台托管", then fall back to known Xiaomi coordinates.
tap_text_or_fallback "启动后台托管" 540 527 "start_service" | tee "$OUT_DIR/start_service.txt"
sleep 8

echo "[7/8] Collecting runtime evidence"
"$ADB_BIN" shell dumpsys package "$PKG" > "$OUT_DIR/dumpsys_package.txt" || true
"$ADB_BIN" shell dumpsys activity services "$PKG" > "$OUT_DIR/dumpsys_services.txt" || true
"$ADB_BIN" logcat -d -v time > "$OUT_DIR/logcat.txt" || true
"$ADB_BIN" exec-out screencap -p > "$OUT_DIR/after_service.png" || true

echo "[8/9] Stopping service through UI button"
tap_text_or_fallback "停止后台托管" 540 662 "stop_service" > "$OUT_DIR/stop_service.txt" 2>&1 || true
sleep 4
"$ADB_BIN" shell dumpsys activity services "$PKG" > "$OUT_DIR/dumpsys_services_after_stop.txt" || true
"$ADB_BIN" logcat -d -v time > "$OUT_DIR/logcat_after_stop.txt" || true

cat "$OUT_DIR/logcat.txt" "$OUT_DIR/logcat_after_stop.txt" > "$OUT_DIR/logcat_combined.txt" 2>/dev/null || true

echo "[9/9] Verifying self-lifecycle logcat markers"
python3 "$ROOT/tools/verify_self_lifecycle_logcat.py" "$OUT_DIR/logcat_combined.txt"   --out "$OUT_DIR/self_lifecycle_logcat_check.json"   --markdown-out "$OUT_DIR/self_lifecycle_logcat_check.md" || true

cat > "$OUT_DIR/summary.md" <<EOF
# 自研服务 APK 真机烟测

- device: $SERIAL
- apk: $APK
- package: $PKG
- install: see install.txt
- launch: see launch.txt
- UI dump: window.xml
- screenshots: home.png, after_service.png
- service evidence: dumpsys_services.txt
- logs: logcat.txt, logcat_after_stop.txt, logcat_combined.txt
- self lifecycle marker check: self_lifecycle_logcat_check.md
- UI tap evidence: start_service_tap.txt, stop_service_tap.txt, start_service_window.xml, stop_service_window.xml

说明：本烟测验证安装、启动、页面可渲染、前台服务可拉起、停止流程与日志采集；不验证真实游戏协议等价性，也不执行真实游戏自动化动作。按钮点击优先使用 uiautomator 文本定位，失败才回退固定坐标。如果 self_lifecycle_logcat_check.md 未通过，请先确认自研账号/任务计划存在并通过 UI 完整执行启动后停止。
EOF

echo "Smoke test artifacts: $OUT_DIR"
