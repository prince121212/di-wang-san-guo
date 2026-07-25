#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_FRIDA_SCRIPT="$ROOT/../reverse_cases/apk/scripts/frida_native_session_trace_v2.js"
DEFAULT_SELF_APK="$ROOT/app/build/outputs/apk/debug/app-debug.apk"
DEFAULT_XIAOHUANG_APK="$ROOT/../小黄点辅助.apk"
DEFAULT_GAME_APK="$ROOT/../三国·帝王联盟1.66.apk"
FRIDA_SCRIPT="$DEFAULT_FRIDA_SCRIPT"
SELF_APK="$DEFAULT_SELF_APK"
XIAOHUANG_APK="$DEFAULT_XIAOHUANG_APK"
GAME_APK="$DEFAULT_GAME_APK"
PKG=""
MODE="spawn"
DURATION="120"
OUT_DIR="$ROOT/reports/device_protocol_$(date +%Y%m%d_%H%M%S)"
INCLUDE_VALUES="false"
BASE_CHANNEL_EXTRA=""
PREFLIGHT="true"
FRIDA_BIN="${FRIDA_BIN:-frida}"
FRIDA_PS_BIN="${FRIDA_PS_BIN:-frida-ps}"
ADB_BIN="${ADB_BIN:-adb}"

usage() {
  cat <<EOF
Usage: $0 --package <android.package> [options]

Options:
  --package <pkg>          Target package to spawn/attach with Frida. Required.
  --mode spawn|attach      spawn uses: frida -U -f <pkg>; attach uses: frida -U -n <pkg>. Default: spawn.
  --duration <seconds>     Capture duration before stopping Frida/logcat. Default: 120.
  --out-dir <dir>          Output directory. Default: reports/device_protocol_<timestamp>.
  --frida-script <path>    Frida script path. Default: reverse_cases/apk/scripts/frida_native_session_trace_v2.js.
  --self-apk <path>        Self-developed assistant APK checked by preflight. Default: app-debug.apk.
  --xiaohuang-apk <path>   小黄点 APK checked by preflight. Default: ../小黄点辅助.apk.
  --game-apk <path>        Game APK checked by preflight. Default: ../三国·帝王联盟1.66.apk.
  --base-channel-extra <json>
                           Optional base session/channelExtra JSON used by replay contract verification.
                           Put login-derived identity/role/resource/general/formation fields here.
  --include-values         Pass raw wrapper values to offline regression outputs. Use only on isolated test accounts.
  --skip-preflight         Skip check_device_regression_preflight.py. Not recommended; use only for tool debugging.
  -h, --help               Show this help.

This script captures logs only. It does not enable real action sends in the self-developed app.
Use an isolated AVD/test account and comply with the target app/server rules.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --package) PKG="${2:-}"; shift 2 ;;
    --mode) MODE="${2:-}"; shift 2 ;;
    --duration) DURATION="${2:-}"; shift 2 ;;
    --out-dir) OUT_DIR="${2:-}"; shift 2 ;;
    --frida-script) FRIDA_SCRIPT="${2:-}"; shift 2 ;;
    --self-apk) SELF_APK="${2:-}"; shift 2 ;;
    --xiaohuang-apk) XIAOHUANG_APK="${2:-}"; shift 2 ;;
    --game-apk) GAME_APK="${2:-}"; shift 2 ;;
    --base-channel-extra) BASE_CHANNEL_EXTRA="${2:-}"; shift 2 ;;
    --include-values) INCLUDE_VALUES="true"; shift ;;
    --skip-preflight) PREFLIGHT="false"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 64 ;;
  esac
done

if [[ -z "$PKG" ]]; then
  echo "ERROR: --package is required" >&2
  usage >&2
  exit 64
fi
if [[ "$MODE" != "spawn" && "$MODE" != "attach" ]]; then
  echo "ERROR: --mode must be spawn or attach" >&2
  exit 64
fi
if ! [[ "$DURATION" =~ ^[0-9]+$ ]] || [[ "$DURATION" -lt 5 ]]; then
  echo "ERROR: --duration must be an integer >= 5" >&2
  exit 64
fi

mkdir -p "$OUT_DIR"
COMBINED_LOG="$OUT_DIR/device_combined.log"
FRIDA_LOG="$OUT_DIR/frida.log"
LOGCAT_LOG="$OUT_DIR/logcat.txt"
SUMMARY="$OUT_DIR/capture_summary.md"
PREFLIGHT_JSON="$OUT_DIR/preflight.json"
PREFLIGHT_MD="$OUT_DIR/preflight.md"
OPERATOR_GUIDE="$OUT_DIR/capture_operator_guide.md"

