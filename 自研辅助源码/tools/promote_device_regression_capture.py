#!/usr/bin/env python3
"""Promote a verified device protocol capture into canonical reports.

This tool bridges capture_device_protocol_regression.sh outputs and the top-level
readiness dashboard. It is offline-only: it verifies files already captured on disk,
then writes auditable latest_* reports. Canonical report promotion is intentionally gated
behind --promote-canonical and requires trueDeviceRegressionEvidenceReady unless
--allow-partial is provided for debugging.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

TOOL_DIR = Path(__file__).resolve().parent
ROOT = TOOL_DIR.parent
VERIFY_ARTIFACTS_PATH = TOOL_DIR / "verify_device_regression_artifacts.py"
OVERALL_PATH = TOOL_DIR / "verify_overall_regression_readiness.py"


def load_tool(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


artifact_verifier = load_tool(VERIFY_ARTIFACTS_PATH, "verify_device_regression_artifacts")
overall = load_tool(OVERALL_PATH, "verify_overall_regression_readiness")


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain JSON object")
    return data


def regression_and_capture_dirs(input_path: Path) -> tuple[Path, Path | None]:
    return artifact_verifier.locate_regression_dir(input_path)


def copy_if_exists(src: Path, dst: Path, copied: list[dict[str, str]]) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    copied.append({"from": str(src), "to": str(dst)})


def promote(
    input_path: Path,
    reports_dir: Path,
    promote_canonical: bool = False,
    allow_partial: bool = False,
) -> dict[str, Any]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    verification = artifact_verifier.verify(input_path)
    regression_dir, capture_root = regression_and_capture_dirs(input_path)
    evidence_ready = bool(verification["summary"].get("trueDeviceRegressionEvidenceReady"))
    copied: list[dict[str, str]] = []

    latest_json = reports_dir / "latest_device_regression_artifact_check.json"
    latest_md = reports_dir / "latest_device_regression_artifact_check.md"
    latest_json.write_text(json.dumps(verification, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    latest_md.write_text(artifact_verifier.to_markdown(verification) + "\n", encoding="utf-8")
    copied.append({"from": "<generated verification>", "to": str(latest_json)})
    copied.append({"from": "<generated verification>", "to": str(latest_md)})

    # Always keep latest capture reports under non-canonical names for inspection.
    latest_pairs = [
        (regression_dir / "device_regression_report.json", reports_dir / "latest_device_regression_report.json"),
        (regression_dir / "summary.md", reports_dir / "latest_device_regression_summary.md"),
        (regression_dir / "full_offline_replay.json", reports_dir / "latest_device_full_offline_replay.json"),
        (regression_dir / "full_offline_replay.md", reports_dir / "latest_device_full_offline_replay.md"),
        (regression_dir / "action_gate_readiness.json", reports_dir / "latest_device_action_gate_readiness.json"),
        (regression_dir / "action_gate_readiness.md", reports_dir / "latest_device_action_gate_readiness.md"),
        (regression_dir / "merged_channel_extra.json", reports_dir / "latest_device_merged_channel_extra.json"),
    ]
    if capture_root:
        latest_pairs.extend([
            (capture_root / "preflight.json", reports_dir / "latest_device_preflight.json"),
            (capture_root / "preflight.md", reports_dir / "latest_device_preflight.md"),
            (capture_root / "capture_scenario_check.json", reports_dir / "latest_device_capture_scenario_check.json"),
            (capture_root / "capture_scenario_check.md", reports_dir / "latest_device_capture_scenario_check.md"),
            (capture_root / "self_lifecycle_logcat_check.json", reports_dir / "latest_device_self_lifecycle_logcat_check.json"),
            (capture_root / "self_lifecycle_logcat_check.md", reports_dir / "latest_device_self_lifecycle_logcat_check.md"),
            (capture_root / "shuahuang_minimum_goal_check.json", reports_dir / "latest_device_shuahuang_minimum_goal_check.json"),
            (capture_root / "shuahuang_minimum_goal_check.md", reports_dir / "latest_device_shuahuang_minimum_goal_check.md"),
        ])
    for src, dst in latest_pairs:
        copy_if_exists(src, dst, copied)

    canonical_promoted = False
    canonical_blocker = ""
    if promote_canonical:
        if not evidence_ready and not allow_partial:
            canonical_blocker = "canonical promotion refused: trueDeviceRegressionEvidenceReady=false; rerun with --allow-partial only for debugging"
        else:
            canonical_pairs = [
                (regression_dir / "full_offline_replay.json", reports_dir / "full_offline_replay_report.json"),
                (regression_dir / "full_offline_replay.md", reports_dir / "full_offline_replay_report.md"),
                (regression_dir / "action_gate_readiness.json", reports_dir / "action_gate_readiness.json"),
                (regression_dir / "action_gate_readiness.md", reports_dir / "action_gate_readiness.md"),
                (regression_dir / "device_regression_report.json", reports_dir / "device_regression_report.json"),
            ]
            if capture_root:
                canonical_pairs.extend([
                    (capture_root / "preflight.json", reports_dir / "device_regression_preflight.json"),
                    (capture_root / "preflight.md", reports_dir / "device_regression_preflight.md"),
                    (capture_root / "capture_scenario_check.json", reports_dir / "device_capture_scenario_check.json"),
                    (capture_root / "capture_scenario_check.md", reports_dir / "device_capture_scenario_check.md"),
                    (capture_root / "self_lifecycle_logcat_check.json", reports_dir / "device_self_lifecycle_logcat_check.json"),
                    (capture_root / "self_lifecycle_logcat_check.md", reports_dir / "device_self_lifecycle_logcat_check.md"),
                    (capture_root / "shuahuang_minimum_goal_check.json", reports_dir / "device_shuahuang_minimum_goal_check.json"),
                    (capture_root / "shuahuang_minimum_goal_check.md", reports_dir / "device_shuahuang_minimum_goal_check.md"),
                ])
            for src, dst in canonical_pairs:
                copy_if_exists(src, dst, copied)
            canonical_promoted = True

    # Recompute overall after optional promotion. This does not mark final migration complete
    # unless migration_goal_status.json already proves it.
    overall_report = overall.audit(reports_dir.parent)
    summary = {
        "input": str(input_path),
        "reportsDir": str(reports_dir),
        "captureRoot": str(capture_root) if capture_root else "",
        "regressionDir": str(regression_dir),
        "latestReportsWritten": True,
        "canonicalPromoteRequested": promote_canonical,
        "canonicalPromoted": canonical_promoted,
        "allowPartial": allow_partial,
        "trueDeviceRegressionEvidenceReady": evidence_ready,
        "overallTrueDeviceRegressionReadyAfterPromotion": bool(overall_report["summary"].get("trueDeviceRegressionReady")),
        "overallDryRunActionEvidenceReadyAfterPromotion": bool(overall_report["summary"].get("dryRunActionEvidenceReady")),
        "realActionNetworkAllowed": False,
        "realActionSendReady": False,
        "canonicalBlocker": canonical_blocker,
        "blocker": "promotion only imports verified local evidence; real action send remains disabled",
    }
    result = {
        "summary": summary,
        "copied": copied,
        "artifactVerification": verification,
        "overallAfterPromotion": overall_report,
    }
    (reports_dir / "latest_device_regression_promotion.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (reports_dir / "latest_device_regression_promotion.md").write_text(to_markdown(result) + "\n", encoding="utf-8")
    return result


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 设备回归采集产物导入报告",
        "",
        "## Summary",
        "",
        f"- input: {s['input']}",
        f"- latestReportsWritten: {str(s['latestReportsWritten']).lower()}",
        f"- canonicalPromoteRequested: {str(s['canonicalPromoteRequested']).lower()}",
        f"- canonicalPromoted: {str(s['canonicalPromoted']).lower()}",
        f"- allowPartial: {str(s['allowPartial']).lower()}",
        f"- trueDeviceRegressionEvidenceReady: {str(s['trueDeviceRegressionEvidenceReady']).lower()}",
        f"- overallDryRunActionEvidenceReadyAfterPromotion: {str(s['overallDryRunActionEvidenceReadyAfterPromotion']).lower()}",
        f"- overallTrueDeviceRegressionReadyAfterPromotion: {str(s['overallTrueDeviceRegressionReadyAfterPromotion']).lower()}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- realActionSendReady: {str(s['realActionSendReady']).lower()}",
        f"- canonicalBlocker: {s['canonicalBlocker']}",
        f"- blocker: {s['blocker']}",
        "",
        "## Copied files",
        "",
        "```json",
        json.dumps(report.get("copied", []), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Artifact verification summary",
        "",
        "```json",
        json.dumps(report["artifactVerification"].get("summary", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Overall summary after promotion",
        "",
        "```json",
        json.dumps(report["overallAfterPromotion"].get("summary", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="capture root or regression directory produced by capture_device_protocol_regression.sh")
    ap.add_argument("--reports-dir", default=str(ROOT / "reports"), help="Reports directory to write latest/promoted reports")
    ap.add_argument("--promote-canonical", action="store_true", help="Copy verified capture outputs to canonical report filenames")
    ap.add_argument("--allow-partial", action="store_true", help="Allow canonical promotion even when artifact evidence is incomplete; debugging only")
    ap.add_argument("--out", help="Optional JSON output path; latest_device_regression_promotion.json is always written to reports-dir")
    ap.add_argument("--markdown-out", help="Optional Markdown output path; latest_device_regression_promotion.md is always written to reports-dir")
    ns = ap.parse_args()
    report = promote(Path(ns.input), Path(ns.reports_dir), promote_canonical=ns.promote_canonical, allow_partial=ns.allow_partial)
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
