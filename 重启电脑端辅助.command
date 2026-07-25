#!/bin/zsh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PORT=17351
LOG="$DIR/电脑端辅助前端/reports/server.log"
PIDFILE="$DIR/电脑端辅助前端/reports/server.pid"
mkdir -p "$(dirname "$LOG")"
USER_HOME="${HOME:-/Users/${USER:-$(id -un)}}"
MOBILE_CONFIG_DIR="${DWPM_MOBILE_API_CONFIG_DIR:-$USER_HOME/Library/Application Support/DWPMDesktop}"
MOBILE_CONFIG_FILE="$MOBILE_CONFIG_DIR/mobile_api.env"

# If the dedicated mobile launcher was used before, carry its LAN binding and
# credentials into ordinary restarts.  Explicit environment values (for
# example a deliberate loopback restart) take precedence over the saved file.
if [[ -z "${DWPM_MOBILE_API_TOKEN:-}" && -z "${DWPM_DESKTOP_BIND_HOST:-}" && -f "$MOBILE_CONFIG_FILE" ]]; then
  source "$MOBILE_CONFIG_FILE"
fi
export DWPM_DESKTOP_BIND_HOST="${DWPM_DESKTOP_BIND_HOST:-127.0.0.1}"

/usr/bin/python3 - "$DIR" "$PORT" "$LOG" "$PIDFILE" <<'PY'
import os, signal, subprocess, sys, time, pathlib
root = pathlib.Path(sys.argv[1])
port = sys.argv[2]
log = pathlib.Path(sys.argv[3])
pidfile = pathlib.Path(sys.argv[4])

# 关闭旧服务
pids = subprocess.run(
    ["bash", "-lc", f"lsof -tiTCP:{port} -sTCP:LISTEN || true"],
    capture_output=True, text=True
).stdout.split()
for pid in pids:
    try:
        os.kill(int(pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
if pids:
    time.sleep(0.8)

# 如果还没退出，强制关闭
pids = subprocess.run(
    ["bash", "-lc", f"lsof -tiTCP:{port} -sTCP:LISTEN || true"],
    capture_output=True, text=True
).stdout.split()
for pid in pids:
    try:
        os.kill(int(pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
if pids:
    time.sleep(0.3)

# 启动新服务：独立 session，关闭终端也不影响
with open(log, "ab", buffering=0) as f:
    proc = subprocess.Popen(
        ["/usr/bin/python3", str(root / "电脑端辅助前端/server.py")],
        cwd=str(root),
        stdin=subprocess.DEVNULL,
        stdout=f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
pidfile.write_text(str(proc.pid))
time.sleep(1)
print(proc.pid)
PY

PID="$(cat "$PIDFILE" 2>/dev/null || true)"
echo "电脑端辅助已重启，PID=$PID"
echo "健康检查："
curl -sS --max-time 3 "http://127.0.0.1:$PORT/api/health" || true
echo ""
echo "打开页面：http://127.0.0.1:$PORT/index.html"
open "http://127.0.0.1:$PORT/index.html"