if [[ "$PREFLIGHT" == "true" ]]; then
  PREFLIGHT_ARGS=(
    "$ROOT/tools/check_device_regression_preflight.py"
    --adb-bin "$ADB_BIN"
    --frida-bin "$FRIDA_BIN"
    --frida-ps-bin "$FRIDA_PS_BIN"
    --package "$PKG"
    --self-apk "$SELF_APK"
    --xiaohuang-apk "$XIAOHUANG_APK"
    --game-apk "$GAME_APK"
    --frida-script "$FRIDA_SCRIPT"
    --out "$PREFLIGHT_JSON"
    --markdown-out "$PREFLIGHT_MD"
  )
  if [[ -n "$BASE_CHANNEL_EXTRA" ]]; then
    PREFLIGHT_ARGS+=(--base-channel-extra "$BASE_CHANNEL_EXTRA")
  fi
  python3 "${PREFLIGHT_ARGS[@]}"
  PREFLIGHT_READY="$(python3 - "$PREFLIGHT_JSON" <<'PY'
import json
import sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print("true" if data.get("summary", {}).get("preflightReady") else "false")
PY
)"
  if [[ "$PREFLIGHT_READY" != "true" ]]; then
    echo "ERROR: device regression preflight failed. See:" >&2
    echo "  $PREFLIGHT_MD" >&2
    exit 69
  fi
else
  echo "WARNING: --skip-preflight used; capture may fail later if ADB/Frida/APK state is incomplete." >&2
fi
python3 "$ROOT/tools/generate_device_capture_operator_guide.py" \
  --package "$PKG" \
  --mode "$MODE" \
  --duration "$DURATION" \
  --base-channel-extra "$BASE_CHANNEL_EXTRA" \
  --out "$OPERATOR_GUIDE"

if [[ ! -f "$FRIDA_SCRIPT" ]]; then
  echo "ERROR: Frida script not found: $FRIDA_SCRIPT" >&2
  exit 66
fi
if [[ -n "$BASE_CHANNEL_EXTRA" && ! -f "$BASE_CHANNEL_EXTRA" ]]; then
  echo "ERROR: base channelExtra JSON not found: $BASE_CHANNEL_EXTRA" >&2
  exit 66
fi
if ! command -v "$ADB_BIN" >/dev/null 2>&1; then
  echo "ERROR: adb not found. Set ADB_BIN or install Android platform-tools." >&2
  exit 69
fi
if ! command -v "$FRIDA_BIN" >/dev/null 2>&1; then
  echo "ERROR: frida CLI not found. Set FRIDA_BIN or install frida-tools." >&2
  exit 69
fi
if ! command -v "$FRIDA_PS_BIN" >/dev/null 2>&1; then
  echo "ERROR: frida-ps CLI not found. Set FRIDA_PS_BIN or install frida-tools." >&2
  exit 69
fi
if ! "$ADB_BIN" get-state >/dev/null 2>&1; then
  echo "ERROR: no adb device detected or authorized." >&2
  exit 69
fi

