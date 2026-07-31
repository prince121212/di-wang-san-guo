#!/usr/bin/env python3
"""Static safety invariant verifier for action/network send gates.

This verifier is intentionally conservative and offline-only. Its default mode checks that
production source files do not hard-code obvious `...Allowed=true` / `...SendReady=true`
literals for real action/network gates. Historical evidence JSON may truthfully record an
explicitly authorized run with those gates enabled, so report scanning is opt-in via
`--json-dir`.

It is not a substitute for code review or device regression; it is a regression tripwire.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

UNSAFE_KEYS = {
    "realActionNetworkAllowed",
    "networkSendAllowed",
    "realActionSendReady",
    "actionSendReady",
}
SOURCE_SUFFIXES = {".kt", ".java", ".py", ".sh"}
DEFAULT_SOURCE_DIRS = ["app/src/main", "tools"]
DEFAULT_JSON_DIRS: list[str] = []

SOURCE_TRUE_PATTERNS = [
    re.compile(r"\b(realActionNetworkAllowed|networkSendAllowed|realActionSendReady|actionSendReady)\b\s*[:=]\s*(true|True)\b"),
    re.compile(r"[\"'](realActionNetworkAllowed|networkSendAllowed|realActionSendReady|actionSendReady)[\"']\s*[:=]\s*(true|True)\b"),
    re.compile(r"\b(realActionNetworkAllowed|networkSendAllowed|realActionSendReady|actionSendReady)=true\b", re.I),
]


def is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    if isinstance(value, (int, float)):
        return value != 0
    return False


def should_scan_source(path: Path) -> bool:
    if path.suffix not in SOURCE_SUFFIXES:
        return False
    name = path.name
    if name.startswith("test_") or name.endswith("Test.kt") or name.endswith("Test.java"):
        return False
    if name == "verify_action_safety_invariants.py":
        return False
    parts = set(path.parts)
    if "build" in parts or ".gradle" in parts:
        return False
    return True


def scan_source_file(path: Path, root: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    violations: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            continue
        # User-facing guidance can explain that an authorized run needs `gate=true`;
        # a returned string is not a source assignment or an enabled default.
        if re.match(r"^return\s+[furbFURB]*[\"']", stripped):
            continue
        # Diagnostic strings such as safety_violations.append("...=true") are expected
        # in verifier code; they are not assignments or output claims.
        if "append(" in line and ("violation" in line.lower() or "missing" in line.lower()):
            continue
        for pattern in SOURCE_TRUE_PATTERNS:
            match = pattern.search(line)
            if match:
                violations.append({
                    "file": str(path.relative_to(root)),
                    "line": line_no,
                    "key": match.group(1),
                    "text": stripped[:240],
                })
                break
    return violations


def iter_files(root: Path, rel_dirs: list[str], suffixes: set[str] | None = None) -> list[Path]:
    files: list[Path] = []
    for rel in rel_dirs:
        base = root / rel
        if not base.exists():
            continue
        if base.is_file():
            if suffixes is None or base.suffix in suffixes:
                files.append(base)
            continue
        for path in base.rglob("*"):
            if path.is_file() and (suffixes is None or path.suffix in suffixes):
                files.append(path)
    return sorted(files)


def scan_sources(root: Path, rel_dirs: list[str]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for path in iter_files(root, rel_dirs, SOURCE_SUFFIXES):
        if should_scan_source(path):
            violations.extend(scan_source_file(path, root))
    return violations


def scan_json_value(value: Any, file_rel: str, json_path: str = "$") -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{json_path}.{key}"
            if key in UNSAFE_KEYS and is_truthy(child):
                violations.append({"file": file_rel, "path": child_path, "key": key, "value": child})
            violations.extend(scan_json_value(child, file_rel, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(scan_json_value(child, file_rel, f"{json_path}[{index}]"))
    return violations


def scan_json_reports(root: Path, rel_dirs: list[str]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for path in iter_files(root, rel_dirs, {".json"}):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            violations.append({"file": str(path.relative_to(root)), "path": "$", "key": "jsonParseError", "value": str(exc)})
            continue
        violations.extend(scan_json_value(data, str(path.relative_to(root))))
    return violations


def verify(root: Path, source_dirs: list[str] | None = None, json_dirs: list[str] | None = None) -> dict[str, Any]:
    root = root.resolve()
    source_dirs = source_dirs or DEFAULT_SOURCE_DIRS
    json_dirs = json_dirs or DEFAULT_JSON_DIRS
    source_violations = scan_sources(root, source_dirs)
    json_violations = scan_json_reports(root, json_dirs)
    ready = not source_violations and not json_violations
    return {
        "summary": {
            "actionSafetyInvariantReady": ready,
            "sourceViolationCount": len(source_violations),
            "jsonViolationCount": len(json_violations),
            "scannedSourceDirs": source_dirs,
            "scannedJsonDirs": json_dirs,
            "realActionNetworkAllowed": False,
            "blocker": "static source invariant only; historical authorized action evidence is not scanned by default",
        },
        "sourceViolations": source_violations,
        "jsonViolations": json_violations,
    }


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# Action Safety Invariants 静态审计",
        "",
        "## Summary",
        "",
        f"- actionSafetyInvariantReady: {str(s['actionSafetyInvariantReady']).lower()}",
        f"- sourceViolationCount: {s['sourceViolationCount']}",
        f"- jsonViolationCount: {s['jsonViolationCount']}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## Source violations",
        "",
        "```json",
        json.dumps(report["sourceViolations"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## JSON report violations",
        "",
        "```json",
        json.dumps(report["jsonViolations"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--source-dir", action="append", default=[], help="Source dir/file relative to root; can repeat")
    ap.add_argument("--json-dir", action="append", default=[], help="JSON report dir/file relative to root; can repeat")
    ap.add_argument("--out")
    ap.add_argument("--markdown-out")
    ns = ap.parse_args()
    report = verify(
        Path(ns.root),
        source_dirs=ns.source_dir or None,
        json_dirs=ns.json_dir or None,
    )
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
