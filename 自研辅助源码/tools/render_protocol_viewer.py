#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render docs/protocol/protocol_viewer.html from YAML source files."""
from __future__ import annotations
import html
import pathlib
import sys

try:
    import yaml
except Exception as exc:
    raise SystemExit("需要 PyYAML：python3 -m pip install pyyaml") from exc

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROTO = ROOT / "docs" / "protocol"
REQ = PROTO / "protocol_requests.yaml"
DICT = PROTO / "protocol_field_dictionary.yaml"
OUT = PROTO / "protocol_viewer.html"

def esc(x):
    return html.escape("" if x is None else str(x))

def confidence_class(c):
    return {
        "confirmed": "ok",
        "high": "ok",
        "medium": "warn",
        "low": "bad",
    }.get(str(c), "muted")

def render():
    req = yaml.safe_load(REQ.read_text(encoding="utf-8"))
    dic = yaml.safe_load(DICT.read_text(encoding="utf-8"))
    requests = req.get("requests", [])
    schemas = dic.get("schemas", [])
    schema_by_req = {}
    for s in schemas:
        schema_by_req.setdefault(s.get("requestId") or s.get("opcode") or "unknown", []).append(s)

    cards = []
    for r in requests:
        rid = r.get("id")
        known = r.get("request", {}).get("knownShape", [])
        fields_html = "".join(
            f"<tr><td>{esc(f.get('field'))}</td><td>{esc(f.get('label'))}</td><td>{esc(f.get('type'))}</td><td><code>{esc(f.get('value') or f.get('example') or f.get('formula') or '')}</code></td><td><span class='pill {confidence_class(f.get('confidence'))}'>{esc(f.get('confidence'))}</span></td></tr>"
            for f in known
        ) or "<tr><td colspan='5' class='muted'>暂无 knownShape</td></tr>"
        strings = r.get("response", {}).get("observedStrings", [])
        strings_html = "".join(f"<span class='tag'>{esc(s)}</span>" for s in strings[:20]) or "<span class='muted'>暂无</span>"
        evidence = r.get("evidence", {})
        cap_count = len(evidence.get("captures", []) or [])
        rep_count = len(evidence.get("reverseReports", []) or []) + len(evidence.get("runtimeReports", []) or [])
        cards.append(f"""
        <section class="card" data-opcode="{esc(r.get('opcode'))}" data-status="{esc(r.get('status'))}">
          <div class="card-head">
            <div><h2>{esc(r.get('label'))}</h2><p>{esc(r.get('name'))} · <code>{esc(r.get('id'))}</code></p></div>
            <div class="opcode">{esc(r.get('opcode'))}</div>
          </div>
          <div class="meta">
            <span>状态：<b>{esc(r.get('status'))}</b></span>
            <span>置信度：<b>{esc(r.get('confidence'))}</b></span>
            <span>endpoint：<b>{esc(r.get('endpoint'))}</b></span>
            <span>证据：抓包 {cap_count} / 报告 {rep_count}</span>
          </div>
          <details open><summary>请求字段</summary><table><thead><tr><th>field</th><th>中文</th><th>类型</th><th>值/示例/公式</th><th>置信度</th></tr></thead><tbody>{fields_html}</tbody></table></details>
          <details><summary>响应关键内容</summary><div class="tags">{strings_html}</div><p class="muted">parserStatus: {esc(r.get('response', {}).get('parserStatus'))}</p></details>
        </section>""")

    schema_cards = []
    for s in schemas:
        fields = s.get("fields", [])
        if not fields and s.get("repeatedGroups"):
            for g in s.get("repeatedGroups", []):
                fields.extend(g.get("fields", []))
        fields_html = "".join(
            f"<tr><td>{esc(f.get('id'))}</td><td>{esc(f.get('label'))}</td><td>{esc(f.get('type'))}</td><td>{esc(f.get('offset') or f.get('offsetRange') or '')}</td><td><code>{esc(f.get('value') or f.get('example') or f.get('formula') or '')}</code></td><td><span class='pill {confidence_class(f.get('confidence'))}'>{esc(f.get('confidence'))}</span></td></tr>"
            for f in fields
        ) or "<tr><td colspan='6' class='muted'>暂无字段</td></tr>"
        schema_cards.append(f"""
        <section class="card schema" data-opcode="{esc(s.get('opcode'))}" data-status="{esc(s.get('status'))}">
          <div class="card-head"><div><h2>{esc(s.get('id'))}</h2><p>{esc(s.get('direction'))} · {esc(s.get('status'))}</p></div><div class="opcode">{esc(s.get('opcode'))}</div></div>
          <table><thead><tr><th>id</th><th>中文</th><th>类型</th><th>offset</th><th>值/示例/公式</th><th>置信度</th></tr></thead><tbody>{fields_html}</tbody></table>
        </section>""")

    html_doc = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>帝王三国协议视图</title>
