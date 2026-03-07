#!/usr/bin/env python3
"""
Callgraph Studio — Function Documentation Generator

Generates browsable documentation of all functions with call graphs.
Two modes:
  - single: one self-contained HTML file
  - multi:  ZIP with index.html + per-function + per-module pages + CSS

Usage:
  CLI:   python3 generator.py graph.json -o docs.html --mode single
         python3 generator.py graph.json -o docs.zip --mode multi
  API:   POST /api/docs?mode=single  (or multi)
"""

import json, sys, os, io, zipfile, re
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# ── Helpers ──────────────────────────────────────────────────

def esc(s):
    return (s or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def _node_map(graph):
    return {n['id']: n for n in graph['nodes']}

MOD_COLORS = ['#2563eb','#16a34a','#dc2626','#7c3aed','#d97706','#0891b2',
              '#db2777','#ea580c','#65a30d','#c026d3','#0284c7','#ca8a04',
              '#059669','#e11d48','#6366f1','#a16207','#0d9488','#eab308']

def mod_color(mod, mods):
    mods_clean = [m for m in mods if m not in ('external','.')]
    idx = mods_clean.index(mod) if mod in mods_clean else 0
    return MOD_COLORS[idx % len(MOD_COLORS)]

def flag_badges(n):
    b = ''
    if n.get('is_isr'): b += '<span class="badge isr">ISR</span>'
    if n.get('is_entry'): b += '<span class="badge entry">entry</span>'
    if n.get('has_critical'): b += '<span class="badge crit">critical</span>'
    if n.get('delay_in_loop'): b += '<span class="badge poll">polling</span>'
    if n.get('peripherals'): b += '<span class="badge hw">hw</span>'
    return b

def mini_svg(fn, graph, nmap, mods):
    """Build a mini call graph SVG: callers → fn → callees (2-level)."""
    callers = (graph.get('callers',{}).get(fn,[]))[:8]
    callees = (graph.get('edges',{}).get(fn,[]))[:8]
    n = nmap.get(fn,{})

    NW, NH, HGAP, VGAP = 120, 26, 40, 8
    cols = [callers, [fn], callees]
    max_rows = max(len(c) for c in cols) if cols else 1
    W = 3*(NW+HGAP) + 40
    H = max(max_rows*(NH+VGAP)+40, 80)

    svg = f'<svg width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg" style="display:block;max-width:100%">\n'

    positions = {}
    for ci, col in enumerate(cols):
        x = 20 + ci*(NW+HGAP)
        col_h = len(col)*(NH+VGAP)
        y_off = (H - col_h)/2
        for ri, item in enumerate(col):
            y = y_off + ri*(NH+VGAP)
            nd = nmap.get(item,{})
            mod = nd.get('mod') or nd.get('module') or ''
            color = mod_color(mod, mods) if mod and mod not in ('external','.') else '#666'
            is_center = (ci == 1)
            sw = '2.5' if is_center else '1.5'
            fill = f'{color}1a' if not is_center else f'{color}22'
            stroke = '#fff' if is_center else color
            label = item if len(item) <= 14 else item[:12]+'…'

            svg += f'  <rect x="{x}" y="{y}" width="{NW}" height="{NH}" rx="5" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>\n'
            svg += f'  <text x="{x+NW/2}" y="{y+NH/2}" text-anchor="middle" dominant-baseline="middle" font-size="9" font-family="monospace" fill="{color}">{esc(label)}</text>\n'
            positions[item] = (x, y)

    # Arrows: callers → fn
    fx, fy = positions.get(fn, (0,0))
    for c in callers:
        cx, cy = positions.get(c, (0,0))
        svg += f'  <path d="M{cx+NW},{cy+NH/2} C{cx+NW+HGAP/2},{cy+NH/2} {fx-HGAP/2},{fy+NH/2} {fx},{fy+NH/2}" fill="none" stroke="#ef654880" stroke-width="1.2"/>\n'

    # Arrows: fn → callees
    for c in callees:
        cx, cy = positions.get(c, (0,0))
        svg += f'  <path d="M{fx+NW},{fy+NH/2} C{fx+NW+HGAP/2},{fy+NH/2} {cx-HGAP/2},{cy+NH/2} {cx},{cy+NH/2}" fill="none" stroke="#22c55e80" stroke-width="1.2"/>\n'

    svg += '</svg>'
    return svg


# ── CSS ──────────────────────────────────────────────────────

SHARED_CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0c0e14;--bg2:#12151e;--bg3:#181c28;--text:#dce0ec;--text2:#8890a8;--text3:#555a6c;--accent:#60a5fa;--border:#2a2f3e;--green:#4ade80;--red:#f87171;--amber:#fbbf24;--purple:#a78bfa;--cyan:#22d3ee;--font:'IBM Plex Mono',monospace}
.light{--bg:#f5f5f0;--bg2:#fff;--bg3:#eaeae2;--text:#1a1a18;--text2:#555;--text3:#888;--accent:#2563eb;--border:#c8c8bc;--green:#16a34a;--red:#dc2626;--amber:#d97706;--purple:#7c3aed;--cyan:#0891b2}
body{font-family:'DM Sans',sans-serif;font-size:13px;background:var(--bg);color:var(--text);line-height:1.6}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.container{max-width:1000px;margin:0 auto;padding:1.5rem}
h1{font-family:'Source Serif 4',Georgia,serif;font-size:1.6rem;margin-bottom:.3rem}
h2{font-family:'Source Serif 4',Georgia,serif;font-size:1.2rem;margin:1.5rem 0 .5rem;border-bottom:1px solid var(--border);padding-bottom:.3rem}
h3{font-size:.95rem;margin:.8rem 0 .3rem;color:var(--accent)}
.sub{font-size:.75rem;color:var(--text3);margin-bottom:1.5rem}
table{width:100%;border-collapse:collapse;font-size:.78rem;margin:.5rem 0}
th{text-align:left;padding:.4rem .5rem;border-bottom:2px solid var(--border);font-weight:500;color:var(--text2);font-size:.68rem;text-transform:uppercase}
td{padding:.35rem .5rem;border-bottom:1px solid var(--border)}
tr:hover td{background:var(--bg3)}
.fn-link{font-family:var(--font);color:var(--accent);cursor:pointer}
.fn-link:hover{text-decoration:underline}
.badge{display:inline-block;font-size:.58rem;padding:.1rem .3rem;border-radius:3px;margin-right:.2rem;font-family:var(--font)}
.badge.isr{background:#a78bfa22;color:#a78bfa}
.badge.entry{background:#60a5fa22;color:#60a5fa}
.badge.crit{background:#fbbf2422;color:#fbbf24}
.badge.poll{background:#f8717122;color:#f87171}
.badge.hw{background:#d9770622;color:#d97706}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:8px;margin:.6rem 0;overflow:hidden}
.card-hdr{display:flex;align-items:center;gap:.5rem;padding:.55rem .8rem;cursor:pointer}
.card-hdr:hover{background:var(--bg3)}
.card-arrow{font-size:.6rem;color:var(--text3);transition:transform .2s}
.card.open .card-arrow{transform:rotate(90deg)}
.card-title{font-family:var(--font);font-size:.85rem;font-weight:500;flex:1}
.card-body{display:none;padding:.6rem .8rem;border-top:1px solid var(--border);font-size:.78rem}
.card.open .card-body{display:block}
.meta-row{display:flex;gap:1.5rem;flex-wrap:wrap;margin-bottom:.4rem;font-size:.72rem;color:var(--text2)}
.meta-label{color:var(--text3);font-size:.62rem;text-transform:uppercase}
.list-inline{display:flex;flex-wrap:wrap;gap:.3rem;margin:.2rem 0}
.list-inline a,.list-inline span{font-family:var(--font);font-size:.72rem}
.graph-wrap{border:1px solid var(--border);border-radius:6px;padding:.4rem;margin:.5rem 0;overflow-x:auto;background:var(--bg)}
.search{width:100%;padding:.4rem .6rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-family:var(--font);font-size:.75rem;outline:none;margin-bottom:.8rem}
.search:focus{border-color:var(--accent)}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem}
.topbar button{background:none;border:1px solid var(--border);border-radius:4px;padding:.2rem .5rem;font-size:.65rem;color:var(--text2);cursor:pointer}
.topbar button:hover{border-color:var(--accent);color:var(--accent)}
.mod-tag{font-size:.62rem;padding:.1rem .35rem;border-radius:3px;font-family:var(--font)}
.section-label{font-size:.68rem;color:var(--text3);text-transform:uppercase;letter-spacing:.08em;margin:.6rem 0 .2rem}
.globals-list{font-family:var(--font);font-size:.7rem}
.globals-list .read{color:var(--accent)}.globals-list .write{color:var(--red)}.globals-list .rw{color:var(--amber)}
@media print{body{background:#fff;color:#000;font-size:11px}.card-body{display:block!important}.topbar button{display:none}}
"""


# ── Single-file generator ────────────────────────────────────

def build_single(graph):
    """Build one self-contained HTML with all functions."""
    nmap = _node_map(graph)
    mods = [m for m in graph.get('mods',[]) if m not in ('external','.')]
    proj_fns = sorted([n for n in graph['nodes'] if n.get('type')=='project'], key=lambda n: n['id'])
    proj_name = Path(graph.get('source','project')).name
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    edges = graph.get('edges',{})
    callers = graph.get('callers',{})
    races_by_fn = defaultdict(list)
    for r in graph.get('races',[]):
        races_by_fn[r.get('task_fn','')].append(r)
        for iw in r.get('isr_writers',[]): races_by_fn[iw].append(r)

    html = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(proj_name)} — Function Documentation</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>{SHARED_CSS}</style></head><body>
<div class="container">
<div class="topbar">
  <div><h1>{esc(proj_name)}</h1><div class="sub">{len(proj_fns)} functions · {len(mods)} modules · {graph.get("files",0)} files · {now}</div></div>
  <div><button onclick="document.body.classList.toggle('light')">◐ Theme</button> <button onclick="window.print()">⎙ Print</button>
  <button onclick="expandAll()">▶ All</button> <button onclick="collapseAll()">▼ All</button></div>
</div>
<input class="search" id="search" placeholder="Search functions…" oninput="filterFns(this.value)">
'''

    # Module legend
    if mods:
        html += '<div style="display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:1rem">'
        for m in mods:
            c = mod_color(m, mods)
            html += f'<span class="mod-tag" style="background:{c}1a;color:{c};border:1px solid {c}44">{esc(m)}</span>'
        html += '</div>'

    # Function index table
    html += '<h2>Function Index</h2>'
    html += '<table id="fn-table"><thead><tr><th>Function</th><th>Module</th><th>File</th><th>In</th><th>Out</th><th>Flags</th></tr></thead><tbody>'
    for n in proj_fns:
        mod = n.get('mod') or n.get('module') or ''
        c = mod_color(mod, mods) if mod and mod not in ('external','.') else 'var(--text2)'
        html += f'<tr data-fn="{esc(n["id"])}"><td><a class="fn-link" href="#fn-{esc(n["id"])}">{esc(n["id"])}</a></td>'
        html += f'<td><span class="mod-tag" style="color:{c}">{esc(mod)}</span></td>'
        html += f'<td style="font-size:.7rem;color:var(--text3)">{esc(n.get("file",""))}</td>'
        html += f'<td>{n.get("in_degree",0)}</td><td>{n.get("out_degree",0)}</td>'
        html += f'<td>{flag_badges(n)}</td></tr>'
    html += '</tbody></table>'

    # Per-function cards
    html += '<h2>Function Details</h2>'
    for n in proj_fns:
        fn = n['id']
        mod = n.get('mod') or n.get('module') or ''
        c = mod_color(mod, mods) if mod and mod not in ('external','.') else 'var(--text2)'
        fn_callers = callers.get(fn,[])
        fn_callees = edges.get(fn,[])
        fn_reads = n.get('reads',[])
        fn_writes = n.get('writes',[])
        fn_rw = n.get('rw',[])
        fn_periphs = n.get('peripherals',[])
        fn_races = races_by_fn.get(fn,[])

        html += f'<div class="card" id="fn-{esc(fn)}" data-fn="{esc(fn)}">'
        html += f'<div class="card-hdr" onclick="this.parentElement.classList.toggle(\'open\')">'
        html += f'<span class="card-arrow">▶</span>'
        html += f'<span class="card-title" style="color:{c}">{esc(fn)}</span>'
        html += f'{flag_badges(n)}'
        html += f'<span style="font-size:.62rem;color:var(--text3)">{esc(mod)} · {esc(n.get("file",""))}:{n.get("line",0)}</span>'
        html += '</div><div class="card-body">'

        # Meta row
        html += '<div class="meta-row">'
        html += f'<div><span class="meta-label">File</span><br>{esc(n.get("file",""))}</div>'
        html += f'<div><span class="meta-label">Line</span><br>{n.get("line",0)}</div>'
        html += f'<div><span class="meta-label">Module</span><br><span style="color:{c}">{esc(mod)}</span></div>'
        html += f'<div><span class="meta-label">Callers</span><br>{n.get("in_degree",0)}</div>'
        html += f'<div><span class="meta-label">Calls</span><br>{n.get("out_degree",0)}</div>'
        html += '</div>'

        # Mini call graph
        svg = mini_svg(fn, graph, nmap, mods)
        html += f'<div class="graph-wrap">{svg}</div>'

        # Callers
        if fn_callers:
            html += '<div class="section-label">Called by</div><div class="list-inline">'
            for cf in sorted(fn_callers):
                html += f'<a class="fn-link" href="#fn-{esc(cf)}">{esc(cf)}</a>'
            html += '</div>'

        # Callees
        if fn_callees:
            html += '<div class="section-label">Calls</div><div class="list-inline">'
            for cf in sorted(fn_callees):
                html += f'<a class="fn-link" href="#fn-{esc(cf)}">{esc(cf)}</a>'
            html += '</div>'

        # Globals
        if fn_reads or fn_writes or fn_rw:
            html += '<div class="section-label">Globals</div><div class="globals-list">'
            if fn_reads: html += f'<div><span class="read">reads:</span> {", ".join(esc(g) for g in fn_reads)}</div>'
            if fn_writes: html += f'<div><span class="write">writes:</span> {", ".join(esc(g) for g in fn_writes)}</div>'
            if fn_rw: html += f'<div><span class="rw">read+write:</span> {", ".join(esc(g) for g in fn_rw)}</div>'
            html += '</div>'

        # Peripherals
        if fn_periphs:
            html += f'<div class="section-label">Peripherals</div><div style="font-family:var(--font);font-size:.72rem;color:var(--amber)">{", ".join(esc(p) for p in fn_periphs)}</div>'

        # Races
        if fn_races:
            html += '<div class="section-label">Race involvement</div>'
            for r in fn_races:
                sev_col = '#f87171' if r.get('severity')=='high' else '#fbbf24' if r.get('severity')=='medium' else '#4ade80'
                html += f'<div style="font-size:.7rem;margin:.15rem 0"><span style="color:{sev_col}">●</span> {esc(r.get("var",""))} — ISR: {", ".join(r.get("isr_writers",[]))} · task: {esc(r.get("task_fn",""))} · {"protected" if r.get("protected") else "unprotected"}</div>'

        html += '</div></div>'  # card-body, card

    # Footer
    html += f'<div style="text-align:center;padding:2rem 0;font-size:.65rem;color:var(--text3)">Generated by Callgraph Studio · {now} · {len(proj_fns)} functions · {len(mods)} modules</div>'

    # JS
    html += '''
<script>
function filterFns(q){
  const ql=q.toLowerCase();
  document.querySelectorAll('.card[data-fn]').forEach(c=>{
    c.style.display=c.dataset.fn.toLowerCase().includes(ql)?'':'none';
  });
  document.querySelectorAll('#fn-table tbody tr').forEach(r=>{
    r.style.display=r.dataset.fn.toLowerCase().includes(ql)?'':'none';
  });
}
function expandAll(){document.querySelectorAll('.card').forEach(c=>c.classList.add('open'));}
function collapseAll(){document.querySelectorAll('.card').forEach(c=>c.classList.remove('open'));}
// Auto-open card from hash
if(location.hash){const el=document.querySelector(location.hash);if(el&&el.classList.contains('card'))el.classList.add('open');}
window.addEventListener('hashchange',()=>{const el=document.querySelector(location.hash);if(el&&el.classList.contains('card')){el.classList.add('open');el.scrollIntoView({behavior:'smooth'});}});
</script>
</div></body></html>'''

    return html


# ── Multi-file generator ─────────────────────────────────────

def build_multi(graph):
    """Build a ZIP with index.html + per-function + per-module pages."""
    nmap = _node_map(graph)
    mods = [m for m in graph.get('mods',[]) if m not in ('external','.')]
    proj_fns = sorted([n for n in graph['nodes'] if n.get('type')=='project'], key=lambda n: n['id'])
    proj_name = Path(graph.get('source','project')).name
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    edges = graph.get('edges',{})
    callers_map = graph.get('callers',{})
    races_by_fn = defaultdict(list)
    for r in graph.get('races',[]):
        races_by_fn[r.get('task_fn','')].append(r)
        for iw in r.get('isr_writers',[]): races_by_fn[iw].append(r)

    buf = io.BytesIO()
    zf = zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED)

    # style.css
    zf.writestr('assets/style.css', SHARED_CSS)

    def page_head(title, css_path='assets/style.css'):
        return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{css_path}"></head><body><div class="container">'''

    def page_foot(back_link='index.html', back_label='← Index'):
        return f'<div style="margin-top:2rem;padding:1rem 0;border-top:1px solid var(--border);font-size:.72rem;color:var(--text3)"><a href="{back_link}">{back_label}</a> · Generated by Callgraph Studio · {now}</div></div></body></html>'

    def fn_link(fn, prefix='functions/'):
        safe = re.sub(r'[^a-zA-Z0-9_]', '_', fn)
        return f'<a class="fn-link" href="{prefix}{safe}.html">{esc(fn)}</a>'

    # ── Index page ───────────────────────────────────────────
    idx = page_head(f'{proj_name} — Documentation', 'assets/style.css')
    idx += f'''<div class="topbar"><div><h1>{esc(proj_name)}</h1>
<div class="sub">{len(proj_fns)} functions · {len(mods)} modules · {graph.get("files",0)} files · {now}</div></div>
<div><button onclick="document.body.classList.toggle('light')">◐ Theme</button></div></div>'''

    # Module links
    if mods:
        idx += '<h2>Modules</h2><div style="display:flex;flex-wrap:wrap;gap:.5rem;margin-bottom:1rem">'
        for m in mods:
            c = mod_color(m, mods)
            safe_m = re.sub(r'[^a-zA-Z0-9_]', '_', m)
            idx += f'<a href="modules/{safe_m}.html" class="mod-tag" style="background:{c}1a;color:{c};border:1px solid {c}44;text-decoration:none">{esc(m)}</a>'
        idx += '</div>'

    # Function table
    idx += '<h2>All Functions</h2>'
    idx += '<input class="search" placeholder="Search…" oninput="let q=this.value.toLowerCase();document.querySelectorAll(\'#ft tbody tr\').forEach(r=>r.style.display=r.textContent.toLowerCase().includes(q)?\'\':\'none\')">'
    idx += '<table id="ft"><thead><tr><th>Function</th><th>Module</th><th>File</th><th>In</th><th>Out</th><th>Flags</th></tr></thead><tbody>'
    for n in proj_fns:
        mod = n.get('mod') or n.get('module') or ''
        c = mod_color(mod, mods) if mod and mod not in ('external','.') else 'var(--text2)'
        idx += f'<tr><td>{fn_link(n["id"])}</td><td><span style="color:{c}">{esc(mod)}</span></td>'
        idx += f'<td style="font-size:.7rem;color:var(--text3)">{esc(n.get("file",""))}</td>'
        idx += f'<td>{n.get("in_degree",0)}</td><td>{n.get("out_degree",0)}</td><td>{flag_badges(n)}</td></tr>'
    idx += '</tbody></table>'
    idx += page_foot('', '')
    zf.writestr('index.html', idx)

    # ── Per-function pages ───────────────────────────────────
    for n in proj_fns:
        fn = n['id']
        safe_fn = re.sub(r'[^a-zA-Z0-9_]', '_', fn)
        mod = n.get('mod') or n.get('module') or ''
        c = mod_color(mod, mods) if mod and mod not in ('external','.') else 'var(--text2)'
        fn_callers = callers_map.get(fn,[])
        fn_callees = edges.get(fn,[])

        pg = page_head(fn, '../assets/style.css')
        pg += f'<h1 style="color:{c}">{esc(fn)}</h1>'
        pg += f'<div class="sub">{esc(n.get("file",""))}:{n.get("line",0)} · module: <span style="color:{c}">{esc(mod)}</span> · {flag_badges(n)}</div>'

        # Mini SVG
        svg = mini_svg(fn, graph, nmap, mods)
        pg += f'<h2>Call Graph</h2><div class="graph-wrap">{svg}</div>'

        # Meta
        pg += '<div class="meta-row">'
        pg += f'<div><span class="meta-label">Callers</span><br>{n.get("in_degree",0)}</div>'
        pg += f'<div><span class="meta-label">Calls</span><br>{n.get("out_degree",0)}</div>'
        pg += f'<div><span class="meta-label">Type</span><br>{n.get("type","")}</div>'
        pg += '</div>'

        if fn_callers:
            pg += '<h3>Called by</h3><div class="list-inline">'
            for cf in sorted(fn_callers): pg += fn_link(cf, '')
            pg += '</div>'

        if fn_callees:
            pg += '<h3>Calls</h3><div class="list-inline">'
            for cf in sorted(fn_callees): pg += fn_link(cf, '')
            pg += '</div>'

        # Globals
        reads, writes, rw = n.get('reads',[]), n.get('writes',[]), n.get('rw',[])
        if reads or writes or rw:
            pg += '<h3>Globals</h3><div class="globals-list">'
            if reads: pg += f'<div><span class="read">reads:</span> {", ".join(esc(g) for g in reads)}</div>'
            if writes: pg += f'<div><span class="write">writes:</span> {", ".join(esc(g) for g in writes)}</div>'
            if rw: pg += f'<div><span class="rw">read+write:</span> {", ".join(esc(g) for g in rw)}</div>'
            pg += '</div>'

        periphs = n.get('peripherals',[])
        if periphs:
            pg += f'<h3>Peripherals</h3><div style="font-family:var(--font);font-size:.75rem;color:var(--amber)">{", ".join(esc(p) for p in periphs)}</div>'

        fn_races = races_by_fn.get(fn,[])
        if fn_races:
            pg += '<h3>Race Involvement</h3>'
            for r in fn_races:
                sev_col = '#f87171' if r.get('severity')=='high' else '#fbbf24' if r.get('severity')=='medium' else '#4ade80'
                pg += f'<div style="font-size:.75rem;margin:.2rem 0"><span style="color:{sev_col}">●</span> {esc(r.get("var",""))} — {", ".join(r.get("isr_writers",[]))} ↔ {esc(r.get("task_fn",""))}</div>'

        pg += page_foot('../index.html')
        zf.writestr(f'functions/{safe_fn}.html', pg)

    # ── Per-module pages ─────────────────────────────────────
    for mod in mods:
        safe_m = re.sub(r'[^a-zA-Z0-9_]', '_', mod)
        c = mod_color(mod, mods)
        mod_fns = [n for n in proj_fns if (n.get('mod') or n.get('module')) == mod]
        mod_files = sorted(set(n.get('file','') for n in mod_fns if n.get('file')))

        pg = page_head(f'Module: {mod}', '../assets/style.css')
        pg += f'<h1 style="color:{c}">{esc(mod)}</h1>'
        pg += f'<div class="sub">{len(mod_fns)} functions · {len(mod_files)} files</div>'

        pg += '<h2>Files</h2><div style="font-family:var(--font);font-size:.78rem">'
        for f in mod_files: pg += f'<div>{esc(f)}</div>'
        pg += '</div>'

        pg += '<h2>Functions</h2>'
        pg += '<table><thead><tr><th>Function</th><th>In</th><th>Out</th><th>Flags</th></tr></thead><tbody>'
        for n in mod_fns:
            pg += f'<tr><td>{fn_link(n["id"],"../functions/")}</td><td>{n.get("in_degree",0)}</td><td>{n.get("out_degree",0)}</td><td>{flag_badges(n)}</td></tr>'
        pg += '</tbody></table>'

        # Cross-module dependencies
        cross_out = defaultdict(int)
        cross_in = defaultdict(int)
        for key, count in graph.get('mod_edges',{}).items():
            parts = key.split('→')
            if len(parts)==2:
                if parts[0]==mod and parts[1]!=mod: cross_out[parts[1]] += count
                if parts[1]==mod and parts[0]!=mod: cross_in[parts[0]] += count

        if cross_out or cross_in:
            pg += '<h2>Dependencies</h2>'
            if cross_out:
                pg += '<h3>Depends on</h3><div class="list-inline">'
                for m2, cnt in sorted(cross_out.items(), key=lambda x:-x[1]):
                    safe_m2 = re.sub(r'[^a-zA-Z0-9_]', '_', m2)
                    pg += f'<a href="{safe_m2}.html" style="color:{mod_color(m2,mods)}">{esc(m2)} ({cnt})</a>'
                pg += '</div>'
            if cross_in:
                pg += '<h3>Used by</h3><div class="list-inline">'
                for m2, cnt in sorted(cross_in.items(), key=lambda x:-x[1]):
                    safe_m2 = re.sub(r'[^a-zA-Z0-9_]', '_', m2)
                    pg += f'<a href="{safe_m2}.html" style="color:{mod_color(m2,mods)}">{esc(m2)} ({cnt})</a>'
                pg += '</div>'

        pg += page_foot('../index.html')
        zf.writestr(f'modules/{safe_m}.html', pg)

    zf.close()
    return buf.getvalue()


# ── CLI ──────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Callgraph Studio Docs Generator')
    parser.add_argument('graph_json', help='Path to graph JSON')
    parser.add_argument('-o', '--output', default='docs.html')
    parser.add_argument('--mode', choices=['single','multi'], default='single')
    args = parser.parse_args()

    graph = json.loads(Path(args.graph_json).read_text())
    if args.mode == 'single':
        html = build_single(graph)
        Path(args.output).write_text(html, encoding='utf-8')
        print(f"Single-file docs: {args.output} ({len(html)} bytes)")
    else:
        data = build_multi(graph)
        out = args.output if args.output.endswith('.zip') else args.output + '.zip'
        Path(out).write_bytes(data)
        print(f"Multi-file docs: {out} ({len(data)} bytes)")
