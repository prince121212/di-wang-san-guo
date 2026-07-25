#!/usr/bin/env bash
set -euo pipefail
ROOT="/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国"
CURRENT="$ROOT/reverse_cases/apk-sanguo-diwanglianmeng-166/captures/mitm/current_capture_dir.txt"
CAP="${CAPTURE_DIR:-${CAP:-}}"
if [ -z "$CAP" ] && [ -f "$CURRENT" ]; then CAP="$(cat "$CURRENT")"; fi
if [ -z "$CAP" ]; then echo "缺少抓包目录；设置 CAPTURE_DIR 或先启动抓包。" >&2; exit 2; fi
EVENT="$*"
if [ -z "$EVENT" ]; then echo "用法：$0 打开背包/点击科技研究/..." >&2; exit 2; fi
python3 - "$CAP" "$EVENT" <<'PY'
from pathlib import Path
import sys, json, datetime, time, re
cap=Path(sys.argv[1]); event=sys.argv[2].strip(); cap.mkdir(parents=True, exist_ok=True)
pcap=cap/'game_traffic.pcap'
rec={
 'ts': datetime.datetime.now().astimezone().isoformat(timespec='milliseconds'),
 'localTime': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
 'epochMs': int(time.time()*1000),
 'kind': 'mark', 'source': 'cli', 'event': re.sub(r'\s+',' ',event)[:300],
 'captureDir': str(cap), 'pcap': str(pcap), 'pcapSize': pcap.stat().st_size if pcap.exists() else 0,
}
jsonl=cap/'operator_timeline.jsonl'; md=cap/'operator_timeline.md'; is_new=not md.exists()
with jsonl.open('a', encoding='utf-8') as f: f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True)+'\n')
with md.open('a', encoding='utf-8') as f:
    if is_new:
        f.write('# 抓包操作时间线\n\n')
        f.write(f'- captureDir: `{cap}`\n- pcap: `{pcap}`\n\n')
        f.write('| 时间 | 事件 | pcap大小 | 来源 |\n|---|---:|---:|---|\n')
    f.write(f"| {rec['localTime']} | {rec['event']} | {rec['pcapSize']} | {rec['source']} |\n")
print(f"marked: {rec['localTime']} {rec['event']} pcapSize={rec['pcapSize']}")
PY
