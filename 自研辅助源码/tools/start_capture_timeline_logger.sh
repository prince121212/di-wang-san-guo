#!/usr/bin/env bash
set -euo pipefail
ROOT="/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国"
PROJECT="$ROOT/自研辅助源码"
CURRENT="$ROOT/reverse_cases/apk-sanguo-diwanglianmeng-166/captures/mitm/current_capture_dir.txt"
CAP="${1:-${CAPTURE_DIR:-}}"
if [ -z "$CAP" ] && [ -f "$CURRENT" ]; then CAP="$(cat "$CURRENT")"; fi
if [ -z "$CAP" ]; then echo "缺少抓包目录；用法：$0 <capture_dir>" >&2; exit 2; fi
PORT="${PORT:-8091}"
BIND="${BIND:-0.0.0.0}"
SESSION="diwang_timeline_logger"
mkdir -p "$CAP"
screen -S "$SESSION" -X quit 2>/dev/null || true
pkill -f "capture_timeline_logger.py.*$CAP" 2>/dev/null || true
sleep 0.3
screen -dmS "$SESSION" /bin/zsh -lc "cd '$ROOT'; PORT='$PORT' BIND='$BIND' exec python3 -u '$PROJECT/tools/capture_timeline_logger.py' '$CAP' >> '$CAP/timeline_logger.screen.log' 2>&1"
sleep 1
HOTSPOT_IP="$(ifconfig bridge100 2>/dev/null | awk '/inet /{print $2; exit}')"
echo "screen session: $SESSION"
echo "Mac URL: http://127.0.0.1:$PORT/"
if [ -n "$HOTSPOT_IP" ]; then echo "手机热点 URL: http://$HOTSPOT_IP:$PORT/"; fi
echo "timeline jsonl: $CAP/operator_timeline.jsonl"
echo "timeline md: $CAP/operator_timeline.md"
screen -ls | grep "$SESSION" || true
