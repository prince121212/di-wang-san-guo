#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG=""
TIMEOUT="600"
INTERVAL="5"
OUT_DIR="$ROOT/reports/device_protocol_$(date +%Y%m%d_%H%M%S)"
MODE="spawn"
DURATION="120"
BASE_CHANNEL_EXTRA=""
ACCOUNT_EXPORT=""
ACCOUNT_ID=""
ROLE_NAME=""
PROMOTE_CANONICAL="false"
INCLUDE_VALUES="false"
DRY_RUN="false"
RUN_SELF_SMOKE_FIRST="false"
FRIDA_SCRIPT="$ROOT/../reverse_cases/apk/scripts/frida_native_session_trace_v2.js"
SELF_APK="$ROOT/app/build/outputs/apk/debug/app-debug.apk"
XIAOHUANG_APK="$ROOT/../小黄点辅助.apk"
GAME_APK="$ROOT/../三国·帝王联盟1.66.apk"
ADB_BIN="${ADB_BIN:-adb}"
FRIDA_BIN="${FRIDA_BIN:-frida}"
FRIDA_PS_BIN="${FRIDA_PS_BIN:-frida-ps}"

usage() {
  cat <<EOF
Usage: $0 --package <android.package> [options]

Wait until device regression preflight is ready, then run run_device_regression_pipeline.sh.
This is a convenience wrapper for the device-plug-in moment; it captures logs and runs
offline verification only, and never enables real action sends.

Options:
  --package <pkg>             Target package. Required.
  --timeout <seconds>         Max wait time. Default: 600.
  --interval <seconds>        Poll interval. Default: 5.
  --out-dir <dir>             Pipeline output dir. Default: reports/device_protocol_<timestamp>.
  --mode spawn|attach         Frida mode. Default: spawn.
  --duration <seconds>        Capture duration once preflight is ready. Default: 120.
  --base-channel-extra <json> Existing base_channel_extra JSON.
  --account-export <json>     Account export used by pipeline to prepare base_channel_extra.
  --account-id <id>           Select account id for --account-export.
  --role-name <name>          Select role name for --account-export.
  --frida-script <path>       Frida script passed to preflight and pipeline.
  --self-apk <path>           Self APK checked by preflight.
  --xiaohuang-apk <path>      小黄点 APK checked by preflight.
  --game-apk <path>           Game APK checked by preflight.
  --include-values            Keep raw wrapper values in offline reports. Isolated accounts only.
  --promote-canonical         Request canonical promotion after capture.
  --run-self-smoke-first      Ask pipeline to run self-app smoke before protocol capture.
  --dry-run                   Print/write plan; do not wait, preflight, or capture.
  -h, --help                  Show this help.

Environment overrides: ADB_BIN, FRIDA_BIN, FRIDA_PS_BIN.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --package) PKG="${2:-}"; shift 2 ;;
    --timeout) TIMEOUT="${2:-}"; shift 2 ;;
    --interval) INTERVAL="${2:-}"; shift 2 ;;
    --out-dir) OUT_DIR="${2:-}"; shift 2 ;;
    --mode) MODE="${2:-}"; shift 2 ;;
    --duration) DURATION="${2:-}"; shift 2 ;;
    --base-channel-extra) BASE_CHANNEL_EXTRA="${2:-}"; shift 2 ;;
    --account-export) ACCOUNT_EXPORT="${2:-}"; shift 2 ;;
    --account-id) ACCOUNT_ID="${2:-}"; shift 2 ;;
    --role-name) ROLE_NAME="${2:-}"; shift 2 ;;
    --frida-script) FRIDA_SCRIPT="${2:-}"; shift 2 ;;
    --self-apk) SELF_APK="${2:-}"; shift 2 ;;
    --xiaohuang-apk) XIAOHUANG_APK="${2:-}"; shift 2 ;;
    --game-apk) GAME_APK="${2:-}"; shift 2 ;;
    --include-values) INCLUDE_VALUES="true"; shift ;;
    --promote-canonical) PROMOTE_CANONICAL="true"; shift ;;
    --run-self-smoke-first) RUN_SELF_SMOKE_FIRST="true"; shift ;;
    --dry-run) DRY_RUN="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 64 ;;
  esac
