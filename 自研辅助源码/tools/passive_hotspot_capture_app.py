#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-click passive hotspot capture UI for 帝王三国.

This app controls tcpdump on the Mac Internet Sharing bridge, stores every pcap/log
under ctf_out, and renders a small local web UI. It does not set a phone proxy and
does not MITM traffic.
"""
from __future__ import annotations

import datetime as dt
import html
import http.server
import ipaddress
import json
import os
import pathlib
import re
import signal
import subprocess
import threading
import time
import traceback
import urllib.parse

ROOT = pathlib.Path("/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国")
PROJECT = ROOT / "自研辅助源码"
OUT_ROOT = ROOT / "ctf_out"
CURRENT = ROOT / "reverse_cases/apk-sanguo-diwanglianmeng-166/captures/mitm/current_capture_dir.txt"
PARSE = PROJECT / "tools/parse_passive_pcap_httpclient.py"

DEFAULT_IFACE = os.environ.get("CAPTURE_IFACE", "bridge100")
DEFAULT_GAME_PORT = int(os.environ.get("GAME_PORT", "25511"))
GAME_SERVERS = {
    "game351": {
        "label": "351区",
        "host": "118.89.111.11",
        "port": 25511,
    },
    "game352": {
        "label": "352区",
        "host": "115.159.92.72",
        "port": 25511,
    },
    "downjoy1025": {
        "label": "当乐1025区",
        "host": "124.222.176.93",
        "port": 8888,
    },
}
DEFAULT_CAPTURE_MODE = os.environ.get("CAPTURE_MODE", "game351")
CAPTURE_PLATFORMS = {
    "hotblood-alliance": "热血三国联盟",
    "sanguo-alliance": "三国联盟",
    "downjoy": "当乐帝王三国",
    "other": "其他平台",
}
DEFAULT_CAPTURE_PLATFORM = os.environ.get("CAPTURE_PLATFORM", "downjoy")
DEFAULT_GAME_HOST = os.environ.get(
    "GAME_HOST",
    str(GAME_SERVERS["game351"]["host"]),
)
PORT = int(os.environ.get("PORT", "8092"))
BIND = os.environ.get("BIND", "0.0.0.0")

LOCK = threading.RLock()
STATE: dict = {
    "captureDir": "",
    "pcap": "",
    "mode": DEFAULT_CAPTURE_MODE,
    "iface": DEFAULT_IFACE,
    "phoneIp": "",
    "host": DEFAULT_GAME_HOST,
    "port": DEFAULT_GAME_PORT,
    "serverLabel": str(GAME_SERVERS["game351"]["label"]),
    "platform": DEFAULT_CAPTURE_PLATFORM,
    "platformLabel": CAPTURE_PLATFORMS.get(
        DEFAULT_CAPTURE_PLATFORM,
        DEFAULT_CAPTURE_PLATFORM,
    ),
    "filter": "",
    "pid": None,
    "startedAt": None,
    "stoppedAt": None,
    "error": "",
    "lastParseSize": -1,
    "lastParseAt": 0.0,
}


def run(cmd: list[str], timeout: int = 5) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip()
    except Exception as e:
        return 1, str(e)


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ts_name() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def detect_phone_ip() -> str:
    def valid(value: str) -> str:
        value = str(value or "").strip()
        try:
            parsed = ipaddress.ip_address(value)
        except ValueError:
            return ""
        if (
            parsed.version != 4
            or parsed.is_multicast
            or parsed.is_loopback
            or parsed.is_unspecified
            or str(parsed) == bridge_ip()
        ):
            return ""
        return str(parsed)

    env = os.environ.get("PHONE_IP", "").strip()
    if valid(env):
        return valid(env)
    code, out = run(["adb", "shell", "ip -o -4 addr show wlan0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1"], timeout=4)
    adb_values = out.replace("\r", "").strip().splitlines()
    for value in adb_values:
        if valid(value):
            return valid(value)
    # 只读取热点网桥上的单播邻居，避免把mDNS组播224.0.0.251误认成手机。
    code, out = run(["arp", "-an"], timeout=3)
    bridge = bridge_ip()
    network = None
    if bridge:
        try:
            network = ipaddress.ip_network(f"{bridge}/24", strict=False)
        except ValueError:
            pass
    candidates = []
    for line in out.splitlines():
        if DEFAULT_IFACE not in line or "(incomplete)" in line:
            continue
        match = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)", line)
        candidate = valid(match.group(1) if match else "")
        if not candidate:
            continue
        if network and ipaddress.ip_address(candidate) not in network:
            continue
        candidates.append(candidate)
    if candidates:
        # 热点通常依次分配.2、.3；取最小主机地址最稳定。
        return min(candidates, key=lambda value: int(ipaddress.ip_address(value)))
    return ""


def bridge_ip() -> str:
    code, out = run(["sh", "-lc", f"ifconfig {DEFAULT_IFACE} 2>/dev/null | awk '/inet /{{print $2; exit}}'"], timeout=3)
    return out.strip()


def sanitize_ip(value: str) -> str:
    value = (value or "").strip()
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        raise RuntimeError("手机 IP 格式不正确")
    if (
        parsed.version != 4
        or parsed.is_multicast
        or parsed.is_loopback
        or parsed.is_unspecified
    ):
        raise RuntimeError("手机 IP 必须是有效的IPv4单播地址，不能使用组播地址")
    return str(parsed)


def sanitize_host(value: str) -> str:
    value = (value or "").strip()
    if not re.match(r"^[A-Za-z0-9_.:-]+$", value):
        raise RuntimeError("目标地址格式不正确")
    return value


def capture_target(mode: str, host: str, port: int) -> tuple[str, int, str]:
    preset = GAME_SERVERS.get(mode)
    if preset:
        return (
            str(preset["host"]),
            int(preset["port"]),
            str(preset["label"]),
        )
    return host, int(port), ("全量手机TCP" if mode == "wide" else "自定义")


def build_filter(mode: str, phone_ip: str, host: str, port: int) -> str:
    if mode == "wide":
        return f"(host {phone_ip}) and tcp"
    if mode == "custom":
        return f"((host {phone_ip}) and (host {host}) and tcp port {int(port)})"
    target_host, target_port, _label = capture_target(mode, host, port)
    return (
        f"((host {phone_ip}) and (host {target_host}) "
        f"and tcp port {target_port})"
    )


def capture_running() -> bool:
    pid = STATE.get("pid")
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def capture_dir() -> pathlib.Path | None:
    p = STATE.get("captureDir")
    return pathlib.Path(p) if p else None


def pcap_path() -> pathlib.Path | None:
    p = STATE.get("pcap")
    return pathlib.Path(p) if p else None


def append_timeline(event: str, source: str = "web") -> None:
    cap = capture_dir()
    if not cap:
        return
    rec = {
        "ts": dt.datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "localTime": now_text(),
        "epochMs": int(time.time() * 1000),
        "event": str(event or "").strip()[:300] or "未命名事件",
        "source": source,
        "captureDir": str(cap),
        "pcap": str(pcap_path() or ""),
        "pcapSize": (pcap_path().stat().st_size if pcap_path() and pcap_path().exists() else 0),
    }
    with (cap / "operator_timeline.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    md = cap / "operator_timeline.md"
    is_new = not md.exists()
    with md.open("a", encoding="utf-8") as f:
        if is_new:
            f.write("# 抓包操作时间线\n\n")
            f.write(f"- captureDir: `{cap}`\n")
            f.write(f"- pcap: `{pcap_path() or ''}`\n\n")
            f.write("| 时间 | 事件 | pcap大小 | 来源 |\n|---|---|---:|---|\n")
        f.write(f"| {rec['localTime']} | {rec['event']} | {rec['pcapSize']} | {rec['source']} |\n")


def start_capture(params: dict[str, str]) -> dict:
    with LOCK:
        if capture_running():
            raise RuntimeError("抓包已经在运行")
        phone_ip = sanitize_ip(params.get("phoneIp") or detect_phone_ip())
        mode = params.get("mode") or DEFAULT_CAPTURE_MODE
        # 兼容旧页面/旧CLI中的 game，它原来就是351区。
        if mode == "game":
            mode = "game351"
        if mode not in {*GAME_SERVERS, "wide", "custom"}:
            mode = DEFAULT_CAPTURE_MODE
        host = sanitize_host(params.get("host") or DEFAULT_GAME_HOST)
        port = int(params.get("port") or DEFAULT_GAME_PORT)
        host, port, server_label = capture_target(mode, host, port)
        platform = str(params.get("platform") or DEFAULT_CAPTURE_PLATFORM)
        if platform not in CAPTURE_PLATFORMS:
            platform = "other"
        platform_label = CAPTURE_PLATFORMS[platform]
        iface = sanitize_host(params.get("iface") or DEFAULT_IFACE)
        filt = build_filter(mode, phone_ip, host, port)
        cap = OUT_ROOT / f"passive_pcap_hotspot_{ts_name()}"
        cap.mkdir(parents=True, exist_ok=True)
        pcap = cap / ("phone_tcp_all.pcap" if mode == "wide" else "game_traffic.pcap")
        if mode == "wide":
            try:
                (cap / "game_traffic.pcap").symlink_to(pcap.name)
            except FileExistsError:
                pass
        tcpdump_stdout = cap / "tcpdump.stdout.log"
        tcpdump_stderr = cap / "tcpdump.stderr.log"
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            command = ["/usr/sbin/tcpdump", "-i", iface, "-n", "-s", "0", "-U", "-w", str(pcap), filt]
        else:
            command = ["/usr/bin/sudo", "-n", "/usr/sbin/tcpdump", "-i", iface, "-n", "-s", "0", "-U", "-w", str(pcap), filt]
        readme = (
            "# Passive hotspot pcap\n\n"
            f"- createdAt: {now_text()}\n"
            "- method: Mac Internet Sharing hotspot; tcpdump on bridge100; no HTTP proxy; no MITM\n"
            f"- iface: {iface}\n"
            f"- phoneIp: {phone_ip}\n"
            f"- mode: {mode}\n"
            f"- platform: {platform_label} ({platform})\n"
            f"- serverLabel: {server_label}\n"
            f"- target: {host}:{port}\n"
            f"- filter: `{filt}`\n"
            f"- pcap: `{pcap}`\n"
            f"- viewer: http://127.0.0.1:{PORT}/\n"
            f"- hotspotViewer: http://{bridge_ip() or '192.168.3.1'}:{PORT}/\n"
        )
        (cap / "README.md").write_text(readme, encoding="utf-8")
        (cap / "capture_config.json").write_text(json.dumps({
            "createdAt": now_text(),
            "mode": mode,
            "platform": platform,
            "platformLabel": platform_label,
            "serverLabel": server_label,
            "iface": iface,
            "phoneIp": phone_ip,
            "host": host,
            "port": port,
            "filter": filt,
            "pcap": str(pcap),
            "command": command,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        (cap / "run_tcpdump_command.sh").write_text("#!/bin/sh\n" + " ".join("'" + x.replace("'", "'\\''") + "'" for x in command) + "\n", encoding="utf-8")
        CURRENT.parent.mkdir(parents=True, exist_ok=True)
        CURRENT.write_text(str(cap), encoding="utf-8")
        out_f = tcpdump_stdout.open("ab", buffering=0)
        err_f = tcpdump_stderr.open("ab", buffering=0)
        proc = subprocess.Popen(command, stdout=out_f, stderr=err_f, stdin=subprocess.DEVNULL, start_new_session=True, close_fds=True)
        STATE.update({
            "captureDir": str(cap),
            "pcap": str(pcap),
            "mode": mode,
            "iface": iface,
            "phoneIp": phone_ip,
            "host": host,
            "port": port,
            "serverLabel": server_label,
            "platform": platform,
            "platformLabel": platform_label,
            "filter": filt,
            "pid": proc.pid,
            "startedAt": now_text(),
            "stoppedAt": None,
            "error": "",
            "lastParseSize": -1,
            "lastParseAt": 0.0,
        })
        (cap / "tcpdump.pid").write_text(str(proc.pid), encoding="utf-8")
        append_timeline("抓包启动", "system")
        time.sleep(0.5)
        if proc.poll() is not None:
            err = tcpdump_stderr.read_text(encoding="utf-8", errors="replace") if tcpdump_stderr.exists() else ""
            STATE["error"] = err or "tcpdump 启动后立即退出"
            raise RuntimeError(STATE["error"])
        return status_payload()


def stop_capture() -> dict:
    with LOCK:
        pid = STATE.get("pid")
        if not pid:
            return status_payload()
        try:
            os.killpg(int(pid), signal.SIGINT)
        except Exception:
            run(["/usr/bin/sudo", "-n", "/bin/kill", "-INT", str(pid)], timeout=3)
        STATE["stoppedAt"] = now_text()
        append_timeline("抓包停止", "system")
        return status_payload()


def parse_flows(cap: pathlib.Path, pcap: pathlib.Path) -> list[dict]:
    if not pcap.exists() or pcap.stat().st_size <= 24:
        return []
    analyzed = cap / "live_analyzed"
    size = pcap.stat().st_size
    if size != STATE.get("lastParseSize") and time.time() - float(STATE.get("lastParseAt") or 0) > 2:
        analyzed.mkdir(parents=True, exist_ok=True)
        command = ["python3", str(PARSE), str(pcap), str(analyzed)]
        if STATE.get("mode") == "wide":
            # 当乐使用独立的8888端口，不能与联盟平台25511端口混在
            # parse_passive_pcap_httpclient.py 的单端口调用中。
            if STATE.get("platform") == "downjoy":
                preset = GAME_SERVERS["downjoy1025"]
                command.extend(["--host", str(preset["host"]), "--port", str(preset["port"])])
            else:
                for key in ("game351", "game352"):
                    command.extend(["--host", str(GAME_SERVERS[key]["host"])])
                command.extend(["--port", str(DEFAULT_GAME_PORT)])
        else:
            command.extend([
                "--host", str(STATE.get("host") or DEFAULT_GAME_HOST),
                "--port", str(STATE.get("port") or DEFAULT_GAME_PORT),
            ])
        run(command, timeout=30)
        STATE["lastParseSize"] = size
        STATE["lastParseAt"] = time.time()
    jf = analyzed / "game_http_flows.json"
    if not jf.exists():
        return []
    try:
        data = json.loads(jf.read_text(encoding="utf-8"))
    except Exception:
        return []
    for item in data:
        req_hex = analyzed / f"{int(item.get('index', 0)):03d}" / "req.hex"
        text = req_hex.read_text(encoding="utf-8", errors="replace") if req_hex.exists() else ""
        item["requestHeadHex"] = text[:80]
    return data[-80:]


def capture_records(pcap: pathlib.Path) -> list[dict]:
    if not pcap.exists() or pcap.stat().st_size <= 24:
        return []
    code, out = run(["tcpdump", "-nn", "-tttt", "-r", str(pcap)], timeout=10)
    records: dict[tuple[str, str, str], dict] = {}
    for line in out.splitlines():
        if not line or "reading from file" in line:
            continue
        m = re.search(r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+IP\s+((?:\d+\.){3}\d+)(?:\.(\d+))?\s+>\s+((?:\d+\.){3}\d+)(?:\.(\d+))?:", line)
        if not m:
            continue
        ts, src, sport, dst, dport = m.groups()
        target = f"{dst}:{dport}" if dport else dst
        source = f"{src}:{sport}" if sport else src
        direction = "手机 -> 外部" if src == str(STATE.get("phoneIp") or "") else ("外部 -> 手机" if dst == str(STATE.get("phoneIp") or "") else "其他")
        key = (source, target, direction)
        item = records.setdefault(key, {"source": source, "target": target, "direction": direction, "count": 0, "lastSeen": ts})
        item["count"] += 1
        item["lastSeen"] = ts
    return sorted(records.values(), key=lambda x: (x.get("lastSeen", ""), x.get("count", 0)), reverse=True)[:50]


def status_payload() -> dict:
    cap = capture_dir()
    pcap = pcap_path()
    size = pcap.stat().st_size if pcap and pcap.exists() else 0
    stderr_tail = ""
    if cap and (cap / "tcpdump.stderr.log").exists():
        stderr_tail = "\n".join((cap / "tcpdump.stderr.log").read_text(encoding="utf-8", errors="replace").splitlines()[-30:])
    recent = []
    if cap and (cap / "operator_timeline.jsonl").exists():
        for line in (cap / "operator_timeline.jsonl").read_text(encoding="utf-8", errors="replace").splitlines()[-40:]:
            try:
                recent.append(json.loads(line))
            except Exception:
                pass
    flows = parse_flows(cap, pcap) if cap and pcap else []
    return {
        "ok": True,
        "time": now_text(),
        "running": capture_running(),
        "captureDir": str(cap or ""),
        "pcap": str(pcap or ""),
        "pcapSize": size,
        "mode": STATE.get("mode"),
        "iface": STATE.get("iface") or DEFAULT_IFACE,
        "phoneIp": STATE.get("phoneIp") or detect_phone_ip(),
        "bridgeIp": bridge_ip(),
        "host": STATE.get("host") or DEFAULT_GAME_HOST,
        "port": STATE.get("port") or DEFAULT_GAME_PORT,
        "serverLabel": STATE.get("serverLabel") or "",
        "platform": STATE.get("platform") or DEFAULT_CAPTURE_PLATFORM,
        "platformLabel": STATE.get("platformLabel") or "",
        "filter": STATE.get("filter"),
        "pid": STATE.get("pid"),
        "startedAt": STATE.get("startedAt"),
        "stoppedAt": STATE.get("stoppedAt"),
        "error": STATE.get("error") or "",
        "stderrTail": stderr_tail,
        "records": capture_records(pcap) if pcap else [],
        "flows": flows,
        "recent": recent,
    }


def send_json(handler: http.server.BaseHTTPRequestHandler, obj: dict, code: int = 200) -> None:
    body = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


HTML = r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>帝王三国无痕抓包</title><style>
*{box-sizing:border-box}body{margin:0;background:#0b1020;color:#e5e7eb;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif}header{padding:18px 22px;background:#111827;border-bottom:1px solid #293548}h1{margin:0;font-size:22px}.sub{margin-top:6px;color:#9ca3af}.wrap{padding:16px 22px;max-width:1280px;margin:0 auto}.panel{background:#111827;border:1px solid #334155;border-radius:8px;margin-bottom:14px;overflow:hidden}.panel h2{font-size:16px;margin:0;padding:10px 12px;border-bottom:1px solid #334155}.body{padding:12px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.field label{display:block;font-size:12px;color:#9ca3af;margin-bottom:5px}.field input,.field select{width:100%;height:38px;border:1px solid #475569;border-radius:6px;background:#0f172a;color:#e5e7eb;padding:0 10px;font-size:14px}.cards{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}.card{background:#0f172a;border:1px solid #334155;border-radius:8px;padding:10px}.k{font-size:12px;color:#94a3b8}.v{font-size:18px;font-weight:700;margin-top:4px;word-break:break-all}.actions{display:flex;gap:10px;margin-top:12px;flex-wrap:wrap}button{border:0;border-radius:6px;height:38px;padding:0 14px;background:#2563eb;color:#eff6ff;font-weight:700;cursor:pointer}button.stop{background:#b91c1c}button.ghost{background:#374151}button:disabled{opacity:.45;cursor:not-allowed}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap;word-break:break-all}.log{max-height:300px;overflow:auto;padding:10px;font-size:12px;background:#08111f}.pill{display:inline-block;border-radius:999px;background:#1e3a8a;color:#dbeafe;padding:2px 8px;font-size:12px}.ok{color:#34d399}.bad{color:#fca5a5}table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid #263244;padding:7px;text-align:left;vertical-align:top}th{background:#0f172a;color:#93c5fd}.timeline{display:flex;gap:8px}.timeline input{flex:1;height:38px;border:1px solid #475569;border-radius:6px;background:#0f172a;color:#e5e7eb;padding:0 10px}.muted{color:#9ca3af}@media(max-width:900px){.grid,.cards{grid-template-columns:1fr 1fr}}@media(max-width:560px){.grid,.cards{grid-template-columns:1fr}}</style></head><body><header><h1>帝王三国无痕抓包</h1><div class="sub">Mac 热点 bridge100 被动抓包；不改手机代理，不装证书；所有 pcap / 日志 / 解析结果保存到 ctf_out。</div></header><div class="wrap">
<section class="panel"><h2>抓包控制</h2><div class="body"><div class="grid">
<div class="field"><label>游戏平台</label><select id="capturePlatform"><option value="downjoy">当乐帝王三国</option><option value="hotblood-alliance">热血三国联盟</option><option value="sanguo-alliance">三国联盟</option><option value="other">其他平台</option></select></div>
<div class="field"><label>抓包模式</label><select id="mode"><option value="game351">只抓351区 · 118.89.111.11:25511</option><option value="game352">只抓352区 · 115.159.92.72:25511</option><option value="wide">全量抓手机 TCP（自动解析351/352）</option><option value="custom">只抓自定义地址</option></select></div>
<div class="field"><label>手机 IP</label><input id="phoneIp" placeholder="自动识别，例如 192.168.3.2"></div>
<div class="field"><label>网卡</label><input id="iface" value="bridge100"></div>
<div class="field"><label>自定义 host:port</label><input id="target" value="118.89.111.11:25511"></div>
</div><div class="actions"><button id="startBtn" onclick="start()">开始抓包</button><button id="stopBtn" class="stop" onclick="stop()">停止抓包</button><button class="ghost" onclick="detectPhoneIp()">重新识别手机IP</button><button class="ghost" onclick="mark('开始操作')">标记：开始操作</button><button class="ghost" onclick="mark('配兵确认')">标记：配兵确认</button><button class="ghost" onclick="refresh()">刷新</button></div></div></section>
<section class="panel"><h2>状态</h2><div class="body"><div class="cards"><div class="card"><div class="k">运行状态</div><div id="running" class="v">-</div></div><div class="card"><div class="k">PCAP</div><div id="size" class="v">-</div></div><div class="card"><div class="k">业务流</div><div id="flowCount" class="v">-</div></div><div class="card"><div class="k">手机 IP</div><div id="phone" class="v">-</div></div><div class="card"><div class="k">监听</div><div id="listen" class="v">-</div></div></div><div class="log mono" id="paths"></div></div></section>
<section class="panel"><h2>操作时间线</h2><div class="body"><div class="timeline"><input id="eventText" placeholder="输入你刚做了什么，比如：进入军事-配兵，选择车1，改为178轻骑兵，点击确认"><button onclick="mark()">记录</button></div><div class="log mono" id="timeline"></div></div></section>
<section class="panel"><h2>解析到的 HTTPClient 业务包</h2><table><thead><tr><th>#</th><th>请求大小</th><th>响应大小</th><th>响应预览</th></tr></thead><tbody id="flows"><tr><td colspan="4" class="muted">等待游戏业务包...</td></tr></tbody></table></section>
<section class="panel"><h2>最近抓包记录</h2><table><thead><tr><th>最后时间</th><th>方向</th><th>来源</th><th>目标地址</th><th>包数</th></tr></thead><tbody id="records"><tr><td colspan="5" class="muted">等待数据...</td></tr></tbody></table></section>
<section class="panel"><h2>tcpdump 日志</h2><div class="log mono" id="stderr"></div></section>
</div><script>
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function fmt(n){n=Number(n||0);if(n<1024)return n+' B';if(n<1048576)return (n/1024).toFixed(1)+' KB';return (n/1048576).toFixed(2)+' MB'}
async function api(path, body){const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,cache:'no-store'});const d=await r.json();if(!d.ok)throw new Error(d.error||'请求失败');return d}
const presetTargets={game351:'118.89.111.11:25511',game352:'115.159.92.72:25511'};
mode.addEventListener('change',()=>{if(presetTargets[mode.value])target.value=presetTargets[mode.value]});
let formInitialized=false;
function params(){const [host,port]=(target.value||'118.89.111.11:25511').split(':');return {platform:capturePlatform.value,mode:mode.value,phoneIp:phoneIp.value,iface:iface.value||'bridge100',host:host||'118.89.111.11',port:Number(port||25511)}}
async function start(){try{await api('/api/start',params());await refresh()}catch(e){alert(e.message)}}
async function stop(){try{await api('/api/stop',{});await refresh()}catch(e){alert(e.message)}}
async function detectPhoneIp(){try{const d=await api('/api/detect-phone-ip',{});phoneIp.value=d.phoneIp||''}catch(e){alert(e.message)}}
async function mark(text){try{const event=text||eventText.value; if(!event)return; await api('/api/mark',{event}); eventText.value=''; await refresh()}catch(e){alert(e.message)}}
async function refresh(){try{const d=await api('/api/status');if(!formInitialized){phoneIp.value=d.phoneIp||'';iface.value=d.iface||'bridge100';mode.value=d.mode||'game351';capturePlatform.value=d.platform||'downjoy';target.value=(d.host||'118.89.111.11')+':'+(d.port||25511);formInitialized=true} running.innerHTML=d.running?'<span class="ok">抓包中</span>':'<span class="bad">未运行</span>'; size.textContent=fmt(d.pcapSize); flowCount.textContent=(d.flows||[]).length; phone.textContent=d.phoneIp||'-'; listen.textContent=(d.bridgeIp||'127.0.0.1')+':8092'; paths.textContent='captureDir: '+(d.captureDir||'-')+'\\npcap: '+(d.pcap||'-')+'\\nplatform: '+(d.platformLabel||d.platform||'-')+'\\nmode: '+(d.mode||'-')+'\\ntarget: '+(d.serverLabel||'-')+' '+(d.host||'-')+':'+(d.port||'-')+'\\nfilter: '+(d.filter||'-')+'\\npid: '+(d.pid||'-')+'\\nstartedAt: '+(d.startedAt||'-')+'\\nstoppedAt: '+(d.stoppedAt||'-')+'\\nerror: '+(d.error||''); records.innerHTML=(d.records&&d.records.length)?d.records.map(r=>`<tr><td>${esc(r.lastSeen)}</td><td>${esc(r.direction)}</td><td>${esc(r.source)}</td><td>${esc(r.target)}</td><td>${esc(r.count)}</td></tr>`).join(''):'<tr><td colspan="5" class="muted">等待数据...</td></tr>'; stderr.textContent=d.stderrTail||''; timeline.textContent=(d.recent||[]).slice().reverse().map(x=>`[${x.localTime}] ${x.event}`).join('\\n')||'暂无记录'; flows.innerHTML=(d.flows&&d.flows.length)?d.flows.slice().reverse().map(f=>`<tr><td>${esc(f.index)}<br><span class="muted">${esc(f.serverLabel||f.serverHost||'')}</span></td><td>${esc(f.requestLength??'-')} B</td><td>${esc(f.responseLength??'-')} B</td><td>${esc(f.responseTextPreview||'')}</td></tr>`).join(''):'<tr><td colspan="4" class="muted">等待游戏业务包...</td></tr>'}catch(e){stderr.textContent='刷新失败：'+e.message}}
setInterval(refresh,2000);refresh();
</script></body></html>'''


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        pass

    def do_OPTIONS(self) -> None:
        send_json(self, {"ok": True})

    def do_GET(self) -> None:
        try:
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/status":
                send_json(self, status_payload())
                return
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            send_json(self, {"ok": False, "error": str(e), "trace": traceback.format_exc()}, 500)

    def do_POST(self) -> None:
        try:
            ln = int(self.headers.get("Content-Length") or "0")
            body = json.loads(self.rfile.read(ln).decode("utf-8")) if ln else {}
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/start":
                send_json(self, start_capture(body))
                return
            if path == "/api/stop":
                send_json(self, stop_capture())
                return
            if path == "/api/detect-phone-ip":
                if capture_running():
                    raise RuntimeError("抓包运行中不能切换手机IP，请先停止抓包")
                phone_ip = detect_phone_ip()
                if not phone_ip:
                    raise RuntimeError("未识别到热点中的手机，请确认手机已连接Mac热点")
                STATE["phoneIp"] = phone_ip
                send_json(self, {
                    "ok": True,
                    "phoneIp": phone_ip,
                    "bridgeIp": bridge_ip(),
                })
                return
            if path == "/api/mark":
                event = str(body.get("event") or "")
                append_timeline(event, "web")
                send_json(self, status_payload())
                return
            send_json(self, {"ok": False, "error": "unknown api"}, 404)
        except Exception as e:
            send_json(self, {"ok": False, "error": str(e), "trace": traceback.format_exc()}, 500)


def main() -> int:
    STATE["phoneIp"] = detect_phone_ip()
    class Server(http.server.ThreadingHTTPServer):
        allow_reuse_address = True
    print(f"无痕抓包控制台：http://127.0.0.1:{PORT}/", flush=True)
    ip = bridge_ip()
    if ip:
        print(f"手机连 Mac 热点后也可访问：http://{ip}:{PORT}/", flush=True)
    Server((BIND, PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