<style>
body{{margin:0;background:#eef2f7;color:#1f2937;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",Arial,sans-serif}}
header{{background:#0f3f8f;color:white;padding:22px 28px}} h1{{margin:0;font-size:26px}} header p{{margin:8px 0 0;color:#dbeafe}}
main{{max-width:1180px;margin:0 auto;padding:18px}} .toolbar{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}}
input,select{{height:36px;border:1px solid #cbd5e1;border-radius:8px;padding:0 10px;background:white}}
.card{{background:white;border:1px solid #d8e0ea;border-radius:14px;padding:16px;margin:12px 0;box-shadow:0 2px 10px rgba(15,23,42,.06)}}
.card-head{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}} h2{{margin:0;font-size:19px}} .card p{{margin:5px 0;color:#64748b}}
.opcode{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;border-radius:10px;padding:8px 10px;font-weight:800}}
.meta{{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}} .meta span{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:999px;padding:5px 9px;font-size:12px}}
table{{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px}} th,td{{border-bottom:1px solid #e5e7eb;text-align:left;padding:8px;vertical-align:top}} th{{background:#f8fafc;color:#475569}}
code{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}} summary{{cursor:pointer;font-weight:700;margin-top:8px}}
.pill{{border-radius:999px;padding:3px 7px;font-size:11px}} .pill.ok{{background:#dcfce7;color:#166534}} .pill.warn{{background:#fff7ed;color:#9a3412}} .pill.bad{{background:#fee2e2;color:#991b1b}} .pill.muted{{background:#f1f5f9;color:#64748b}}
.tag{{display:inline-block;background:#eef2ff;color:#3730a3;border-radius:999px;padding:5px 8px;margin:3px;font-size:12px}} .muted{{color:#64748b}} .section-title{{margin:24px 0 8px;font-size:23px}}
.footer{{color:#64748b;font-size:12px;margin:24px 0}} .hidden{{display:none}}
</style></head><body>
<header><h1>帝王三国协议视图</h1><p>数据源：<code>protocol_requests.yaml</code> + <code>protocol_field_dictionary.yaml</code>。本 HTML 由 <code>tools/render_protocol_viewer.py</code> 生成。</p></header>
<main>
<div class="toolbar"><input id="q" placeholder="搜索 opcode / 名称 / 字段..." oninput="filterCards()"/><select id="kind" onchange="filterCards()"><option value="all">全部</option><option value="request">接口</option><option value="schema">字段字典</option></select></div>
<h2 class="section-title">接口列表</h2>
<div id="requests">{''.join(cards)}</div>
<h2 class="section-title">字段字典</h2>
<div id="schemas">{''.join(schema_cards)}</div>
<div class="footer">updatedAt: {esc(req.get('updatedAt'))}；sourceOfTruth: YAML。</div>
</main>
<script>
function filterCards(){{
  const q=document.getElementById('q').value.toLowerCase(); const kind=document.getElementById('kind').value;
  document.querySelectorAll('.card').forEach(c=>{{
    const isSchema=c.classList.contains('schema');
    const typeOk=kind==='all'||(kind==='schema'&&isSchema)||(kind==='request'&&!isSchema);
    const qOk=!q||c.textContent.toLowerCase().includes(q)||String(c.dataset.opcode||'').toLowerCase().includes(q);
    c.classList.toggle('hidden',!(typeOk&&qOk));
  }});
}}
</script></body></html>"""
    OUT.write_text(html_doc, encoding="utf-8")
    return OUT

if __name__ == "__main__":
    out = render()
    print(out)
