#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightweight operator timeline logger for passive pcap sessions.

Writes operator events to the active capture directory:
  - operator_timeline.jsonl
  - operator_timeline.md

Default capture dir is read from:
  /Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国/reverse_cases/apk-sanguo-diwanglianmeng-166/captures/mitm/current_capture_dir.txt

Usage:
  python3 tools/capture_timeline_logger.py [capture_dir]
  PORT=8091 BIND=0.0.0.0 python3 tools/capture_timeline_logger.py
"""
from __future__ import annotations
import datetime as _dt
import html
import http.server
import json
import os
import pathlib
import re
import socket
import threading
import time
import urllib.parse

ROOT = pathlib.Path('/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国')
CURRENT = ROOT / 'reverse_cases/apk-sanguo-diwanglianmeng-166/captures/mitm/current_capture_dir.txt'
DEFAULT_BUTTONS = [
    '开始一轮操作', '登录/重登', '进主城', '地图拖动', '城池详情', '背包', '使用物品', '丢弃物品',
    '科技页面', '开始研究', '建筑页面', '建筑升级', '编组', '改名', '找黄/搜山贼', '刷黄出征',
    '出征状态', '战报', '竞技场', '任务', '活动', '签到', '邮件', '聊天', '国家', '官职', '排行榜',
    '商城', '结束当前场景'
]
LOCK = threading.Lock()


def resolve_capture_dir(argv_dir: str | None = None) -> pathlib.Path:
    if argv_dir:
        return pathlib.Path(argv_dir).expanduser().resolve()
    if os.environ.get('CAPTURE_DIR'):
        return pathlib.Path(os.environ['CAPTURE_DIR']).expanduser().resolve()
    if os.environ.get('CAP'):
        return pathlib.Path(os.environ['CAP']).expanduser().resolve()
    if CURRENT.exists():
        text = CURRENT.read_text('utf-8').strip()
        if text:
            return pathlib.Path(text).expanduser().resolve()
    fallback = ROOT / 'ctf_out' / ('operator_timeline_' + _dt.datetime.now().strftime('%Y%m%d_%H%M%S'))
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


CAP = resolve_capture_dir(os.sys.argv[1] if len(os.sys.argv) > 1 else None)
CAP.mkdir(parents=True, exist_ok=True)
JSONL = CAP / 'operator_timeline.jsonl'
MD = CAP / 'operator_timeline.md'
PCAP = CAP / 'game_traffic.pcap'


def now_info() -> dict:
    now = _dt.datetime.now().astimezone()
    info = {
        'ts': now.isoformat(timespec='milliseconds'),
        'localTime': now.strftime('%Y-%m-%d %H:%M:%S'),
        'epochMs': int(time.time() * 1000),
        'captureDir': str(CAP),
        'pcap': str(PCAP),
        'pcapSize': PCAP.stat().st_size if PCAP.exists() else 0,
    }
    if PCAP.exists():
        info['pcapMtime'] = _dt.datetime.fromtimestamp(PCAP.stat().st_mtime).astimezone().isoformat(timespec='milliseconds')
    return info


def sanitize_event(s: str) -> str:
    s = (s or '').strip()
    s = re.sub(r'\s+', ' ', s)
    return s[:300] if s else '未命名事件'


def append_event(event: str, kind: str = 'mark', source: str = 'web', extra: dict | None = None) -> dict:
    rec = now_info()
    rec.update({'kind': kind or 'mark', 'source': source or 'web', 'event': sanitize_event(event)})
    if extra:
        rec.update(extra)
    with LOCK:
        is_new = not MD.exists()
        with JSONL.open('a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + '\n')
        with MD.open('a', encoding='utf-8') as f:
            if is_new:
                f.write('# 抓包操作时间线\n\n')
                f.write(f'- captureDir: `{CAP}`\n')
                f.write(f'- pcap: `{PCAP}`\n\n')
                f.write('| 时间 | 事件 | pcap大小 | 来源 |\n|---|---:|---:|---|\n')
            f.write(f"| {rec['localTime']} | {rec['event']} | {rec['pcapSize']} | {rec['source']} |\n")
    return rec


def read_recent(n: int = 80) -> list[dict]:
    if not JSONL.exists():
        return []
    lines = JSONL.read_text('utf-8', errors='replace').splitlines()[-n:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def get_ip_hint() -> str:
    # Prefer hotspot bridge gateway if present; otherwise best-effort local hostname IP.
    try:
        import subprocess
        p = subprocess.run(['ifconfig', 'bridge100'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=2)
        m = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', p.stdout)
        if m:
            return m.group(1)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


CSS = '''
*{box-sizing:border-box}body{margin:0;background:#0b1020;color:#e5e7eb;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif}.wrap{max-width:760px;margin:0 auto;padding:18px}form{position:sticky;top:0;background:#0b1020;padding:14px 0 12px;border-bottom:1px solid #1f2937}input{width:100%;height:52px;border:1px solid #374151;background:#111827;color:#f9fafb;border-radius:12px;padding:0 14px;font-size:18px;outline:none}input:focus{border-color:#60a5fa;box-shadow:0 0 0 3px rgba(96,165,250,.18)}.timeline{margin:14px 0 0;padding:0;list-style:none}.item{padding:12px 2px;border-bottom:1px solid #1f2937}.time{color:#9ca3af;font-size:12px;margin-bottom:5px}.event{font-size:17px;line-height:1.45;white-space:pre-wrap;word-break:break-word}.empty{color:#6b7280;padding:24px 0}.toast{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);background:#064e3b;color:#d1fae5;border:1px solid #10b981;border-radius:999px;padding:10px 16px;display:none;font-size:14px}
'''


def page() -> bytes:
    html_doc = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>抓包时间线</title><style>{CSS}</style></head>
<body><div class="wrap">
<form onsubmit="mark();return false"><input id="event" autofocus autocomplete="off" placeholder="输入当前操作，回车记录"></form>
<ul id="timeline" class="timeline"><li class="empty">暂无记录</li></ul>
</div><div class="toast" id="toast"></div>
<script>
function esc(s){{return String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}
async function mark(){{const input=document.getElementById('event');const ev=input.value.trim();if(!ev)return;await fetch('/api/mark?event='+encodeURIComponent(ev),{{cache:'no-store'}});input.value='';show('已记录');await load();}}
function show(s){{const t=document.getElementById('toast');t.textContent=s;t.style.display='block';setTimeout(()=>t.style.display='none',900)}}
async function load(){{const d=await (await fetch('/api/status?'+Date.now(),{{cache:'no-store'}})).json();const rows=d.recent||[];document.getElementById('timeline').innerHTML=rows.slice().reverse().map(r=>`<li class="item"><div class="time">${{esc(r.localTime)}}</div><div class="event">${{esc(r.event)}}</div></li>`).join('')||'<li class="empty">暂无记录</li>';}}
setInterval(load,2000);load();
</script></body></html>'''
    return html_doc.encode('utf-8')


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass
    def send_json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == '/api/mark':
            q = urllib.parse.parse_qs(u.query)
            event = q.get('event', [''])[0]
            self.send_json(append_event(event, source='web'))
            return
        if u.path == '/api/status':
            rec = now_info()
            rec.update({'ok': True, 'recent': read_recent(), 'jsonl': str(JSONL), 'markdown': str(MD)})
            self.send_json(rec)
            return
        b = page()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)


if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', '8091'))
    BIND = os.environ.get('BIND', '0.0.0.0')
    append_event('时间线记录器启动', kind='system', source='logger')
    class Server(http.server.ThreadingHTTPServer):
        allow_reuse_address = True
    print(f'Timeline logger: http://127.0.0.1:{PORT}/', flush=True)
    print(f'Hotspot URL: http://{get_ip_hint()}:{PORT}/', flush=True)
    print(f'Capture dir: {CAP}', flush=True)
    print(f'JSONL: {JSONL}', flush=True)
    print(f'Markdown: {MD}', flush=True)
    Server((BIND, PORT), Handler).serve_forever()