done

if [[ -z "$PKG" ]]; then
  echo "ERROR: --package is required" >&2
  usage >&2
  exit 64
fi
if ! [[ "$TIMEOUT" =~ ^[0-9]+$ ]] || [[ "$TIMEOUT" -lt 1 ]]; then
  echo "ERROR: --timeout must be an integer >= 1" >&2
  exit 64
fi
if ! [[ "$INTERVAL" =~ ^[0-9]+$ ]] || [[ "$INTERVAL" -lt 1 ]]; then
  echo "ERROR: --interval must be an integer >= 1" >&2
  exit 64
fi
if ! [[ "$DURATION" =~ ^[0-9]+$ ]] || [[ "$DURATION" -lt 5 ]]; then
  echo "ERROR: --duration must be an integer >= 5" >&2
  exit 64
fi

mkdir -p "$OUT_DIR"
WAIT_JSON="$OUT_DIR/wait_for_device_summary.json"
WAIT_MD="$OUT_DIR/wait_for_device_summary.md"
PREFLIGHT_JSON="$OUT_DIR/wait_preflight_latest.json"
PREFLIGHT_MD="$OUT_DIR/wait_preflight_latest.md"

PIPELINE_CMD=(bash "$ROOT/tools/run_device_regression_pipeline.sh" --package "$PKG" --mode "$MODE" --duration "$DURATION" --out-dir "$OUT_DIR" --frida-script "$FRIDA_SCRIPT" --self-apk "$SELF_APK" --xiaohuang-apk "$XIAOHUANG_APK" --game-apk "$GAME_APK")
if [[ -n "$BASE_CHANNEL_EXTRA" ]]; then PIPELINE_CMD+=(--base-channel-extra "$BASE_CHANNEL_EXTRA"); fi
if [[ -n "$ACCOUNT_EXPORT" ]]; then PIPELINE_CMD+=(--account-export "$ACCOUNT_EXPORT"); fi
if [[ -n "$ACCOUNT_ID" ]]; then PIPELINE_CMD+=(--account-id "$ACCOUNT_ID"); fi
if [[ -n "$ROLE_NAME" ]]; then PIPELINE_CMD+=(--role-name "$ROLE_NAME"); fi
if [[ "$INCLUDE_VALUES" == "true" ]]; then PIPELINE_CMD+=(--include-values); fi
if [[ "$PROMOTE_CANONICAL" == "true" ]]; then PIPELINE_CMD+=(--promote-canonical); fi
if [[ "$RUN_SELF_SMOKE_FIRST" == "true" ]]; then PIPELINE_CMD+=(--run-self-smoke-first); fi

write_wait_report() {
  local status="$1"
  local ready="$2"
  local attempts="$3"
  local pipeline_json="$OUT_DIR/pipeline_summary.json"
  local shua_gate_ready="false"
  local true_device_ready="false"
  if [[ -f "$pipeline_json" ]]; then
    shua_gate_ready="$(python3 - "$pipeline_json" <<'PY'
import json, sys
from pathlib import Path
d=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print('true' if d.get('summary', {}).get('shuaHuangMinimumLiveEvidenceReady') else 'false')
PY
)"
    true_device_ready="$(python3 - "$pipeline_json" <<'PY'
