#!/usr/bin/env python3
"""Copy only non-secret account metadata/settings to the fresh internal APK.

Never uninstalls, clears app data, copies Keystore ciphertext, or logs credentials.
Export files are sensitive account metadata: local owner-only storage is required.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time
import xml.etree.ElementTree as ET
import copy

SOURCE = "com.example.dwpmclone"
TARGET = "com.example.dwpmclone.internal"
ACCOUNT_FILE = "files/shared_python_core/accounts-v1.json"
CONFIG_FILE = "shared_prefs/dwpm_clone_configs.xml"
IDENTITY_FIELDS = ("accountRef", "id", "displayName", "username", "serverName", "serverId",
                   "gameVersion", "channel", "monarchName", "nation", "platform", "platformKey", "serial", "serverQuery")

def adb(*args, data=None, check=True):
    return subprocess.run(["adb", *args], input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=check, timeout=60)

def read_file(package, name):
    return adb("exec-out", "run-as", package, "cat", name).stdout

def reject_secrets(value):
    if isinstance(value, dict):
        for key, child in value.items():
            compact = str(key).lower().replace("_", "").replace("-", "")
            if any(part in compact for part in ("password", "passwd", "token", "secret", "cookie", "authorization", "credential", "privatekey")) or compact in ("dm", "userid", "gameauthsign"):
                raise ValueError("Settings contain credential-like fields; migration stopped")
            reject_secrets(child)
    elif isinstance(value, list):
        for child in value:
            reject_secrets(child)
    elif isinstance(value, str) and value.strip().startswith(("{", "[")):
        reject_secrets(json.loads(value))

def config_keys(xml):
    root = ET.fromstring(xml)
    if root.tag != "map":
        raise ValueError("Invalid configuration XML")
    keys = []
    for entry in root:
        if entry.tag != "string" or "::" not in entry.attrib.get("name", ""):
            raise ValueError("Unexpected config entry; migration stopped")
        reject_secrets(json.loads(entry.text or "{}"))
        keys.append(entry.attrib["name"])
    return sorted(keys)

def sanitize_accounts(raw):
    source = json.loads(raw)
    if source.get("schemaVersion") != 1 or not isinstance(source.get("accounts"), list):
        raise ValueError("Unsupported account store")
    records = []
    for account in source["accounts"]:
        item = {k: account[k] for k in IDENTITY_FIELDS if k in account}
        item.update(enabled=False, loginState="LOCAL_NOT_LOGGED_IN")
        config = ((account.get("session") or {}).get("publicState") or {}).get("residentAutomationConfigJson")
        state = {}
        if config:
            reject_secrets(json.loads(config))
            state["residentAutomationConfigJson"] = config
        # Preserve saved automation configuration, but not a usable login session,
        # resource snapshots, pending operations, deadlines or savedTasksStarted.
        item["session"] = {"accountId": account["id"], "sourceMode": 0,
                           "expiresAtMillis": None, "publicState": state}
        records.append(item)
    refs = [str(x.get("accountRef", x.get("id"))) for x in records]
    if not refs or len(refs) != len(set(refs)):
        raise ValueError("Empty or duplicate account identities")
    return {"schemaVersion": 1, "revision": 1, "updatedAtMillis": int(time.time()*1000), "accounts": records}

def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

def make_snapshot():
    raw = read_file(SOURCE, ACCOUNT_FILE)
    config = read_file(SOURCE, CONFIG_FILE)
    accounts = sanitize_accounts(raw)
    keys = config_keys(config)
    # User changes to settings during capture require a fresh snapshot.
    again = sanitize_accounts(read_file(SOURCE, ACCOUNT_FILE))
    if accounts["accounts"] != again["accounts"] or config != read_file(SOURCE, CONFIG_FILE):
        raise ValueError("Source settings changed during capture; retry after editing ends")
    return {"format": "dwpm-portable-internal-v1", "sourcePackage": SOURCE, "targetPackage": TARGET,
            "accounts": accounts, "configXml": config.decode(), "configKeys": keys}

def validate(snapshot):
    if snapshot.get("format") != "dwpm-portable-internal-v1" or snapshot.get("targetPackage") != TARGET:
        raise ValueError("Wrong migration format/target")
    accounts = sanitize_accounts(encoded(snapshot["accounts"]))
    if accounts["accounts"] != snapshot["accounts"]["accounts"]:
        raise ValueError("Snapshot contains unsupported account state")
    if config_keys(snapshot["configXml"]) != snapshot["configKeys"]:
        raise ValueError("Config manifest mismatch")

def exists(package, path):
    return adb("shell", "run-as", package, "test", "-e", path, check=False).returncode == 0

def verify(snapshot):
    actual = json.loads(read_file(TARGET, ACCOUNT_FILE))
    expected = snapshot["accounts"]["accounts"]
    records = actual.get("accounts", [])
    if len(records) != len(expected):
        raise ValueError("Target account count mismatch")
    for old, new in zip(expected, records):
        if any(old.get(k) != new.get(k) for k in IDENTITY_FIELDS):
            raise ValueError("Target identity mismatch")
        if new.get("enabled") or new.get("session", {}).get("sourceMode") != 0:
            raise ValueError("Target unexpectedly enabled or logged in")
        a = old["session"]["publicState"].get("residentAutomationConfigJson")
        b = new.get("session", {}).get("publicState", {}).get("residentAutomationConfigJson")
        if a != b:
            raise ValueError("Automation config mismatch")
    config = read_file(TARGET, CONFIG_FILE)
    if config != snapshot["configXml"].encode():
        raise ValueError("Feature configuration bytes differ")
    return {"accounts": len(expected), "configEntries": len(snapshot["configKeys"]),
            "configSha256": hashlib.sha256(config).hexdigest(), "allAccountsStopped": True,
            "credentialFilesCopied": 0, "sourceUntouched": True}

def import_snapshot(snapshot):
    validate(snapshot)
    # Never overwrite an existing target or migrate into the live source package.
    if exists(TARGET, ACCOUNT_FILE) or exists(TARGET, CONFIG_FILE) or exists(TARGET, "shared_prefs/dwpm_membership_v1.xml"):
        raise ValueError("Target already has data; refusing overwrite")
    adb("shell", "am", "force-stop", TARGET)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, data in ((ACCOUNT_FILE, encoded(snapshot["accounts"])), (CONFIG_FILE, snapshot["configXml"].encode())):
            info = tarfile.TarInfo(name); info.size = len(data); info.mode = 0o600
            archive.addfile(info, io.BytesIO(data))
    # stdin is a small, validated data archive, not a shell command or key file.
    adb("shell", "-T", "run-as", TARGET, "tar", "-xf", "-", data=buffer.getvalue())
    return verify(snapshot)

def merge_missing(snapshot, current, xml, ref):
    validate(snapshot)
    previous = next(x for x in snapshot["accounts"]["accounts"] if str(x["accountRef"]) == ref)
    updated = copy.deepcopy(current)
    target = next(x for x in updated["accounts"] if str(x["accountRef"]) == ref)
    if any(previous.get(k) != target.get(k) for k in ("username", "platformKey", "serverName")):
        raise ValueError("Account identity changed; refusing restoration")
    config_keys(xml)
    root = ET.fromstring(xml)
    present = {x.attrib["name"] for x in root}
    added = []
    for entry in ET.fromstring(snapshot["configXml"]):
        name = entry.attrib["name"]
        if name.startswith(ref + "::") and name not in present:
            root.append(copy.deepcopy(entry)); added.append(name)
    public = (target.get("session") or {}).get("publicState")
    if public is None:
        raise ValueError("Current account has no session state; inspect before restoring")
    restored_automation = False
    if "residentAutomationConfigJson" not in public:
        prior_config = previous["session"]["publicState"].get("residentAutomationConfigJson")
        if prior_config:
            public["residentAutomationConfigJson"] = prior_config
            restored_automation = True
    return updated, ET.tostring(root, encoding="utf-8", xml_declaration=True), added, restored_automation

def restore_missing(snapshot, ref, backup_dir):
    if ref is None or backup_dir is None:
        raise ValueError("restore-missing requires --account-ref and --backup-dir")
    backup_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    adb("shell", "am", "force-stop", TARGET)
    account_bytes, config_bytes = read_file(TARGET, ACCOUNT_FILE), read_file(TARGET, CONFIG_FILE)
    current = json.loads(account_bytes)
    accounts, xml, added, restored = merge_missing(snapshot, current, config_bytes, ref)
    for name, data in (("accounts-before.json", account_bytes), ("configs-before.xml", config_bytes)):
        fd = os.open(backup_dir / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f: f.write(data)
    credential_files = ["shared_prefs/dwpm_secure_credentials.xml", "shared_prefs/dwpm_secure_session_secrets.xml", "shared_prefs/dwpm_membership_v1.xml"]
    before = {f: hashlib.sha256(read_file(TARGET, f)).hexdigest() for f in credential_files if exists(TARGET, f)}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, data in ((ACCOUNT_FILE, encoded(accounts)), (CONFIG_FILE, xml)):
            info = tarfile.TarInfo(name); info.size = len(data); info.mode = 0o600
            archive.addfile(info, io.BytesIO(data))
    adb("shell", "-T", "run-as", TARGET, "tar", "-xf", "-", data=buffer.getvalue())
    if read_file(TARGET, ACCOUNT_FILE) != encoded(accounts) or read_file(TARGET, CONFIG_FILE) != xml:
        raise ValueError("Restoration verification failed; do not restart")
    if any(hashlib.sha256(read_file(TARGET, f)).hexdigest() != digest for f, digest in before.items()):
        raise ValueError("Credentials unexpectedly changed; do not restart")
    return {"restoredConfigEntries": len(added), "restoredAutomation": restored, "existingConfigsPreserved": True, "credentialFilesUnchanged": True, "appLeftStopped": True}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("export", "import", "verify", "restore-missing"))
    p.add_argument("snapshot", type=Path)
    p.add_argument("--account-ref")
    p.add_argument("--backup-dir", type=Path)
    args = p.parse_args()
    if args.action == "export":
        snapshot = make_snapshot()
        fd = os.open(args.snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f: f.write(encoded(snapshot))
        print(json.dumps({"accounts": len(snapshot["accounts"]["accounts"]), "configEntries": len(snapshot["configKeys"]), "credentialFilesCopied": 0}))
    else:
        if args.snapshot.is_symlink() or args.snapshot.stat().st_mode & 0o077:
            raise ValueError("Migration snapshot must be an owner-only regular file")
        snapshot = json.loads(args.snapshot.read_text())
        validate(snapshot)
        if args.action == "restore-missing":
            result = restore_missing(snapshot, args.account_ref, args.backup_dir)
        else:
            result = import_snapshot(snapshot) if args.action == "import" else verify(snapshot)
        print(json.dumps(result))

if __name__ == "__main__":
    try: main()
    except (ValueError, OSError, subprocess.SubprocessError) as e:
        # Never include command buffers or raw account data in errors.
        print("Migration stopped:", str(e) if isinstance(e, ValueError) else type(e).__name__)
        raise SystemExit(1)