cleanup() {
  set +e
  if [[ -n "${FRIDA_PID:-}" ]]; then kill "$FRIDA_PID" >/dev/null 2>&1 || true; fi
  if [[ -n "${LOGCAT_PID:-}" ]]; then kill "$LOGCAT_PID" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT

{
  echo "# Device protocol capture"
  echo
  echo "- package: $PKG"
  echo "- mode: $MODE"
  echo "- duration: ${DURATION}s"
  echo "- fridaScript: $FRIDA_SCRIPT"
  echo "- selfApk: $SELF_APK"
  echo "- xiaohuangApk: $XIAOHUANG_APK"
  echo "- gameApk: $GAME_APK"
  echo "- preflight: $PREFLIGHT"
  if [[ "$PREFLIGHT" == "true" ]]; then
    echo "- preflightJson: $PREFLIGHT_JSON"
    echo "- preflightMarkdown: $PREFLIGHT_MD"
  fi
  echo "- operatorGuide: $OPERATOR_GUIDE"
  if [[ -n "$BASE_CHANNEL_EXTRA" ]]; then echo "- baseChannelExtra: $BASE_CHANNEL_EXTRA"; fi
  echo "- networkSendAllowed: false"
  echo "- note: capture/log aggregation only; real action gate remains disabled in self-developed app."
} > "$SUMMARY"

"$ADB_BIN" devices -l > "$OUT_DIR/adb_devices.txt"
"$ADB_BIN" logcat -c || true
"$ADB_BIN" logcat -v time > "$LOGCAT_LOG" &
LOGCAT_PID=$!

if [[ "$MODE" == "spawn" ]]; then
  "$FRIDA_BIN" -U -f "$PKG" -l "$FRIDA_SCRIPT" > "$FRIDA_LOG" 2>&1 &
else
  "$FRIDA_BIN" -U -n "$PKG" -l "$FRIDA_SCRIPT" > "$FRIDA_LOG" 2>&1 &
fi
FRIDA_PID=$!

sleep "$DURATION"
cleanup
trap - EXIT

{
  echo "===== frida.log ====="
  cat "$FRIDA_LOG" || true
  echo
  echo "===== logcat.txt ====="
  cat "$LOGCAT_LOG" || true
} > "$COMBINED_LOG"

REGRESSION_ARGS=("$ROOT/tools/device_regression_from_logs.py" "$COMBINED_LOG" --out-dir "$OUT_DIR/regression")
if [[ -n "$BASE_CHANNEL_EXTRA" ]]; then
  REGRESSION_ARGS+=(--base-channel-extra "$BASE_CHANNEL_EXTRA")
fi
if [[ "$INCLUDE_VALUES" == "true" ]]; then
  REGRESSION_ARGS+=(--include-values)
fi
python3 "${REGRESSION_ARGS[@]}"
python3 "$ROOT/tools/verify_device_capture_scenarios.py" "$COMBINED_LOG" \
  --out "$OUT_DIR/capture_scenario_check.json" \
  --markdown-out "$OUT_DIR/capture_scenario_check.md"
python3 "$ROOT/tools/verify_self_lifecycle_logcat.py" "$COMBINED_LOG" \
  --out "$OUT_DIR/self_lifecycle_logcat_check.json" \
  --markdown-out "$OUT_DIR/self_lifecycle_logcat_check.md"
python3 "$ROOT/tools/verify_shuahuang_minimum_goal.py" "$OUT_DIR" \
  --out "$OUT_DIR/shuahuang_minimum_goal_check.json" \
  --markdown-out "$OUT_DIR/shuahuang_minimum_goal_check.md"
python3 "$ROOT/tools/verify_device_regression_artifacts.py" "$OUT_DIR" \
  --out "$OUT_DIR/regression_artifact_check.json" \
  --markdown-out "$OUT_DIR/regression_artifact_check.md"

cat >> "$SUMMARY" <<EOF

## Outputs

- frida.log
- logcat.txt
- device_combined.log
- preflight.md
- preflight.json
- capture_operator_guide.md
- regression/summary.md
- regression/device_regression_report.json
- regression/merged_channel_extra.json
- regression/capture_scenario_coverage.md
- regression/replay_contract.md
- regression/shuahuang_offline_replay.md
- regression/daily_offline_replay.md
- regression/mine_offline_replay.md
- regression/action_gate_readiness.md
- regression/full_offline_replay.md
- capture_scenario_check.md
- self_lifecycle_logcat_check.md
- regression_artifact_check.md
- shuahuang_minimum_goal_check.md

Next: inspect capture_operator_guide.md before operating the device. After capture, inspect capture_scenario_check.md, self_lifecycle_logcat_check.md, shuahuang_minimum_goal_check.md and regression_artifact_check.md first, then regression/summary.md, regression/capture_scenario_coverage.md, regression/replay_contract.md, regression/shuahuang_offline_replay.md, regression/daily_offline_replay.md, regression/mine_offline_replay.md, regression/full_offline_replay.md and regression/action_gate_readiness.md. captureScenarioRequiredReady=true now requires login/0x8004 role-resource evidence, generals/formations baseline evidence, self-app stop/logout lifecycle evidence, and brush-yellow native wrapper coverage for both 1520030 and 1522030, not just a generic wrapper sample. selfLifecycleLogcatReady=true means logcat contains explicit [self-lifecycle-json] task_stop and session_logout records with realActionNetworkAllowed=false. shuaHuangMinimumLiveEvidenceReady=true means the captured/base data proves the minimum brush-yellow evidence chain up to dry-run wrapper/action-response validation plus stop/logout lifecycle validation; shuaHuangMinimumFinalReady=false is expected while self-app real action sends remain disabled. offlineReplayReady=true is the loose log-sample indicator; shuaHuangOfflineReplayReady=true is the strict replay contract indicator; shuaHuangOfflineClosedLoopReplayReady=true means the captured/base data can replay the brush-yellow sequence offline; dailyOfflineClosedLoopReplayReady=true means one-click daily can replay offline in recovered order; mineOfflineClosedLoopReplayReady=true means 041542 mine search can replay and select a mine offline; fullOfflineReplayReady=true means brush-yellow, daily and mine replay suites are all green; dryRunActionEvidenceReady=true means wrapper/replay evidence is sufficient for dry-run audit only. None of these mean real action sends are enabled.
EOF

echo "Capture artifacts: $OUT_DIR"
