#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三国·帝王联盟 TCP 协议探针服务器

APK 的历史配置里出现 dxt11v13g.3gking.net:25511，说明进入游戏后可能还有
非 HTTP 的长连接/二进制协议。本脚本只做本地监听和日志记录，用于恢复协议。
"""
from __future__ import annotations
import argparse, socketserver, time, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGS = ROOT / 'logs'

class TCPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        LOGS.mkdir(exist_ok=True)
        peer = f"{self.client_address[0]}:{self.client_address[1]}"
        with open(LOGS / 'tcp_packets.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps({'ts':time.time(),'event':'connect','peer':peer}, ensure_ascii=False)+'\n')
            self.request.settimeout(20)
            while True:
                try:
                    data = self.request.recv(8192)
                except TimeoutError:
                    f.write(json.dumps({'ts':time.time(),'event':'timeout','peer':peer}, ensure_ascii=False)+'\n')
                    break
                except Exception as e:
                    f.write(json.dumps({'ts':time.time(),'event':'error','peer':peer,'error':repr(e)}, ensure_ascii=False)+'\n')
                    break
                if not data:
                    f.write(json.dumps({'ts':time.time(),'event':'close','peer':peer}, ensure_ascii=False)+'\n')
                    break
                rec={'ts':time.time(),'event':'recv','peer':peer,'len':len(data),'hex':data.hex(),'text':data[:512].decode('utf-8','replace')}
                f.write(json.dumps(rec, ensure_ascii=False)+'\n'); f.flush()
                # Conservative response: do not invent gameplay state yet; send nothing by default.
                # If later we identify heartbeat bytes, add a response table here.

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=25511)
    args=ap.parse_args()
    LOGS.mkdir(exist_ok=True)
    with socketserver.ThreadingTCPServer((args.host,args.port), TCPHandler) as srv:
        srv.allow_reuse_address=True
        print(f'Diwang TCP probe listening on {args.host}:{args.port}')
        print(f'Packet log: {LOGS / "tcp_packets.jsonl"}')
        srv.serve_forever()
if __name__ == '__main__': main()
