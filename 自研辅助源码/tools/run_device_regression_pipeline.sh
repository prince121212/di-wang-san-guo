#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG=""
MODE="spawn"
DURATION="120"
OUT_DIR="$ROOT/reports/device_protocol_$(date +%Y%m%d_%H%M%S)"
ACCOUNT_EXPORT=""
ACCOUNT_ID=""
ROLE_NAME=""
BASE_CHANNEL_EXTRA=""
MERGE_EXTRA=()
FRIDA_SCRIPT="$ROOT/../reverse_cases/apk/scripts/frida_native_session_trace_v2.js"
SELF_APK="$ROOT/app/build/outputs/apk/debug/app-debug.apk"
XIAOHUANG_APK="$ROOT/../小黄点辅助.apk"
GAME_APK="$ROOT/../三国·帝王联盟1.66.apk"
INCLUDE_VALUES="false"
SKIP_PREFLIGHT="false"
PROMOTE_CANONICAL="false"
ALLOW_PARTIAL_PROMOTION="false"
DRY_RUN="false"
RUN_SELF_SMOKE_FIRST="false"

usage() {
  cat <<EOF
Usage: $0 --package <android.package> [options]

One-command device regression pipeline:
  optional account export -> base_channel_extra -> capture -> artifact verification -> promotion -> overall readiness refresh.

Options:
  --package <pkg>             Target package for Frida capture. Required.
  --account-export <json>     LocalAccountRepository export/account/session/channelExtra JSON used to prepare base_channel_extra.
  --account-id <id>           Select account id from --account-export.
  --role-name <name>          Select role/monarch name from --account-export.
  --base-channel-extra <json> Use existing base_channel_extra JSON. If --account-export is set, generated base takes precedence.
  --merge-extra <json>        Merge additional channelExtra into generated base; can repeat.
  --mode spawn|attach         Frida capture mode. Default: spawn.
  --duration <seconds>        Capture duration. Default: 120.
  --out-dir <dir>             Capture output directory. Default: reports/device_protocol_<timestamp>.
  --frida-script <path>       Frida script. Default: reverse_cases/apk/scripts/frida_native_session_trace_v2.js.
  --self-apk <path>           Self-developed APK checked by preflight.
  --xiaohuang-apk <path>      小黄点 APK checked by preflight.
  --game-apk <path>           Game APK checked by preflight.
  --include-values            Keep raw wrapper values in offline reports. Isolated test accounts only.
  --skip-preflight            Forward --skip-preflight to capture script. Not recommended.
  --promote-canonical         After capture, promote verified artifacts to canonical top-level reports.
  --allow-partial-promotion   Allow canonical promotion even when evidence is incomplete. Debugging only.
  --run-self-smoke-first      Run device_smoke_test.sh before protocol capture to prove self-app stop/logout logcat markers.
  --dry-run                   Write pipeline plan and print commands without running capture/promote.
  -h, --help                  Show this help.

Safety:
  This pipeline captures logs and runs offline verification only. It never enables real action sends.
EOF
}

quote() { printf '%q' "$1"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --package) PKG="${2:-}"; shift 2 ;;
    --account-export) ACCOUNT_EXPORT="${2:-}"; shift 2 ;;
    --account-id) ACCOUNT_ID="${2:-}"; shift 2 ;;
    --role-name) ROLE_NAME="${2:-}"; shift 2 ;;
    --base-channel-extra) BASE_CHANNEL_EXTRA="${2:-}"; shift 2 ;;
    --merge-extra) MERGE_EXTRA+=("${2:-}"); shift 2 ;;
    --mode) MODE="${2:-}"; shift 2 ;;
    --duration) DURATION="${2:-}"; shift 2 ;;
    --out-dir) OUT_DIR="${2:-}"; shift 2 ;;
    --frida-script) FRIDA_SCRIPT="${2:-}"; shift 2 ;;
    --self-apk) SELF_APK="${2:-}"; shift 2 ;;
    --xiaohuang-apk) XIAOHUANG_APK="${2:-}"; shift 2 ;;
    --game-apk) GAME_APK="${2:-}"; shift 2 ;;
    --include-values) INCLUDE_VALUES="true"; shift ;;
    --skip-preflight) SKIP_PREFLIGHT="true"; shift ;;
    --promote-canonical) PROMOTE_CANONICAL="true"; shift ;;
    --allow-partial-promotion) ALLOW_PARTIAL_PROMOTION="true"; shift ;;
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
if [[ "$MODE" != "spawn" && "$MODE" != "attach" ]]; then
  echo "ERROR: --mode must be spawn or attach" >&2
  exit 64
