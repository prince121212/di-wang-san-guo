#!/usr/bin/env python3
"""Preflight checker for isolated device protocol regression.

Checks host tools, required APK/script artifacts, optional base_channel_extra, and ADB device
visibility before running capture_device_protocol_regression.sh. It does not install apps,
attach Frida to a target process, or send any network request. When an authorized ADB device is
present it runs the safe `frida-ps -U` enumeration command to verify frida-server reachability.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import zipfile
import importlib.util
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
INSPECT_APK_PATH = Path(__file__).with_name("inspect_apk_manifest.py")
VERIFY_REPLAY_CONTRACT_PATH = Path(__file__).with_name("verify_replay_contract.py")
DEFAULTS = {
    "selfApk": ROOT / "app/build/outputs/apk/debug/app-debug.apk",
    "xiaohuangApk": ROOT.parent / "小黄点辅助.apk",
    "gameApk": ROOT.parent / "三国·帝王联盟1.66.apk",
    "fridaScript": ROOT.parent / "reverse_cases/apk/scripts/frida_native_session_trace_v2.js",
}



def infer_apk_package(apk: Path) -> dict[str, Any]:
    if not apk.exists():
        return {"attempted": False, "package": "", "error": "apk missing"}
    try:
        spec = importlib.util.spec_from_file_location("inspect_apk_manifest", INSPECT_APK_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        info = mod.inspect_apk(apk)
        return {"attempted": True, "package": info.get("package", ""), "launchActivity": info.get("launchActivity", ""), "versionName": info.get("versionName", ""), "error": ""}
    except Exception as exc:
        return {"attempted": True, "package": "", "error": str(exc)}


def load_verify_replay_contract():
    spec = importlib.util.spec_from_file_location("verify_replay_contract", VERIFY_REPLAY_CONTRACT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def stringify_channel_extra(data: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            out[str(key)] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            text = str(value)
            if text != "":
                out[str(key)] = text
    return out


def load_channel_extraish(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("base channelExtra must be a JSON object")
    if isinstance(data.get("baseChannelExtra"), dict):
        data = data["baseChannelExtra"]
    elif isinstance(data.get("channelExtra"), dict):
        data = data["channelExtra"]
    elif isinstance(data.get("session"), dict) and isinstance(data["session"].get("channelExtra"), dict):
        data = data["session"]["channelExtra"]
    return stringify_channel_extra(data)


def base_channel_extra_audit(path_text: str) -> dict[str, Any]:
    if not path_text:
        return {
            "checked": False,
            "path": "",
            "exists": False,
            "validJsonObject": False,
            "safetyOk": True,
            "baselineReadyForCapture": False,
            "strictReplayReadyBeforeCapture": False,
            "error": "",
            "missingBaseline": [],
            "contractSummary": {},
            "contractMissing": {},
            "unsafeTrueFlags": [],
        }
    path = Path(path_text)
    result: dict[str, Any] = {
        "checked": True,
        "path": str(path),
        "exists": path.exists(),
        "validJsonObject": False,
        "safetyOk": False,
        "baselineReadyForCapture": False,
        "strictReplayReadyBeforeCapture": False,
        "error": "",
        "missingBaseline": [],
        "contractSummary": {},
        "contractMissing": {},
        "unsafeTrueFlags": [],
    }
    if not path.exists():
        result["error"] = "base channelExtra file missing"
        return result
    try:
        extra = load_channel_extraish(path)
        verifier = load_verify_replay_contract()
        extra = verifier.with_recovered_role_resource(extra)
        contract = verifier.verify(extra)
        evidence = contract.get("evidence", {}) if isinstance(contract.get("evidence"), dict) else {}
        missing_baseline: list[str] = []
        if len(evidence.get("identity", []) or []) < 2:
            missing_baseline.append("identity:userId/serverUrl")
        if len(evidence.get("role", []) or []) < 2:
            missing_baseline.append("role:roleName/level")
        if len(evidence.get("resource", []) or []) < 2:
            missing_baseline.append("resource:copper/food")
        if not evidence.get("generalParseReadySource"):
            missing_baseline.append("generals:parseable")
        if not evidence.get("formationParseReadySource"):
            missing_baseline.append("formations:parseable")
        unsafe = evidence.get("unsafeTrueFlags", []) if isinstance(evidence.get("unsafeTrueFlags", []), list) else []
        result.update({
            "validJsonObject": True,
            "fieldCount": len(extra),
            "safetyOk": not unsafe,
            "baselineReadyForCapture": not missing_baseline and not unsafe,
            "strictReplayReadyBeforeCapture": bool(
                contract.get("summary", {}).get("shuaHuangOfflineReplayReady")
                and contract.get("summary", {}).get("dailyOfflineReplayReady")
                and contract.get("summary", {}).get("mineOfflineReplayReady")
            ),
            "missingBaseline": missing_baseline,
            "contractSummary": contract.get("summary", {}),
            "contractMissing": contract.get("missing", {}),
            "unsafeTrueFlags": unsafe,
        })
    except Exception as exc:
        result["error"] = str(exc)
    return result


def which(cmd: str) -> str:
    return shutil.which(cmd) or ""


def resolve_bin(cmd: str) -> str:
    return which(cmd) if os.path.basename(cmd) == cmd else (cmd if Path(cmd).exists() else "")


def run(cmd: list[str], timeout: int = 5) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        return p.returncode, p.stdout
    except Exception as exc:
        return 999, str(exc)


def adb_devices(adb_bin: str) -> dict[str, Any]:
    if not adb_bin:
        return {"ok": False, "devices": [], "raw": "adb not found"}
    code, out = run([adb_bin, "devices", "-l"])
    devices = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append({"serial": parts[0], "state": parts[1], "raw": line})
    authorized = [d for d in devices if d["state"] == "device"]
    return {"ok": code == 0 and bool(authorized), "devices": devices, "authorizedDeviceCount": len(authorized), "raw": out}


def _count_frida_process_rows(out: str) -> int:
    count = 0
    for line in out.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if lower.startswith(("pid", "name", "spawned", "attached")):
            continue
        if set(stripped) <= {"-", " "}:
            continue
        if "failed to enumerate" in lower or "unable to connect" in lower or "error" == lower:
            continue
        count += 1
    return count


def frida_usb(frida_ps_bin: str, devices_ok: bool) -> dict[str, Any]:
    if not frida_ps_bin:
        return {
            "checked": False,
            "ok": False,
            "raw": "frida-ps not found",
            "processCount": 0,
            "command": "",
        }
    command = [frida_ps_bin, "-U"]
    if not devices_ok:
        return {
            "checked": False,
            "ok": False,
            "raw": "authorized adb device missing",
            "processCount": 0,
            "command": " ".join(command),
        }
    code, out = run(command, timeout=8)
    process_count = _count_frida_process_rows(out)
    return {
        "checked": True,
        "ok": code == 0,
        "raw": out.strip(),
        "processCount": process_count,
        "command": " ".join(command),
        "exitCode": code,
    }


def file_check(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists(), "size": path.stat().st_size if path.exists() else 0}


def self_apk_freshness(self_apk: Path, root: Path = ROOT) -> dict[str, Any]:
    """Check whether the debug self APK is newer than self-app source files.

    This prevents a common regression-capture mistake: source code contains the latest
    self-lifecycle markers, but the installed/debug APK was built before those markers.
    """
    result: dict[str, Any] = {
        "checked": True,
        "apkPath": str(self_apk),
        "apkExists": self_apk.exists(),
        "fresh": False,
        "apkMtime": 0,
        "latestSourceMtime": 0,
        "latestSourcePath": "",
        "error": "",
    }
    if not self_apk.exists():
        result["error"] = "self APK missing"
        return result
    source_roots = [root / "app/src/main", root / "app/build.gradle.kts", root / "build.gradle.kts", root / "settings.gradle.kts"]
    latest_mtime = 0.0
    latest_path = ""
    try:
        for source in source_roots:
            if source.is_file():
                candidates = [source]
            elif source.is_dir():
                candidates = [p for p in source.rglob("*") if p.is_file()]
            else:
                candidates = []
            for candidate in candidates:
                mtime = candidate.stat().st_mtime
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_path = str(candidate)
        apk_mtime = self_apk.stat().st_mtime
        result.update({
            "apkMtime": apk_mtime,
            "latestSourceMtime": latest_mtime,
            "latestSourcePath": latest_path,
            "fresh": bool(latest_mtime and apk_mtime >= latest_mtime),
        })
    except Exception as exc:
        result["error"] = str(exc)
    return result


def self_apk_marker_audit(self_apk: Path, marker: str = "self-lifecycle-json") -> dict[str, Any]:
    result: dict[str, Any] = {
        "checked": True,
        "apkPath": str(self_apk),
        "apkExists": self_apk.exists(),
        "marker": marker,
        "markerFound": False,
        "matchingEntries": [],
        "error": "",
    }
    if not self_apk.exists():
        result["error"] = "self APK missing"
        return result
    needle = marker.encode("utf-8")
    try:
        with zipfile.ZipFile(self_apk) as zf:
            matches: list[str] = []
            for name in zf.namelist():
                if not name.endswith((".dex", ".arsc", ".xml")):
                    continue
                data = zf.read(name)
                if needle in data:
                    matches.append(name)
            result["matchingEntries"] = matches
            result["markerFound"] = bool(matches)
    except Exception as exc:
        result["error"] = str(exc)
    return result


def check_package(adb_bin: str, package: str) -> dict[str, Any]:
    if not package or not adb_bin:
        return {"checked": False, "installed": False, "package": package, "raw": ""}
    code, out = run([adb_bin, "shell", "pm", "path", package], timeout=8)
    return {"checked": True, "installed": code == 0 and "package:" in out, "package": package, "raw": out.strip()}


def preflight(
    adb_bin: str = "adb",
    frida_bin: str = "frida",
    frida_ps_bin: str = "frida-ps",
    package: str = "",
    base_channel_extra: str = "",
    self_apk: Path = DEFAULTS["selfApk"],
    xiaohuang_apk: Path = DEFAULTS["xiaohuangApk"],
    game_apk: Path = DEFAULTS["gameApk"],
    frida_script: Path = DEFAULTS["fridaScript"],
) -> dict[str, Any]:
    apk_manifest = infer_apk_package(xiaohuang_apk)
    self_apk_manifest = infer_apk_package(self_apk)
    game_apk_manifest = infer_apk_package(game_apk)
    if not package and apk_manifest.get("package"):
        package = str(apk_manifest["package"])
    self_package = str(self_apk_manifest.get("package") or "")
    game_package = str(game_apk_manifest.get("package") or "")
    adb_path = resolve_bin(adb_bin)
    frida_path = resolve_bin(frida_bin)
    frida_ps_path = resolve_bin(frida_ps_bin)
    devices = adb_devices(adb_path)
    frida_usb_state = frida_usb(frida_ps_path, devices["ok"])
    self_apk_fresh = self_apk_freshness(self_apk)
    self_apk_marker = self_apk_marker_audit(self_apk)
    files = {
        "selfApk": {**file_check(self_apk), "buildFresh": self_apk_fresh.get("fresh", False)},
        "xiaohuangApk": file_check(xiaohuang_apk),
        "gameApk": file_check(game_apk),
        "fridaScript": file_check(frida_script),
    }
    if base_channel_extra:
        files["baseChannelExtra"] = file_check(Path(base_channel_extra))
    base_audit = base_channel_extra_audit(base_channel_extra)
    package_state = check_package(adb_path, package) if devices["ok"] and package else {"checked": bool(package), "installed": False, "package": package, "raw": "device unavailable or package omitted"}
    self_package_state = check_package(adb_path, self_package) if devices["ok"] and self_package else {"checked": bool(self_package), "installed": False, "package": self_package, "raw": "device unavailable or self package omitted"}
    game_package_state = check_package(adb_path, game_package) if devices["ok"] and game_package else {"checked": bool(game_package), "installed": False, "package": game_package, "raw": "device unavailable or game package omitted"}
    missing = []
    if not adb_path:
        missing.append("adb")
    if not frida_path:
        missing.append("frida")
    if not frida_ps_path:
        missing.append("frida-ps")
    if not devices["ok"]:
        missing.append("authorized adb device")
    if devices["ok"] and frida_path and frida_ps_path and not frida_usb_state["ok"]:
        missing.append("frida usb device/server")
    for name, item in files.items():
        if not item["exists"]:
            missing.append(name)
    if files.get("selfApk", {}).get("exists") and not self_apk_fresh.get("fresh"):
        missing.append("selfApk:fresh debug build")
    if files.get("selfApk", {}).get("exists") and not self_apk_marker.get("markerFound"):
        missing.append("selfApk:self-lifecycle-json marker")
    if base_channel_extra and base_audit.get("exists") and not base_audit.get("validJsonObject"):
        missing.append("baseChannelExtra:valid json object")
    if base_channel_extra and base_audit.get("validJsonObject") and not base_audit.get("safetyOk"):
        missing.append("baseChannelExtra unsafe network flag must be false")
    if package and devices["ok"] and not package_state["installed"]:
        missing.append(f"package installed:{package}")
    if self_package and devices["ok"] and not self_package_state["installed"]:
        missing.append(f"self package installed:{self_package}")
    if game_package and devices["ok"] and not game_package_state["installed"]:
        missing.append(f"game package installed:{game_package}")
    install_commands = recommended_install_commands(files, package, self_package, game_package)
    runbook = capture_runbook(package, base_channel_extra, frida_script, install_commands)
    return {
        "summary": {
            "preflightReady": not missing,
            "adbFound": bool(adb_path),
            "fridaFound": bool(frida_path),
            "fridaPsFound": bool(frida_ps_path),
            "fridaUsbChecked": bool(frida_usb_state.get("checked")),
            "fridaUsbOk": bool(frida_usb_state.get("ok")),
            "fridaUsbProcessCount": frida_usb_state.get("processCount", 0),
            "authorizedDeviceCount": devices.get("authorizedDeviceCount", 0),
            "packageInstalled": package_state.get("installed", False),
            "selfPackageInstalled": self_package_state.get("installed", False),
            "selfPackage": self_package,
            "selfApkBuildFresh": bool(self_apk_fresh.get("fresh")),
            "selfApkLifecycleMarkerReady": bool(self_apk_marker.get("markerFound")),
            "gamePackageInstalled": game_package_state.get("installed", False),
            "gamePackage": game_package,
            "baseChannelExtraChecked": bool(base_audit.get("checked")),
            "baseChannelExtraValid": bool(base_audit.get("validJsonObject")),
            "baseChannelExtraSafetyOk": bool(base_audit.get("safetyOk", True)),
            "baseChannelExtraBaselineReady": bool(base_audit.get("baselineReadyForCapture")),
            "baseChannelExtraStrictReplayReadyBeforeCapture": bool(base_audit.get("strictReplayReadyBeforeCapture")),
            "realActionNetworkAllowed": False,
            "blocker": "preflight only; capture/action execution not started",
        },
        "missing": missing,
        "tools": {"adb": adb_path, "frida": frida_path, "fridaPs": frida_ps_path},
        "adbDevices": devices,
        "fridaUsb": frida_usb_state,
        "files": files,
        "selfApkFreshness": self_apk_fresh,
        "selfApkLifecycleMarkerAudit": self_apk_marker,
        "apkManifest": apk_manifest,
        "selfApkManifest": self_apk_manifest,
        "gameApkManifest": game_apk_manifest,
        "package": package_state,
        "selfPackage": self_package_state,
        "gamePackage": game_package_state,
        "baseChannelExtraAudit": base_audit,
        "nextActions": next_actions(missing, package, files, base_audit),
        "installCommands": install_commands,
        "runbook": runbook,
        "recommendedCommand": recommended_command(package, base_channel_extra, frida_script),
    }


def recommended_install_commands(files: dict[str, dict[str, Any]], package: str, self_package: str = "", game_package: str = "") -> list[str]:
    commands: list[str] = []
    game = files.get("gameApk", {})
    xh = files.get("xiaohuangApk", {})
    self_apk = files.get("selfApk", {})
    if game.get("exists"):
        commands.append(f"adb install -r \"{game['path']}\"")
    if xh.get("exists"):
        commands.append(f"adb install -r \"{xh['path']}\"")
    if self_apk.get("exists"):
        commands.append(f"adb install -r \"{self_apk['path']}\"")
    if package:
        commands.append(f"adb shell pm path {package}")
    if self_package:
        commands.append(f"adb shell pm path {self_package}")
    if game_package:
        commands.append(f"adb shell pm path {game_package}")
    return commands


def next_actions(missing: list[str], package: str, files: dict[str, dict[str, Any]], base_audit: dict[str, Any] | None = None) -> list[str]:
    actions: list[str] = []
    if "adb" in missing:
        actions.append("安装 Android platform-tools，或通过 --adb-bin 指向可用 adb。")
    if "frida" in missing:
        actions.append("安装 frida-tools，或通过 --frida-bin 指向可用 frida。")
    if "frida-ps" in missing:
        actions.append("安装 frida-tools，或通过 --frida-ps-bin 指向可用 frida-ps。")
    if "authorized adb device" in missing:
        actions.extend([
            "手机开启开发者选项和 USB 调试，连接 USB 后执行 adb devices。",
            "如果 adb devices 显示 unauthorized，请在手机上确认 RSA 授权；必要时执行 adb kill-server && adb start-server 后重新插拔。",
            "确认设备状态为 device 后，再运行 capture_device_protocol_regression.sh。",
        ])
    missing_files = [item for item in missing if item in files]
    if missing_files:
        actions.append("补齐缺失文件：" + ", ".join(missing_files))
    if "selfApk:fresh debug build" in missing:
        actions.append("重新构建自研调试 APK：cd 自研辅助源码 && ./gradlew :app:assembleDebug；否则设备上安装的自研包可能缺少最新 self-lifecycle-json marker。")
    if "selfApk:self-lifecycle-json marker" in missing:
        actions.append("检查/重建自研调试 APK：app-debug.apk 内未发现 self-lifecycle-json marker，真机无法证明 stop/logout；请确认 SelfLifecycleLogFormatter 已编译进 APK。")
    pkg_missing = [item for item in missing if item.startswith("package installed:")]
    if pkg_missing:
        pkg = package or pkg_missing[0].split(":", 1)[-1]
        actions.append(f"安装或启动小黄点 APK，并确认 adb shell pm path {pkg} 可返回 package 路径。")
    self_pkg_missing = [item for item in missing if item.startswith("self package installed:")]
    if self_pkg_missing:
        pkg = self_pkg_missing[0].split(":", 1)[-1]
        actions.append(f"安装自研辅助 APK，并确认 adb shell pm path {pkg} 可返回 package 路径；否则 selfStopLogout / self-lifecycle-json 无法采集。")
    game_pkg_missing = [item for item in missing if item.startswith("game package installed:")]
    if game_pkg_missing:
        pkg = game_pkg_missing[0].split(":", 1)[-1]
        actions.append(f"安装游戏本体 APK，并确认 adb shell pm path {pkg} 可返回 package 路径；否则登录/地图/刷黄场景无法完整采集。")
    if "frida usb device/server" in missing:
        actions.extend([
            "在测试设备上启动与本机 frida-tools 版本匹配的 frida-server，并确认进程未被系统杀掉。",
            "执行 frida-ps -U；只有能列出设备进程后再运行 capture_device_protocol_regression.sh。",
            "如 frida-ps -U 报版本不匹配，请替换设备端 frida-server 为相同 major/minor 版本。",
        ])
    if base_audit and base_audit.get("checked"):
        if base_audit.get("error"):
            actions.append(f"修复 base_channel_extra：{base_audit['error']}")
        elif not base_audit.get("safetyOk", True):
            actions.append("修复 base_channel_extra：移除或改为 false 的 networkSendAllowed/deviceRegressionNetworkSendAllowed 等危险 flag。")
        elif not base_audit.get("baselineReadyForCapture"):
            missing_base = ", ".join(base_audit.get("missingBaseline", []))
            actions.append("建议在采集前补齐 base_channel_extra 基线字段：" + missing_base + "；否则真机日志可能需要额外补采才能通过严格回放。")
    if not missing and not any("Preflight 已就绪" in item for item in actions):
        actions.insert(0, "Preflight 已就绪：运行 recommendedCommand，并按 capture_scenario_check.md 完成登录、找黄、刷黄、日常、找矿采集。")
    elif not actions:
        actions.append("Preflight 已就绪：运行 recommendedCommand，并按 capture_scenario_check.md 完成登录、找黄、刷黄、日常、找矿采集。")
    return actions


def capture_runbook(package: str, base: str, frida_script: Path, install_commands: list[str]) -> list[str]:
    runbook = [
        "1. 连接隔离测试手机/模拟器，开启 USB 调试并确认 adb devices 显示 state=device。",
        "2. 如 APK 未安装，按 installCommands 安装游戏本体、小黄点辅助和自研 APK。",
        "3. 确认目标设备已启动 frida-server，且 frida-ps -U 可列出进程。",
        f"4. 运行采集命令：{recommended_command(package, base, frida_script).replace(chr(10), ' ')}",
        "5. 在采集窗口内按顺序操作：登录/同步角色状态 -> 找黄/刷黄搜索 -> 刷黄出征样本 -> 切到自研辅助停止任务并退出登录 -> 一键日常样本 -> 找矿/资源点扫描样本。",
        "6. 采集结束后先看 capture_scenario_check.md 和 regression_artifact_check.md；不要根据单个日志片段判断完成。",
    ]
    return runbook


def recommended_command(package: str, base: str, frida_script: Path) -> str:
    pkg = package or "<小黄点包名>"
    parts = [
        "bash tools/capture_device_protocol_regression.sh",
        f"  --package {pkg}",
        "  --mode spawn",
        "  --duration 120",
        f"  --frida-script {frida_script}",
    ]
    if base:
        parts.append(f"  --base-channel-extra {base}")
    parts.append("  --out-dir reports/device_protocol_$(date +%Y%m%d_%H%M%S)")
    return " \\\n".join(parts)


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 设备回归 Preflight 检查",
        "",
        "## Summary",
        "",
        f"- preflightReady: {str(s['preflightReady']).lower()}",
        f"- adbFound: {str(s['adbFound']).lower()}",
        f"- fridaFound: {str(s['fridaFound']).lower()}",
        f"- fridaPsFound: {str(s['fridaPsFound']).lower()}",
        f"- fridaUsbChecked: {str(s['fridaUsbChecked']).lower()}",
        f"- fridaUsbOk: {str(s['fridaUsbOk']).lower()}",
        f"- fridaUsbProcessCount: {s['fridaUsbProcessCount']}",
        f"- authorizedDeviceCount: {s['authorizedDeviceCount']}",
        f"- packageInstalled: {str(s['packageInstalled']).lower()}",
        f"- selfPackageInstalled: {str(s['selfPackageInstalled']).lower()}",
        f"- selfPackage: {s.get('selfPackage', '')}",
        f"- selfApkBuildFresh: {str(s.get('selfApkBuildFresh', False)).lower()}",
        f"- selfApkLifecycleMarkerReady: {str(s.get('selfApkLifecycleMarkerReady', False)).lower()}",
        f"- gamePackageInstalled: {str(s['gamePackageInstalled']).lower()}",
        f"- gamePackage: {s.get('gamePackage', '')}",
        f"- baseChannelExtraChecked: {str(s['baseChannelExtraChecked']).lower()}",
        f"- baseChannelExtraValid: {str(s['baseChannelExtraValid']).lower()}",
        f"- baseChannelExtraSafetyOk: {str(s['baseChannelExtraSafetyOk']).lower()}",
        f"- baseChannelExtraBaselineReady: {str(s['baseChannelExtraBaselineReady']).lower()}",
        f"- baseChannelExtraStrictReplayReadyBeforeCapture: {str(s['baseChannelExtraStrictReplayReadyBeforeCapture']).lower()}",
        f"- realActionNetworkAllowed: {str(s['realActionNetworkAllowed']).lower()}",
        f"- blocker: {s['blocker']}",
        "",
        "## Missing",
        "",
        "```json",
        json.dumps(report["missing"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## APK manifest inference",
        "",
        "```json",
        json.dumps(report.get("apkManifest", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Self APK manifest inference",
        "",
        "```json",
        json.dumps(report.get("selfApkManifest", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Game APK manifest inference",
        "",
        "```json",
        json.dumps(report.get("gameApkManifest", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Package install checks",
        "",
        "```json",
        json.dumps({"target": report.get("package", {}), "self": report.get("selfPackage", {}), "game": report.get("gamePackage", {})}, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Files",
        "",
        "```json",
        json.dumps(report["files"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Self APK freshness",
        "",
        "```json",
        json.dumps(report.get("selfApkFreshness", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Self APK lifecycle marker audit",
        "",
        "```json",
        json.dumps(report.get("selfApkLifecycleMarkerAudit", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Base channelExtra audit",
        "",
        "```json",
        json.dumps(report.get("baseChannelExtraAudit", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## ADB devices",
        "",
        "```json",
        json.dumps(report["adbDevices"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Frida USB",
        "",
        "```json",
        json.dumps(report["fridaUsb"], ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Recommended command",
        "",
        "```bash",
        report["recommendedCommand"],
        "```",
        "",
        "## Next actions",
        "",
    ]
    lines.extend(f"- {item}" for item in report.get("nextActions", []))
    lines += [
        "",
        "## Install commands",
        "",
        "```bash",
        "\n".join(report.get("installCommands", [])),
        "```",
        "",
        "## Capture runbook",
        "",
    ]
    lines.extend(f"- {item}" for item in report.get("runbook", []))
    lines += [
        "",
        "安全边界：preflight/runbook 只生成本地检查和采集命令；真实动作发送仍由自研侧保持关闭。",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adb-bin", default=os.environ.get("ADB_BIN", "adb"))
    ap.add_argument("--frida-bin", default=os.environ.get("FRIDA_BIN", "frida"))
    ap.add_argument("--frida-ps-bin", default=os.environ.get("FRIDA_PS_BIN", "frida-ps"))
    ap.add_argument("--package", default="", help="Optional package name to check with adb shell pm path")
    ap.add_argument("--base-channel-extra", default="")
    ap.add_argument("--self-apk", default=str(DEFAULTS["selfApk"]))
    ap.add_argument("--xiaohuang-apk", default=str(DEFAULTS["xiaohuangApk"]))
    ap.add_argument("--game-apk", default=str(DEFAULTS["gameApk"]))
    ap.add_argument("--frida-script", default=str(DEFAULTS["fridaScript"]))
    ap.add_argument("--out")
    ap.add_argument("--markdown-out")
    ns = ap.parse_args()
    report = preflight(
        adb_bin=ns.adb_bin,
        frida_bin=ns.frida_bin,
        frida_ps_bin=ns.frida_ps_bin,
        package=ns.package,
        base_channel_extra=ns.base_channel_extra,
        self_apk=Path(ns.self_apk),
        xiaohuang_apk=Path(ns.xiaohuang_apk),
        game_apk=Path(ns.game_apk),
        frida_script=Path(ns.frida_script),
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
