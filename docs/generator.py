#!/usr/bin/env python3
"""
Callgraph Studio — Function Documentation Generator v2

Single HTML: sidebar TOC, module sections with subgraphs, function cards
grouped by module, cross-references, expand/collapse, search, diagrams.

Multi ZIP: per-function + per-module pages.
"""

import json, sys, os, io, zipfile, re
from pathlib import Path
from collections import defaultdict
from datetime import datetime

def esc(s):
    return (s or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def _nmap(graph): return {n['id']: n for n in graph.get('nodes',[])}

MOD_COLORS = ['#2563eb','#16a34a','#dc2626','#7c3aed','#d97706','#0891b2',
              '#db2777','#ea580c','#65a30d','#c026d3','#0284c7','#ca8a04',
              '#059669','#e11d48','#6366f1','#a16207','#0d9488','#eab308']

def _mc(mod, mods):
    clean = [m for m in mods if m not in ('external','.')]
    idx = clean.index(mod) if mod in clean else 0
    return MOD_COLORS[idx % len(MOD_COLORS)]

def _mod(n): return n.get('mod') or n.get('module') or 'external'

def _badges(n):
    b = ''
    if n.get('is_isr'): b += '<span class="bdg isr">ISR</span>'
    if n.get('is_entry'): b += '<span class="bdg entry">entry</span>'
    if n.get('has_critical'): b += '<span class="bdg crit">critical</span>'
    if n.get('delay_in_loop'): b += '<span class="bdg poll">polling</span>'
    if n.get('peripherals'): b += '<span class="bdg hw">hw</span>'
    return b

def _mini_svg(fn, graph, nmap, mods):
    callers = (graph.get('callers',{}).get(fn,[]))[:8]
    callees = (graph.get('edges',{}).get(fn,[]))[:8]
    NW, NH, HGAP, VGAP = 115, 24, 35, 7
    cols = [callers, [fn], callees]
    max_rows = max(len(c) for c in cols) if cols else 1
    W = 3*(NW+HGAP) + 30
    H = max(max_rows*(NH+VGAP)+30, 70)
    svg = f'<svg width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg" style="display:block;max-width:100%">\n'
    positions = {}
    for ci, col in enumerate(cols):
        x = 15 + ci*(NW+HGAP)
        col_h = len(col)*(NH+VGAP)
        y_off = (H - col_h)/2
        for ri, item in enumerate(col):
            y = y_off + ri*(NH+VGAP)
            nd = nmap.get(item,{})
            mod = _mod(nd)
            color = _mc(mod, mods) if mod not in ('external','.') else '#666'
            is_ctr = (ci == 1)
            sw = '2.5' if is_ctr else '1.2'
            fill = f'{color}{"22" if is_ctr else "0d"}'
            label = item if len(item)<=14 else item[:12]+'…'
            svg += f'  <rect x="{x}" y="{y}" width="{NW}" height="{NH}" rx="4" fill="{fill}" stroke="{color}" stroke-width="{sw}"/>\n'
            svg += f'  <text x="{x+NW/2}" y="{y+NH/2}" text-anchor="middle" dominant-baseline="middle" font-size="8" font-family="monospace" fill="{color}">{esc(label)}</text>\n'
            positions[item] = (x, y)
    fx, fy = positions.get(fn, (0,0))
    for c in callers:
        cx, cy = positions.get(c, (0,0))
        svg += f'  <path d="M{cx+NW},{cy+NH/2} C{cx+NW+HGAP/2},{cy+NH/2} {fx-HGAP/2},{fy+NH/2} {fx},{fy+NH/2}" fill="none" stroke="#ef654860" stroke-width="1.2"/>\n'
    for c in callees:
        cx, cy = positions.get(c, (0,0))
        svg += f'  <path d="M{fx+NW},{fy+NH/2} C{fx+NW+HGAP/2},{fy+NH/2} {cx-HGAP/2},{cy+NH/2} {cx},{cy+NH/2}" fill="none" stroke="#22c55e60" stroke-width="1.2"/>\n'
    svg += '</svg>'
    return svg


# ══════════════════════════════════════════════════════════
# SINGLE-FILE (full-featured)
# ══════════════════════════════════════════════════════════

def build_single(graph):
    nmap = _nmap(graph)
    mods = [m for m in graph.get('mods',[]) if m not in ('external','.')]
    edges = graph.get('edges',{})
    callers = graph.get('callers',{})
    proj_name = Path(graph.get('source','project')).name
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    races_by_fn = defaultdict(list)
    for r in graph.get('races',[]):
        races_by_fn[r.get('task_fn','')].append(r)
        for w in r.get('isr_writers',[]): races_by_fn[w].append(r)

    # Group functions by module
    by_mod = defaultdict(list)
    for n in graph['nodes']:
        if n.get('type')!='project': continue
        by_mod[_mod(n)].append(n)
    for m in by_mod: by_mod[m].sort(key=lambda n: n['id'])

    all_fns = sorted([n for n in graph['nodes'] if n.get('type')=='project'], key=lambda n: n['id'])

    # ── CSS ──────────────────────────────────────────────
    css = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0c0e14;--bg2:#12151e;--bg3:#181c28;--bg4:#1e2334;--text:#dce0ec;--text2:#8890a8;--text3:#555a6c;
--accent:#60a5fa;--border:#2a2f3e;--border2:#353b4e;--green:#4ade80;--red:#f87171;--amber:#fbbf24;--purple:#a78bfa;--cyan:#22d3ee;
--sidebar-w:230px;--font-body:'DM Sans',sans-serif;--font-head:'Source Serif 4',Georgia,serif;--font-mono:'IBM Plex Mono',monospace}
.light{--bg:#f5f5f0;--bg2:#fff;--bg3:#eaeae2;--bg4:#ddddd5;--text:#1a1a18;--text2:#555;--text3:#888;--accent:#2563eb;--border:#c8c8bc;--border2:#b8b8ac}
html,body{height:100%;overflow:hidden;font-family:var(--font-body);font-size:13px;background:var(--bg);color:var(--text)}
.shell{display:flex;height:100%}
.sidebar{width:var(--sidebar-w);background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;flex-shrink:0}
.sidebar-head{padding:.8rem 1rem;border-bottom:1px solid var(--border)}
.sidebar-head h1{font-family:var(--font-head);font-size:1.1rem;margin-bottom:.15rem}
.sidebar-head .sub{font-size:.65rem;color:var(--text3)}
.toc{flex:1;overflow-y:auto;padding:.4rem 0}
.toc-mod{padding:.3rem .8rem;font-size:.68rem;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:.3rem}
.toc-mod:hover{background:var(--bg3)}
.toc-fn{padding:.15rem .8rem .15rem 1.6rem;font-size:.65rem;color:var(--text2);cursor:pointer;font-family:var(--font-mono);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.toc-fn:hover{background:var(--bg3);color:var(--accent)}
.toc-fn.active{color:var(--accent);background:var(--accent)0d}
.toc-fns{display:none;max-height:200px;overflow-y:auto}
.toc-mod.expanded .toc-fns{display:block}
.toc-arrow{font-size:.5rem;color:var(--text3);transition:transform .2s}
.toc-mod.expanded .toc-arrow{transform:rotate(90deg)}
.sidebar-foot{padding:.5rem .8rem;border-top:1px solid var(--border);display:flex;gap:.3rem;flex-wrap:wrap}
.sidebar-foot button{background:none;border:1px solid var(--border);border-radius:4px;padding:.15rem .4rem;font-size:.58rem;color:var(--text3);cursor:pointer}
.sidebar-foot button:hover{border-color:var(--accent);color:var(--accent)}
.content{flex:1;overflow-y:auto;padding:1.5rem 2.5rem 3rem}
.search{width:100%;padding:.4rem .7rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-family:var(--font-mono);font-size:.75rem;outline:none;margin-bottom:1rem}
.search:focus{border-color:var(--accent)}
.section{padding-bottom:1.5rem;border-bottom:1px solid var(--border);margin-bottom:1.5rem}
.sect-title{font-family:var(--font-head);font-size:1.15rem;margin-bottom:.6rem}
.mod-tag{font-size:.6rem;padding:.12rem .4rem;border-radius:3px;font-family:var(--font-mono)}
table{width:100%;border-collapse:collapse;font-size:.75rem;margin:.5rem 0}
th{text-align:left;padding:.35rem .5rem;border-bottom:2px solid var(--border);font-weight:500;color:var(--text3);font-size:.62rem;text-transform:uppercase}
td{padding:.3rem .5rem;border-bottom:1px solid var(--border)}
tr:hover td{background:var(--bg3)}
.fn-link{font-family:var(--font-mono);color:var(--accent);cursor:pointer;text-decoration:none;font-size:.75rem}
.fn-link:hover{text-decoration:underline}
.bdg{display:inline-block;font-size:.55rem;padding:.08rem .25rem;border-radius:3px;margin-right:.15rem;font-family:var(--font-mono)}
.bdg.isr{background:#a78bfa18;color:#a78bfa}.bdg.entry{background:#60a5fa18;color:#60a5fa}.bdg.crit{background:#fbbf2418;color:#fbbf24}.bdg.poll{background:#f8717118;color:#f87171}.bdg.hw{background:#d9770618;color:#d97706}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:8px;margin:.5rem 0;overflow:hidden}
.card-hdr{display:flex;align-items:center;gap:.4rem;padding:.45rem .7rem;cursor:pointer}
.card-hdr:hover{background:var(--bg3)}
.card-arrow{font-size:.55rem;color:var(--text3);transition:transform .2s}
.card.open .card-arrow{transform:rotate(90deg)}
.card-title{font-family:var(--font-mono);font-size:.8rem;font-weight:500;flex:1}
.card-body{display:none;padding:.5rem .7rem;border-top:1px solid var(--border);font-size:.75rem;line-height:1.6}
.card.open .card-body{display:block}
.meta-row{display:flex;gap:1.2rem;flex-wrap:wrap;margin-bottom:.4rem;font-size:.7rem;color:var(--text2)}
.meta-label{color:var(--text3);font-size:.58rem;text-transform:uppercase}
.sect-label{font-size:.62rem;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;margin:.5rem 0 .15rem}
.graph-wrap{border:1px solid var(--border);border-radius:6px;padding:.4rem;margin:.4rem 0;overflow-x:auto;background:var(--bg)}
.globals-list{font-family:var(--font-mono);font-size:.68rem}
.globals-list .rd{color:var(--accent)}.globals-list .wr{color:var(--red)}.globals-list .rw{color:var(--amber)}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(90px,1fr));gap:.5rem;margin-bottom:1rem}
.stat-card{background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:.5rem;text-align:center}
.stat-val{font-size:1.3rem;font-weight:600;font-family:var(--font-mono);color:var(--accent)}
.stat-label{font-size:.58rem;color:var(--text3);text-transform:uppercase;margin-top:.1rem}
@media print{.sidebar{display:none}.content{overflow:visible}.card-body{display:block!important}}
"""

    # ── Build HTML ───────────────────────────────────────
    h = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(proj_name)} — Function Documentation</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>{css}</style></head><body>
<div class="shell">
<nav class="sidebar">
  <div class="sidebar-head">
    <h1>{esc(proj_name)}</h1>
    <div class="sub">{len(all_fns)} functions · {len(mods)} modules · {graph.get("files",0)} files · {now}</div>
  </div>
  <div class="toc" id="toc">
    <div class="toc-fn" onclick="jumpTo('overview')" style="font-weight:500;padding-left:.8rem">◈ Overview</div>
    <div class="toc-fn" onclick="jumpTo('index')" style="font-weight:500;padding-left:.8rem">📇 All Functions</div>
'''

    # Sidebar: module sections with expandable function lists
    for mod in mods:
        c = _mc(mod, mods)
        mod_fns = by_mod.get(mod, [])
        h += f'''    <div class="toc-mod" onclick="this.classList.toggle('expanded')" style="color:{c}">
      <span class="toc-arrow">▶</span> {esc(mod)} <span style="font-size:.55rem;color:var(--text3)">({len(mod_fns)})</span>
      <div class="toc-fns" onclick="event.stopPropagation()">'''
        for n in mod_fns[:50]:
            h += f'<div class="toc-fn" onclick="jumpTo(\'fn-{esc(n["id"])}\')">{esc(n["id"])}</div>'
        if len(mod_fns) > 50:
            h += f'<div class="toc-fn" style="color:var(--text3);font-style:italic">…+{len(mod_fns)-50} more</div>'
        h += '</div></div>'

    h += f'''  </div>
  <div class="sidebar-foot">
    <button onclick="document.documentElement.classList.toggle('light')">◐ Theme</button>
    <button onclick="window.print()">⎙ Print</button>
    <button onclick="expandAll()">▶ All</button>
    <button onclick="collapseAll()">▼ All</button>
    <button onclick="expandMod()">▶ Mod</button>
    <button onclick="collapseMod()">▼ Mod</button>
  </div>
</nav>
<main class="content" id="content">
'''

    # ── Overview section ─────────────────────────────────
    n_isrs = sum(1 for n in all_fns if n.get('is_isr'))
    n_races = len(graph.get('races',[]))
    n_periphs = len(graph.get('peripherals',{}))
    n_dead = sum(1 for n in all_fns if n.get('in_degree',0)==0 and not n.get('is_isr') and not n.get('is_entry') and n['id']!='main')

    h += f'''<div class="section" id="overview">
  <div class="sect-title">◈ Overview</div>
  <div class="stats-grid">
    <div class="stat-card"><div class="stat-val">{len(all_fns)}</div><div class="stat-label">Functions</div></div>
    <div class="stat-card"><div class="stat-val">{sum(len(v) for v in edges.values())}</div><div class="stat-label">Call Edges</div></div>
    <div class="stat-card"><div class="stat-val">{len(mods)}</div><div class="stat-label">Modules</div></div>
    <div class="stat-card"><div class="stat-val">{graph.get("files",0)}</div><div class="stat-label">Files</div></div>
    <div class="stat-card"><div class="stat-val">{n_isrs}</div><div class="stat-label">ISRs</div></div>
    <div class="stat-card"><div class="stat-val">{n_races}</div><div class="stat-label">Races</div></div>
    <div class="stat-card"><div class="stat-val">{n_periphs}</div><div class="stat-label">Peripherals</div></div>
    <div class="stat-card"><div class="stat-val">{n_dead}</div><div class="stat-label">Dead Code</div></div>
  </div>
  <div style="display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.5rem">'''
    for m in mods:
        c = _mc(m, mods)
        h += f'<span class="mod-tag" style="background:{c}15;color:{c};border:1px solid {c}30">{esc(m)} ({len(by_mod.get(m,[]))})</span>'
    h += '</div></div>'

    # ── Function Index ───────────────────────────────────
    h += '''<div class="section" id="index">
  <div class="sect-title">📇 All Functions</div>
  <input class="search" id="search" placeholder="Search functions…" oninput="filterAll(this.value)">
  <table id="fn-tbl"><thead><tr><th>Function</th><th>Module</th><th>File</th><th>In</th><th>Out</th><th>Flags</th></tr></thead><tbody>'''

    for n in all_fns:
        mod = _mod(n)
        c = _mc(mod, mods) if mod not in ('external','.') else 'var(--text2)'
        h += f'<tr data-fn="{esc(n["id"])}"><td><a class="fn-link" href="#fn-{esc(n["id"])}" onclick="jumpTo(\'fn-{esc(n["id"])}\');return false">{esc(n["id"])}</a></td>'
        h += f'<td><span style="color:{c};font-size:.68rem">{esc(mod)}</span></td>'
        h += f'<td style="font-size:.65rem;color:var(--text3)">{esc(n.get("file",""))}</td>'
        h += f'<td>{n.get("in_degree",0)}</td><td>{n.get("out_degree",0)}</td>'
        h += f'<td>{_badges(n)}</td></tr>'
    h += '</tbody></table></div>'

    # ── Module Sections (each with subgraph + function cards) ──
    for mod in mods:
        c = _mc(mod, mods)
        mod_fns = by_mod.get(mod, [])
        mod_files = sorted(set(n.get('file','') for n in mod_fns if n.get('file')))
        mod_isrs = [n for n in mod_fns if n.get('is_isr')]
        n_dead_mod = sum(1 for n in mod_fns if n.get('in_degree',0)==0 and not n.get('is_isr') and not n.get('is_entry') and n['id']!='main')

        h += f'<div class="section" id="mod-{esc(mod)}">'
        h += f'<div class="sect-title" style="color:{c}">📦 {esc(mod)}</div>'
        h += f'<div style="font-size:.75rem;color:var(--text2);margin-bottom:.5rem">{len(mod_fns)} functions · {len(mod_files)} files'
        if mod_isrs: h += f' · {len(mod_isrs)} ISRs'
        if n_dead_mod: h += f' · {n_dead_mod} dead code candidates'
        h += '</div>'
        h += f'<div style="font-size:.7rem;color:var(--text3);margin-bottom:.6rem">Files: {", ".join(esc(f) for f in mod_files[:10])}{"…" if len(mod_files)>10 else ""}</div>'

        # Mini module subgraph (top 30 functions by connectivity)
        top_fns = sorted(mod_fns, key=lambda n: -(n.get('in_degree',0)+n.get('out_degree',0)))[:30]
        mod_fn_set = {n['id'] for n in top_fns}
        if len(top_fns) >= 2:
            NW, NH, INDENT, VGAP, PAD = 110, 22, 25, 6, 12
            # Simple layering by in-degree within module
            in_d = {n['id']:0 for n in top_fns}
            for n in top_fns:
                for callee in edges.get(n['id'],[]):
                    if callee in in_d: in_d[callee] += 1
            layer = {}
            q_lay = [f for f,d in in_d.items() if d==0]
            if not q_lay: q_lay = [top_fns[0]['id']]
            vis_lay = set()
            while q_lay:
                fn = q_lay.pop(0)
                if fn in vis_lay: continue
                vis_lay.add(fn); layer[fn] = layer.get(fn, 0)
                for callee in edges.get(fn,[]):
                    if callee in mod_fn_set and callee not in vis_lay:
                        layer[callee] = max(layer.get(callee,0), layer[fn]+1)
                        q_lay.append(callee)
            for n in top_fns:
                if n['id'] not in layer: layer[n['id']] = 0

            by_layer = defaultdict(list)
            for fn, l in layer.items(): by_layer[l].append(fn)
            layer_nums = sorted(by_layer.keys())
            max_col = max(len(by_layer[l]) for l in layer_nums) if layer_nums else 1
            sg_w = len(layer_nums)*(NW+INDENT*2)+PAD*2
            sg_h = max_col*(NH+VGAP)+PAD*2
            svg_lines = [f'<svg width="{sg_w}" height="{sg_h}" xmlns="http://www.w3.org/2000/svg" style="display:block;max-width:100%">']
            sg_pos = {}
            for li, l in enumerate(layer_nums):
                fns_in_l = by_layer[l]
                col_h = len(fns_in_l)*(NH+VGAP)
                y_off = (sg_h-col_h)/2
                for fi, fn in enumerate(fns_in_l):
                    x = PAD + li*(NW+INDENT*2)
                    y = y_off + fi*(NH+VGAP)
                    sg_pos[fn] = (x, y)
                    nd = nmap.get(fn,{})
                    label = fn if len(fn)<=13 else fn[:11]+'…'
                    svg_lines.append(f'<rect x="{x}" y="{y}" width="{NW}" height="{NH}" rx="4" fill="{c}0d" stroke="{c}" stroke-width="1.2"/>')
                    svg_lines.append(f'<text x="{x+NW/2}" y="{y+NH/2}" text-anchor="middle" dominant-baseline="middle" font-size="7.5" font-family="monospace" fill="{c}">{esc(label)}</text>')
            # Internal edges
            for fn in mod_fn_set:
                for callee in edges.get(fn,[]):
                    if callee in sg_pos and fn in sg_pos:
                        x1, y1 = sg_pos[fn]; x2, y2 = sg_pos[callee]
                        svg_lines.append(f'<path d="M{x1+NW},{y1+NH/2} C{x1+NW+INDENT},{y1+NH/2} {x2-INDENT},{y2+NH/2} {x2},{y2+NH/2}" fill="none" stroke="{c}40" stroke-width="1"/>')
            svg_lines.append('</svg>')
            h += f'<div class="graph-wrap">{"".join(svg_lines)}</div>'

        # Function cards
        for n in mod_fns:
            fn = n['id']
            fn_callers = callers.get(fn,[])
            fn_callees = edges.get(fn,[])
            fn_reads = n.get('reads',[])
            fn_writes = n.get('writes',[])
            fn_periphs = n.get('peripherals',[])
            fn_races = races_by_fn.get(fn,[])

            h += f'<div class="card" id="fn-{esc(fn)}" data-fn="{esc(fn)}" data-mod="{esc(mod)}">'
            h += f'<div class="card-hdr" onclick="this.parentElement.classList.toggle(\'open\')">'
            h += f'<span class="card-arrow">▶</span>'
            h += f'<span class="card-title" style="color:{c}">{esc(fn)}</span>'
            h += f'{_badges(n)}'
            h += f'<span style="font-size:.58rem;color:var(--text3)">{esc(n.get("file",""))}:{n.get("line",0)}</span>'
            h += '</div><div class="card-body">'

            # Meta
            h += '<div class="meta-row">'
            h += f'<div><span class="meta-label">File</span><br>{esc(n.get("file",""))}</div>'
            h += f'<div><span class="meta-label">Line</span><br>{n.get("line",0)}</div>'
            h += f'<div><span class="meta-label">Callers</span><br>{n.get("in_degree",0)}</div>'
            h += f'<div><span class="meta-label">Calls</span><br>{n.get("out_degree",0)}</div>'
            h += '</div>'

            # Mini call graph
            svg = _mini_svg(fn, graph, nmap, mods)
            h += f'<div class="graph-wrap">{svg}</div>'

            # Callers
            if fn_callers:
                h += f'<div class="sect-label">Called by ({len(fn_callers)})</div><div style="display:flex;flex-wrap:wrap;gap:.3rem">'
                for cf in sorted(fn_callers):
                    h += f'<a class="fn-link" href="#fn-{esc(cf)}" onclick="jumpTo(\'fn-{esc(cf)}\');return false">{esc(cf)}</a>'
                h += '</div>'

            # Callees
            if fn_callees:
                h += f'<div class="sect-label">Calls ({len(fn_callees)})</div><div style="display:flex;flex-wrap:wrap;gap:.3rem">'
                for cf in sorted(fn_callees):
                    h += f'<a class="fn-link" href="#fn-{esc(cf)}" onclick="jumpTo(\'fn-{esc(cf)}\');return false">{esc(cf)}</a>'
                h += '</div>'

            # Globals
            if fn_reads or fn_writes:
                h += '<div class="sect-label">Globals</div><div class="globals-list">'
                if fn_reads: h += f'<div><span class="rd">reads:</span> {", ".join(esc(g) for g in fn_reads)}</div>'
                if fn_writes: h += f'<div><span class="wr">writes:</span> {", ".join(esc(g) for g in fn_writes)}</div>'
                h += '</div>'

            # Peripherals
            if fn_periphs:
                h += f'<div class="sect-label">Peripherals</div><div style="font-family:var(--font-mono);font-size:.68rem;color:var(--amber)">{", ".join(esc(p) for p in fn_periphs)}</div>'

            # Races
            if fn_races:
                h += '<div class="sect-label">Race involvement</div>'
                for r in fn_races:
                    sc = '#f87171' if r.get('severity')=='high' else '#fbbf24'
                    h += f'<div style="font-size:.68rem"><span style="color:{sc}">●</span> {esc(r.get("var",""))} — ISR: {", ".join(r.get("isr_writers",[]))} · {"protected" if r.get("protected") else "UNPROTECTED"}</div>'

            h += '</div></div>'  # card-body, card

    # ── Footer ───────────────────────────────────────────
    h += f'<div style="text-align:center;padding:2rem 0;font-size:.62rem;color:var(--text3);border-top:1px solid var(--border)">Generated by Callgraph Studio · {now} · {len(all_fns)} functions · {len(mods)} modules</div>'

    # ── JS ───────────────────────────────────────────────
    h += '''
<script>
function jumpTo(id){
  const el=document.getElementById(id);
  if(!el) return;
  if(el.classList.contains('card')) el.classList.add('open');
  el.scrollIntoView({behavior:'smooth',block:'start'});
}
function filterAll(q){
  const ql=q.toLowerCase();
  document.querySelectorAll('.card[data-fn]').forEach(c=>{
    c.style.display=c.dataset.fn.toLowerCase().includes(ql)?'':'none';
  });
  document.querySelectorAll('#fn-tbl tbody tr').forEach(r=>{
    r.style.display=(r.dataset.fn||'').toLowerCase().includes(ql)?'':'none';
  });
}
function expandAll(){document.querySelectorAll('.card').forEach(c=>c.classList.add('open'));}
function collapseAll(){document.querySelectorAll('.card').forEach(c=>c.classList.remove('open'));}
function expandMod(){document.querySelectorAll('.toc-mod').forEach(m=>m.classList.add('expanded'));}
function collapseMod(){document.querySelectorAll('.toc-mod').forEach(m=>m.classList.remove('expanded'));}
// Auto-open from hash
if(location.hash){const el=document.querySelector(location.hash);if(el&&el.classList.contains('card'))el.classList.add('open');}
window.addEventListener('hashchange',()=>{const el=document.querySelector(location.hash);if(el){if(el.classList.contains('card'))el.classList.add('open');el.scrollIntoView({behavior:'smooth'});}});
</script>
'''
    h += '</main></div></body></html>'
    return h


# ══════════════════════════════════════════════════════════
# MULTI-FILE (unchanged from v1, imports from above)
# ══════════════════════════════════════════════════════════

def build_multi(graph):
    nmap = _nmap(graph)
    mods = [m for m in graph.get('mods',[]) if m not in ('external','.')]
    proj_fns = sorted([n for n in graph['nodes'] if n.get('type')=='project'], key=lambda n: n['id'])
    proj_name = Path(graph.get('source','project')).name
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    edges = graph.get('edges',{})
    callers_map = graph.get('callers',{})
    by_mod = defaultdict(list)
    for n in proj_fns: by_mod[_mod(n)].append(n)
    races_by_fn = defaultdict(list)
    for r in graph.get('races',[]):
        races_by_fn[r.get('task_fn','')].append(r)
        for iw in r.get('isr_writers',[]): races_by_fn[iw].append(r)

    CSS = """*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0c0e14;--bg2:#12151e;--bg3:#181c28;--text:#dce0ec;--text2:#8890a8;--text3:#555a6c;--accent:#60a5fa;--border:#2a2f3e;--font:'IBM Plex Mono',monospace;--amber:#fbbf24;--red:#f87171;--green:#4ade80;--purple:#a78bfa}
.light{--bg:#f5f5f0;--bg2:#fff;--bg3:#eaeae2;--text:#1a1a18;--text2:#555;--text3:#888;--accent:#2563eb;--border:#c8c8bc}
html,body{height:100%;overflow:hidden;font-family:'DM Sans',sans-serif;font-size:13px;background:var(--bg);color:var(--text)}
.shell{display:flex;height:100%}
.sidebar{width:220px;background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;flex-shrink:0}
.sidebar-head{padding:.6rem .8rem;border-bottom:1px solid var(--border)}
.sidebar-head h1{font-family:'Source Serif 4',Georgia,serif;font-size:.95rem}
.sidebar-head .sub{font-size:.58rem;color:var(--text3)}
.nav{flex:1;overflow-y:auto;padding:.3rem 0}
.nav a{display:block;padding:.25rem .8rem;font-size:.68rem;color:var(--text2);text-decoration:none;border-left:2px solid transparent}
.nav a:hover{background:var(--bg3);color:var(--accent)}
.nav a.active{color:var(--accent);border-left-color:var(--accent);background:var(--accent)08}
.nav .mod-hdr{font-weight:600;padding:.3rem .8rem;font-size:.65rem}
.sidebar-foot{padding:.4rem .8rem;border-top:1px solid var(--border)}
.sidebar-foot button{background:none;border:1px solid var(--border);border-radius:4px;padding:.12rem .35rem;font-size:.55rem;color:var(--text3);cursor:pointer;margin-right:.2rem}
.sidebar-foot button:hover{border-color:var(--accent);color:var(--accent)}
.content{flex:1;overflow-y:auto;padding:1.5rem 2rem 3rem}
h1{font-family:'Source Serif 4',Georgia,serif;font-size:1.4rem;margin-bottom:.2rem}
h2{font-size:1rem;margin:1.2rem 0 .4rem;border-bottom:1px solid var(--border);padding-bottom:.2rem}
.sub{font-size:.7rem;color:var(--text3);margin-bottom:.8rem}
table{width:100%;border-collapse:collapse;font-size:.75rem;margin:.4rem 0}
th{text-align:left;padding:.3rem .5rem;border-bottom:2px solid var(--border);font-weight:500;color:var(--text3);font-size:.6rem;text-transform:uppercase}
td{padding:.25rem .5rem;border-bottom:1px solid var(--border)}
tr:hover td{background:var(--bg3)}
.fn-link{font-family:var(--font);color:var(--accent);text-decoration:none;font-size:.75rem}
.fn-link:hover{text-decoration:underline}
.bdg{display:inline-block;font-size:.55rem;padding:.08rem .25rem;border-radius:3px;margin-right:.15rem;font-family:var(--font)}
.bdg.isr{background:#a78bfa18;color:#a78bfa}.bdg.entry{background:#60a5fa18;color:#60a5fa}.bdg.crit{background:#fbbf2418;color:#fbbf24}.bdg.hw{background:#d9770618;color:#d97706}
.graph-wrap{border:1px solid var(--border);border-radius:6px;padding:.4rem;margin:.4rem 0;overflow-x:auto;background:var(--bg)}
.meta-row{display:flex;gap:1rem;flex-wrap:wrap;margin:.4rem 0;font-size:.7rem;color:var(--text2)}
.meta-label{color:var(--text3);font-size:.58rem;text-transform:uppercase}
.sect-label{font-size:.62rem;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;margin:.5rem 0 .15rem}
@media print{.sidebar{display:none}.content{overflow:visible}}"""

    buf = io.BytesIO()
    zf = zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED)
    zf.writestr('assets/style.css', CSS)

    def fn_safe(fn): return re.sub(r'[^a-zA-Z0-9_]', '_', fn)
    def fn_link(fn, prefix='functions/'):
        return f'<a class="fn-link" href="{prefix}{fn_safe(fn)}.html">{esc(fn)}</a>'

    def sidebar_html(active_type='', active_id='', prefix=''):
        s = f'''<nav class="sidebar">
<div class="sidebar-head"><h1>{esc(proj_name)}</h1><div class="sub">{len(proj_fns)} fns · {len(mods)} mods · {now}</div></div>
<div class="nav">
<a href="{prefix}index.html" {"class='active'" if active_type=='index' else ""}>◈ Overview</a>'''
        for mod in mods:
            c = _mc(mod, mods)
            sm = fn_safe(mod)
            s += f'<div class="mod-hdr" style="color:{c}">{esc(mod)}</div>'
            s += f'<a href="{prefix}modules/{sm}.html" {"class=\\'active\\'" if active_type=="mod" and active_id==mod else ""}>&nbsp;&nbsp;📦 Module page</a>'
            for n in by_mod.get(mod,[])[:20]:
                sf = fn_safe(n['id'])
                act = ' class="active"' if active_type=='fn' and active_id==n['id'] else ''
                s += f'<a href="{prefix}functions/{sf}.html"{act} style="padding-left:1.4rem;font-family:var(--font);font-size:.6rem">{esc(n["id"][:22])}</a>'
            if len(by_mod.get(mod,[])) > 20:
                s += f'<a style="padding-left:1.4rem;font-size:.58rem;color:var(--text3);font-style:italic">…+{len(by_mod[mod])-20} more</a>'
        s += '</div><div class="sidebar-foot">'
        s += '<button onclick="document.documentElement.classList.toggle(\'light\')">◐ Theme</button>'
        s += '<button onclick="window.print()">⎙ Print</button></div></nav>'
        return s

    def page_wrap(title, body_html, active_type='', active_id='', prefix=''):
        return f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{prefix}assets/style.css"></head><body>
<div class="shell">{sidebar_html(active_type, active_id, prefix)}
<main class="content">{body_html}</main></div></body></html>'''

    # ── Index page ───────────────────────────────────────
    idx = f'<h1>{esc(proj_name)}</h1><div class="sub">{len(proj_fns)} functions · {len(mods)} modules · {graph.get("files",0)} files · {now}</div>'
    idx += '<h2>Modules</h2><div style="display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:1rem">'
    for m in mods:
        c = _mc(m, mods)
        idx += f'<a href="modules/{fn_safe(m)}.html" style="background:{c}15;color:{c};border:1px solid {c}30;padding:.2rem .5rem;border-radius:4px;font-size:.72rem;text-decoration:none">{esc(m)} ({len(by_mod.get(m,[]))})</a>'
    idx += '</div>'
    idx += '<h2>All Functions</h2><table><thead><tr><th>Function</th><th>Module</th><th>File</th><th>In</th><th>Out</th><th>Flags</th></tr></thead><tbody>'
    for n in proj_fns:
        mod = _mod(n); c = _mc(mod, mods) if mod not in ('external','.') else '#888'
        idx += f'<tr><td>{fn_link(n["id"])}</td><td style="color:{c};font-size:.68rem">{esc(mod)}</td><td style="font-size:.62rem;color:var(--text3)">{esc(n.get("file",""))}</td><td>{n.get("in_degree",0)}</td><td>{n.get("out_degree",0)}</td><td>{_badges(n)}</td></tr>'
    idx += '</tbody></table>'
    zf.writestr('index.html', page_wrap(f'{proj_name} — Docs', idx, 'index', '', ''))

    # ── Per-function pages ───────────────────────────────
    for n in proj_fns:
        fn = n['id']; mod = _mod(n)
        c = _mc(mod, mods) if mod not in ('external','.') else '#888'
        fc = callers_map.get(fn, []); fe = edges.get(fn, [])
        
        body = f'<h1 style="color:{c}">{esc(fn)}</h1>'
        body += f'<div class="sub">{esc(n.get("file",""))}:{n.get("line",0)} · module: <span style="color:{c}">{esc(mod)}</span> · {_badges(n)}</div>'
        body += '<div class="meta-row">'
        body += f'<div><span class="meta-label">Callers</span><br>{n.get("in_degree",0)}</div>'
        body += f'<div><span class="meta-label">Calls</span><br>{n.get("out_degree",0)}</div>'
        body += '</div>'
        body += f'<div class="graph-wrap">{_mini_svg(fn, graph, nmap, mods)}</div>'
        if fc:
            body += f'<h2>Called by ({len(fc)})</h2><div style="display:flex;flex-wrap:wrap;gap:.3rem">'
            for cf in sorted(fc): body += fn_link(cf, '')
            body += '</div>'
        if fe:
            body += f'<h2>Calls ({len(fe)})</h2><div style="display:flex;flex-wrap:wrap;gap:.3rem">'
            for cf in sorted(fe): body += fn_link(cf, '')
            body += '</div>'
        rd, wr = n.get('reads',[]), n.get('writes',[])
        if rd or wr:
            body += '<h2>Globals</h2>'
            if rd: body += f'<div style="color:var(--accent);font-size:.75rem;font-family:var(--font)">reads: {", ".join(esc(g) for g in rd)}</div>'
            if wr: body += f'<div style="color:var(--red);font-size:.75rem;font-family:var(--font)">writes: {", ".join(esc(g) for g in wr)}</div>'
        pp = n.get('peripherals',[])
        if pp: body += f'<h2>Peripherals</h2><div style="color:var(--amber);font-size:.75rem;font-family:var(--font)">{", ".join(esc(p) for p in pp)}</div>'
        fr = races_by_fn.get(fn,[])
        if fr:
            body += '<h2>Race Involvement</h2>'
            for r in fr:
                sc = '#f87171' if r.get('severity')=='high' else '#fbbf24'
                body += f'<div style="font-size:.75rem"><span style="color:{sc}">●</span> {esc(r.get("var",""))} — {"protected" if r.get("protected") else "UNPROTECTED"}</div>'
        zf.writestr(f'functions/{fn_safe(fn)}.html', page_wrap(fn, body, 'fn', fn, '../'))

    # ── Per-module pages ─────────────────────────────────
    for mod in mods:
        c = _mc(mod, mods)
        mod_fns = by_mod.get(mod, [])
        files = sorted(set(n.get('file','') for n in mod_fns if n.get('file')))
        
        body = f'<h1 style="color:{c}">📦 {esc(mod)}</h1>'
        body += f'<div class="sub">{len(mod_fns)} functions · {len(files)} files</div>'
        body += f'<div style="font-size:.7rem;color:var(--text3);margin-bottom:.6rem">Files: {", ".join(esc(f) for f in files[:15])}</div>'
        body += '<h2>Functions</h2><table><thead><tr><th>Function</th><th>File</th><th>In</th><th>Out</th><th>Flags</th></tr></thead><tbody>'
        for n in mod_fns:
            body += f'<tr><td>{fn_link(n["id"],"../functions/")}</td><td style="font-size:.62rem;color:var(--text3)">{esc(n.get("file",""))}</td><td>{n.get("in_degree",0)}</td><td>{n.get("out_degree",0)}</td><td>{_badges(n)}</td></tr>'
        body += '</tbody></table>'
        
        # Cross-module deps
        me = graph.get('mod_edges',{})
        deps_out = [(k.split('→')[1], v) for k,v in me.items() if k.startswith(mod+'→') and k.split('→')[1]!=mod]
        deps_in = [(k.split('→')[0], v) for k,v in me.items() if k.endswith('→'+mod) and k.split('→')[0]!=mod]
        if deps_out or deps_in:
            body += '<h2>Dependencies</h2>'
            if deps_out:
                body += '<div style="font-size:.75rem;margin:.2rem 0"><b>Depends on:</b> '
                body += ', '.join(f'<a href="{fn_safe(m)}.html" style="color:{_mc(m,mods)}">{esc(m)} ({c2})</a>' for m,c2 in sorted(deps_out,key=lambda x:-x[1]))
                body += '</div>'
            if deps_in:
                body += '<div style="font-size:.75rem;margin:.2rem 0"><b>Used by:</b> '
                body += ', '.join(f'<a href="{fn_safe(m)}.html" style="color:{_mc(m,mods)}">{esc(m)} ({c2})</a>' for m,c2 in sorted(deps_in,key=lambda x:-x[1]))
                body += '</div>'
        
        zf.writestr(f'modules/{fn_safe(mod)}.html', page_wrap(f'Module: {mod}', body, 'mod', mod, '../'))

    zf.close()
    return buf.getvalue()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('graph_json')
    parser.add_argument('-o','--output',default='docs.html')
    parser.add_argument('--mode',choices=['single','multi'],default='single')
    args = parser.parse_args()
    graph = json.loads(Path(args.graph_json).read_text())
    if args.mode == 'single':
        Path(args.output).write_text(build_single(graph), encoding='utf-8')
    else:
        out = args.output if args.output.endswith('.zip') else args.output+'.zip'
        Path(out).write_bytes(build_multi(graph))
    print(f"Done: {args.output}")
