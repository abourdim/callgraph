#!/usr/bin/env python3
"""
Callgraph Studio — Data Dependencies Report Generator

Generates standalone HTML showing all data dependencies:
1. Global variable data flow (writer→reader chains)
2. Peripheral register data flow (per-register, ISR vs task)
3. RTOS queue/mutex dependencies (producer→consumer)
4. Struct field tracking (peripheral register access patterns)
"""

import json, sys, re
from pathlib import Path
from collections import defaultdict
from datetime import datetime

def esc(s):
    return (s or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

MOD_COLORS = ['#2563eb','#16a34a','#dc2626','#7c3aed','#d97706','#0891b2',
              '#db2777','#ea580c','#65a30d','#c026d3','#0284c7','#ca8a04',
              '#059669','#e11d48','#6366f1','#a16207','#0d9488','#eab308']

def _mc(mod, mods):
    clean = [m for m in mods if m not in ('external','.')]
    idx = clean.index(mod) if mod in clean else 0
    return MOD_COLORS[idx % len(MOD_COLORS)]

def _mod(n): return n.get('mod') or n.get('module') or 'external'


def _flow_svg(writers, name, readers, color='#60a5fa', w_label='Writers', r_label='Readers'):
    """Generic flow diagram: writers → central node → readers."""
    NW, NH, HGAP, VGAP = 170, 26, 40, 8
    max_rows = max(len(writers), len(readers), 1)
    W = 3*(NW+HGAP) + 20
    H = max(max_rows*(NH+VGAP)+40, 70)
    svg = f'<svg width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg" style="display:block;max-width:100%">\n'

    # Headers
    svg += f'<text x="{15+NW/2}" y="12" text-anchor="middle" font-size="8" fill="#888" font-family="monospace">{w_label}</text>\n'
    svg += f'<text x="{15+(NW+HGAP)+NW/2}" y="12" text-anchor="middle" font-size="8" fill="{color}" font-family="monospace" font-weight="600">{esc(name[:18])}</text>\n'
    svg += f'<text x="{15+2*(NW+HGAP)+NW/2}" y="12" text-anchor="middle" font-size="8" fill="#888" font-family="monospace">{r_label}</text>\n'

    # Center node
    cy = 20 + (max_rows*(NH+VGAP)-NH)/2
    cx = 15 + (NW+HGAP)
    svg += f'<rect x="{cx}" y="{cy}" width="{NW}" height="{NH}" rx="5" fill="{color}22" stroke="{color}" stroke-width="2.5"/>\n'
    label = name if len(name)<=22 else name[:20]+'…'
    svg += f'<text x="{cx+NW/2}" y="{cy+NH/2}" text-anchor="middle" dominant-baseline="middle" font-size="9" font-family="monospace" fill="{color}" font-weight="600">{esc(label)}</text>\n'

    # Writers
    for i, (fn, ctx, col) in enumerate(writers):
        y = 20 + i*(NH+VGAP)
        x = 15
        svg += f'<rect x="{x}" y="{y}" width="{NW}" height="{NH}" rx="4" fill="{col}0d" stroke="{col}" stroke-width="1.2"/>\n'
        fl = fn if len(fn)<=20 else fn[:18]+'…'
        svg += f'<text x="{x+NW/2}" y="{y+NH/2-3}" text-anchor="middle" dominant-baseline="middle" font-size="8" font-family="monospace" fill="{col}">{esc(fl)}</text>\n'
        if ctx:
            svg += f'<text x="{x+NW/2}" y="{y+NH/2+8}" text-anchor="middle" font-size="6" fill="#888" font-family="monospace">{esc(ctx)}</text>\n'
        # Arrow
        svg += f'<path d="M{x+NW},{y+NH/2} C{x+NW+HGAP/2},{y+NH/2} {cx-HGAP/2},{cy+NH/2} {cx},{cy+NH/2}" fill="none" stroke="{col}50" stroke-width="1.2"/>\n'

    # Readers
    for i, (fn, ctx, col) in enumerate(readers):
        y = 20 + i*(NH+VGAP)
        x = 15 + 2*(NW+HGAP)
        svg += f'<rect x="{x}" y="{y}" width="{NW}" height="{NH}" rx="4" fill="{col}0d" stroke="{col}" stroke-width="1.2"/>\n'
        fl = fn if len(fn)<=20 else fn[:18]+'…'
        svg += f'<text x="{x+NW/2}" y="{y+NH/2-3}" text-anchor="middle" dominant-baseline="middle" font-size="8" font-family="monospace" fill="{col}">{esc(fl)}</text>\n'
        if ctx:
            svg += f'<text x="{x+NW/2}" y="{y+NH/2+8}" text-anchor="middle" font-size="6" fill="#888" font-family="monospace">{esc(ctx)}</text>\n'
        svg += f'<path d="M{cx+NW},{cy+NH/2} C{cx+NW+HGAP/2},{cy+NH/2} {x-HGAP/2},{y+NH/2} {x},{y+NH/2}" fill="none" stroke="{col}50" stroke-width="1.2"/>\n'

    svg += '</svg>'
    return svg


def build_data_deps(graph):
    nmap = {n['id']: n for n in graph.get('nodes',[])}
    mods = [m for m in graph.get('mods',[]) if m not in ('external','.')]
    edges = graph.get('edges',{})
    callers = graph.get('callers',{})
    proj_name = Path(graph.get('source','project')).name
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    # ── Analyze ──────────────────────────────────────────

    # 1. Global variable data flow
    globals_flow = []
    gl = graph.get('globals',{})
    for gname, gmeta in gl.items():
        writers = []
        readers = []
        for n in graph['nodes']:
            if n.get('type')!='project': continue
            mod = _mod(n)
            col = _mc(mod, mods) if mod not in ('external','.') else '#888'
            ctx = 'ISR' if n.get('is_isr') else 'task'
            if gname in (n.get('writes',[]) or []): writers.append({'fn':n['id'],'mod':mod,'ctx':ctx,'col':col})
            if gname in (n.get('reads',[]) or []): readers.append({'fn':n['id'],'mod':mod,'ctx':ctx,'col':col})
            if gname in (n.get('rw',[]) or []): writers.append({'fn':n['id'],'mod':mod,'ctx':ctx,'col':col}); readers.append({'fn':n['id'],'mod':mod,'ctx':ctx,'col':col})
        if not writers and not readers: continue
        # Detect conflicts
        isr_writers = [w for w in writers if w['ctx']=='ISR']
        task_readers = [r for r in readers if r['ctx']=='task']
        conflict = bool(isr_writers) and bool(task_readers)
        globals_flow.append({
            'name':gname, 'volatile':gmeta.get('volatile',False), 'extern':gmeta.get('extern',False),
            'file':gmeta.get('file',''), 'line':gmeta.get('line',0),
            'writers':writers, 'readers':readers,
            'conflict':conflict, 'n_writers':len(writers), 'n_readers':len(readers),
            'cross_module': len(set(w['mod'] for w in writers) | set(r['mod'] for r in readers)) > 1,
        })
    globals_flow.sort(key=lambda g: -(g['n_writers']+g['n_readers']))

    # 2. Peripheral register data flow
    periph_flow = []
    reg_map = defaultdict(lambda: {'readers':[],'writers':[]})
    for n in graph['nodes']:
        if n.get('type')!='project': continue
        mod = _mod(n)
        col = _mc(mod, mods) if mod not in ('external','.') else '#888'
        ctx = 'ISR' if n.get('is_isr') else 'task'
        for p in n.get('peripherals',[]):
            reg_map[p]['readers' if 'read' in p.lower() or '->' in p else 'writers'].append(
                {'fn':n['id'],'mod':mod,'ctx':ctx,'col':col})
            # Also add as reader by default (we can't distinguish perfectly)
            if '->' in p:
                reg_map[p]['readers'].append({'fn':n['id'],'mod':mod,'ctx':ctx,'col':col})

    # Deduplicate and structure by peripheral base
    periph_bases = defaultdict(list)
    for reg, access in reg_map.items():
        base = reg.split('->')[0] if '->' in reg else reg
        reg_name = reg.split('->')[1] if '->' in reg else '(base)'
        # Deduplicate by fn
        seen_r = set(); seen_w = set()
        readers = [a for a in access['readers'] if a['fn'] not in seen_r and not seen_r.add(a['fn'])]
        writers = [a for a in access['writers'] if a['fn'] not in seen_w and not seen_w.add(a['fn'])]
        isr_access = any(a['ctx']=='ISR' for a in readers+writers)
        task_access = any(a['ctx']=='task' for a in readers+writers)
        periph_bases[base].append({
            'register':reg, 'reg_name':reg_name,
            'readers':readers[:10], 'writers':writers[:10],
            'isr_access':isr_access, 'task_access':task_access,
            'conflict':isr_access and task_access,
        })

    # 3. RTOS dependencies
    rtos = graph.get('rtos',{})
    tasks = rtos.get('tasks',{})
    objects = rtos.get('objects',{})
    rtos_flows = []

    for oname, odata in objects.items():
        kind = odata.get('kind','')
        users = odata.get('users',[])
        producers = []
        consumers = []
        holders = []
        for tname, tdata in tasks.items():
            mod = _mod(nmap.get(tname,{}))
            col = _mc(mod, mods) if mod not in ('external','.') else '#888'
            if oname in tdata.get('sends_to',[]): producers.append({'fn':tname,'mod':mod,'col':col,'role':'sender'})
            if oname in tdata.get('recvs_from',[]): consumers.append({'fn':tname,'mod':mod,'col':col,'role':'receiver'})
            if oname in tdata.get('takes',[]): holders.append({'fn':tname,'mod':mod,'col':col,'role':'takes'})
            if oname in tdata.get('gives',[]): holders.append({'fn':tname,'mod':mod,'col':col,'role':'gives'})
        # Also check ISRs for FromISR calls
        for n in graph['nodes']:
            if not n.get('is_isr'): continue
            for rc in n.get('rtos',[]):
                if rc.get('target')==oname:
                    mod = _mod(n)
                    col = _mc(mod, mods) if mod not in ('external','.') else '#888'
                    producers.append({'fn':n['id'],'mod':mod,'col':col,'role':'ISR sender'})

        rtos_flows.append({
            'name':oname, 'kind':kind, 'users':users,
            'producers':producers, 'consumers':consumers, 'holders':holders,
            'cross_module': len(set(p['mod'] for p in producers+consumers+holders)) > 1,
        })

    # 4. Struct field tracking (from peripheral access patterns)
    struct_fields = defaultdict(lambda: defaultdict(list))
    for n in graph['nodes']:
        if n.get('type')!='project': continue
        mod = _mod(n)
        col = _mc(mod, mods) if mod not in ('external','.') else '#888'
        for p in n.get('peripherals',[]):
            if '->' in p:
                base, field = p.split('->', 1)
                struct_fields[base][field].append({'fn':n['id'],'mod':mod,'col':col,'is_isr':n.get('is_isr',False)})

    # ── Build HTML ───────────────────────────────────────

    CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0c0e14;--bg2:#12151e;--bg3:#181c28;--text:#dce0ec;--text2:#8890a8;--text3:#555a6c;
--accent:#60a5fa;--border:#2a2f3e;--border2:#353b4e;--green:#4ade80;--red:#f87171;--amber:#fbbf24;--purple:#a78bfa;
--sidebar-w:220px;--font-body:'DM Sans',sans-serif;--font-head:'Source Serif 4',Georgia,serif;--font-mono:'IBM Plex Mono',monospace}
.light{--bg:#f5f5f0;--bg2:#fff;--bg3:#eaeae2;--text:#1a1a18;--text2:#555;--text3:#888;--accent:#2563eb;--border:#c8c8bc;--border2:#b8b8ac}
html,body{height:100%;overflow:hidden;font-family:var(--font-body);font-size:13px;background:var(--bg);color:var(--text)}
.shell{display:flex;height:100%}
.sidebar{width:var(--sidebar-w);background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;flex-shrink:0}
.sidebar-head{padding:.8rem 1rem;border-bottom:1px solid var(--border)}
.sidebar-head h1{font-family:var(--font-head);font-size:1rem;margin-bottom:.1rem}
.sidebar-head .sub{font-size:.6rem;color:var(--text3)}
.toc{flex:1;overflow-y:auto;padding:.4rem 0}
.toc-item{display:block;padding:.3rem .8rem;font-size:.68rem;color:var(--text2);cursor:pointer;text-decoration:none;border-left:2px solid transparent}
.toc-item:hover{background:var(--bg3);color:var(--accent)}
.toc-item.active{color:var(--accent);border-left-color:var(--accent);background:var(--accent)08}
.sidebar-foot{padding:.5rem .8rem;border-top:1px solid var(--border);display:flex;gap:.3rem;flex-wrap:wrap}
.sidebar-foot button{background:none;border:1px solid var(--border);border-radius:4px;padding:.15rem .4rem;font-size:.58rem;color:var(--text3);cursor:pointer}
.sidebar-foot button:hover{border-color:var(--accent);color:var(--accent)}
.content{flex:1;overflow-y:auto;padding:1.5rem 2.5rem 3rem}
.section{padding-bottom:1.5rem;border-bottom:1px solid var(--border);margin-bottom:1.5rem}
.sect-title{font-family:var(--font-head);font-size:1.15rem;margin-bottom:.6rem}
.search{width:100%;padding:.4rem .7rem;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-family:var(--font-mono);font-size:.75rem;outline:none;margin-bottom:.8rem}
.search:focus{border-color:var(--accent)}
table{width:100%;border-collapse:collapse;font-size:.75rem;margin:.5rem 0}
th{text-align:left;padding:.35rem .5rem;border-bottom:2px solid var(--border);font-weight:500;color:var(--text3);font-size:.62rem;text-transform:uppercase}
td{padding:.3rem .5rem;border-bottom:1px solid var(--border)}
tr:hover td{background:var(--bg3)}
.card{background:var(--bg2);border:1px solid var(--border);border-radius:8px;margin:.5rem 0;overflow:hidden}
.card-hdr{display:flex;align-items:center;gap:.4rem;padding:.45rem .7rem;cursor:pointer}
.card-hdr:hover{background:var(--bg3)}
.card-arrow{font-size:.55rem;color:var(--text3);transition:transform .2s}
.card.open .card-arrow{transform:rotate(90deg)}
.card-title{font-family:var(--font-mono);font-size:.8rem;font-weight:500;flex:1}
.card-body{display:none;padding:.5rem .7rem;border-top:1px solid var(--border);font-size:.75rem;line-height:1.6}
.card.open .card-body{display:block}
.graph-wrap{border:1px solid var(--border);border-radius:6px;padding:.4rem;margin:.4rem 0;overflow-x:auto;background:var(--bg)}
.tag{display:inline-block;font-size:.55rem;padding:.1rem .3rem;border-radius:3px;font-family:var(--font-mono)}
.tag-warn{background:#f8717118;color:#f87171}.tag-ok{background:#4ade8018;color:#4ade80}.tag-info{background:#60a5fa18;color:#60a5fa}
.tag-vol{background:#fbbf2418;color:#fbbf24}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:.5rem;margin-bottom:1rem}
.stat-card{background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:.5rem;text-align:center}
.stat-val{font-size:1.3rem;font-weight:600;font-family:var(--font-mono);color:var(--accent)}
.stat-label{font-size:.58rem;color:var(--text3);text-transform:uppercase;margin-top:.1rem}
@media print{.sidebar{display:none}.content{overflow:visible}.card-body{display:block!important}}
"""

    h = f'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(proj_name)} — Data Dependencies</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<div class="shell">
<nav class="sidebar">
  <div class="sidebar-head">
    <h1>{esc(proj_name)}</h1>
    <div class="sub">Data Dependencies · {now}</div>
  </div>
  <div class="toc">
    <a class="toc-item" onclick="jumpTo('overview')">◈ Overview</a>
    <a class="toc-item" onclick="jumpTo('globals')">📊 Globals ({len(globals_flow)})</a>
    <a class="toc-item" onclick="jumpTo('peripherals')">🔌 Peripherals ({len(periph_bases)})</a>
    <a class="toc-item" onclick="jumpTo('rtos')">🔄 RTOS Objects ({len(rtos_flows)})</a>
    <a class="toc-item" onclick="jumpTo('structs')">🏗 Struct Fields ({len(struct_fields)})</a>
  </div>
  <div class="sidebar-foot">
    <button onclick="document.documentElement.classList.toggle('light')">◐ Theme</button>
    <button onclick="window.print()">⎙ Print</button>
    <button onclick="document.querySelectorAll('.card').forEach(c=>c.classList.add('open'))">▶ All</button>
    <button onclick="document.querySelectorAll('.card').forEach(c=>c.classList.remove('open'))">▼ All</button>
  </div>
</nav>
<main class="content" id="content">
'''

    # ── Overview ─────────────────────────────────────────
    n_conflicts = sum(1 for g in globals_flow if g['conflict'])
    n_cross = sum(1 for g in globals_flow if g['cross_module'])
    n_periph_conflicts = sum(1 for regs in periph_bases.values() for r in regs if r['conflict'])

    h += f'''<div class="section" id="overview">
<div class="sect-title">◈ Data Dependencies Overview</div>
<div class="stats-grid">
  <div class="stat-card"><div class="stat-val">{len(globals_flow)}</div><div class="stat-label">Shared Globals</div></div>
  <div class="stat-card"><div class="stat-val">{n_conflicts}</div><div class="stat-label">ISR/Task Conflicts</div></div>
  <div class="stat-card"><div class="stat-val">{n_cross}</div><div class="stat-label">Cross-Module</div></div>
  <div class="stat-card"><div class="stat-val">{len(periph_bases)}</div><div class="stat-label">Peripherals</div></div>
  <div class="stat-card"><div class="stat-val">{sum(len(regs) for regs in periph_bases.values())}</div><div class="stat-label">Registers</div></div>
  <div class="stat-card"><div class="stat-val">{n_periph_conflicts}</div><div class="stat-label">Register Conflicts</div></div>
  <div class="stat-card"><div class="stat-val">{len(rtos_flows)}</div><div class="stat-label">RTOS Objects</div></div>
  <div class="stat-card"><div class="stat-val">{len(struct_fields)}</div><div class="stat-label">Struct Bases</div></div>
</div></div>
'''

    # ── 1. Global Variable Data Flow ─────────────────────
    h += '<div class="section" id="globals">'
    h += f'<div class="sect-title">📊 Global Variable Data Flow ({len(globals_flow)})</div>'
    h += '<div style="color:var(--text2);font-size:.78rem;margin-bottom:.6rem">Every shared global variable: who writes it, who reads it, ISR vs task context, cross-module access.</div>'

    if globals_flow:
        h += '<input class="search" placeholder="Search globals…" oninput="filterCards(this.value,\'glob-card\')">'
        h += '<table><thead><tr><th>Variable</th><th>Writers</th><th>Readers</th><th>Volatile</th><th>Cross-Mod</th><th>Conflict</th></tr></thead><tbody>'
        for g in globals_flow:
            conf_tag = '<span class="tag tag-warn">⚠ ISR/TASK</span>' if g['conflict'] else '<span class="tag tag-ok">OK</span>'
            vol_tag = '<span class="tag tag-vol">volatile</span>' if g['volatile'] else '—'
            cross_tag = '<span class="tag tag-info">cross</span>' if g['cross_module'] else '—'
            h += f'<tr><td style="font-family:var(--font-mono);color:var(--accent)">{esc(g["name"])}</td><td>{g["n_writers"]}</td><td>{g["n_readers"]}</td><td>{vol_tag}</td><td>{cross_tag}</td><td>{conf_tag}</td></tr>'
        h += '</tbody></table>'

        for g in globals_flow:
            col = '#f87171' if g['conflict'] else '#60a5fa'
            tags = ''
            if g['volatile']: tags += '<span class="tag tag-vol">volatile</span> '
            if g['conflict']: tags += '<span class="tag tag-warn">⚠ ISR/TASK CONFLICT</span> '
            if g['cross_module']: tags += '<span class="tag tag-info">cross-module</span> '

            h += f'<div class="card glob-card" data-name="{esc(g["name"])}">'
            h += f'<div class="card-hdr" onclick="this.parentElement.classList.toggle(\'open\')">'
            h += f'<span class="card-arrow">▶</span>'
            h += f'<span class="card-title" style="color:{col}">{esc(g["name"])}</span>'
            h += f'{tags}'
            h += f'<span style="font-size:.58rem;color:var(--text3)">{g["n_writers"]}W {g["n_readers"]}R · {esc(g["file"])}:{g["line"]}</span>'
            h += '</div><div class="card-body">'

            # Flow diagram
            w_items = [(w['fn'], w['ctx'], w['col']) for w in g['writers'][:8]]
            r_items = [(r['fn'], r['ctx'], r['col']) for r in g['readers'][:8]]
            if w_items or r_items:
                h += f'<div class="graph-wrap">{_flow_svg(w_items, g["name"], r_items, col)}</div>'

            # Detail lists
            if g['writers']:
                h += '<div style="font-size:.68rem;margin:.3rem 0"><b>Writers:</b> '
                h += ', '.join(f'<span style="color:{w["col"]}">{esc(w["fn"])}</span> <span style="color:var(--text3)">({w["ctx"]}·{esc(w["mod"])})</span>' for w in g['writers'])
                h += '</div>'
            if g['readers']:
                h += '<div style="font-size:.68rem;margin:.3rem 0"><b>Readers:</b> '
                h += ', '.join(f'<span style="color:{r["col"]}">{esc(r["fn"])}</span> <span style="color:var(--text3)">({r["ctx"]}·{esc(r["mod"])})</span>' for r in g['readers'])
                h += '</div>'
            h += '</div></div>'
    else:
        h += '<div style="color:var(--text3)">No shared globals detected.</div>'
    h += '</div>'

    # ── 2. Peripheral Register Data Flow ─────────────────
    h += '<div class="section" id="peripherals">'
    h += f'<div class="sect-title">🔌 Peripheral Register Data Flow ({len(periph_bases)})</div>'
    h += '<div style="color:var(--text2);font-size:.78rem;margin-bottom:.6rem">Every peripheral register accessed: who reads, who writes, ISR vs task context, potential conflicts.</div>'

    for base in sorted(periph_bases.keys()):
        regs = periph_bases[base]
        n_conf = sum(1 for r in regs if r['conflict'])
        conf_badge = f' <span class="tag tag-warn">⚠ {n_conf} conflicts</span>' if n_conf else ''

        h += f'<div class="card">'
        h += f'<div class="card-hdr" onclick="this.parentElement.classList.toggle(\'open\')">'
        h += f'<span class="card-arrow">▶</span>'
        h += f'<span class="card-title" style="color:var(--amber)">{esc(base)}</span>'
        h += f'{conf_badge}'
        h += f'<span style="font-size:.58rem;color:var(--text3)">{len(regs)} registers</span>'
        h += '</div><div class="card-body">'

        h += '<table><thead><tr><th>Register</th><th>Accessors</th><th>ISR</th><th>Task</th><th>Conflict</th></tr></thead><tbody>'
        for r in regs:
            all_fns = sorted(set(a['fn'] for a in r['readers']+r['writers']))
            conf = '<span class="tag tag-warn">⚠</span>' if r['conflict'] else '<span class="tag tag-ok">✓</span>'
            h += f'<tr><td style="font-family:var(--font-mono);color:var(--amber)">{esc(r["register"])}</td>'
            h += f'<td style="font-size:.65rem">{", ".join(esc(f) for f in all_fns[:6])}</td>'
            h += f'<td>{"✓" if r["isr_access"] else "—"}</td>'
            h += f'<td>{"✓" if r["task_access"] else "—"}</td>'
            h += f'<td>{conf}</td></tr>'
        h += '</tbody></table>'
        h += '</div></div>'

    if not periph_bases:
        h += '<div style="color:var(--text3)">No peripheral access detected.</div>'
    h += '</div>'

    # ── 3. RTOS Dependencies ─────────────────────────────
    h += '<div class="section" id="rtos">'
    h += f'<div class="sect-title">🔄 RTOS Object Dependencies ({len(rtos_flows)})</div>'
    h += '<div style="color:var(--text2);font-size:.78rem;margin-bottom:.6rem">Queues, mutexes, semaphores: who produces, who consumes, cross-module communication.</div>'

    for rf in rtos_flows:
        kind_icon = '📬' if rf['kind']=='queue' else '🔒' if rf['kind'] in ('mutex','semaphore') else '📦'
        cross_badge = ' <span class="tag tag-info">cross-module</span>' if rf['cross_module'] else ''

        h += f'<div class="card">'
        h += f'<div class="card-hdr" onclick="this.parentElement.classList.toggle(\'open\')">'
        h += f'<span class="card-arrow">▶</span>'
        h += f'<span class="card-title" style="color:var(--cyan)">{kind_icon} {esc(rf["name"])}</span>'
        h += f'<span class="tag tag-info">{esc(rf["kind"])}</span>{cross_badge}'
        h += '</div><div class="card-body">'

        # Flow diagram for queues
        if rf['producers'] or rf['consumers']:
            w = [(p['fn'], p['role'], p['col']) for p in rf['producers'][:6]]
            r = [(c['fn'], c['role'], c['col']) for c in rf['consumers'][:6]]
            h += f'<div class="graph-wrap">{_flow_svg(w, rf["name"], r, "#22d3ee", "Producers", "Consumers")}</div>'

        if rf['producers']:
            h += '<div style="font-size:.7rem;margin:.2rem 0"><b>Producers:</b> '
            h += ', '.join(f'<span style="color:{p["col"]}">{esc(p["fn"])}</span> ({p["role"]})' for p in rf['producers'])
            h += '</div>'
        if rf['consumers']:
            h += '<div style="font-size:.7rem;margin:.2rem 0"><b>Consumers:</b> '
            h += ', '.join(f'<span style="color:{c["col"]}">{esc(c["fn"])}</span> ({c["role"]})' for c in rf['consumers'])
            h += '</div>'
        if rf['holders']:
            h += '<div style="font-size:.7rem;margin:.2rem 0"><b>Lock holders:</b> '
            h += ', '.join(f'<span style="color:{h2["col"]}">{esc(h2["fn"])}</span> ({h2["role"]})' for h2 in rf['holders'])
            h += '</div>'
        h += '</div></div>'

    if not rtos_flows:
        h += '<div style="color:var(--text3)">No RTOS objects detected.</div>'
    h += '</div>'

    # ── 4. Struct Field Tracking ─────────────────────────
    h += '<div class="section" id="structs">'
    h += f'<div class="sect-title">🏗 Struct Field Access ({len(struct_fields)})</div>'
    h += '<div style="color:var(--text2);font-size:.78rem;margin-bottom:.6rem">Peripheral register access patterns: which functions touch which fields of each hardware struct.</div>'

    for base in sorted(struct_fields.keys()):
        fields = struct_fields[base]
        total_accessors = set()
        for fld, accs in fields.items():
            for a in accs: total_accessors.add(a['fn'])

        h += f'<div class="card">'
        h += f'<div class="card-hdr" onclick="this.parentElement.classList.toggle(\'open\')">'
        h += f'<span class="card-arrow">▶</span>'
        h += f'<span class="card-title" style="color:var(--amber)">{esc(base)}</span>'
        h += f'<span style="font-size:.58rem;color:var(--text3)">{len(fields)} fields · {len(total_accessors)} functions</span>'
        h += '</div><div class="card-body">'

        h += '<table><thead><tr><th>Field</th><th>Accessors</th><th>ISR</th><th>Modules</th></tr></thead><tbody>'
        for field in sorted(fields.keys()):
            accs = fields[field]
            fns = sorted(set(a['fn'] for a in accs))
            has_isr = any(a['is_isr'] for a in accs)
            mods_involved = sorted(set(a['mod'] for a in accs))
            h += f'<tr><td style="font-family:var(--font-mono);color:var(--amber)">{esc(base)}->{esc(field)}</td>'
            h += f'<td style="font-size:.65rem">{", ".join(esc(f) for f in fns[:6])}{"…" if len(fns)>6 else ""}</td>'
            h += f'<td>{"⚡" if has_isr else "—"}</td>'
            h += f'<td style="font-size:.65rem">{", ".join(esc(m) for m in mods_involved)}</td></tr>'
        h += '</tbody></table>'
        h += '</div></div>'

    if not struct_fields:
        h += '<div style="color:var(--text3)">No struct field access patterns detected.</div>'
    h += '</div>'

    # ── Footer + JS ──────────────────────────────────────
    h += f'<div style="text-align:center;padding:2rem 0;font-size:.62rem;color:var(--text3);border-top:1px solid var(--border)">Generated by Callgraph Studio · {now}</div>'

    h += '''
<script>
function jumpTo(id){const el=document.getElementById(id);if(el)el.scrollIntoView({behavior:'smooth',block:'start'});}
function filterCards(q, cls){
  const ql=q.toLowerCase();
  document.querySelectorAll('.'+cls).forEach(c=>{
    c.style.display=(c.dataset.name||'').toLowerCase().includes(ql)?'':'none';
  });
}
// Scroll spy for TOC
const contentEl=document.getElementById('content');
const tocItems=document.querySelectorAll('.toc-item');
const sections=['overview','globals','peripherals','rtos','structs'];
contentEl.addEventListener('scroll',()=>{
  const st=contentEl.scrollTop;
  let active='overview';
  sections.forEach(s=>{const el=document.getElementById(s);if(el&&el.offsetTop-100<=st)active=s;});
  tocItems.forEach((t,i)=>t.classList.toggle('active',sections[i]===active));
});
</script>
</main></div></body></html>'''

    return h


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('graph_json')
    parser.add_argument('-o','--output',default='data-deps.html')
    args = parser.parse_args()
    graph = json.loads(Path(args.graph_json).read_text())
    html = build_data_deps(graph)
    Path(args.output).write_text(html, encoding='utf-8')
    print(f"Data deps: {args.output} ({len(html)} bytes)")
