#!/usr/bin/env python3
"""Package device regression evidence into a reproducible ZIP archive.

This is an offline archival helper. Given either a capture root, a regression/ directory,
or no input (current reports/ only), it writes a ZIP with checksummed reports and a manifest.
Raw logs are excluded by default to avoid accidentally sharing sensitive wrapper/session data;
use --include-raw-logs explicitly for a full internal evidence bundle.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOOL_DIR = Path(__file__).resolve().parent
ROOT = TOOL_DIR.parent
VERIFY_ARTIFACTS_PATH = TOOL_DIR / "verify_device_regression_artifacts.py"
OVERALL_PATH = TOOL_DIR / "verify_overall_regression_readiness.py"

RAW_LOG_NAMES = {"frida.log", "logcat.txt", "device_combined.log"}
SENSITIVE_KEY_TOKENS = [
    "password", "token", "authorization", "cookie",
    "nativewrapperlx", "nativewrapperkey", "nativewrapperlb",
    "recoverednativelx", "recoverednativekey", "recoverednativelb",
    "derivednativewrapperlx", "derivednativewrapperkey", "derivednativewrapperlb",
    "nativewrappersession", "recoverednativesession", "helpclasssession",
    "nativewrapperpasscode", "recoverednativepasscode", "helpclasspasscode",
    "session", "passcode",
]
SENSITIVE_TEXT_RE = re.compile(
    r"(?P<key>nativeWrapper(?:Lx|Key|Lb|Session|PassCode)|"
    r"recoveredNative(?:Lx|Key|Lb|Session|PassCode)|"
    r"derivedNativeWrapper(?:Lx|Key|Lb)|helpClass(?:Session|PassCode|Key)|"
    r"tokenCiphertext|encryptedPassword|plainPassword|password|authorization|cookie|passCode|session)"
    r"(?P<sep>['\"]?\s*[:=]\s*['\"]?)(?P<value>[^,'\"\s}\]]+)",
    re.I,
)
CURRENT_REPORTS = [
    "migration_goal_status.json",
    "migration_goal_status.md",
    "overall_regression_readiness.json",
    "overall_regression_readiness.md",
    "device_regression_preflight.json",
    "device_regression_preflight.md",
    "device_regression_checklist.md",
    "device_capture_operator_guide_latest.md",
    "device_capture_operator_guide_unified_evidence.md",
    "replay_contract_report.json",
    "replay_contract_report.md",
    "full_offline_replay_report.json",
    "full_offline_replay_report.md",
    "daily_offline_replay_report.json",
    "daily_offline_replay_report.md",
    "daily_protocol_gate_evidence.md",
    "mine_offline_replay_report.json",
    "mine_offline_replay_report.md",
    "mine_readonly_selection_gate_evidence.md",
    "remaining_action_dryrun_payload_gate_evidence.json",
    "remaining_action_dryrun_payload_gate_evidence.md",
    "role_resource_general_parse_gate_evidence.md",
    "action_safety_invariants.json",
    "action_safety_invariants.md",
    "native_wrapper_positive_fixture_readiness_evidence.json",
    "native_wrapper_positive_fixture_readiness_evidence.md",
    "shuahuang_dispatch_evidence.md",
    "configured_target_selection_gate_evidence.md",
    "brush_yellow_dispatch_payload_gate_evidence.md",
    "shuahuang_minimum_closed_loop_acceptance.json",
    "shuahuang_minimum_closed_loop_acceptance.md",
    "shuahuang_capture_gate_tightening_evidence.md",
    "shuahuang_minimum_goal_gate_evidence.md",
    "shuahuang_minimum_goal_artifact_gate_evidence.md",
    "device_pipeline_shuahuang_gate_summary_evidence.md",
    "shuahuang_stop_logout_live_gate_evidence.md",
    "self_lifecycle_logcat_marker_evidence.md",
    "self_lifecycle_artifact_gate_evidence.md",
    "preflight_self_game_package_gate_evidence.md",
    "preflight_self_apk_freshness_gate_evidence.md",
    "preflight_self_apk_marker_gate_evidence.md",
]


def load_tool(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


artifact_verifier = load_tool(VERIFY_ARTIFACTS_PATH, "verify_device_regression_artifacts")
overall_tool = load_tool(OVERALL_PATH, "verify_overall_regression_readiness")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_sensitive_key(key: str) -> bool:
    normalized = "".join(ch for ch in key.lower() if ch.isalnum())
    return any(token in normalized for token in SENSITIVE_KEY_TOKENS)


def redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if is_sensitive_key(str(key)):
                out[key] = "<redacted>"
            else:
                out[key] = redact_json(item)
        return out
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    return value


def redact_text(text: str) -> str:
    return SENSITIVE_TEXT_RE.sub(lambda m: f"{m.group('key')}{m.group('sep')}<redacted>", text)


def archive_payload(src: Path, sanitize: bool) -> bytes:
    raw = src.read_bytes()
    if not sanitize:
        return raw
    if src.suffix.lower() == ".json":
        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
            return (json.dumps(redact_json(data), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        except Exception:
            pass
    if src.suffix.lower() in {".md", ".txt", ".log"}:
        return redact_text(raw.decode("utf-8", errors="replace")).encode("utf-8")
    return raw


def add_file(zf: zipfile.ZipFile, src: Path, arcname: str, entries: list[dict[str, Any]], sanitize: bool = False) -> None:
    if not src.exists() or not src.is_file():
        return
    payload = archive_payload(src, sanitize=sanitize)
    zf.writestr(arcname, payload)
    entries.append({
        "archivePath": arcname,
        "sourcePath": str(src),
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "sanitized": sanitize,
    })


def safe_load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def capture_paths(input_path: Path | None) -> tuple[Path | None, Path | None, dict[str, Any]]:
    if input_path is None:
        return None, None, {}
    verification = artifact_verifier.verify(input_path)
    regression_dir, capture_root = artifact_verifier.locate_regression_dir(input_path)
    return regression_dir, capture_root, verification


def package(
    input_path: Path | None,
    out: Path,
    reports_dir: Path,
    include_raw_logs: bool = False,
    include_sensitive_values: bool = False,
) -> dict[str, Any]:
    reports_dir = reports_dir.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    regression_dir, capture_root, verification = capture_paths(input_path)
    overall = overall_tool.audit(reports_dir.parent) if reports_dir.exists() else {}
    entries: list[dict[str, Any]] = []
    generated: dict[str, str] = {}

    manifest: dict[str, Any] = {
        "schema": "dwpm-device-regression-evidence-package-v1",
        "createdAtUtc": datetime.now(timezone.utc).isoformat(),
        "input": str(input_path.resolve()) if input_path else "",
        "reportsDir": str(reports_dir),
        "includeRawLogs": include_raw_logs,
        "includeSensitiveValues": include_sensitive_values,
        "realActionNetworkAllowed": False,
        "realActionSendReady": False,
        "artifactVerificationSummary": verification.get("summary", {}) if verification else {},
        "overallSummary": overall.get("summary", {}) if overall else {},
        "entries": entries,
    }

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Generated verification snapshots.
        if verification:
            generated["artifact_verification.json"] = json.dumps(verification, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            generated["artifact_verification.md"] = artifact_verifier.to_markdown(verification) + "\n"
        if overall:
            generated["overall_regression_readiness.current.json"] = json.dumps(overall, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            generated["overall_regression_readiness.current.md"] = overall_tool.to_markdown(overall) + "\n"
        for arcname, content in generated.items():
            payload = content.encode("utf-8")
            zf.writestr("generated/" + arcname, payload)
            entries.append({
                "archivePath": "generated/" + arcname,
                "sourcePath": "<generated>",
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            })

        # Current top-level reports, useful even before live capture.
        for name in CURRENT_REPORTS:
            add_file(zf, reports_dir / name, "current_reports/" + name, entries, sanitize=not include_sensitive_values)

        # Capture/regression artifacts when available.
        if regression_dir:
            for name in artifact_verifier.REGRESSION_REQUIRED:
                add_file(zf, regression_dir / name, "capture/regression/" + name, entries, sanitize=not include_sensitive_values)
        if capture_root:
            for name in artifact_verifier.CAPTURE_ROOT_EXPECTED:
                if name in RAW_LOG_NAMES and not include_raw_logs:
                    continue
                add_file(zf, capture_root / name, "capture/" + name, entries, sanitize=not include_sensitive_values)
            # Pipeline/wait/promotion summaries are optional but useful.
            for name in [
                "pipeline_summary.md", "pipeline_summary.json",
                "promotion.md", "promotion.json",
                "wait_for_device_summary.md", "wait_for_device_summary.json",
                "wait_preflight_latest.md", "wait_preflight_latest.json",
                "regression_artifact_check.md", "regression_artifact_check.json",
            ]:
                add_file(zf, capture_root / name, "capture/" + name, entries, sanitize=not include_sensitive_values)

        summary_lines = [
            "# 设备回归证据包",
            "",
            "## Summary",
            "",
            f"- input: {manifest['input'] or '<current reports only>'}",
            f"- includeRawLogs: {str(include_raw_logs).lower()}",
            f"- includeSensitiveValues: {str(include_sensitive_values).lower()}",
            f"- realActionNetworkAllowed: false",
            f"- realActionSendReady: false",
            f"- entryCount: {len(entries)}",
            f"- artifactTrueDeviceRegressionEvidenceReady: {str(manifest['artifactVerificationSummary'].get('trueDeviceRegressionEvidenceReady', False)).lower()}",
            f"- overallTrueDeviceRegressionReady: {str(manifest['overallSummary'].get('trueDeviceRegressionReady', False)).lower()}",
            "",
            "说明：该 ZIP 只归档本地采集/离线审计证据，不表示真实动作发送已启用。",
        ]
        summary_payload = ("\n".join(summary_lines) + "\n").encode("utf-8")
        zf.writestr("SUMMARY.md", summary_payload)
        entries.append({
            "archivePath": "SUMMARY.md",
            "sourcePath": "<generated>",
            "size": len(summary_payload),
            "sha256": hashlib.sha256(summary_payload).hexdigest(),
        })
        manifest_payload = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        zf.writestr("manifest.json", manifest_payload)
        entries.append({
            "archivePath": "manifest.json",
            "sourcePath": "<generated>",
            "size": len(manifest_payload),
            "sha256": hashlib.sha256(manifest_payload).hexdigest(),
        })

    return {
        "summary": {
            "packagePath": str(out),
            "input": manifest["input"],
            "includeRawLogs": include_raw_logs,
            "includeSensitiveValues": include_sensitive_values,
            "entryCount": len(entries),
            "realActionNetworkAllowed": False,
            "realActionSendReady": False,
            "artifactTrueDeviceRegressionEvidenceReady": bool(manifest["artifactVerificationSummary"].get("trueDeviceRegressionEvidenceReady", False)),
            "overallTrueDeviceRegressionReady": bool(manifest["overallSummary"].get("trueDeviceRegressionReady", False)),
        },
        "manifest": manifest,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", help="Optional capture root or regression/ directory. If omitted, packages current reports only.")
    ap.add_argument("--out", default=str(ROOT / "reports" / "device_regression_evidence_package.zip"))
    ap.add_argument("--reports-dir", default=str(ROOT / "reports"))
    ap.add_argument("--include-raw-logs", action="store_true", help="Include frida.log/logcat.txt/device_combined.log; may contain sensitive test-account data")
    ap.add_argument("--include-sensitive-values", action="store_true", help="Disable default redaction for channelExtra/native/session fields; internal use only")
    ap.add_argument("--summary-out", help="Optional JSON summary output")
    ns = ap.parse_args()
    report = package(
        Path(ns.input) if ns.input else None,
        Path(ns.out),
        Path(ns.reports_dir),
        include_raw_logs=ns.include_raw_logs,
        include_sensitive_values=ns.include_sensitive_values,
    )
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.summary_out:
        Path(ns.summary_out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)


if __name__ == "__main__":
    main()