import json, sys
from pathlib import Path
d=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print('true' if d.get('summary', {}).get('trueDeviceRegressionEvidenceReady') else 'false')
PY
)"
  fi
  {
    echo "# 等待设备并运行回归管线"
    echo
    echo "## Summary"
    echo
    echo "- status: $status"
    echo "- preflightReady: $ready"
    echo "- attempts: $attempts"
    echo "- timeoutSeconds: $TIMEOUT"
    echo "- intervalSeconds: $INTERVAL"
    echo "- outDir: $OUT_DIR"
    echo "- package: $PKG"
    echo "- realActionNetworkAllowed: false"
    echo "- realActionSendReady: false"
    echo "- shuaHuangMinimumLiveEvidenceReady: $shua_gate_ready"
    echo "- trueDeviceRegressionEvidenceReady: $true_device_ready"
    echo "- runSelfSmokeFirst: $RUN_SELF_SMOKE_FIRST"
    echo
    echo "## Required gate outputs after pipeline"
    echo
    echo "- shuahuangMinimumGoalCheck: $OUT_DIR/shuahuang_minimum_goal_check.md"
    echo "- regressionArtifactCheck: $OUT_DIR/regression_artifact_check.md"
    echo "- pipelineSummary: $OUT_DIR/pipeline_summary.md"
    echo
    echo "## Pipeline command"
    echo
    printf '`'; printf '%s ' "${PIPELINE_CMD[@]}"; printf '`\n'
    echo
    echo "安全边界：该脚本只等待 preflight 就绪并调用日志采集/离线审计管线，不打开真实动作发送。"
  } > "$WAIT_MD"
  python3 - "$WAIT_JSON" <<PY
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
  "summary": {
    "status": "$status",
    "preflightReady": "$ready" == "true",
    "attempts": int("$attempts"),
    "timeoutSeconds": int("$TIMEOUT"),
    "intervalSeconds": int("$INTERVAL"),
    "outDir": "$OUT_DIR",
    "package": "$PKG",
    "realActionNetworkAllowed": False,
    "realActionSendReady": False,
    "runSelfSmokeFirst": "$RUN_SELF_SMOKE_FIRST" == "true",
    "shuaHuangMinimumLiveEvidenceReady": "$shua_gate_ready" == "true",
    "trueDeviceRegressionEvidenceReady": "$true_device_ready" == "true",
    "shuahuangMinimumGoalCheckMarkdown": "$OUT_DIR/shuahuang_minimum_goal_check.md",
    "regressionArtifactCheckMarkdown": "$OUT_DIR/regression_artifact_check.md",
    "pipelineSummaryMarkdown": "$OUT_DIR/pipeline_summary.md",
  }
}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

if [[ "$DRY_RUN" == "true" ]]; then
  write_wait_report "planned" "false" "0"
  cat "$WAIT_MD"
  exit 0
fi

start_epoch="$(date +%s)"
attempts=0
while true; do
  attempts=$((attempts + 1))
  PREFLIGHT_CMD=(python3 "$ROOT/tools/check_device_regression_preflight.py"
    --adb-bin "$ADB_BIN"
    --frida-bin "$FRIDA_BIN"
    --frida-ps-bin "$FRIDA_PS_BIN"
    --package "$PKG"
    --self-apk "$SELF_APK"
    --xiaohuang-apk "$XIAOHUANG_APK"
    --game-apk "$GAME_APK"
    --frida-script "$FRIDA_SCRIPT"
    --out "$PREFLIGHT_JSON"
    --markdown-out "$PREFLIGHT_MD")
  if [[ -n "$BASE_CHANNEL_EXTRA" ]]; then PREFLIGHT_CMD+=(--base-channel-extra "$BASE_CHANNEL_EXTRA"); fi
  "${PREFLIGHT_CMD[@]}" >/dev/null
  ready="$(python3 - "$PREFLIGHT_JSON" <<'PY'
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print('true' if data.get('summary', {}).get('preflightReady') else 'false')
PY
)"
  if [[ "$ready" == "true" ]]; then
    write_wait_report "preflight-ready-running-pipeline" "true" "$attempts"
    "${PIPELINE_CMD[@]}"
    write_wait_report "completed" "true" "$attempts"
    exit 0
  fi
  now="$(date +%s)"
  elapsed=$((now - start_epoch))
  if [[ "$elapsed" -ge "$TIMEOUT" ]]; then
    write_wait_report "timeout" "false" "$attempts"
    echo "ERROR: preflight did not become ready within ${TIMEOUT}s. See $PREFLIGHT_MD" >&2
    exit 69
  fi
  sleep "$INTERVAL"
done