fi
if ! [[ "$DURATION" =~ ^[0-9]+$ ]] || [[ "$DURATION" -lt 5 ]]; then
  echo "ERROR: --duration must be an integer >= 5" >&2
  exit 64
fi
if [[ -n "$ACCOUNT_EXPORT" && ! -f "$ACCOUNT_EXPORT" ]]; then
  echo "ERROR: --account-export not found: $ACCOUNT_EXPORT" >&2
  exit 66
fi
if [[ -n "$BASE_CHANNEL_EXTRA" && ! -f "$BASE_CHANNEL_EXTRA" ]]; then
  echo "ERROR: --base-channel-extra not found: $BASE_CHANNEL_EXTRA" >&2
  exit 66
fi
for item in ${MERGE_EXTRA[@]+"${MERGE_EXTRA[@]}"}; do
  if [[ ! -f "$item" ]]; then
    echo "ERROR: --merge-extra not found: $item" >&2
    exit 66
  fi
done

mkdir -p "$OUT_DIR"
PIPELINE_SUMMARY="$OUT_DIR/pipeline_summary.md"
PIPELINE_JSON="$OUT_DIR/pipeline_summary.json"
BASE_FOR_CAPTURE="$BASE_CHANNEL_EXTRA"
BASE_REPORT_JSON="$OUT_DIR/base_channel_extra_report.json"
BASE_REPORT_MD="$OUT_DIR/base_channel_extra_report.md"

PREPARE_CMD=()
if [[ -n "$ACCOUNT_EXPORT" ]]; then
  BASE_FOR_CAPTURE="$OUT_DIR/base_channel_extra.json"
  PREPARE_CMD=(python3 "$ROOT/tools/prepare_base_channel_extra.py" "$ACCOUNT_EXPORT" --out "$BASE_FOR_CAPTURE" --report-out "$BASE_REPORT_JSON" --markdown-out "$BASE_REPORT_MD")
  if [[ -n "$ACCOUNT_ID" ]]; then PREPARE_CMD+=(--account-id "$ACCOUNT_ID"); fi
  if [[ -n "$ROLE_NAME" ]]; then PREPARE_CMD+=(--role-name "$ROLE_NAME"); fi
  for item in ${MERGE_EXTRA[@]+"${MERGE_EXTRA[@]}"}; do PREPARE_CMD+=(--merge-extra "$item"); done
fi

CAPTURE_CMD=(bash "$ROOT/tools/capture_device_protocol_regression.sh" --package "$PKG" --mode "$MODE" --duration "$DURATION" --out-dir "$OUT_DIR" --frida-script "$FRIDA_SCRIPT" --self-apk "$SELF_APK" --xiaohuang-apk "$XIAOHUANG_APK" --game-apk "$GAME_APK")
if [[ -n "$BASE_FOR_CAPTURE" ]]; then CAPTURE_CMD+=(--base-channel-extra "$BASE_FOR_CAPTURE"); fi
if [[ "$INCLUDE_VALUES" == "true" ]]; then CAPTURE_CMD+=(--include-values); fi
if [[ "$SKIP_PREFLIGHT" == "true" ]]; then CAPTURE_CMD+=(--skip-preflight); fi

