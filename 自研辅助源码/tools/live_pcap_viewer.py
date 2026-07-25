#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import http.server, json, pathlib, subprocess, sys, os, time, re, urllib.parse, traceback
ROOT=pathlib.Path('/Users/huangchangwei/Desktop/gitSpaceC/Toy/帝王三国')
PROJECT=ROOT/'自研辅助源码'
PARSE=PROJECT/'tools'/'parse_passive_pcap_httpclient.py'
CAP=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else pathlib.Path((ROOT/'reverse_cases/apk-sanguo-diwanglianmeng-166/captures/mitm/current_capture_dir.txt').read_text().strip())
PCAP=CAP/'game_traffic.pcap'
ANALYZED=CAP/'live_analyzed'
PHONE_IP=os.environ.get('PHONE_IP','192.168.3.2')
LAST_SIZE=-1
LAST_TS=0

def run(cmd, timeout=6):
    try:
        p=subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        return p.stdout
    except Exception as e:
        return 'ERR: '+str(e)

def opcode_guess(tail, req_hex=''):
    h=((req_hex or '')+(tail or '')).lower()
    known=[('1003','登录/进服初始化'),('1016','登录后初始化'),('1025','未知/会话后续'),('1114','战报详情'),('111f','战报参战方'),('1800','登录后同步'),('3110','心跳/状态'),('1130','成长任务'),('6200','日常任务'),('6202','签到领奖'),('6287','未知确认'),('3940','活动列表'),('3941','活动详情'),('1008','地图分页'),('6444','地图确认'),('1012','城池详情'),('041540','找黄'),('1520030','刷黄prepare'),('1522030','刷黄出征'),('01190000','闯关状态')]
    hits=[op+' '+name for op,name in known if op.lower() in h]
    return ' + '.join(hits) if hits else '未知'

def parse_flows():
    global LAST_SIZE,LAST_TS
    if not PCAP.exists() or PCAP.stat().st_size<=24:
        return []
    size=PCAP.stat().st_size
    if size!=LAST_SIZE and time.time()-LAST_TS>2:
        ANALYZED.mkdir(parents=True, exist_ok=True)
        run(['python3', str(PARSE), str(PCAP), str(ANALYZED)], timeout=10)
        LAST_SIZE=size; LAST_TS=time.time()
    jf=ANALYZED/'game_http_flows.json'
    if not jf.exists(): return []
    try:
        data=json.loads(jf.read_text(encoding='utf-8'))
        for f in data:
            rh=ANALYZED/(f"{f['index']:03d}")/'req.hex'
            req_hex=rh.read_text()[:400] if rh.exists() else ''
            f['opcodeGuess']=opcode_guess(f.get('requestTailHex',''), req_hex)
        return data[-60:]
    except Exception:
        return []

def api_status():
    size=PCAP.stat().st_size if PCAP.exists() else 0
    lines=[]
    if size>24:
        out=run(['tcpdump','-nn','-tttt','-r',str(PCAP)], timeout=8)
        lines=[x for x in out.splitlines() if x and 'reading from file' not in x]
    return {'ok':True,'ts':time.strftime('%Y-%m-%d %H:%M:%S'),'captureDir':str(CAP),'pcap':str(PCAP),'phoneIp':PHONE_IP,'game':'118.89.111.11:25511','size':size,'packetCount':len(lines),'packets':lines[-100:],'flows':parse_flows()}

