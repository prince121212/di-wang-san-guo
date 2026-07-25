#!/bin/zsh
set -e

ROOT="/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国"
cd "$ROOT"

echo "清理最近 10 分钟测试抓包目录"
echo "需要输入一次 Mac 密码来删除 root 权限的 tcpdump 文件。"
echo

sudo rm -rf \
  "$ROOT/ctf_out/passive_pcap_hotspot_20260709_032747" \
  "$ROOT/ctf_out/passive_pcap_hotspot_20260709_032937"

: > "$ROOT/reverse_cases/apk-sanguo-diwanglianmeng-166/captures/mitm/current_capture_dir.txt"

echo
echo "已清理："
echo "- ctf_out/passive_pcap_hotspot_20260709_032747"
echo "- ctf_out/passive_pcap_hotspot_20260709_032937"
echo
echo "按回车关闭窗口。"
read
