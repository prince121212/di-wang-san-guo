#!/usr/bin/env bash
set -euo pipefail
ROOT="/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国"
PROJECT="$ROOT/自研辅助源码"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="$ROOT/ctf_out/passive_pcap_${TS}"
mkdir -p "$OUT"
PHONE_IP="${PHONE_IP:-}"
GAME_HOST="${GAME_HOST:-118.89.111.11}"
GAME_PORT="${GAME_PORT:-25511}"
IFACE="${IFACE:-en0}"
if command -v adb >/dev/null 2>&1; then
  adb shell settings put global http_proxy :0 >/dev/null 2>&1 || true
  adb shell settings delete global http_proxy >/dev/null 2>&1 || true
  adb shell settings delete global global_http_proxy_host >/dev/null 2>&1 || true
  adb shell settings delete global global_http_proxy_port >/dev/null 2>&1 || true
  if [ -z "$PHONE_IP" ]; then
    PHONE_IP="$(adb shell "ip -o -4 addr show wlan0 2>/dev/null | awk '{print \$4}' | cut -d/ -f1 | head -1" | tr -d '\r' || true)"
  fi
fi
if [ -z "$PHONE_IP" ]; then
  echo "PHONE_IP 未识别。请用：PHONE_IP=192.168.2.4 $0" >&2
  exit 2
fi
cat > "$OUT/README.md" <<EOF
# Passive pcap capture

- createdAt: $(date '+%Y-%m-%d %H:%M:%S')
- method: tcpdump pcap, no HTTP proxy, no MITM
- iface: $IFACE
- phoneIp: $PHONE_IP
- gameServer: $GAME_HOST:$GAME_PORT
- pcap: $OUT/game_traffic.pcap

注意：普通 Mac Wi-Fi 客户端不一定能看到同一 AP 下手机的单播流量。最稳位置是手机本机 root tcpdump 或路由器/AP 侧抓包/镜像。
EOF
echo "$OUT" > "$ROOT/reverse_cases/apk-sanguo-diwanglianmeng-166/captures/mitm/current_capture_dir.txt"
echo "被动抓包目录：$OUT"
echo "手机代理已清空；开始 tcpdump。若提示 password，请输入 macOS 管理员密码。"
echo "停止：Ctrl-C"
# -s 0: full packet; -U: packet-buffered; filter only game TCP traffic.
sudo tcpdump -i "$IFACE" -n -s 0 -U -w "$OUT/game_traffic.pcap" \
  "((host $PHONE_IP) and (host $GAME_HOST) and tcp port $GAME_PORT)"