PROMOTE_CMD=(python3 "$ROOT/tools/promote_device_regression_capture.py" "$OUT_DIR" --reports-dir "$ROOT/reports" --out "$OUT_DIR/promotion.json" --markdown-out "$OUT_DIR/promotion.md")
if [[ "$PROMOTE_CANONICAL" == "true" ]]; then PROMOTE_CMD+=(--promote-canonical); fi
if [[ "$ALLOW_PARTIAL_PROMOTION" == "true" ]]; then PROMOTE_CMD+=(--allow-partial); fi

OVERALL_CMD=(python3 "$ROOT/tools/verify_overall_regression_readiness.py" --out "$ROOT/reports/overall_regression_readiness.json" --markdown-out "$ROOT/reports/overall_regression_readiness.md")
MIGRATION_CMD=(python3 "$ROOT/tools/verify_migration_goal_status.py" --out "$ROOT/reports/migration_goal_status.json" --markdown-out "$ROOT/reports/migration_goal_status.md")
SELF_SMOKE_CMD=(bash "$ROOT/tools/device_smoke_test.sh")

write_summary() {
  local status="$1"
  local shua_gate_json="$OUT_DIR/shuahuang_minimum_goal_check.json"
  local artifact_json="$OUT_DIR/regression_artifact_check.json"
  local shua_gate_ready="false"
  local shua_gate_final="false"
  local artifact_true_ready="false"
  if [[ -f "$shua_gate_json" ]]; then
    shua_gate_ready="$(python3 - "$shua_gate_json" <<'PY'
import json, sys
from pathlib import Path
d=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print('true' if d.get('summary', {}).get('shuaHuangMinimumLiveEvidenceReady') else 'false')
PY
)"
    shua_gate_final="$(python3 - "$shua_gate_json" <<'PY'
import json, sys
from pathlib import Path
d=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print('true' if d.get('summary', {}).get('shuaHuangMinimumFinalReady') else 'false')
PY
)"
  fi
  if [[ -f "$artifact_json" ]]; then
    artifact_true_ready="$(python3 - "$artifact_json" <<'PY'