HTML='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>帝王三国实时被动抓包</title><style>
body{margin:0;background:#0b1020;color:#e5e7eb;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",Arial,sans-serif}header{background:#111827;padding:18px 24px;border-bottom:1px solid #374151}h1{margin:0;font-size:22px}.sub{color:#9ca3af;margin-top:6px}.wrap{padding:16px 24px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.card{background:#111827;border:1px solid #374151;border-radius:12px;padding:12px}.k{color:#9ca3af;font-size:12px}.v{font-size:18px;font-weight:700;margin-top:4px}.panel{background:#111827;border:1px solid #374151;border-radius:12px;margin-top:14px;overflow:hidden}.panel h2{font-size:16px;margin:0;padding:10px 12px;border-bottom:1px solid #374151}table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid #263244;padding:7px;text-align:left;vertical-align:top}th{background:#0f172a;color:#93c5fd}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:pre-wrap}.packets{max-height:380px;overflow:auto;padding:10px;font-size:12px}.pill{background:#1e3a8a;color:#dbeafe;border-radius:999px;padding:2px 8px;display:inline-block}.muted{color:#9ca3af}code{color:#bfdbfe}.preview{color:#d1fae5;max-width:700px}.blink{animation:blink .5s}@keyframes blink{from{outline:3px solid #10b981}to{outline:none}}</style></head><body><header><h1>帝王三国实时被动抓包</h1><div class="sub">Mac 热点 bridge100 被动监听；不走代理 / 不走 mitm；目标 118.89.111.11:25511</div></header><div class="wrap"><div class="cards"><div class="card"><div class="k">更新时间</div><div id="ts" class="v">-</div></div><div class="card"><div class="k">PCAP大小</div><div id="size" class="v">-</div></div><div class="card"><div class="k">包数量</div><div id="count" class="v">-</div></div><div class="card"><div class="k">手机 → 游戏服</div><div id="target" class="v">-</div></div></div><div class="panel"><h2>解析到的 HTTPClient 业务包</h2><table><thead><tr><th>#</th><th>请求</th><th>响应</th><th>接口猜测</th><th>响应文本预览</th><th>请求尾部</th></tr></thead><tbody id="flows"><tr><td colspan="6" class="muted">等待游戏业务包...</td></tr></tbody></table></div><div class="panel"><h2>最近原始 TCP 包</h2><div id="packets" class="packets mono muted">等待数据...</div></div><div class="panel"><h2>文件位置</h2><div id="paths" class="packets mono"></div></div></div><script>
let last='';function fmt(n){n=n||0;if(n<1024)return n+' B';if(n<1048576)return (n/1024).toFixed(1)+' KB';return (n/1048576).toFixed(2)+' MB'}function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}async function tick(){try{let r=await fetch('/api/status?'+Date.now(),{cache:'no-store'});let d=await r.json();if(!d.ok&&d.error){packets.textContent='后端解析异常：'+d.error+'\\n'+(d.trace||'');return}ts.textContent=d.ts||'-';size.textContent=fmt(d.size);count.textContent=d.packetCount??'-';target.innerHTML='<span class="pill">'+esc(d.phoneIp)+'</span> → <span class="pill">'+esc(d.game)+'</span>';paths.textContent='captureDir: '+(d.captureDir||'')+'\\npcap: '+(d.pcap||'');packets.textContent=(d.packets||[]).join('\\n')||'等待数据...';if(d.flows&&d.flows.length){flows.innerHTML=d.flows.slice().reverse().map(f=>'<tr><td>'+esc(f.index)+'</td><td>'+esc(f.requestLength??'-')+' B</td><td>'+esc(f.responseLength??'-')+' B</td><td><span class="pill">'+esc(f.opcodeGuess||'未知')+'</span></td><td class="preview">'+esc(f.responseTextPreview||'')+'</td><td><code>'+esc(f.requestTailHex||'')+'</code></td></tr>').join('')}else flows.innerHTML='<tr><td colspan="6" class="muted">等待游戏业务包...</td></tr>';if(String(d.packetCount)!==last){document.body.classList.add('blink');setTimeout(()=>document.body.classList.remove('blink'),300);last=String(d.packetCount)}}catch(e){packets.textContent='读取失败：'+e+'\\n如果这里持续出现，请确认 8090 后端进程是否还在。'}}setInterval(tick,2000);tick();
</script></body></html>'''

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
    def do_GET(self):
        try:
            if urllib.parse.urlparse(self.path).path=='/api/status':
                payload=api_status()
                b=json.dumps(payload,ensure_ascii=False).encode('utf-8')
                self.send_response(200); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
            else:
                b=HTML.encode('utf-8')
                self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
        except Exception as e:
            traceback.print_exc()
            b=json.dumps({'ok':False,'error':str(e),'trace':traceback.format_exc()},ensure_ascii=False).encode('utf-8')
            try:
                self.send_response(500); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
            except Exception:
                pass

if __name__=='__main__':
    port=int(os.environ.get('PORT','8090'))
    class Server(http.server.ThreadingHTTPServer):
        allow_reuse_address=True
    print('Live viewer: http://127.0.0.1:%d/'%port, flush=True)
    Server(('127.0.0.1',port),Handler).serve_forever()
