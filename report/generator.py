#!/usr/bin/env python3
"""
Callgraph Studio — Report Generator v2.0 (Deep Analysis)

Exhaustive handover report: every function, every global, every peripheral
register, every race condition, every cross-module interaction documented.

Engines:
  1. Architecture narrative (auto-generated prose)
  2. Exhaustive requirements (100-300 per project)
  3. Function-level deep analysis (every function)
  4. Data flow narrative (per-task, per-ISR, per-global)
  5. Block interaction map (every module pair)
  6. Peripheral register map (every register, every accessor)
  7. Race condition deep analysis (per-race full page)
  8. Risk & complexity scoring (per-function + per-module)
  9. Reading order with rationale
  10. Pattern detection (state machines, producer-consumer, etc.)
  11. Bus factor & change difficulty (per-function)
  12. Dead code investigation
  13. Exhaustive question generator (50-100)
  14. Glossary (every entity)
  15. Recommended tools (context-aware)
  16. Boot/init timeline (deep)
"""

import json, sys, os, math, re
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# ── Helpers ──────────────────────────────────────────────

def esc(s): return (s or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def _nmap(graph): return {n['id']: n for n in graph.get('nodes',[])}

def _mod(n):
    return n.get('mod') or n.get('module') or 'external'

def _proj(graph):
    return {n['id'] for n in graph['nodes'] if n.get('type')=='project'}

def _bfs(start, adj, max_d=999):
    vis = {start:0}; q=[start]
    while q:
        n = q.pop(0); d = vis[n]
        if d >= max_d: continue
        for c in adj.get(n,[]):
            if c not in vis: vis[c]=d+1; q.append(c)
    return vis

def _impact(fn, edges):
    return len(_bfs(fn, edges)) - 1

# ══════════════════════════════════════════════════════════
# ENGINE 1: ARCHITECTURE NARRATIVE
# ══════════════════════════════════════════════════════════

def build_architecture_narrative(graph):
    nmap = _nmap(graph)
    mods = [m for m in graph.get('mods',[]) if m not in ('external','.')]
    edges = graph.get('edges',{})
    callers = graph.get('callers',{})
    me = graph.get('mod_edges',{})
    periph = graph.get('peripherals',{})
    rtos = graph.get('rtos',{})
    races = graph.get('races',[])
    isrs = [n for n in graph['nodes'] if n.get('is_isr')]
    tasks = rtos.get('tasks',{})
    n_fns = len(graph['nodes'])
    n_edges = sum(len(v) for v in edges.values())
    n_files = graph.get('files',0)

    narrative = []

    # System overview
    narrative.append({
        'title': 'System Overview',
        'text': f'This project consists of {n_fns} functions organized into {len(mods)} modules '
                f'across {n_files} source files. The call graph contains {n_edges} directed edges '
                f'representing function-to-function call relationships. '
                f'{"The system uses FreeRTOS/CMSIS-RTOS with " + str(len(tasks)) + " tasks." if tasks else "No RTOS usage detected."} '
                f'{"There are " + str(len(isrs)) + " interrupt service routines." if isrs else "No ISRs detected."} '
                f'{"The system accesses " + str(len(periph)) + " peripheral blocks." if periph else "No direct peripheral access detected."} '
                f'{"WARNING: " + str(len(races)) + " race condition candidates were identified." if races else "No race conditions detected."}'
    })

    # Module descriptions
    for mod in mods:
        mod_fns = [n for n in graph['nodes'] if _mod(n)==mod]
        mod_files = sorted(set(n.get('file','') for n in mod_fns if n.get('file')))
        mod_isrs = [n for n in mod_fns if n.get('is_isr')]
        mod_entries = [n for n in mod_fns if n.get('is_entry')]
        mod_periphs = set()
        for n in mod_fns:
            for p in n.get('peripherals',[]):
                mod_periphs.add(p.split('->')[0])
        mod_globals_w = set()
        mod_globals_r = set()
        for n in mod_fns:
            mod_globals_w.update(n.get('writes',[]))
            mod_globals_r.update(n.get('reads',[]))

        # Infer purpose from function names and peripherals
        fn_names = ' '.join(n['id'].lower() for n in mod_fns)
        purpose_hints = []
        if any(w in fn_names for w in ['uart','usart','serial','comm','tx','rx']): purpose_hints.append('serial communication')
        if any(w in fn_names for w in ['spi','miso','mosi']): purpose_hints.append('SPI interface')
        if any(w in fn_names for w in ['i2c','twi','scl','sda']): purpose_hints.append('I2C interface')
        if any(w in fn_names for w in ['adc','analog','sensor','measure']): purpose_hints.append('analog sensing')
        if any(w in fn_names for w in ['gpio','pin','port','led','button']): purpose_hints.append('GPIO/digital I/O')
        if any(w in fn_names for w in ['timer','pwm','capture','compare']): purpose_hints.append('timer/PWM')
        if any(w in fn_names for w in ['flash','eeprom','nvm','storage']): purpose_hints.append('non-volatile storage')
        if any(w in fn_names for w in ['dma','transfer']): purpose_hints.append('DMA transfers')
        if any(w in fn_names for w in ['nfc','rfid','tag','card','reader']): purpose_hints.append('NFC/RFID')
        if any(w in fn_names for w in ['motor','drive','pwm','speed']): purpose_hints.append('motor control')
        if any(w in fn_names for w in ['display','lcd','oled','screen']): purpose_hints.append('display')
        if any(w in fn_names for w in ['init','setup','config','start']): purpose_hints.append('initialization/configuration')
        if any(w in fn_names for w in ['task','thread','process']): purpose_hints.append('task management')
        if any(w in fn_names for w in ['queue','event','notify','signal']): purpose_hints.append('inter-task communication')
        if any(w in fn_names for w in ['error','fault','assert','panic']): purpose_hints.append('error handling')
        if any(w in fn_names for w in ['test','check','verify','validate']): purpose_hints.append('testing/validation')
        if any(w in fn_names for w in ['log','print','debug','trace']): purpose_hints.append('logging/debug')
        if any(w in fn_names for w in ['host','reg','register','cmd','command']): purpose_hints.append('host interface/register map')
        if any(w in fn_names for w in ['pilot','state','machine','fsm']): purpose_hints.append('state machine / control logic')
        if any(w in fn_names for w in ['cal','calibr','offset','gain']): purpose_hints.append('calibration')

        purpose = ', '.join(purpose_hints[:5]) if purpose_hints else 'general functionality'

        # Dependencies
        deps_out = {to for key in me if key.startswith(mod+'→') for to in [key.split('→')[1]] if to != mod}
        deps_in = {fr for key in me if key.endswith('→'+mod) for fr in [key.split('→')[0]] if fr != mod}

        text = f'Module "{mod}" contains {len(mod_fns)} functions across {len(mod_files)} files. '
        text += f'Its primary role appears to be: {purpose}. '
        if mod_isrs: text += f'It contains {len(mod_isrs)} ISR handlers: {", ".join(n["id"] for n in mod_isrs)}. '
        if mod_entries: text += f'It contains entry points: {", ".join(n["id"] for n in mod_entries)}. '
        if mod_periphs: text += f'It directly accesses hardware peripherals: {", ".join(sorted(mod_periphs))}. '
        if mod_globals_w: text += f'It writes to {len(mod_globals_w)} global variables. '
        if deps_out: text += f'It depends on: {", ".join(sorted(deps_out))}. '
        if deps_in: text += f'It is used by: {", ".join(sorted(deps_in))}. '

        narrative.append({'title': f'Module: {mod}', 'text': text, 'mod': mod})

    # Layer description
    dep_graph = defaultdict(set)
    for key in me:
        parts = key.split('→')
        if len(parts)==2 and parts[0] in mods and parts[1] in mods and parts[0]!=parts[1]:
            dep_graph[parts[0]].add(parts[1])
    has_deps = {m for m,ds in dep_graph.items() if ds}
    depended_on = {d for ds in dep_graph.values() for d in ds}
    top_layer = [m for m in mods if m in has_deps and m not in depended_on]
    mid_layer = [m for m in mods if m in has_deps and m in depended_on]
    bot_layer = [m for m in mods if m not in has_deps]

    layer_text = 'The system follows a layered architecture: '
    if top_layer: layer_text += f'Application layer ({", ".join(top_layer)}) → '
    if mid_layer: layer_text += f'Middle layer ({", ".join(mid_layer)}) → '
    if bot_layer: layer_text += f'Foundation layer ({", ".join(bot_layer)}). '
    else: layer_text += 'No clear layering detected (flat architecture). '
    layer_text += f'There are {len(me)} cross-module call relationships.'

    narrative.append({'title': 'Architecture Layers', 'text': layer_text})

    # Data flow summary
    if tasks or isrs:
        flow_text = 'Data flows through the system via: '
        flows = []
        if isrs: flows.append(f'{len(isrs)} interrupt handlers capturing hardware events')
        if tasks: flows.append(f'{len(tasks)} RTOS tasks processing data')
        rtos_objs = rtos.get('objects',{})
        queues = [k for k,v in rtos_objs.items() if v.get('kind')=='queue']
        mutexes = [k for k,v in rtos_objs.items() if v.get('kind') in ('mutex','semaphore')]
        if queues: flows.append(f'{len(queues)} message queues ({", ".join(queues[:5])})')
        if mutexes: flows.append(f'{len(mutexes)} mutexes/semaphores ({", ".join(mutexes[:5])})')
        shared_globals = set()
        for r in races: shared_globals.add(r.get('var',''))
        if shared_globals: flows.append(f'{len(shared_globals)} shared global variables with concurrent access')
        flow_text += '; '.join(flows) + '.'
        narrative.append({'title': 'Data Flow Overview', 'text': flow_text})

    return narrative


# ══════════════════════════════════════════════════════════
# ENGINE 2: EXHAUSTIVE REQUIREMENTS
# ══════════════════════════════════════════════════════════

def build_requirements(graph):
    nmap = _nmap(graph)
    reqs = []
    rid = [0]
    def add(cat, sub, desc, evidence, conf, related=None):
        rid[0] += 1
        reqs.append({'id':f'REQ-{rid[0]:03d}','category':cat,'subcategory':sub,
                      'description':desc,'evidence':evidence,'confidence':conf,
                      'related_functions':related or []})

    # Per-module functional requirements
    mods = [m for m in graph.get('mods',[]) if m not in ('external','.')]
    for mod in mods:
        mod_fns = [n for n in graph['nodes'] if _mod(n)==mod]
        fn_names = [n['id'] for n in mod_fns]
        add('functional','module',f'System shall include the "{mod}" subsystem with {len(mod_fns)} functions',
            f'Module contains: {", ".join(fn_names[:10])}{"..." if len(fn_names)>10 else ""}','high',fn_names[:5])

    # Per-task requirements
    tasks = graph.get('rtos',{}).get('tasks',{})
    for tname, tdata in tasks.items():
        desc = f'System shall execute task "{tname}" as a concurrent RTOS task'
        ev_parts = []
        if tdata.get('sends_to'): ev_parts.append(f'sends to: {", ".join(tdata["sends_to"])}')
        if tdata.get('recvs_from'): ev_parts.append(f'receives from: {", ".join(tdata["recvs_from"])}')
        if tdata.get('takes'): ev_parts.append(f'takes: {", ".join(tdata["takes"])}')
        if tdata.get('delays'): ev_parts.append(f'delays: {", ".join(str(d) for d in tdata["delays"][:3])}')
        add('functional','rtos_task',desc,'; '.join(ev_parts) or 'Task creation detected','high',[tname])

    # Per-ISR requirements
    for n in graph['nodes']:
        if not n.get('is_isr'): continue
        writes = n.get('writes',[])
        periphs = n.get('peripherals',[])
        desc = f'System shall handle interrupt "{n["id"]}" with maximum allowable latency'
        ev = f'ISR handler in {n.get("file","")}, line {n.get("line",0)}'
        if writes: ev += f'; writes globals: {", ".join(writes)}'
        if periphs: ev += f'; accesses: {", ".join(periphs)}'
        add('timing','isr',desc,ev,'high',[n['id']])

    # Per-peripheral requirements (register level)
    periph = graph.get('peripherals',{})
    for pname, pdata in periph.items():
        readers = pdata.get('readers',[])
        writers = pdata.get('writers',[])
        rw = pdata.get('rw',[])
        all_accessors = sorted(set(readers + writers + rw))
        add('hardware','peripheral',f'System shall interface with {pname} peripheral',
            f'Accessed by {len(all_accessors)} functions: {", ".join(all_accessors[:8])}','high',all_accessors[:5])

    # Per-register requirements (from node peripherals field)
    reg_map = defaultdict(lambda: {'readers':set(),'writers':set()})
    for n in graph['nodes']:
        for p in n.get('peripherals',[]):
            if '->' in p:
                base, reg = p.split('->', 1)
                if p in ' '.join(n.get('writes',[]) or []):
                    reg_map[p]['writers'].add(n['id'])
                else:
                    reg_map[p]['readers'].add(n['id'])
    for reg, access in reg_map.items():
        all_fns = sorted(access['readers'] | access['writers'])
        add('hardware','register',f'System shall access register {reg}',
            f'Read by: {", ".join(sorted(access["readers"]))}; Written by: {", ".join(sorted(access["writers"]))}',
            'high', all_fns[:5])

    # Per-shared-global concurrency requirements
    gl = graph.get('globals',{})
    for gname, gmeta in gl.items():
        # Find all functions that access this global
        readers = set()
        writers = set()
        for n in graph['nodes']:
            if gname in (n.get('reads',[]) or []): readers.add(n['id'])
            if gname in (n.get('writes',[]) or []): writers.add(n['id'])
            if gname in (n.get('rw',[]) or []): readers.add(n['id']); writers.add(n['id'])
        if len(readers)+len(writers) < 2: continue
        vol = 'volatile ' if gmeta.get('volatile') else ''
        ext = 'extern ' if gmeta.get('extern') else ''
        desc = f'{vol}{ext}global "{gname}" shall be accessed safely by {len(readers|writers)} functions'
        ev = f'Declared in {gmeta.get("file","")}: readers={", ".join(sorted(readers)[:5])}; writers={", ".join(sorted(writers)[:5])}'
        add('concurrency','shared_global',desc,ev,'high' if gmeta.get('volatile') else 'medium',
            sorted(readers|writers)[:5])

    # Per-race protection requirements
    for r in graph.get('races',[]):
        desc = f'Race on "{r["var"]}": access from {r["task_fn"]} ({r.get("task_access","?")}) ' \
               f'and ISR writers {", ".join(r.get("isr_writers",[]))} shall be protected'
        fix = 'Use critical section or volatile+atomic' if not r.get('protected') else 'Already protected via critical section'
        add('safety','race',desc,
            f'Severity: {r.get("severity","?")}; Protected: {r.get("protected",False)}; Fix: {fix}',
            'high' if r.get('severity')=='high' else 'medium',
            [r['task_fn']] + r.get('isr_writers',[]))

    # Per cross-module interface requirements
    me = graph.get('mod_edges',{})
    edges = graph.get('edges',{})
    for key, count in me.items():
        parts = key.split('→')
        if len(parts)!=2: continue
        fr, to = parts
        # Find actual cross-module functions
        cross_calls = []
        for caller_fn, callees in edges.items():
            cn = nmap.get(caller_fn,{})
            if _mod(cn) != fr: continue
            for callee_fn in callees:
                cn2 = nmap.get(callee_fn,{})
                if _mod(cn2) == to:
                    cross_calls.append(f'{caller_fn}→{callee_fn}')
        desc = f'Module "{fr}" shall interface with module "{to}" via {count} call edges'
        add('interface','cross_module',desc,
            f'Calls: {"; ".join(cross_calls[:8])}{"..." if len(cross_calls)>8 else ""}',
            'high', [c.split('→')[0] for c in cross_calls[:3]])

    # Critical section requirements
    crit_fns = [n for n in graph['nodes'] if n.get('has_critical')]
    if crit_fns:
        for n in crit_fns:
            add('concurrency','critical_section',
                f'Function "{n["id"]}" uses critical sections for mutual exclusion',
                f'File: {n.get("file","")}, line {n.get("line",0)}','high',[n['id']])

    # Delay/timing requirements
    delay_fns = [n for n in graph['nodes'] if n.get('delay_in_loop')]
    for n in delay_fns:
        add('timing','polling',f'Function "{n["id"]}" implements polling with delay-in-loop',
            f'File: {n.get("file","")}, line {n.get("line",0)}. Verify timing requirements.','medium',[n['id']])

    # Entry point requirements
    for n in graph['nodes']:
        if n.get('is_entry') and n.get('type')=='project':
            add('functional','entry',f'Function "{n["id"]}" is a system entry point',
                f'File: {n.get("file","")}:{n.get("line",0)}','high',[n['id']])

    return reqs


# ══════════════════════════════════════════════════════════
# ENGINE 3: FUNCTION-LEVEL DEEP ANALYSIS
# ══════════════════════════════════════════════════════════

def analyze_functions_deep(graph):
    nmap = _nmap(graph)
    edges = graph.get('edges',{})
    callers = graph.get('callers',{})
    races = graph.get('races',[])
    race_fns = set()
    for r in races:
        race_fns.add(r.get('task_fn',''))
        for w in r.get('isr_writers',[]): race_fns.add(w)

    results = []
    for n in graph['nodes']:
        if n.get('type') != 'project': continue
        fn = n['id']
        fn_callers = callers.get(fn,[])
        fn_callees = edges.get(fn,[])
        fn_reads = n.get('reads',[])
        fn_writes = n.get('writes',[])
        fn_rw = n.get('rw',[])
        fn_periphs = n.get('peripherals',[])

        # Complexity: fan_in * fan_out + globals coupling
        fan_in = len(fn_callers)
        fan_out = len(fn_callees)
        global_coupling = len(fn_reads) + len(fn_writes) + len(fn_rw)
        complexity = fan_in * fan_out + global_coupling * 2

        # Impact radius
        impact = _impact(fn, edges)

        # Risk factors
        risk_factors = []
        risk_score = 0
        if fn in race_fns:
            risk_factors.append('Involved in race condition')
            risk_score += 30
        if n.get('is_isr'):
            risk_factors.append('ISR — timing-critical, must be fast')
            risk_score += 20
        if fn_writes:
            risk_factors.append(f'Writes {len(fn_writes)} globals: {", ".join(fn_writes[:5])}')
            risk_score += len(fn_writes) * 5
        if fn_periphs:
            risk_factors.append(f'Direct hardware access: {", ".join(fn_periphs[:5])}')
            risk_score += 10
        if impact > 10:
            risk_factors.append(f'High impact: {impact} downstream functions affected')
            risk_score += 15
        if fan_in > 5:
            risk_factors.append(f'Many callers ({fan_in}) — changes affect many call sites')
            risk_score += 10
        if n.get('has_critical'):
            risk_factors.append('Uses critical sections')
            risk_score += 5
        if n.get('delay_in_loop'):
            risk_factors.append('Contains delay-in-loop (polling pattern)')
            risk_score += 5

        risk_level = 'low' if risk_score < 20 else 'medium' if risk_score < 40 else 'high' if risk_score < 60 else 'critical'

        # Infer purpose from name
        name_lower = fn.lower()
        purpose_hints = []
        if 'init' in name_lower: purpose_hints.append('initialization')
        if 'read' in name_lower: purpose_hints.append('data reading')
        if 'write' in name_lower: purpose_hints.append('data writing')
        if 'send' in name_lower: purpose_hints.append('data transmission')
        if 'recv' in name_lower or 'receive' in name_lower: purpose_hints.append('data reception')
        if 'set' in name_lower and 'reset' not in name_lower: purpose_hints.append('configuration/setter')
        if 'get' in name_lower: purpose_hints.append('getter/accessor')
        if 'handler' in name_lower or 'irq' in name_lower: purpose_hints.append('interrupt handling')
        if 'task' in name_lower or 'thread' in name_lower: purpose_hints.append('RTOS task')
        if 'enable' in name_lower: purpose_hints.append('enable/activate')
        if 'disable' in name_lower: purpose_hints.append('disable/deactivate')
        if 'reset' in name_lower: purpose_hints.append('reset')
        if 'check' in name_lower or 'is_' in name_lower: purpose_hints.append('status check')
        if 'process' in name_lower: purpose_hints.append('data processing')
        if 'callback' in name_lower or 'cb_' in name_lower: purpose_hints.append('callback handler')
        if 'error' in name_lower or 'fault' in name_lower: purpose_hints.append('error handling')
        purpose = ', '.join(purpose_hints) if purpose_hints else 'general'

        # Recommended reading before modifying
        prereqs = set()
        for c in fn_callers[:5]: prereqs.add(c)
        for c in fn_callees[:5]: prereqs.add(c)
        prereqs.discard(fn)

        results.append({
            'id': fn,
            'file': n.get('file',''),
            'line': n.get('line',0),
            'mod': _mod(n),
            'purpose': purpose,
            'complexity': complexity,
            'complexity_label': 'low' if complexity < 10 else 'medium' if complexity < 30 else 'high',
            'impact': impact,
            'risk_score': min(risk_score, 100),
            'risk_level': risk_level,
            'risk_factors': risk_factors,
            'fan_in': fan_in,
            'fan_out': fan_out,
            'callers': fn_callers,
            'callees': fn_callees,
            'reads': fn_reads,
            'writes': fn_writes,
            'rw': fn_rw,
            'peripherals': fn_periphs,
            'is_isr': n.get('is_isr', False),
            'is_entry': n.get('is_entry', False),
            'has_critical': n.get('has_critical', False),
            'delay_in_loop': n.get('delay_in_loop', False),
            'rtos': n.get('rtos', []),
            'prereqs': sorted(prereqs),
        })

    results.sort(key=lambda x: -x['risk_score'])
    return results


# ══════════════════════════════════════════════════════════
# ENGINE 4: DATA FLOW NARRATIVE
# ══════════════════════════════════════════════════════════

def build_data_flows(graph):
    nmap = _nmap(graph)
    edges = graph.get('edges',{})
    rtos = graph.get('rtos',{})
    tasks = rtos.get('tasks',{})
    objects = rtos.get('objects',{})
    flows = []

    # Per-ISR flow
    for n in graph['nodes']:
        if not n.get('is_isr'): continue
        writes = n.get('writes',[])
        periphs = n.get('peripherals',[])
        callees = edges.get(n['id'],[])
        rtos_calls = n.get('rtos',[])

        text = f'**{n["id"]}** (ISR in {n.get("file","")}) fires on interrupt. '
        if periphs: text += f'It reads/writes hardware registers: {", ".join(periphs)}. '
        if writes: text += f'It writes global variables: {", ".join(writes)}. '
        from_isr_calls = [rc for rc in rtos_calls if 'FromISR' in (rc.get('api','') or '')]
        if from_isr_calls:
            for rc in from_isr_calls:
                text += f'It calls {rc["api"]}({rc.get("target","?")}) to notify tasks. '
        if callees: text += f'It calls: {", ".join(callees[:5])}. '

        # Find which tasks consume the data this ISR produces
        consumers = []
        for gvar in writes:
            for n2 in graph['nodes']:
                if n2['id'] == n['id']: continue
                if gvar in (n2.get('reads',[]) or []) or gvar in (n2.get('rw',[]) or []):
                    consumers.append(f'{n2["id"]} reads {gvar}')
        if consumers: text += f'Data consumers: {"; ".join(consumers[:5])}. '

        flows.append({'type':'isr','fn':n['id'],'text':text,'severity':'high' if writes else 'medium'})

    # Per-task flow
    for tname, tdata in tasks.items():
        tn = nmap.get(tname,{})
        text = f'**{tname}** (task in {tn.get("file","")}) '
        parts = []
        if tdata.get('recvs_from'): parts.append(f'receives data from queues: {", ".join(tdata["recvs_from"])}')
        if tdata.get('sends_to'): parts.append(f'sends data to queues: {", ".join(tdata["sends_to"])}')
        if tdata.get('takes'): parts.append(f'acquires mutexes: {", ".join(tdata["takes"])}')
        if tdata.get('gives'): parts.append(f'releases mutexes: {", ".join(tdata["gives"])}')
        if tdata.get('delays'): parts.append(f'delays: {", ".join(str(d) for d in tdata["delays"][:3])}')
        text += '; '.join(parts) + '. ' if parts else 'runs as an RTOS task. '

        callees = edges.get(tname,[])
        if callees: text += f'Calls: {", ".join(callees[:8])}. '
        reads = tn.get('reads',[])
        writes = tn.get('writes',[])
        if reads: text += f'Reads globals: {", ".join(reads[:5])}. '
        if writes: text += f'Writes globals: {", ".join(writes[:5])}. '

        flows.append({'type':'task','fn':tname,'text':text,'severity':'medium'})

    # Per shared global flow
    for r in graph.get('races',[]):
        text = f'**{r["var"]}** — shared between ISR ({", ".join(r.get("isr_writers",[]))}) '
        text += f'and task ({r["task_fn"]}). '
        text += f'Task access type: {r.get("task_access","?")}. '
        text += f'Protection: {"critical section" if r.get("protected") else "NONE — UNPROTECTED"}. '
        text += f'Volatile: {"yes" if r.get("volatile") else "no"}. '
        text += f'Severity: {r.get("severity","?")}. '
        if not r.get('protected'):
            text += 'RECOMMENDATION: Protect with __disable_irq() / taskENTER_CRITICAL() or use atomic operations.'
        flows.append({'type':'race','fn':r['var'],'text':text,'severity':r.get('severity','medium')})

    return flows


# ══════════════════════════════════════════════════════════
# ENGINE 5: BLOCK INTERACTION MAP
# ══════════════════════════════════════════════════════════

def build_interactions(graph):
    nmap = _nmap(graph)
    edges = graph.get('edges',{})
    mods = [m for m in graph.get('mods',[]) if m not in ('external','.')]
    gl = graph.get('globals',{})
    interactions = []

    # For each module pair
    for i, m1 in enumerate(mods):
        for m2 in mods[i+1:]:
            m1_fns = {n['id'] for n in graph['nodes'] if _mod(n)==m1}
            m2_fns = {n['id'] for n in graph['nodes'] if _mod(n)==m2}

            # Direct calls m1→m2
            calls_12 = []
            for fn in m1_fns:
                for callee in edges.get(fn,[]):
                    if callee in m2_fns:
                        calls_12.append(f'{fn}→{callee}')
            # Direct calls m2→m1
            calls_21 = []
            for fn in m2_fns:
                for callee in edges.get(fn,[]):
                    if callee in m1_fns:
                        calls_21.append(f'{fn}→{callee}')

            # Shared globals
            m1_globals = set()
            m2_globals = set()
            for n in graph['nodes']:
                if _mod(n)==m1:
                    m1_globals.update(n.get('reads',[])); m1_globals.update(n.get('writes',[])); m1_globals.update(n.get('rw',[]))
                if _mod(n)==m2:
                    m2_globals.update(n.get('reads',[])); m2_globals.update(n.get('writes',[])); m2_globals.update(n.get('rw',[]))
            shared = sorted(m1_globals & m2_globals)

            # Shared peripherals
            m1_periphs = set()
            m2_periphs = set()
            for n in graph['nodes']:
                if _mod(n)==m1:
                    for p in n.get('peripherals',[]): m1_periphs.add(p.split('->')[0])
                if _mod(n)==m2:
                    for p in n.get('peripherals',[]): m2_periphs.add(p.split('->')[0])
            shared_periphs = sorted(m1_periphs & m2_periphs)

            if not calls_12 and not calls_21 and not shared and not shared_periphs:
                continue

            interactions.append({
                'mod1': m1, 'mod2': m2,
                'calls_12': calls_12, 'calls_21': calls_21,
                'shared_globals': shared[:20],
                'shared_peripherals': shared_periphs,
                'total_edges': len(calls_12) + len(calls_21),
            })

    interactions.sort(key=lambda x: -x['total_edges'])
    return interactions


# ══════════════════════════════════════════════════════════
# ENGINE 6: PERIPHERAL REGISTER MAP (EXHAUSTIVE)
# ══════════════════════════════════════════════════════════

def build_peripheral_map(graph):
    nmap = _nmap(graph)
    periph_detail = defaultdict(lambda: {'registers':defaultdict(lambda: {'readers':set(),'writers':set()}),'accessors':set()})

    for n in graph['nodes']:
        for p in n.get('peripherals',[]):
            if '->' in p:
                base, reg = p.split('->', 1)
            else:
                base, reg = p, '(base)'
            periph_detail[base]['accessors'].add(n['id'])
            # Determine R/W from context
            if p in (n.get('writes',[]) or []):
                periph_detail[base]['registers'][reg]['writers'].add(n['id'])
            else:
                periph_detail[base]['registers'][reg]['readers'].add(n['id'])

    result = {}
    for base, data in periph_detail.items():
        regs = {}
        for reg, access in data['registers'].items():
            isr_readers = [f for f in access['readers'] if nmap.get(f,{}).get('is_isr')]
            isr_writers = [f for f in access['writers'] if nmap.get(f,{}).get('is_isr')]
            regs[reg] = {
                'readers': sorted(access['readers']),
                'writers': sorted(access['writers']),
                'isr_readers': isr_readers,
                'isr_writers': isr_writers,
                'conflict': bool(isr_readers or isr_writers) and bool(access['readers'] - set(isr_readers) or access['writers'] - set(isr_writers)),
            }
        result[base] = {
            'registers': regs,
            'total_accessors': sorted(data['accessors']),
            'n_registers': len(regs),
        }

    return result


# ══════════════════════════════════════════════════════════
# ENGINE 7: RACE CONDITION DEEP ANALYSIS
# ══════════════════════════════════════════════════════════

def analyze_races_deep(graph):
    nmap = _nmap(graph)
    results = []
    for r in graph.get('races',[]):
        var = r.get('var','')
        gmeta = graph.get('globals',{}).get(var,{})

        # Find ALL functions that access this variable
        all_readers = set()
        all_writers = set()
        for n in graph['nodes']:
            if var in (n.get('reads',[]) or []): all_readers.add(n['id'])
            if var in (n.get('writes',[]) or []): all_writers.add(n['id'])
            if var in (n.get('rw',[]) or []): all_readers.add(n['id']); all_writers.add(n['id'])

        # Determine fix recommendation
        if r.get('protected'):
            fix = 'Already protected by critical section. Verify the protection scope covers all access.'
        elif gmeta.get('volatile') and len(all_writers) == 1:
            fix = 'Single writer + volatile: consider if volatile alone is sufficient (atomic writes on this platform). Otherwise add __disable_irq() around read-modify-write sequences.'
        elif r.get('severity') == 'high':
            fix = 'HIGH RISK: Add taskENTER_CRITICAL() / taskEXIT_CRITICAL() around access in task context. Ensure ISR handler is kept short.'
        else:
            fix = 'Add critical section protection or use atomic operations.'

        results.append({
            **r,
            'all_readers': sorted(all_readers),
            'all_writers': sorted(all_writers),
            'file': gmeta.get('file',''),
            'line': gmeta.get('line',0),
            'is_volatile': gmeta.get('volatile', False),
            'is_extern': gmeta.get('extern', False),
            'fix_recommendation': fix,
        })

    results.sort(key=lambda x: {'high':0,'medium':1,'low':2}.get(x.get('severity','low'),9))
    return results


# ══════════════════════════════════════════════════════════
# ENGINE 8: RISK & COMPLEXITY (per-module)
# ══════════════════════════════════════════════════════════

def compute_risk_scores(graph):
    nmap = _nmap(graph)
    mods = graph.get('mods',[])
    races = graph.get('races',[])
    race_fns = set()
    for r in races:
        race_fns.add(r.get('task_fn',''))
        race_fns.update(r.get('isr_writers',[]))

    modules = {}
    for mod in mods:
        if mod in ('external','.'): continue
        mod_nodes = [n for n in graph['nodes'] if _mod(n)==mod]
        if not mod_nodes: continue
        fc = len(mod_nodes)
        avg_out = sum(n.get('out_degree',0) for n in mod_nodes)/max(fc,1)
        cross = sum(v for k,v in graph.get('mod_edges',{}).items() if mod in k.split('→') and k.split('→')[0]!=k.split('→')[1])
        rc = sum(1 for n in mod_nodes if n['id'] in race_fns)
        ic = sum(1 for n in mod_nodes if n.get('is_isr'))
        dead = sum(1 for n in mod_nodes if n.get('in_degree',0)==0 and not n.get('is_isr') and not n.get('is_entry') and n['id']!='main' and n.get('type')=='project')
        dr = dead/max(fc,1)
        raw = min(avg_out*5,25)+min(cross*2,25)+min(rc*10,20)+min(ic*8,15)+min(dr*30,15)
        score = min(100,int(raw))
        grade = 'A' if score<20 else 'B' if score<40 else 'C' if score<60 else 'D' if score<80 else 'F'
        modules[mod] = {'score':score,'grade':grade,'fn_count':fc,
                         'factors':{'avg_fan_out':round(avg_out,1),'cross_module':cross,
                                    'races':rc,'isrs':ic,'dead':dead,'dead_pct':round(dr*100,1)}}

    total = sum(m.get('fn_count',1) for m in modules.values())
    overall = sum(m['score']*m.get('fn_count',1) for m in modules.values())/max(total,1)
    og = 'A' if overall<20 else 'B' if overall<40 else 'C' if overall<60 else 'D' if overall<80 else 'F'
    return {'modules':modules,'overall':{'score':int(overall),'grade':og}}


# ══════════════════════════════════════════════════════════
# ENGINE 9: READING ORDER
# ══════════════════════════════════════════════════════════

def compute_reading_order(graph):
    mods = [m for m in graph.get('mods',[]) if m not in ('external','.')]
    nmap = _nmap(graph)
    me = graph.get('mod_edges',{})
    deps = defaultdict(set)
    rdeps = defaultdict(set)
    for key in me:
        parts = key.split('→')
        if len(parts)==2 and parts[0] in mods and parts[1] in mods and parts[0]!=parts[1]:
            deps[parts[0]].add(parts[1])
            rdeps[parts[1]].add(parts[0])
    # Kahn's
    indeg = {m:len(deps.get(m,set())) for m in mods}
    q = sorted([m for m in mods if indeg[m]==0])
    order = []
    while q:
        m = q.pop(0); order.append(m)
        for dep in sorted(rdeps.get(m,set())):
            indeg[dep] -= 1
            if indeg[dep]==0: q.append(dep)
    for m in sorted(mods):
        if m not in order: order.append(m)

    result = []
    for mod in order:
        mod_fns = [n for n in graph['nodes'] if _mod(n)==mod and n.get('file')]
        files = sorted(set(n['file'] for n in mod_fns))
        result.append({'module':mod,'files':files,'fn_count':len(mod_fns),
                        'depends_on':sorted(deps.get(mod,set())),
                        'used_by':sorted(rdeps.get(mod,set()))})
    return result


# ══════════════════════════════════════════════════════════
# ENGINE 10: PATTERN DETECTION
# ══════════════════════════════════════════════════════════

def detect_patterns(graph):
    nmap = _nmap(graph)
    edges = graph.get('edges',{})
    callers = graph.get('callers',{})
    rtos = graph.get('rtos',{})
    patterns = []
    seen = set()

    def add_pat(t,l,d,fns,c='high'):
        key = t+'|'+','.join(sorted(fns))
        if key in seen: return
        seen.add(key)
        patterns.append({'type':t,'label':l,'description':d,'functions':fns,'confidence':c})

    # Producer-consumer
    for oname, odata in rtos.get('objects',{}).items():
        if odata.get('kind')!='queue': continue
        senders = set(); receivers = set()
        for fn, td in rtos.get('tasks',{}).items():
            if oname in td.get('sends_to',[]): senders.add(fn)
            if oname in td.get('recvs_from',[]): receivers.add(fn)
        if senders and receivers:
            add_pat('producer_consumer','Producer-Consumer',
                    f'Queue "{oname}": producers={", ".join(sorted(senders))} → consumers={", ".join(sorted(receivers))}',
                    sorted(senders|receivers))

    # ISR pipeline
    for n in graph['nodes']:
        if not n.get('is_isr'): continue
        writes = set(n.get('writes',[]))
        for n2 in graph['nodes']:
            if n2.get('is_isr') or n2['id']==n['id']: continue
            reads = set(n2.get('reads',[]))
            shared = writes & reads
            if shared:
                add_pat('isr_pipeline','ISR-Driven Pipeline',
                        f'{n["id"]} writes → {n2["id"]} reads: {", ".join(sorted(shared))}',
                        [n['id'],n2['id']])

    # Polling loops
    pollers = [n['id'] for n in graph['nodes'] if n.get('delay_in_loop')]
    if pollers:
        add_pat('polling','Polling Loop',f'Functions with delay-in-loop: {", ".join(pollers)}',pollers)

    # Hub functions
    for n in graph['nodes']:
        if n.get('out_degree',0)>=8 and n.get('type')=='project':
            add_pat('hub','Hub/Dispatcher',f'{n["id"]}() calls {n["out_degree"]} functions',
                    [n['id']],'medium')

    # Init-once
    for n in graph['nodes']:
        if n.get('type')!='project' or n.get('is_entry'): continue
        cs = callers.get(n['id'],[])
        if len(cs)==1:
            cn = nmap.get(cs[0],{})
            if cn.get('is_entry') or cs[0]=='main':
                if n.get('writes'):
                    add_pat('init_once','Init-Once Setup',
                            f'{n["id"]}() called only from {cs[0]}(), writes: {", ".join(n["writes"][:5])}',
                            [n['id']],'medium')

    # Accessor pairs (get_X / set_X)
    fn_names = {n['id'] for n in graph['nodes'] if n.get('type')=='project'}
    for fn in fn_names:
        if fn.startswith('get_') or fn.startswith('Get') or fn.startswith('GET_'):
            base = fn[3:] if fn[3]=='_' else fn[3:]
            for prefix in ['set_','Set','SET_']:
                pair = prefix + base
                if pair in fn_names:
                    add_pat('accessor_pair','Accessor Pair',f'{fn} / {pair}',
                            [fn, pair],'medium')
                    break

    return patterns


# ══════════════════════════════════════════════════════════
# ENGINE 11: BUS FACTOR & CHANGE DIFFICULTY
# ══════════════════════════════════════════════════════════

def compute_bus_factor(graph):
    edges = graph.get('edges',{})
    nmap = _nmap(graph)
    proj = _proj(graph)
    results = []
    for fn in proj:
        impact = _impact(fn, edges)
        if impact >= 2:
            results.append({'fn':fn,'impact':impact,'file':nmap.get(fn,{}).get('file',''),
                            'mod':_mod(nmap.get(fn,{})),'is_isr':nmap.get(fn,{}).get('is_isr',False),
                            'in_degree':nmap.get(fn,{}).get('in_degree',0)})
    results.sort(key=lambda x:-x['impact'])
    return results[:50]

def compute_change_difficulty(graph):
    nmap = _nmap(graph)
    edges = graph.get('edges',{})
    callers = graph.get('callers',{})
    races = graph.get('races',[])
    race_fns = set()
    for r in races:
        race_fns.add(r.get('task_fn',''))
        race_fns.update(r.get('isr_writers',[]))

    results = {}
    for mod in graph.get('mods',[]):
        if mod in ('external','.'): continue
        mod_fns = [n for n in graph['nodes'] if _mod(n)==mod]
        if not mod_fns:
            results[mod] = {'difficulty':'low','score':0,'reasons':[]}
            continue
        reasons = []; score = 0
        ext_callers = sum(1 for n in mod_fns for c in callers.get(n['id'],[]) if _mod(nmap.get(c,{}))!=mod)
        if ext_callers>5: score+=25; reasons.append(f'{ext_callers} external callers')
        elif ext_callers>0: score+=10; reasons.append(f'{ext_callers} external callers')
        rc = sum(1 for n in mod_fns if n['id'] in race_fns)
        if rc: score+=min(rc*12,25); reasons.append(f'{rc} race-involved functions')
        ic = sum(1 for n in mod_fns if n.get('is_isr'))
        if ic: score+=min(ic*10,20); reasons.append(f'{ic} ISRs')
        gw = set()
        for n in mod_fns: gw.update(n.get('writes',[]))
        if len(gw)>3: score+=10; reasons.append(f'writes {len(gw)} globals')
        diff = 'low' if score<25 else 'medium' if score<50 else 'high' if score<75 else 'critical'
        results[mod] = {'difficulty':diff,'score':min(score,100),'reasons':reasons,'fn_count':len(mod_fns)}
    return results


# ══════════════════════════════════════════════════════════
# ENGINE 12: DEAD CODE INVESTIGATION
# ══════════════════════════════════════════════════════════

def investigate_dead_code(graph):
    nmap = _nmap(graph)
    callers = graph.get('callers',{})
    results = []
    for n in graph['nodes']:
        if n.get('type')!='project': continue
        if n.get('is_isr') or n.get('is_entry'): continue
        if n['id']=='main': continue
        if n.get('in_degree',0) > 0: continue

        # Investigate
        name = n['id'].lower()
        hints = []
        if 'test' in name or 'debug' in name: hints.append('Possibly a test/debug function')
        if 'unused' in name or 'deprecated' in name: hints.append('Name suggests intentionally unused')
        if 'callback' in name or 'cb_' in name: hints.append('May be used as function pointer callback')
        if 'weak' in name or '__attribute__' in name: hints.append('May be a weak symbol override')
        if n.get('writes'): hints.append(f'Writes globals: {", ".join(n["writes"][:3])} — may have side effects')
        if n.get('peripherals'): hints.append(f'Accesses hardware: {", ".join(n["peripherals"][:3])}')
        if not hints: hints.append('No clear reason for being unused — candidate for removal')

        results.append({
            'fn': n['id'], 'file': n.get('file',''), 'line': n.get('line',0),
            'mod': _mod(n), 'hints': hints,
            'recommendation': 'investigate' if any('callback' in h or 'function pointer' in h for h in hints)
                              else 'likely_remove' if not n.get('writes') and not n.get('peripherals')
                              else 'verify_intent',
        })
    return results


# ══════════════════════════════════════════════════════════
# ENGINE 13: EXHAUSTIVE QUESTIONS
# ══════════════════════════════════════════════════════════

def generate_questions(graph):
    nmap = _nmap(graph)
    qs = []
    def add(q, cat, prio, ev, fns=None):
        qs.append({'question':q,'category':cat,'priority':prio,'evidence':ev,'related':fns or []})

    # Per race
    for r in graph.get('races',[]):
        if not r.get('protected'):
            add(f'Is the race on "{r["var"]}" between {", ".join(r.get("isr_writers",[]))} and {r["task_fn"]} intentional? What protection strategy should be used?',
                'safety','high',f'Severity: {r.get("severity")}; unprotected concurrent access',
                [r['task_fn']]+r.get('isr_writers',[]))

    # Per ISR
    for n in graph['nodes']:
        if not n.get('is_isr'): continue
        add(f'What is the maximum acceptable latency for {n["id"]}? What is the interrupt source and priority?',
            'timing','high',f'ISR in {n.get("file","")}, out_degree={n.get("out_degree",0)}',[n['id']])

    # Per peripheral
    for pname in graph.get('peripherals',{}):
        add(f'What is the complete configuration for {pname}? (clock, pins, mode, frequency, etc.)',
            'hardware','medium',f'Peripheral accessed by project code',[])

    # Per dead function
    dead = investigate_dead_code(graph)
    for d in dead[:15]:
        add(f'Is {d["fn"]}() in {d["file"]} intentionally unused or should it be removed?',
            'maintenance','medium',f'No callers found; hints: {"; ".join(d["hints"][:2])}',[d['fn']])

    # Per task
    for tname in graph.get('rtos',{}).get('tasks',{}):
        add(f'What are the stack size and priority for task "{tname}"? Are they measured or estimated?',
            'rtos','high',f'RTOS task detected',[tname])

    # Per module
    for mod in graph.get('mods',[]):
        if mod in ('external','.'): continue
        add(f'What is the exact purpose and responsibility boundary of module "{mod}"?',
            'architecture','low',f'Module boundary from directory structure',[])

    # Per high-coupling pair
    interactions = build_interactions(graph)
    for inter in interactions[:5]:
        if inter['total_edges'] > 5:
            add(f'Is the tight coupling between "{inter["mod1"]}" and "{inter["mod2"]}" ({inter["total_edges"]} cross-calls) intentional? Should they be merged or decoupled?',
                'architecture','medium',f'{len(inter["calls_12"])} calls {inter["mod1"]}→{inter["mod2"]}, {len(inter["calls_21"])} calls {inter["mod2"]}→{inter["mod1"]}',[])

    # Per shared global with multiple writers
    gl = graph.get('globals',{})
    for gname, gmeta in gl.items():
        writers = set()
        for n in graph['nodes']:
            if gname in (n.get('writes',[]) or []): writers.add(n['id'])
        if len(writers) >= 2:
            add(f'Global "{gname}" is written by {len(writers)} functions ({", ".join(sorted(writers)[:4])}). Is concurrent write access safe?',
                'concurrency','medium',f'Multiple writers: {", ".join(sorted(writers)[:5])}',[])

    qs.sort(key=lambda q: {'high':0,'medium':1,'low':2}.get(q['priority'],9))
    return qs


# ══════════════════════════════════════════════════════════
# ENGINE 14: GLOSSARY
# ══════════════════════════════════════════════════════════

def build_glossary(graph):
    nmap = _nmap(graph)
    entries = []
    for n in graph['nodes']:
        tags = []
        if n.get('is_isr'): tags.append('ISR')
        if n.get('is_entry'): tags.append('entry')
        if n.get('has_critical'): tags.append('critical')
        if n.get('delay_in_loop'): tags.append('polling')
        if n.get('peripherals'): tags.append('hw-access')
        entries.append({'name':n['id'],'kind':'function','module':_mod(n),'file':n.get('file',''),
                        'line':n.get('line',0),'tags':tags,
                        'detail':f'in:{n.get("in_degree",0)} out:{n.get("out_degree",0)}'+(' · ISR' if n.get('is_isr') else '')})

    for mod in graph.get('mods',[]):
        mc = len([n for n in graph['nodes'] if _mod(n)==mod])
        entries.append({'name':mod,'kind':'module','module':mod,'file':'','line':0,'tags':[],'detail':f'{mc} functions'})

    for gname, gmeta in graph.get('globals',{}).items():
        tags = []
        if gmeta.get('volatile'): tags.append('volatile')
        if gmeta.get('extern'): tags.append('extern')
        entries.append({'name':gname,'kind':'global','module':'','file':gmeta.get('file',''),
                        'line':gmeta.get('line',0),'tags':tags,
                        'detail':('volatile ' if gmeta.get('volatile') else '')+('extern' if gmeta.get('extern') else '')})

    for pname, pdata in graph.get('peripherals',{}).items():
        entries.append({'name':pname,'kind':'peripheral','module':'','file':'','line':0,
                        'tags':['hardware'],
                        'detail':f'readers:{len(pdata.get("readers",[]))} writers:{len(pdata.get("writers",[]))}'})

    for oname, odata in graph.get('rtos',{}).get('objects',{}).items():
        entries.append({'name':oname,'kind':odata.get('kind','rtos'),'module':'','file':'','line':0,
                        'tags':['rtos'],'detail':f'{odata.get("kind","?")} · users: {", ".join(odata.get("users",[])[:5])}'})

    # Add individual RTOS API calls as entries
    rtos_apis_used = set()
    for n in graph['nodes']:
        for rc in n.get('rtos',[]):
            if rc.get('api'): rtos_apis_used.add(rc['api'])
    for api in sorted(rtos_apis_used):
        users = [n['id'] for n in graph['nodes'] if any(rc.get('api')==api for rc in n.get('rtos',[]))]
        entries.append({'name':api,'kind':'rtos_api','module':'','file':'','line':0,
                        'tags':['rtos'],'detail':f'Used by: {", ".join(users[:5])}'})

    entries.sort(key=lambda e:(e['kind'],e['name'].lower()))
    return entries


# ══════════════════════════════════════════════════════════
# ENGINE 15: RECOMMENDED TOOLS
# ══════════════════════════════════════════════════════════

def recommend_tools(graph):
    tools = []
    races = len(graph.get('races',[]))
    isrs = len([n for n in graph['nodes'] if n.get('is_isr')])
    has_rtos = bool(graph.get('rtos',{}).get('tasks'))
    periphs = len(graph.get('peripherals',{}))

    tools.append({'name':'Valgrind (Memcheck)','desc':'Runtime memory error detection','category':'dynamic','free':True,
                  'why':'Essential for any C project — detects leaks, overflows, use-after-free'})
    tools.append({'name':'cppcheck','desc':'Static analysis for C/C++','category':'static','free':True,
                  'why':'Catches undefined behavior, style issues, potential bugs'})

    if races:
        tools.append({'name':'ThreadSanitizer','desc':'Runtime race detector (-fsanitize=thread)','category':'dynamic','free':True,
                      'why':f'{races} race candidates detected'})
        tools.append({'name':'PC-lint Plus','desc':'Deep static analysis with concurrency checks','category':'static','free':False,
                      'why':'ISR-task shared data needs static verification'})
    if has_rtos:
        tools.append({'name':'Tracealyzer (Percepio)','desc':'Visual RTOS trace — task timing, queue usage','category':'rtos','free':False,
                      'why':f'{len(graph["rtos"]["tasks"])} RTOS tasks — runtime visualization essential'})
        tools.append({'name':'SystemView (Segger)','desc':'Free real-time RTOS + ISR event recording','category':'rtos','free':True,
                      'why':'Complements Tracealyzer with ISR timing data'})
    if isrs:
        tools.append({'name':'GCC -fstack-usage','desc':'Per-function stack consumption at compile time','category':'analysis','free':True,
                      'why':f'{isrs} ISRs — stack sizing critical for interrupt handlers'})
    if periphs:
        tools.append({'name':'QEMU + GDB','desc':'ARM Cortex-M emulation — debug without hardware','category':'debug','free':True,
                      'why':f'{periphs} peripherals — emulation catches register access bugs'})
        tools.append({'name':'Ozone (Segger)','desc':'Visual debugger with peripheral register view','category':'debug','free':False,
                      'why':'Register-level debugging for hardware interaction'})
    tools.append({'name':'Doxygen','desc':'API documentation from source comments','category':'documentation','free':True,
                  'why':'Auto-generate reference docs'})
    tools.append({'name':'PVS-Studio','desc':'Deep static analysis, MISRA checks','category':'static','free':False,
                  'why':'Finds subtle bugs: integer overflow, null deref, MISRA violations'})
    tools.append({'name':'gcov / lcov','desc':'Code coverage measurement','category':'testing','free':True,
                  'why':'Verify dead code candidates and test completeness'})

    return tools


# ══════════════════════════════════════════════════════════
# ENGINE 16: BOOT TIMELINE (DEEP)
# ══════════════════════════════════════════════════════════

def build_timeline(graph):
    edges = graph.get('edges',{})
    nmap = _nmap(graph)
    entry = None
    for n in graph['nodes']:
        if n['id']=='main': entry='main'; break
    if not entry:
        for n in graph['nodes']:
            if n.get('is_entry') and n.get('type')=='project': entry=n['id']; break
    if not entry: return []

    visited = _bfs(entry, edges, max_d=10)
    frames = defaultdict(list)
    for fn, d in visited.items():
        nd = nmap.get(fn,{})
        frames[d].append({'fn':fn,'mod':_mod(nd),'file':nd.get('file',''),
                          'is_isr':nd.get('is_isr',False),'out_degree':nd.get('out_degree',0)})

    timeline = []
    for step in sorted(frames.keys()):
        fns = frames[step]
        fns.sort(key=lambda f: f['fn'])
        timeline.append({'step':step,'label':f'Boot +{step}' if step>0 else 'Entry',
                          'functions':fns,'fn_count':len(fns)})
    return timeline


# ══════════════════════════════════════════════════════════
# ASSEMBLY
# ══════════════════════════════════════════════════════════

def generate_report_data(graph):
    return {
        'graph': graph,
        'analysis': {
            'narrative': build_architecture_narrative(graph),
            'requirements': build_requirements(graph),
            'functions_deep': analyze_functions_deep(graph),
            'data_flows': build_data_flows(graph),
            'interactions': build_interactions(graph),
            'peripheral_map': build_peripheral_map(graph),
            'races_deep': analyze_races_deep(graph),
            'risk_scores': compute_risk_scores(graph),
            'reading_order': compute_reading_order(graph),
            'patterns': detect_patterns(graph),
            'bus_factor': compute_bus_factor(graph),
            'change_difficulty': compute_change_difficulty(graph),
            'dead_code': investigate_dead_code(graph),
            'questions': generate_questions(graph),
            'glossary': build_glossary(graph),
            'tools': recommend_tools(graph),
            'timeline': build_timeline(graph),
        },
        'meta': {
            'generated_at': datetime.now().isoformat(),
            'generator_version': '2.0.0',
            'project_name': Path(graph.get('source','project')).name,
            'project_path': graph.get('source',''),
            'file_count': graph.get('files',0),
            'fn_count': len(graph.get('nodes',[])),
            'edge_count': sum(len(v) for v in graph.get('edges',{}).values()),
            'module_count': len([m for m in graph.get('mods',[]) if m not in ('external','.')]),
            'race_count': len(graph.get('races',[])),
            'isr_count': len([n for n in graph.get('nodes',[]) if n.get('is_isr')]),
            'peripheral_count': len(graph.get('peripherals',{})),
            'req_count': 0,  # filled below
            'question_count': 0,
        },
    }


def build_html(report_data, template_path=None):
    if template_path is None:
        template_path = Path(__file__).parent / "template.html"
    else:
        template_path = Path(template_path)
    if not template_path.exists():
        raise FileNotFoundError(f"template.html not found at {template_path}")

    # Update meta counts
    report_data['meta']['req_count'] = len(report_data['analysis'].get('requirements',[]))
    report_data['meta']['question_count'] = len(report_data['analysis'].get('questions',[]))

    template = template_path.read_text(encoding='utf-8')
    data_json = json.dumps(report_data, separators=(',',':'), ensure_ascii=True)
    data_json = data_json.replace('</script>','<\\/script>').replace('<!--','<\\!--')
    html = template.replace('/*__REPORT_DATA__*/', f'const REPORT_DATA = {data_json};')
    return html


# ── CLI ──────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Callgraph Report Generator v2')
    parser.add_argument('graph_json')
    parser.add_argument('-o','--output',default='report.html')
    args = parser.parse_args()
    graph = json.loads(Path(args.graph_json).read_text())
    rd = generate_report_data(graph)
    html = build_html(rd)
    Path(args.output).write_text(html, encoding='utf-8')
    print(f"Report: {args.output} ({len(html)} bytes), {rd['meta']['req_count']} requirements, {rd['meta']['question_count']} questions")
