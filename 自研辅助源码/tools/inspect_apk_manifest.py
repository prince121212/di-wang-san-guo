#!/usr/bin/env python3
"""Inspect APK manifest package and launch activity for regression setup.

Uses `apkanalyzer manifest print` when available. This is read-only and does not install or
run the APK.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ANDROID_NS = "http://schemas.android.com/apk/res/android"
DEFAULT_JAVA_HOME = "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"


def ensure_java_env(env: dict[str, str]) -> dict[str, str]:
    out = dict(env)
    if not out.get("JAVA_HOME") and Path(DEFAULT_JAVA_HOME).exists():
        out["JAVA_HOME"] = DEFAULT_JAVA_HOME
        out["PATH"] = str(Path(DEFAULT_JAVA_HOME) / "bin") + os.pathsep + out.get("PATH", "")
    return out


def run_apkanalyzer(apk: Path, apkanalyzer: str = "apkanalyzer") -> str:
    exe = shutil.which(apkanalyzer) or apkanalyzer
    if not exe or (os.sep in exe and not Path(exe).exists()):
        raise FileNotFoundError("apkanalyzer not found")
    proc = subprocess.run(
        [exe, "manifest", "print", str(apk)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=ensure_java_env(os.environ),
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout.strip())
    return proc.stdout


def attr(element: ET.Element, name: str) -> str:
    return element.attrib.get(f"{{{ANDROID_NS}}}{name}") or element.attrib.get(f"android:{name}") or element.attrib.get(name, "")


def normalize_component(package: str, name: str) -> str:
    if not name:
        return ""
    if name.startswith("."):
        return package + name
    if "." not in name:
        return package + "." + name
    return name


def parse_manifest(xml_text: str) -> dict[str, Any]:
    root = ET.fromstring(xml_text)
    package = root.attrib.get("package", "")
    application = root.find("application")
    activities = []
    services = []
    receivers = []
    launch_activity = ""
    if application is not None:
        for activity in application.findall("activity") + application.findall("activity-alias"):
            name = normalize_component(package, attr(activity, "name"))
            actions = []
            categories = []
            for filt in activity.findall("intent-filter"):
                actions.extend(attr(a, "name") for a in filt.findall("action"))
                categories.extend(attr(c, "name") for c in filt.findall("category"))
            item = {"name": name, "exported": attr(activity, "exported"), "actions": [x for x in actions if x], "categories": [x for x in categories if x]}
            activities.append(item)
            if "android.intent.action.MAIN" in item["actions"] and "android.intent.category.LAUNCHER" in item["categories"] and not launch_activity:
                launch_activity = name
        for service in application.findall("service"):
            services.append({"name": normalize_component(package, attr(service, "name")), "exported": attr(service, "exported")})
        for receiver in application.findall("receiver"):
            receivers.append({"name": normalize_component(package, attr(receiver, "name")), "exported": attr(receiver, "exported")})
    permissions = [attr(p, "name") for p in root.findall("uses-permission") if attr(p, "name")]
    return {
        "package": package,
        "versionCode": attr(root, "versionCode"),
        "versionName": attr(root, "versionName"),
        "minSdk": attr(root.find("uses-sdk") or ET.Element("none"), "minSdkVersion"),
        "targetSdk": attr(root.find("uses-sdk") or ET.Element("none"), "targetSdkVersion"),
        "launchActivity": launch_activity,
        "activityCount": len(activities),
        "serviceCount": len(services),
        "receiverCount": len(receivers),
        "permissionCount": len(permissions),
        "permissions": permissions,
        "activities": activities,
        "services": services,
        "receivers": receivers,
    }


def inspect_apk(apk: Path, apkanalyzer: str = "apkanalyzer") -> dict[str, Any]:
    xml = run_apkanalyzer(apk, apkanalyzer=apkanalyzer)
    info = parse_manifest(xml)
    info["apk"] = str(apk)
    info["exists"] = apk.exists()
    info["size"] = apk.stat().st_size if apk.exists() else 0
    info["tool"] = "apkanalyzer manifest print"
    return info


def to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# APK Manifest 检查",
        "",
        f"- apk: {report.get('apk', '')}",
        f"- package: {report.get('package', '')}",
        f"- launchActivity: {report.get('launchActivity', '')}",
        f"- versionName: {report.get('versionName', '')}",
        f"- versionCode: {report.get('versionCode', '')}",
        f"- minSdk: {report.get('minSdk', '')}",
        f"- targetSdk: {report.get('targetSdk', '')}",
        f"- activityCount: {report.get('activityCount', 0)}",
        f"- serviceCount: {report.get('serviceCount', 0)}",
        f"- receiverCount: {report.get('receiverCount', 0)}",
        f"- permissionCount: {report.get('permissionCount', 0)}",
        "",
        "## Launch command hint",
        "",
        "```bash",
        f"adb shell monkey -p {report.get('package', '<package>')} -c android.intent.category.LAUNCHER 1",
        "```",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("apk")
    ap.add_argument("--apkanalyzer", default="apkanalyzer")
    ap.add_argument("--out")
    ap.add_argument("--markdown-out")
    ns = ap.parse_args()
    report = inspect_apk(Path(ns.apk), apkanalyzer=ns.apkanalyzer)
    data = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.out:
        Path(ns.out).write_text(data + "\n", encoding="utf-8")
    else:
        print(data)
    if ns.markdown_out:
        Path(ns.markdown_out).write_text(to_markdown(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
