#!/usr/bin/env bash
set -euo pipefail
ROOT="/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国"
CAP="${1:-$ROOT/ctf_out/passive_pcap_hotspot_20260707_234936}"
VIEW="$ROOT/自研辅助源码/tools/live_pcap_viewer.py"
SESSION="diwang_live_pcap"
PORT="${PORT:-8090}"
mkdir -p "$CAP"
# 只停实时页面，不碰 tcpdump 抓包进程
screen -S "$SESSION" -X quit 2>/dev/null || true
pkill -f "live_pcap_viewer.py" 2>/dev/null || true
sleep 0.5
screen -dmS "$SESSION" /bin/zsh -lc "cd '$ROOT'; exec python3 -u '$VIEW' '$CAP' >> '$CAP/live_pcap_viewer.screen.log' 2>&1"
sleep 1
echo "screen session: $SESSION"
echo "url: http://127.0.0.1:$PORT/"
screen -ls | grep "$SESSION" || true