import json, sys
from pathlib import Path
d=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print('true' if d.get('summary', {}).get('trueDeviceRegressionEvidenceReady') else 'false')
PY
)"
  fi
  {
    echo "# 设备回归一键管线"
    echo
    echo "## Summary"
    echo
    echo "- status: $status"
    echo "- package: $PKG"
    echo "- mode: $MODE"
    echo "- durationSeconds: $DURATION"
    echo "- outDir: $OUT_DIR"
    echo "- baseChannelExtra: ${BASE_FOR_CAPTURE:-<none>}"
    echo "- accountExport: ${ACCOUNT_EXPORT:-<none>}"
    echo "- promoteCanonical: $PROMOTE_CANONICAL"
    echo "- allowPartialPromotion: $ALLOW_PARTIAL_PROMOTION"
    echo "- includeValues: $INCLUDE_VALUES"
    echo "- skipPreflight: $SKIP_PREFLIGHT"
    echo "- runSelfSmokeFirst: $RUN_SELF_SMOKE_FIRST"
    echo "- dryRun: $DRY_RUN"
    echo "- realActionNetworkAllowed: false"
    echo "- realActionSendReady: false"
    echo "- shuaHuangMinimumLiveEvidenceReady: $shua_gate_ready"
    echo "- shuaHuangMinimumFinalReady: $shua_gate_final"
    echo "- trueDeviceRegressionEvidenceReady: $artifact_true_ready"
    echo
    echo "## Required gate outputs"
    echo
    echo "- shuahuangMinimumGoalCheckJson: $OUT_DIR/shuahuang_minimum_goal_check.json"
    echo "- shuahuangMinimumGoalCheckMarkdown: $OUT_DIR/shuahuang_minimum_goal_check.md"
    echo "- regressionArtifactCheckJson: $OUT_DIR/regression_artifact_check.json"
    echo "- regressionArtifactCheckMarkdown: $OUT_DIR/regression_artifact_check.md"
    echo
    echo "## Commands"
    echo
    if [[ ${#PREPARE_CMD[@]} -gt 0 ]]; then
      printf -- '- prepare: `'; printf '%s ' "${PREPARE_CMD[@]}"; printf '`\n'
    else
      echo "- prepare: <skipped>"
    fi
    if [[ "$RUN_SELF_SMOKE_FIRST" == "true" ]]; then
      printf -- '- selfSmoke: `'; printf '%s ' "${SELF_SMOKE_CMD[@]}"; printf '`\n'
    else
      echo "- selfSmoke: <skipped>"
    fi
    printf -- '- capture: `'; printf '%s ' "${CAPTURE_CMD[@]}"; printf '`\n'
    printf -- '- promote: `'; printf '%s ' "${PROMOTE_CMD[@]}"; printf '`\n'
    printf -- '- overall: `'; printf '%s ' "${OVERALL_CMD[@]}"; printf '`\n'
    printf -- '- migration: `'; printf '%s ' "${MIGRATION_CMD[@]}"; printf '`\n'
    echo
    echo "安全边界：该管线只组织采集和离线审计，不打开自研真实动作发送。"
  } > "$PIPELINE_SUMMARY"
  python3 - "$PIPELINE_JSON" <<PY
import json, sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
  "summary": {
    "status": "$status",
    "package": "$PKG",
    "mode": "$MODE",
    "durationSeconds": int("$DURATION"),
    "outDir": "$OUT_DIR",
    "baseChannelExtra": "${BASE_FOR_CAPTURE:-}",
    "accountExport": "${ACCOUNT_EXPORT:-}",
    "promoteCanonical": "$PROMOTE_CANONICAL" == "true",
    "allowPartialPromotion": "$ALLOW_PARTIAL_PROMOTION" == "true",
    "includeValues": "$INCLUDE_VALUES" == "true",
    "skipPreflight": "$SKIP_PREFLIGHT" == "true",
    "runSelfSmokeFirst": "$RUN_SELF_SMOKE_FIRST" == "true",
    "dryRun": "$DRY_RUN" == "true",
    "realActionNetworkAllowed": False,
    "realActionSendReady": False,
    "shuaHuangMinimumLiveEvidenceReady": "$shua_gate_ready" == "true",
    "shuaHuangMinimumFinalReady": "$shua_gate_final" == "true",
    "trueDeviceRegressionEvidenceReady": "$artifact_true_ready" == "true",
    "shuahuangMinimumGoalCheckJson": "$OUT_DIR/shuahuang_minimum_goal_check.json",
    "shuahuangMinimumGoalCheckMarkdown": "$OUT_DIR/shuahuang_minimum_goal_check.md",
    "regressionArtifactCheckJson": "$OUT_DIR/regression_artifact_check.json",
    "regressionArtifactCheckMarkdown": "$OUT_DIR/regression_artifact_check.md",
  }
}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

write_summary "planned"

if [[ "$DRY_RUN" == "true" ]]; then
  cat "$PIPELINE_SUMMARY"
  echo "Dry-run pipeline plan written: $PIPELINE_SUMMARY"
  exit 0
fi

if [[ ${#PREPARE_CMD[@]} -gt 0 ]]; then
  "${PREPARE_CMD[@]}"
fi
if [[ "$RUN_SELF_SMOKE_FIRST" == "true" ]]; then
  "${SELF_SMOKE_CMD[@]}"
fi
"${CAPTURE_CMD[@]}"
"${PROMOTE_CMD[@]}"
"${OVERALL_CMD[@]}"
"${MIGRATION_CMD[@]}"
write_summary "completed"
echo "Pipeline artifacts: $OUT_DIR"
