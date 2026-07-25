#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract 帝王三国 /kingWapServer/HttpClient HTTP bodies from a pcap.
Stdlib-only minimal parser: Ethernet/IPv4/TCP, TCP stream reassembly, HTTP Content-Length/chunked.
Usage:
  python3 parse_passive_pcap_httpclient.py <pcap> <out_dir> [--host IP ...] [--port 25511]
"""
from __future__ import annotations
import argparse, sys, struct, pathlib, json, re
DEFAULT_GAME_HOSTS=("118.89.111.11",)
GAME_PORT=25511
SERVER_LABELS={
    "118.89.111.11": "351区",
    "115.159.92.72": "352区",
}

def rd_pcap(path):
    data=path.read_bytes(); off=0
    if len(data)<24: return
    magic=data[:4]
    le = magic in (b'\xd4\xc3\xb2\xa1', b'\x4d\x3c\xb2\xa1')
    ns = magic in (b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d')
    endian='<' if le else '>'
    off=24
    while off+16<=len(data):
        ts_sec, ts_usec, incl, orig = struct.unpack_from(endian+'IIII', data, off); off+=16
        pkt=data[off:off+incl]; off+=incl
        yield ts_sec + ts_usec/(1_000_000_000 if ns else 1_000_000), pkt

def ipstr(b): return '.'.join(str(x) for x in b)
def parse_pkt(pkt):
    if len(pkt)<14: return None
    eth_type=struct.unpack('!H', pkt[12:14])[0]
    if eth_type!=0x0800: return None
    ip=pkt[14:]
    if len(ip)<20: return None
    ihl=(ip[0]&0x0f)*4
    if ip[0]>>4 !=4 or ip[9]!=6 or len(ip)<ihl+20: return None
    src=ipstr(ip[12:16]); dst=ipstr(ip[16:20])
    total=struct.unpack('!H', ip[2:4])[0]
    tcp=ip[ihl:total]
    if len(tcp)<20: return None
    sp,dp,seq,ack,off_flags=struct.unpack('!HHIIH', tcp[:14])
    doff=((off_flags>>12)&0xf)*4
    payload=tcp[doff:]
    if not payload: return None
    return src,dst,sp,dp,seq,payload

def dechunk(b):
    out=bytearray(); i=0
    while True:
        j=b.find(b'\r\n', i)
        if j<0: break
        line=b[i:j].split(b';',1)[0].strip()
        try: n=int(line,16)
        except Exception: break
        i=j+2
        if n==0: break
        if i+n>len(b): break
        out += b[i:i+n]
        i += n+2
    return bytes(out)

def parse_http_stream(raw, direction):
    items=[]; i=0
    while i < len(raw):
        if direction=='request':
            m=re.search(br'POST\s+/kingWapServer/HttpClient\s+HTTP/1\.[01]\r\n', raw[i:])
        else:
            m=re.search(br'HTTP/1\.[01]\s+200[^\r]*\r\n', raw[i:])
        if not m: break
        start=i+m.start(); h_end=raw.find(b'\r\n\r\n', start)
        if h_end<0: break
        head=raw[start:h_end].decode('iso-8859-1','replace')
        body_start=h_end+4
        clen=None; chunked=False
        for line in head.split('\r\n')[1:]:
            k,_,v=line.partition(':')
            if k.lower()=='content-length':
                try: clen=int(v.strip())
                except: pass
            if k.lower()=='transfer-encoding' and 'chunked' in v.lower(): chunked=True
        if clen is not None:
            body=raw[body_start:body_start+clen]; end=body_start+clen
        elif chunked:
            # take until next HTTP marker, decode what we can
            nxt=raw.find(b'HTTP/1.', body_start+1) if direction=='response' else raw.find(b'POST ', body_start+1)
            block=raw[body_start: nxt if nxt>0 else len(raw)]
            body=dechunk(block); end=nxt if nxt>0 else len(raw)
        else:
            nxt=raw.find(b'HTTP/1.', body_start+1) if direction=='response' else raw.find(b'POST ', body_start+1)
            body=raw[body_start:nxt if nxt>0 else len(raw)]; end=nxt if nxt>0 else len(raw)
        items.append({'headers':head,'body':body,'streamOffset':start})
        i=max(end, start+1)
    return items

def reassemble(parts):
    """Best-effort in-order TCP payload assembly with retransmission trimming."""
    if not parts:
        return b"", 0.0
    ordered=sorted(parts, key=lambda x:x[0])
    out=bytearray(); next_seq=None
    for seq,payload,_ts in ordered:
        if next_seq is None:
            out.extend(payload); next_seq=seq+len(payload); continue
        if seq < next_seq:
            overlap=next_seq-seq
            if overlap >= len(payload):
                continue
            payload=payload[overlap:]; seq=next_seq
        out.extend(payload)
        next_seq=seq+len(payload)
    return bytes(out), min(float(item[2]) for item in parts)


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pcap")
    p.add_argument("out_dir")
    p.add_argument("--host", action="append", dest="hosts",
                   help="游戏服IP，可重复；默认只解析351区")
    p.add_argument("--port", type=int, default=GAME_PORT)
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    pcap=pathlib.Path(args.pcap)
    out=pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    hosts=tuple(dict.fromkeys(args.hosts or DEFAULT_GAME_HOSTS))
    host_set=set(hosts); port=int(args.port)
    streams={}
    for ts,pkt in rd_pcap(pcap):
        x=parse_pkt(pkt)
        if not x: continue
        src,dst,sp,dp,seq,payload=x
        if not ((src in host_set or dst in host_set) and (sp==port or dp==port)):
            continue
        key=(src,sp,dst,dp)
        streams.setdefault(key,[]).append((seq,payload,ts))

    connections={}
    for key,parts in streams.items():
        src,sp,dst,dp=key
        if dst in host_set and dp==port:
            conn=(src,sp,dst,dp); direction="request"
        elif src in host_set and sp==port:
            conn=(dst,dp,src,sp); direction="response"
        else:
            continue
        connections.setdefault(conn,{})[direction]=parts

    parsed_connections=[]
    for conn,directions in connections.items():
        client,client_port,server,server_port=conn
        req_raw,req_ts=reassemble(directions.get("request") or [])
        resp_raw,resp_ts=reassemble(directions.get("response") or [])
        requests=parse_http_stream(req_raw,"request")
        responses=parse_http_stream(resp_raw,"response")
        if not requests and not responses:
            continue
        starts=[value for value in (req_ts,resp_ts) if value]
        parsed_connections.append({
            "connection": conn,
            "startedAt": min(starts) if starts else 0.0,
            "requests": requests,
            "responses": responses,
        })
    parsed_connections.sort(key=lambda item:item["startedAt"])

    summary=[]
    for parsed in parsed_connections:
        client,client_port,server,server_port=parsed["connection"]
        requests=parsed["requests"]; responses=parsed["responses"]
        for local_index in range(max(len(requests),len(responses))):
            index=len(summary)
            d=out/f'{index:03d}'; d.mkdir(exist_ok=True)
            rec={
                'index':index,
                'connectionIndex':local_index,
                'client':f'{client}:{client_port}',
                'serverHost':server,
                'serverPort':server_port,
                'serverLabel':SERVER_LABELS.get(server,server),
                'connectionStartedAt':parsed["startedAt"],
            }
            if local_index<len(requests):
                body=requests[local_index]['body']
                (d/'req.bin').write_bytes(body)
                (d/'req.hex').write_text(body.hex())
                rec['requestLength']=len(body)
                rec['requestTailHex']=body[-32:].hex()
            if local_index<len(responses):
                body=responses[local_index]['body']
                (d/'resp.bin').write_bytes(body)
                (d/'resp.hex').write_text(body.hex())
                txt=body.decode('utf-8','ignore')
                rec['responseLength']=len(body)
                rec['responseTextPreview']=' | '.join(
                    re.findall(r'[\u4e00-\u9fffA-Za-z0-9，。：；、“”《》（）\-\+\[\]/ ]{4,}',txt)[:10]
                )[:500]
            summary.append(rec)
    (out/'game_http_flows.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2), encoding='utf-8')
    counts={host:sum(1 for item in summary if item.get("serverHost")==host) for host in hosts}
    print(f'extracted {len(summary)} flows {counts} -> {out}')
if __name__=='__main__': raise SystemExit(main())
