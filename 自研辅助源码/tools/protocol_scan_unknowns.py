#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scan parsed passive pcap HTTPClient flows and report request candidates not yet in protocol_requests.yaml.
Usage:
  python3 tools/protocol_scan_unknowns.py <analyzed_dir>
"""
from __future__ import annotations
import json, pathlib, re, sys
try:
    import yaml
except Exception as exc:
    raise SystemExit('需要 PyYAML') from exc

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROTO = ROOT / 'docs' / 'protocol'
REQ_YAML = PROTO / 'protocol_requests.yaml'
KNOWN = set()
req_doc = yaml.safe_load(REQ_YAML.read_text('utf-8'))
for r in req_doc.get('requests', []):
    op = str(r.get('opcode') or '').lower().replace('+','')
    if re.fullmatch(r'[0-9a-f]+', op):
        # compound opcodes are handled by substring scan too
        KNOWN.add(op)

def candidate_ops(req_hex: str):
    h = req_hex.lower()
    hits = sorted([op for op in KNOWN if op and op in h], key=len, reverse=True)
    # common shape: ... 00000000000000000001/02 + opcode + params
    cands = re.findall(r'000000000000000000(?:00|01|02|08)([0-9a-f]{4})(?:0000)?', h)
    # also command-like marker after command length in login-ish packets
    cands += re.findall(r'000000[0-9a-f]{2}([0-9a-f]{4})0000', h)
    return hits, list(dict.fromkeys(cands))

def main():
    analyzed = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path.cwd()
    flows_path = analyzed / 'game_http_flows.json'
    if not flows_path.exists():
        raise SystemExit(f'缺少 {flows_path}')
    flows = json.loads(flows_path.read_text('utf-8'))
    unknown = {}
    for f in flows:
        idx = int(f['index'])
        req_hex_path = analyzed / f'{idx:03d}' / 'req.hex'
        if not req_hex_path.exists():
            continue
        req_hex = req_hex_path.read_text().strip().lower()
        hits, cands = candidate_ops(req_hex)
        new_cands = [c for c in cands if c not in KNOWN]
        if not hits and new_cands:
            key = (','.join(new_cands[:4]), f.get('requestLength'), f.get('responseLength'), (f.get('responseTextPreview') or '')[:80])
            unknown.setdefault(key, []).append(idx)
    print(f'known_opcodes={len(KNOWN)} flows={len(flows)} unknown_groups={len(unknown)}')
    for (cands, req_len, resp_len, text), idxs in sorted(unknown.items(), key=lambda x: x[1][0]):
        print(f'idxs={idxs} candidates={cands} reqLen={req_len} respLen={resp_len} text={text}')

if __name__ == '__main__':
    main()
