#!/usr/bin/env python3
import argparse, html, json, re, struct, subprocess, sys, time, urllib.request, urllib.error, urllib.parse, ssl
from pathlib import Path

HEADER = '1660606`7054`0000480502'

PASSPORT = 'https://sglmpass.3gking.net:12443/'
CHANNEL_NUM = '0000480502'
SOURCE = 'diwang.sanguo'
GAME_KEY = 'diwang.sanguo'
CTYPE = '7054'
VERSION = '1660606'
TARGETS = '1,2,3,5,11,12,13,14,15,16,17,18,19,20,21,31,32,33,34,41,91'

def http_get(base, params):
    url = base + '?' + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, context=ssl._create_unverified_context(), timeout=20) as r:
        return r.read().decode('utf-8', errors='ignore')

def parse_utf_payload(payload, p):
    ln = int.from_bytes(payload[p:p+2], 'big'); p += 2
    return payload[p:p+ln].decode('utf-8', errors='ignore'), p+ln

def parse8003(payload):
    p=0
    status = struct.unpack('>b', payload[p:p+1])[0]; p+=1
    msg,p = parse_utf_payload(payload,p)
    dm = struct.unpack('>q', payload[p:p+8])[0]; p+=8
    selected=0; roles=[]
    if status == 0:
        p += 8
        selected = struct.unpack('>i', payload[p:p+4])[0]; p += 4
        count = struct.unpack('>i', payload[p:p+4])[0]; p += 4
        for _ in range(count):
            rid = struct.unpack('>q', payload[p:p+8])[0]; p += 8
            p += 2
            name,p = parse_utf_payload(payload,p)
            level = struct.unpack('>b', payload[p:p+1])[0]; p += 1
            country,p = parse_utf_payload(payload,p)
            title,p = parse_utf_payload(payload,p)
            roles.append({'roleId':rid,'roleName':name,'level':level,'country':country,'title':title})
    return {'status':status,'message':msg,'dm':dm,'selected':selected,'roles':roles}

def fresh_login(username, password, server_query='周年服351区'):
    text = http_get(PASSPORT+'common/area/list.action', dict(username=username,password=password,channelId=CHANNEL_NUM,source=SOURCE,cType=CTYPE,cVersion=VERSION,gameKey=GAME_KEY,target=TARGETS))
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    head = lines[0].split('`')
    session, user_id = head[0], head[1]
    areas=[]
    for line in lines[1:]:
        p=line.split('`')
        if len(p)>=12:
            areas.append({'target':p[0],'areaId':p[1],'areaName':p[2],'serverUrl':p[3],'serverKey':p[11],'raw':line})
    area = next((a for a in areas if server_query in a['areaName'] or '351' in a['areaName'] or a['serverKey']=='qzone_351'), None)
    if not area: raise RuntimeError('area not found')
    enter = http_get(PASSPORT+'common/area/enter.action', dict(session=session, areaKey=area['serverKey'])).strip()
    if enter != '1': raise RuntimeError('enter area failed: '+enter)
    game_http = area['serverUrl'].rstrip('/') + '/kingWapServer/HttpClient'
    login_payload = utf(user_id) + utf(session) + utf(CHANNEL_NUM)
    code,data,packets = post_game(game_http, [(0x1003, login_payload)], 0)
    p8003 = next((p for p in packets if p.get('opcode') == 0x8003), None)
    if not p8003: raise RuntimeError('0x1003 no 0x8003: '+str(summarize_packets(packets)))
    info = parse8003(p8003['payload'])
    if info['status'] != 0: raise RuntimeError('login status failed: '+info['message'])
    role = info['roles'][max(0, info['selected'])] if info['roles'] else None
    if not role: raise RuntimeError('no role')
    # init role once to bind dm/role context
    post_game(game_http, [(0x1004, struct.pack('>q', -1))], info['dm'])
    code2,data2,packets2 = post_game(game_http, [(0x1016, struct.pack('>q', role['roleId']))], info['dm'])
    return {'gameHttp': game_http, 'dm': info['dm'], 'role': role, 'area': area, 'session': session, 'userId': user_id, 'initOpcodes':[f"0x{p['opcode']:04x}" for p in packets2 if 'opcode' in p]}

KIND_MARKERS = {
    'E5B1B1E8B38A': '山贼',
    'E5B1B1E8B4BC': '山贼',
    'E9BB83E5B7BE': '黄巾',
    'E9BB84E5B7BE': '黄巾',
    'E6B8A0E5B885': '渠帅',
    'E6B8A0E5B8A5': '渠帅',
    'E4B8BBE5B086': '主将',
    'E4B8BBE5B087': '主将',
    'E4B8BBE5B885': '主帅',
    'E4B8BBE5B8A5': '主帅',
}

