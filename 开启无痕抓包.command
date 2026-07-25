#!/bin/zsh
set -e

ROOT="/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国"
APP="$ROOT/自研辅助源码/tools/passive_hotspot_capture_app.py"
PORT="${PORT:-8092}"

cd "$ROOT"
clear
echo "帝王三国无痕抓包控制台"
echo
echo "1. 请确认 Mac 已开启互联网共享热点，手机已连接这个热点。"
echo "2. 本方案不设置手机代理、不安装证书，只在 Mac 热点网桥 bridge100 上被动抓包。"
echo "3. tcpdump 需要管理员权限，下面可能会要求输入本机登录密码。"
echo

sudo -v

# 控制台可能从上一次抓包后一直驻留。重新运行本命令时先关闭旧版本，
# 确保351/352区等最新抓包选项立即生效。
OLD_PIDS="$(pgrep -f "$APP" 2>/dev/null || true)"
if [ -n "$OLD_PIDS" ]; then
  echo "正在关闭旧抓包控制台：$OLD_PIDS"
  echo "$OLD_PIDS" | xargs sudo kill 2>/dev/null || true
  sleep 1
fi

python3 -m py_compile "$APP"

PHONE_IP="$(adb shell "ip -o -4 addr show wlan0 2>/dev/null | awk '{print \$4}' | cut -d/ -f1 | head -1" 2>/dev/null | tr -d '\r' || true)"

echo
echo "正在打开控制台：http://127.0.0.1:$PORT/"
open "http://127.0.0.1:$PORT/" >/dev/null 2>&1 || true
if [ -n "$PHONE_IP" ]; then
  echo "已识别手机 IP：$PHONE_IP"
  sudo env PORT="$PORT" PHONE_IP="$PHONE_IP" python3 -u "$APP"
else
  sudo env PORT="$PORT" python3 -u "$APP"
fi