def adb_run_as_cat(path):
    return subprocess.check_output(['adb','shell','run-as','com.example.dwpmclone','cat',path], text=True, errors='ignore')

def load_session():
    raw = adb_run_as_cat('shared_prefs/dwpm_clone_accounts.xml')
    m = re.search(r'<string name="accounts_json">(.*?)</string>', raw, re.S)
    if not m:
        raise SystemExit('accounts_json not found; 请先在自研 app 登录')
    root = json.loads(html.unescape(m.group(1)))
    account = root['accounts'][0]
    sess = account['session']
    extra = sess['channelExtra']
    return account, sess, extra

def utf(s):
    b=s.encode('utf-8')
    return struct.pack('>H', len(b))+b

def make_packet(commands, dm):
    out=bytearray()
    out += utf(HEADER)
    out += struct.pack('>q', int(time.time()*1000))
    out += struct.pack('>B', len(commands))
    for opcode, payload in commands:
        out += struct.pack('>q', dm)
        out += struct.pack('>q', 0)
        out += struct.pack('>H', len(payload))
        out += struct.pack('>H', opcode)
        out += utf('')
        out += payload
    return bytes(out)

def post_game(url, commands, dm):
    body = make_packet(commands, dm)
    req = urllib.request.Request(url, data=body, method='POST', headers={
        'Content-Type':'application/octet-stream',
        'User-Agent':'DWPMClone/1.0 direct-binary-probe',
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read(); code = r.status
    except urllib.error.HTTPError as e:
        data = e.read(); code = e.code
    return code, data, parse_response(data)

def parse_response(data):
    p=0; packets=[]
    def need(n):
        nonlocal p
        if p+n>len(data): raise ValueError(f'parse overflow pos={p} need={n} size={len(data)}')
    def u8():
        nonlocal p; need(1); v=data[p]; p+=1; return v
    def i64():
        nonlocal p; need(8); v=struct.unpack('>q', data[p:p+8])[0]; p+=8; return v
    def i32():
        nonlocal p; need(4); v=struct.unpack('>i', data[p:p+4])[0]; p+=4; return v
    def u16():
        nonlocal p; need(2); v=struct.unpack('>H', data[p:p+2])[0]; p+=2; return v
    try:
        outer=u8()
        for oi in range(outer):
            inner=u8()
            for ii in range(inner):
                long0=i64(); long1=i64(); obf=u8(); ln=i32(); op=u16(); frag=u8(); need(ln); payload=data[p:p+ln]; p+=ln
                packets.append({'outer':oi,'inner':ii,'long0':long0,'long1':long1,'obf':obf,'len':ln,'opcode':op,'frag':frag,'payload':payload})
    except Exception as e:
        packets.append({'parseError':str(e), 'rawHex':data.hex()[:2048]})
    return packets

def printable(bs, limit=512):
    s = bs.decode('utf-8', errors='ignore')
    s = ''.join(ch if (0x20 <= ord(ch) <= 0x7e or '\u4e00' <= ch <= '\u9fff') else ' ' for ch in s)
    return re.sub(r'\s+', ' ', s).strip()[:limit]

def encode_xy(x,y): return f'{x:04x}{y:04x}'

def read_only_gamehex_to_cmd(gamehex):
    body = gamehex[18:]
    declared = int(body[:2],16); op = int(body[2:6],16); payload = bytes.fromhex(body[6:])
    assert len(payload)==declared, (gamehex, declared, len(payload))
    return op,payload

def action_gamehex_to_cmd(gamehex):
    # 小黄点 shape: 18 zero prefix + one-byte len + two-byte opcode + payload.
    body = gamehex[18:]
    declared = int(body[:2],16); op = int(body[2:6],16); payload = bytes.fromhex(body[6:])
    return declared, op, payload

def scan_targets(response_hex):
    norm = ''.join(c for c in response_hex.upper() if c in '0123456789ABCDEF')
    out=[]
    for marker, kind in KIND_MARKERS.items():
        start=0
        while True:
            idx=norm.find(marker, start)
            if idx<0: break
            for prefix in (26,24,22,20,18):
                s=idx-prefix
                if s<0: continue
                rec=norm[s:idx+len(marker)]
                if len(rec)<20: continue
                try:
                    id_hex=rec[:12]; tid=int(id_hex,16)
                    rank={'渠帅':11,'主将':12,'主帅':13}.get(kind,0)
                    # Same tolerant coordinate heuristic as Kotlin parser.
                    pairs=[(idx-s-8, idx-s-4, idx-s-4, idx-s), (18,22,22,26), (12,16,16,20)]
                    x=y=0
                    for a,b,c,d in pairs:
                        if a>=0 and d<=len(rec):
                            xx=int(rec[a:b],16); yy=int(rec[c:d],16)
                            if 0<=xx<=9999 and 0<=yy<=9999:
                                x,y=xx,yy; break
                    if tid>0:
                        out.append({'id':tid,'idHex':id_hex.lower(),'kind':kind,'rank':rank,'x':x,'y':y,'rawRecord':rec})
                        break
                except Exception:
                    pass
            start=idx+len(marker)
    # dedupe
    seen=set(); res=[]
    for t in out:
        k=(t['id'],t['kind'],t['x'],t['y'])
        if k not in seen:
            seen.add(k); res.append(t)
    return res

def recover_generals_from_8004(hexstr):
    bs=bytes.fromhex(hexstr)
    res=[]
    for pos in range(8, len(bs)-2):
        ln=int.from_bytes(bs[pos:pos+2],'big')
        if not (2<=ln<=24) or pos+2+ln>len(bs): continue
        name=bs[pos+2:pos+2+ln].decode('utf-8', errors='ignore').strip()
        if not name or len(name)>8: continue
        if sum('\u4e00' <= ch <= '\u9fff' for ch in name)<1: continue
        if not all(('\u4e00' <= ch <= '\u9fff') or ch.isalnum() or ch=='·' for ch in name): continue
        gid=int.from_bytes(bs[pos-8:pos],'big')
        if gid<=0: continue
        status=bs[pos+2+ln] if pos+2+ln<len(bs) else None
        tili=bs[pos+2+ln+1] if pos+2+ln+1<len(bs) else None
        res.append({'id':gid,'idHex':f'{gid:016x}','name':name,'status':status,'tili':tili,'offset':pos})
    # focus on plausible general id range; dedupe
    seen=set(); out=[]
    for g in res:
        if g['id'] in seen: continue
        seen.add(g['id']); out.append(g)
    return out

def build_brush_payloads(general_chunks, target_hex):
    n=len(general_chunks); ids=''.join(general_chunks); prefix='0'*18
    prepare = prefix + f'{n*8+0x0a:x}' + '1520030' + str(n) + ids + '0000' + target_hex
    expedition = prefix + f'{n*8+0x15:x}' + '1522030' + str(n) + ids + '0000' + target_hex + 'ffffffffffffffff000000'
    return prepare, expedition

def action_target_hex(target):
    raw = ''.join(c for c in str(target.get('rawRecord') or '') if c in '0123456789abcdefABCDEF').lower()
    if len(raw) >= 18:
        # Same live-calibrated rule as SessionAwareGameProtocolClient.actionTargetHex:
        # use the first 18 chars of the 041540 record and take the trailing 16 as the
        # expedition target id. This is the variant that produced a real 0x8522 battle
        # response in reports/direct_binary_action_probe_targetid_candidates_*.json.
        return raw[:18][-16:]
    return str(target.get('targetIdHex') or target.get('idHex') or target.get('targetHex') or format(int(target['id']), 'x')).removeprefix('0x').removeprefix('0X').rjust(16, '0').lower()

def summarize_packets(packets):
    arr=[]
    for p in packets:
        if 'parseError' in p:
            arr.append(p); continue
        payload=p['payload']
        arr.append({'opcode':f"0x{p['opcode']:04x}", 'len':p['len'], 'frag':p['frag'], 'payloadHex':payload.hex()[:2048], 'textPreview':printable(payload)})
    return arr

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--do-action', action='store_true')
    ap.add_argument('--scan-limit', type=int, default=80)
    ap.add_argument('--start-x', type=int, default=0)
    ap.add_argument('--start-y', type=int, default=0)
    ap.add_argument('--target-kind', default='黄巾')
    ap.add_argument('--target-index', type=int, default=0, help='index inside filtered/found target list; useful when the first live target returns ff0000')
    ap.add_argument('--general-index', type=int, default=0, help='index inside plausible 0x8004 general candidates')
    ap.add_argument('--out', default='reports/direct_binary_action_probe.json')
    ap.add_argument('--fresh-login', action='store_true')
    ap.add_argument('--username', default='1608600')
    ap.add_argument('--password', default=None)
    args=ap.parse_args()
    account,sess,extra=load_session()
    fresh = None
    if args.fresh_login:
        if not args.password:
            raise SystemExit('--fresh-login requires --password')
        fresh = fresh_login(args.username, args.password)
        url = fresh['gameHttp']; dm = int(fresh['dm'])
        extra = dict(extra); extra['gameHttp'] = url; extra['dm'] = str(dm); extra['roleId'] = str(fresh['role']['roleId']); extra['roleName'] = fresh['role']['roleName']
    else:
        url=extra['gameHttp']; dm=int(extra['dm'])
    generals=recover_generals_from_8004(extra['state8004PayloadHex'])
    plausible=[g for g in generals if 1000000 <= g['id'] <= 200000000 and not any(bad in g['name'] for bad in ['基地','封地','洛阳','太祥'])]
    general_pool=plausible or generals
    chosen=general_pool[min(max(args.general_index, 0), len(general_pool)-1)]
    report={'time':int(time.time()*1000),'accountId':account['id'],'roleName':extra.get('roleName'),'url':url,'dm':dm,
            'chosenGeneral':chosen,'generalSelection': {'generalIndex': args.general_index, 'selectableCount': len(general_pool)}, 'generalCandidates':plausible[:20], 'scan':[], 'actionAttempted':False, 'freshLogin': bool(fresh), 'freshLoginInfo': ({'role': fresh['role'], 'areaName': fresh['area']['areaName'], 'initOpcodes': fresh['initOpcodes']} if fresh else None)}
    print(f"[session] role={extra.get('roleName')} url={url} dm={dm}")
    print(f"[general] chosen={chosen}")
    coords=[]
    # scan around configured/default grid first, then from 0,0 grid.
    for x in range(args.start_x, 187, 6):
        for y in range(args.start_y, 67, 6):
            coords.append((x,y))
    coords=coords[:args.scan_limit]
    found=[]
    for i,(x,y) in enumerate(coords,1):
        gh='0'*18+'041540'+encode_xy(x,y)
        op,payload=read_only_gamehex_to_cmd(gh)
        code,data,packets=post_game(url, [(op,payload)], dm)
        resp_hex=''.join(p['payload'].hex() for p in packets if 'payload' in p)
        targets=scan_targets(resp_hex)
        item={'coord':[x,y],'http':code,'opcodes':[f"0x{p['opcode']:04x}" for p in packets if 'opcode' in p], 'targetCount':len(targets), 'targets':targets[:5]}
        report['scan'].append(item)
        print(f"[scan {i}/{len(coords)}] {x},{y} http={code} targets={len(targets)}")
        if targets:
            found=targets; break
        time.sleep(0.15)
    if not found:
        report['error']='no target found in scan limit'
        Path(args.out).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f"[stop] no target found; report={args.out}")
        return 2
    preferred=[t for t in found if args.target_kind in t['kind'] or t['kind'] in args.target_kind]
    selectable=preferred or found
    target=selectable[min(max(args.target_index, 0), len(selectable)-1)]
    report['chosenTarget']=target
    report['targetSelection']={'targetKind': args.target_kind, 'targetIndex': args.target_index, 'selectableCount': len(selectable), 'preferredCount': len(preferred)}
    print(f"[target] chosen={target}")
    gen_chunks=[chosen['idHex']]
    target_hex=action_target_hex(target)
    prepare, expedition=build_brush_payloads(gen_chunks, target_hex)
    report['payloads']={'prepareGameHex':prepare,'expeditionGameHex':expedition,'targetHex':target_hex,'generalChunks':gen_chunks}
    for name,gh in [('prepare',prepare),('expedition',expedition)]:
        declared,op,payload=action_gamehex_to_cmd(gh)
        report['payloads'][name+'BinaryMapping']={'declaredLen':declared,'opcode':f'0x{op:04x}','payloadHex':payload.hex(),'payloadLen':len(payload)}
    if not args.do_action:
        report['note']='dry-run only; pass --do-action to send 1520030/1522030 as binary GameCommand'
        Path(args.out).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f"[dry-run] report={args.out}")
        return 0
    report['actionAttempted']=True
    action_results=[]
    for name, gh in [('prepare',prepare),('expedition',expedition)]:
        declared,op,payload=action_gamehex_to_cmd(gh)
        print(f"[action] sending {name} opcode=0x{op:04x} declared={declared} payloadLen={len(payload)}")
        code,data,packets=post_game(url, [(op,payload)], dm)
        summary=summarize_packets(packets)
        print(f"[action] {name} http={code} packets={[(s.get('opcode'),s.get('len'),s.get('textPreview')) for s in summary]}")
        action_results.append({'phase':name,'http':code,'responseBytes':len(data),'packets':summary})
        time.sleep(0.8)
    report['actionResults']=action_results
    Path(args.out).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"[done] report={args.out}")
    return 0

if __name__=='__main__':
    sys.exit(main())
