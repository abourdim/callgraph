#!/usr/bin/env python3
"""
Callgraph Studio — Report Generator v1.0

Takes graph JSON (from analyzer.py) and produces a self-contained
interactive HTML report for project handover.

Usage:
  CLI:    python3 generator.py graph.json -o report.html
  API:    POST /api/report with graph JSON body → returns HTML

Analysis engines:
  1. Risk scorer        — per-module health score
  2. Reading order      — recommended file reading sequence
  3. Bus factor         — single-point-of-failure functions
  4. Pattern detector   — state machines, producer-consumer, polling, etc.
  5. Change difficulty  — per-module modification risk
  6. Question generator — handover questions for departing dev
  7. Requirements       — inferred specs from code structure
  8. Dependency timeline— boot sequence frames
  9. Glossary           — searchable index of everything
"""

import json, sys, os, math, re
from pathlib import Path
from collections import defaultdict
from datetime import datetime


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _node_map(graph):
    return {n['id']: n for n in graph['nodes']}

def _project_fns(graph):
    return {n['id'] for n in graph['nodes'] if n.get('type') == 'project'}

def _mod_of(fn_id, nmap):
    n = nmap.get(fn_id, {})
    return n.get('mod') or n.get('module') or 'external'

def _bfs_forward(start, edges, max_depth=999):
    """BFS from start through edges, return {node: depth}."""
    visited = {start: 0}
    queue = [start]
    while queue:
        n = queue.pop(0)
        d = visited[n]
        if d >= max_depth:
            continue
        for c in edges.get(n, []):
            if c not in visited:
                visited[c] = d + 1
                queue.append(c)
    return visited

def _bfs_reverse(start, callers, max_depth=999):
    return _bfs_forward(start, callers, max_depth)

def _transitive_impact(fn, edges):
    """Count how many functions become unreachable if fn is removed."""
    return len(_bfs_forward(fn, edges)) - 1


# ══════════════════════════════════════════════════════════════
# ENGINE 1: RISK SCORER
# ══════════════════════════════════════════════════════════════

def compute_risk_scores(graph):
    """Per-module risk score 0-100. Higher = more risky."""
    nmap = _node_map(graph)
    edges = graph['edges']
    callers = graph['callers']
    races = graph.get('races', [])
    mods = graph.get('mods', [])

    race_fns = set()
    for r in races:
        race_fns.add(r.get('task_fn', ''))
        race_fns.update(r.get('isr_writers', []))

    scores = {}
    for mod in mods:
        mod_nodes = [n for n in graph['nodes'] if _mod_of(n['id'], nmap) == mod]
        if not mod_nodes:
            scores[mod] = {'score': 0, 'grade': 'A', 'factors': {}}
            continue

        fn_count = len(mod_nodes)

        # Factor 1: avg fan-out (coupling)
        avg_out = sum(n.get('out_degree', 0) for n in mod_nodes) / max(fn_count, 1)

        # Factor 2: cross-module edges touching this module
        cross = 0
        for key, count in graph.get('mod_edges', {}).items():
            parts = key.split('→')
            if len(parts) == 2 and mod in parts:
                cross += count

        # Factor 3: race involvement
        race_count = sum(1 for n in mod_nodes if n['id'] in race_fns)

        # Factor 4: ISR count (interrupt complexity)
        isr_count = sum(1 for n in mod_nodes if n.get('is_isr'))

        # Factor 5: dead code ratio
        dead = sum(1 for n in mod_nodes if n.get('in_degree', 0) == 0
                   and not n.get('is_isr') and not n.get('is_entry')
                   and n['id'] != 'main' and n.get('type') == 'project')
        dead_ratio = dead / max(fn_count, 1)

        # Weighted score
        raw = (
            min(avg_out * 5, 25) +           # coupling: 0-25
            min(cross * 2, 25) +              # cross-module: 0-25
            min(race_count * 10, 20) +        # races: 0-20
            min(isr_count * 8, 15) +          # ISR complexity: 0-15
            min(dead_ratio * 30, 15)           # dead code: 0-15
        )
        score = min(100, int(raw))

        grade = 'A' if score < 20 else 'B' if score < 40 else 'C' if score < 60 else 'D' if score < 80 else 'F'

        scores[mod] = {
            'score': score,
            'grade': grade,
            'fn_count': fn_count,
            'factors': {
                'avg_fan_out': round(avg_out, 1),
                'cross_module_edges': cross,
                'race_count': race_count,
                'isr_count': isr_count,
                'dead_code': dead,
                'dead_ratio': round(dead_ratio * 100, 1),
            }
        }

    # Overall project score = weighted avg by fn count
    total_fns = sum(s.get('fn_count', 1) for s in scores.values())
    overall = sum(s['score'] * s.get('fn_count', 1) for s in scores.values()) / max(total_fns, 1)
    overall_grade = 'A' if overall < 20 else 'B' if overall < 40 else 'C' if overall < 60 else 'D' if overall < 80 else 'F'

    return {
        'modules': scores,
        'overall': {'score': int(overall), 'grade': overall_grade},
    }


# ══════════════════════════════════════════════════════════════
# ENGINE 2: READING ORDER
# ══════════════════════════════════════════════════════════════

def compute_reading_order(graph):
    """Topological sort of modules by dependency depth."""
    mod_edges = graph.get('mod_edges', {})
    mods = set(graph.get('mods', []))

    # Build module dependency graph
    deps = defaultdict(set)   # mod → set of mods it depends on
    rdeps = defaultdict(set)  # mod → set of mods that depend on it
    for key in mod_edges:
        parts = key.split('→')
        if len(parts) == 2:
            caller_mod, callee_mod = parts
            if caller_mod in mods and callee_mod in mods and caller_mod != callee_mod:
                deps[caller_mod].add(callee_mod)
                rdeps[callee_mod].add(caller_mod)

    # Kahn's topological sort (bottom-up: leaves first)
    in_deg = {m: len(deps.get(m, set())) for m in mods}
    queue = sorted([m for m in mods if in_deg[m] == 0])
    order = []
    while queue:
        m = queue.pop(0)
        order.append(m)
        for dependent in sorted(rdeps.get(m, set())):
            in_deg[dependent] -= 1
            if in_deg[dependent] == 0:
                queue.append(dependent)

    # Add any remaining (cycles)
    for m in sorted(mods):
        if m not in order:
            order.append(m)

    # Build file reading order within each module
    nmap = _node_map(graph)
    result = []
    for mod in order:
        mod_nodes = [n for n in graph['nodes'] if _mod_of(n['id'], nmap) == mod and n.get('file')]
        files = sorted(set(n['file'] for n in mod_nodes))
        dep_on = sorted(deps.get(mod, set()))
        depended_by = sorted(rdeps.get(mod, set()))
        reason = f"Depends on: {', '.join(dep_on) if dep_on else 'nothing (leaf module)'}"
        if depended_by:
            reason += f" · Used by: {', '.join(depended_by)}"
        result.append({
            'module': mod,
            'files': files,
            'reason': reason,
            'fn_count': len(mod_nodes),
        })

    return result


# ══════════════════════════════════════════════════════════════
# ENGINE 3: BUS FACTOR
# ══════════════════════════════════════════════════════════════

def compute_bus_factor(graph):
    """Find single-point-of-failure functions."""
    edges = graph['edges']
    nmap = _node_map(graph)
    proj = _project_fns(graph)
    results = []

    for fn in proj:
        impact = _transitive_impact(fn, edges)
        if impact >= 3:  # Only report significant ones
            results.append({
                'fn': fn,
                'impact': impact,
                'file': nmap.get(fn, {}).get('file', ''),
                'mod': _mod_of(fn, nmap),
                'is_isr': nmap.get(fn, {}).get('is_isr', False),
                'in_degree': nmap.get(fn, {}).get('in_degree', 0),
            })

    results.sort(key=lambda x: -x['impact'])
    return results[:30]


# ══════════════════════════════════════════════════════════════
# ENGINE 4: PATTERN DETECTOR
# ══════════════════════════════════════════════════════════════

def detect_patterns(graph):
    """Detect common embedded C patterns from call graph structure."""
    nmap = _node_map(graph)
    edges = graph['edges']
    callers = graph['callers']
    rtos = graph.get('rtos', {})
    patterns = []

    # Pattern: Producer-Consumer (queue send in one fn, receive in another)
    tasks = rtos.get('tasks', {})
    objects = rtos.get('objects', {})
    for obj_name, obj_data in objects.items():
        if obj_data.get('kind') != 'queue':
            continue
        senders = set()
        receivers = set()
        for fn_name, task_data in tasks.items():
            if obj_name in task_data.get('sends_to', []):
                senders.add(fn_name)
            if obj_name in task_data.get('recvs_from', []):
                receivers.add(fn_name)
        if senders and receivers:
            patterns.append({
                'type': 'producer_consumer',
                'label': 'Producer-Consumer',
                'description': f'Queue "{obj_name}": {", ".join(sorted(senders))} → {", ".join(sorted(receivers))}',
                'functions': sorted(senders | receivers),
                'confidence': 'high',
            })

    # Pattern: ISR-driven pipeline (ISR → queue/global → task)
    for n in graph['nodes']:
        if not n.get('is_isr'):
            continue
        fn = n['id']
        fn_data = nmap.get(fn, {})
        writes = set(fn_data.get('writes', []))
        # Check if any non-ISR reads what this ISR writes
        for reader in graph['nodes']:
            if reader.get('is_isr') or reader['id'] == fn:
                continue
            reader_reads = set(nmap.get(reader['id'], {}).get('reads', []))
            shared = writes & reader_reads
            if shared:
                patterns.append({
                    'type': 'isr_pipeline',
                    'label': 'ISR-Driven Pipeline',
                    'description': f'{fn} writes → {reader["id"]} reads: {", ".join(sorted(shared))}',
                    'functions': [fn, reader['id']],
                    'confidence': 'high',
                })

    # Pattern: Polling loop (delay-in-loop flag)
    pollers = [n['id'] for n in graph['nodes'] if n.get('delay_in_loop')]
    if pollers:
        patterns.append({
            'type': 'polling_loop',
            'label': 'Polling Loop',
            'description': f'Functions with delay-in-loop: {", ".join(pollers)}',
            'functions': pollers,
            'confidence': 'high',
        })

    # Pattern: Init-once (called only from main/init, sets up globals)
    for n in graph['nodes']:
        fn = n['id']
        if not n.get('is_entry') and n.get('type') == 'project':
            fn_callers = callers.get(fn, [])
            if len(fn_callers) == 1:
                caller = fn_callers[0]
                caller_node = nmap.get(caller, {})
                if caller_node.get('is_entry') or caller == 'main':
                    fn_data = nmap.get(fn, {})
                    if fn_data.get('writes'):
                        patterns.append({
                            'type': 'init_once',
                            'label': 'Init-Once Setup',
                            'description': f'{fn}() called only from {caller}(), writes: {", ".join(fn_data["writes"][:5])}',
                            'functions': [fn],
                            'confidence': 'medium',
                        })

    # Pattern: Hub function (very high fan-out, central dispatcher)
    for n in graph['nodes']:
        if n.get('out_degree', 0) >= 8 and n.get('type') == 'project':
            patterns.append({
                'type': 'hub',
                'label': 'Hub / Dispatcher',
                'description': f'{n["id"]}() calls {n["out_degree"]} functions — central coordination point',
                'functions': [n['id']],
                'confidence': 'medium',
            })

    # Deduplicate by type+functions key
    seen = set()
    unique = []
    for p in patterns:
        key = p['type'] + '|' + ','.join(sorted(p['functions']))
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique


# ══════════════════════════════════════════════════════════════
# ENGINE 5: CHANGE DIFFICULTY
# ══════════════════════════════════════════════════════════════

def compute_change_difficulty(graph):
    """Per-module difficulty score for modifications."""
    nmap = _node_map(graph)
    edges = graph['edges']
    callers = graph['callers']
    races = graph.get('races', [])
    mods = graph.get('mods', [])

    race_fns = set()
    for r in races:
        race_fns.add(r.get('task_fn', ''))
        race_fns.update(r.get('isr_writers', []))

    results = {}
    for mod in mods:
        mod_fns = [n for n in graph['nodes'] if _mod_of(n['id'], nmap) == mod]
        if not mod_fns:
            results[mod] = {'difficulty': 'low', 'score': 0, 'reasons': []}
            continue

        reasons = []
        score = 0

        # Cross-module callers (external dependencies on this module)
        ext_callers = 0
        for n in mod_fns:
            for c in callers.get(n['id'], []):
                if _mod_of(c, nmap) != mod:
                    ext_callers += 1
        if ext_callers > 5:
            score += 25
            reasons.append(f'{ext_callers} external callers depend on this module')
        elif ext_callers > 0:
            score += 10
            reasons.append(f'{ext_callers} external callers')

        # Race involvement
        mod_races = sum(1 for n in mod_fns if n['id'] in race_fns)
        if mod_races:
            score += min(mod_races * 12, 25)
            reasons.append(f'{mod_races} functions involved in races')

        # ISR connections
        isr_count = sum(1 for n in mod_fns if n.get('is_isr'))
        if isr_count:
            score += min(isr_count * 10, 20)
            reasons.append(f'{isr_count} ISRs — timing-sensitive')

        # Deep call chains through this module
        max_depth = 0
        for n in mod_fns:
            depth = len(_bfs_forward(n['id'], edges, max_depth=8))
            max_depth = max(max_depth, depth)
        if max_depth > 10:
            score += 15
            reasons.append(f'Deep call chains (max {max_depth} reachable)')
        elif max_depth > 5:
            score += 8
            reasons.append(f'Moderate call depth ({max_depth} reachable)')

        # Shared globals
        globals_written = set()
        for n in mod_fns:
            globals_written.update(nmap.get(n['id'], {}).get('writes', []))
        if len(globals_written) > 3:
            score += 10
            reasons.append(f'Writes {len(globals_written)} globals')

        score = min(100, score)
        difficulty = 'low' if score < 25 else 'medium' if score < 50 else 'high' if score < 75 else 'critical'

        results[mod] = {
            'difficulty': difficulty,
            'score': score,
            'reasons': reasons,
            'fn_count': len(mod_fns),
        }

    return results


# ══════════════════════════════════════════════════════════════
# ENGINE 6: QUESTION GENERATOR
# ══════════════════════════════════════════════════════════════

def generate_questions(graph):
    """Auto-generate handover questions based on analysis gaps."""
    nmap = _node_map(graph)
    questions = []

    # Unprotected races
    for r in graph.get('races', []):
        if not r.get('protected') and r.get('severity') in ('high', 'medium'):
            questions.append({
                'question': f'Is the race on "{r["var"]}" between {", ".join(r.get("isr_writers",[]))} and {r["task_fn"]} intentional? Does it need protection?',
                'category': 'safety',
                'priority': 'high',
                'evidence': f'ISR writes, task {"reads" if r.get("task_access")=="read" else "writes"}, no critical section detected',
            })

    # Dead code
    dead = [n for n in graph['nodes']
            if n.get('type') == 'project' and n.get('in_degree', 0) == 0
            and not n.get('is_isr') and not n.get('is_entry') and n['id'] != 'main']
    for n in dead[:10]:
        questions.append({
            'question': f'Is {n["id"]}() in {n.get("file","")} dead code or conditionally compiled?',
            'category': 'maintenance',
            'priority': 'medium',
            'evidence': 'No callers found in project',
        })

    # Peripherals without clear documentation
    periph = graph.get('peripherals', {})
    for p_name in list(periph.keys())[:10]:
        questions.append({
            'question': f'What is the configuration for {p_name}? (clock, pins, mode, baud rate, etc.)',
            'category': 'hardware',
            'priority': 'medium',
            'evidence': f'Peripheral accessed by {len(periph[p_name].get("readers",[]))+len(periph[p_name].get("writers",[]))} functions',
        })

    # ISR timing
    isrs = [n for n in graph['nodes'] if n.get('is_isr')]
    for isr in isrs:
        questions.append({
            'question': f'What is the max acceptable latency for {isr["id"]}?',
            'category': 'timing',
            'priority': 'medium',
            'evidence': f'ISR handler, out_degree={isr.get("out_degree",0)}',
        })

    # RTOS task stack sizes
    tasks = graph.get('rtos', {}).get('tasks', {})
    if tasks:
        questions.append({
            'question': f'What are the stack sizes for {len(tasks)} RTOS tasks? Are they measured or estimated?',
            'category': 'rtos',
            'priority': 'high',
            'evidence': f'Tasks: {", ".join(list(tasks.keys())[:8])}',
        })

    # Module purpose
    for mod in graph.get('mods', []):
        if mod not in ('.', 'external'):
            questions.append({
                'question': f'What is the purpose and responsibility of the "{mod}" module?',
                'category': 'architecture',
                'priority': 'low',
                'evidence': 'Module boundary detected from directory structure',
            })

    # Sort by priority
    prio_order = {'high': 0, 'medium': 1, 'low': 2}
    questions.sort(key=lambda q: prio_order.get(q['priority'], 9))

    return questions


# ══════════════════════════════════════════════════════════════
# ENGINE 7: INFERRED REQUIREMENTS
# ══════════════════════════════════════════════════════════════

def infer_requirements(graph):
    """Infer functional and non-functional requirements from code."""
    nmap = _node_map(graph)
    reqs = []
    req_id = [0]

    def add(category, desc, evidence, confidence):
        req_id[0] += 1
        reqs.append({
            'id': f'REQ-{req_id[0]:03d}',
            'category': category,
            'description': desc,
            'evidence': evidence,
            'confidence': confidence,
        })

    # Functional: modules = capabilities
    for mod in graph.get('mods', []):
        if mod in ('.', 'external'):
            continue
        mod_fns = [n for n in graph['nodes'] if _mod_of(n['id'], nmap) == mod]
        fn_names = [n['id'] for n in mod_fns[:5]]
        add('functional', f'System includes "{mod}" subsystem',
            f'Module contains {len(mod_fns)} functions: {", ".join(fn_names)}…',
            'high')

    # Functional: RTOS tasks = concurrent behaviors
    tasks = graph.get('rtos', {}).get('tasks', {})
    for task_name in tasks:
        add('functional', f'System runs concurrent task: {task_name}',
            'Detected via RTOS task creation API', 'high')

    # Hardware: peripheral interfaces
    periph = graph.get('peripherals', {})
    for p_name in periph:
        readers = periph[p_name].get('readers', [])
        writers = periph[p_name].get('writers', [])
        add('hardware', f'System interfaces with {p_name} peripheral',
            f'Accessed by {len(readers)} readers, {len(writers)} writers',
            'high')

    # Concurrency: ISR-driven events
    isrs = [n for n in graph['nodes'] if n.get('is_isr')]
    for isr in isrs:
        add('concurrency', f'System handles interrupt: {isr["id"]}',
            f'ISR handler with {isr.get("out_degree",0)} calls',
            'high')

    # Non-functional: critical sections imply concurrency safety requirement
    crit_fns = [n for n in graph['nodes'] if n.get('has_critical')]
    if crit_fns:
        add('non_functional', 'System requires concurrency-safe access to shared resources',
            f'{len(crit_fns)} functions use critical sections',
            'high')

    # Non-functional: RTOS implies real-time constraints
    if tasks:
        add('non_functional', 'System has real-time scheduling requirements',
            f'{len(tasks)} RTOS tasks detected', 'medium')

    # Safety: race conditions imply protection requirements
    races = graph.get('races', [])
    if races:
        high_races = [r for r in races if r.get('severity') == 'high']
        add('safety', f'{len(races)} shared variables need access protection ({len(high_races)} high severity)',
            'Race condition analysis: ISR-task shared data detected',
            'high' if high_races else 'medium')

    return reqs


# ══════════════════════════════════════════════════════════════
# ENGINE 8: DEPENDENCY TIMELINE
# ══════════════════════════════════════════════════════════════

def compute_timeline(graph):
    """Boot sequence: BFS from main, each depth = a time step."""
    edges = graph['edges']
    nmap = _node_map(graph)

    # Find entry point
    entry = None
    for n in graph['nodes']:
        if n['id'] == 'main':
            entry = 'main'
            break
    if not entry:
        for n in graph['nodes']:
            if n.get('is_entry') and n.get('type') == 'project':
                entry = n['id']
                break
    if not entry:
        return []

    visited = _bfs_forward(entry, edges, max_depth=8)
    frames = defaultdict(list)
    for fn, depth in visited.items():
        node = nmap.get(fn, {})
        frames[depth].append({
            'fn': fn,
            'mod': _mod_of(fn, nmap),
            'file': node.get('file', ''),
        })

    timeline = []
    for step in sorted(frames.keys()):
        timeline.append({
            'step': step,
            'label': f'Boot +{step}' if step > 0 else 'Entry',
            'functions': frames[step],
        })

    return timeline


# ══════════════════════════════════════════════════════════════
# ENGINE 9: GLOSSARY
# ══════════════════════════════════════════════════════════════

def build_glossary(graph):
    """Searchable index of functions, modules, globals, peripherals, RTOS objects."""
    nmap = _node_map(graph)
    entries = []

    # Functions
    for n in graph['nodes']:
        tags = []
        if n.get('is_isr'): tags.append('ISR')
        if n.get('is_entry'): tags.append('entry')
        if n.get('has_critical'): tags.append('critical-section')
        if n.get('delay_in_loop'): tags.append('polling')
        if n.get('peripherals'): tags.append('hw-access')
        entries.append({
            'name': n['id'],
            'kind': 'function',
            'module': _mod_of(n['id'], nmap),
            'file': n.get('file', ''),
            'line': n.get('line', 0),
            'tags': tags,
            'detail': f'in:{n.get("in_degree",0)} out:{n.get("out_degree",0)}'
                      + (' · ISR' if n.get('is_isr') else '')
                      + (' · entry' if n.get('is_entry') else ''),
        })

    # Modules
    for mod in graph.get('mods', []):
        mod_fns = [n for n in graph['nodes'] if _mod_of(n['id'], nmap) == mod]
        entries.append({
            'name': mod,
            'kind': 'module',
            'module': mod,
            'file': '',
            'line': 0,
            'tags': [],
            'detail': f'{len(mod_fns)} functions',
        })

    # Globals
    for name, meta in graph.get('globals', {}).items():
        tags = []
        if meta.get('volatile'): tags.append('volatile')
        if meta.get('extern'): tags.append('extern')
        entries.append({
            'name': name,
            'kind': 'global',
            'module': '',
            'file': meta.get('file', ''),
            'line': meta.get('line', 0),
            'tags': tags,
            'detail': ('volatile ' if meta.get('volatile') else '') + ('extern' if meta.get('extern') else 'static' if meta.get('static') else ''),
        })

    # Peripherals
    for p_name, p_data in graph.get('peripherals', {}).items():
        entries.append({
            'name': p_name,
            'kind': 'peripheral',
            'module': '',
            'file': '',
            'line': 0,
            'tags': ['hardware'],
            'detail': f'readers:{len(p_data.get("readers",[]))} writers:{len(p_data.get("writers",[]))}',
        })

    # RTOS objects
    for obj_name, obj_data in graph.get('rtos', {}).get('objects', {}).items():
        entries.append({
            'name': obj_name,
            'kind': obj_data.get('kind', 'rtos-object'),
            'module': '',
            'file': '',
            'line': 0,
            'tags': ['rtos'],
            'detail': f'{obj_data.get("kind","?")} · users: {", ".join(obj_data.get("users",[])[:5])}',
        })

    entries.sort(key=lambda e: (e['kind'], e['name'].lower()))
    return entries


# ══════════════════════════════════════════════════════════════
# REPORT ASSEMBLY
# ══════════════════════════════════════════════════════════════

def generate_report_data(graph):
    """Run all analysis engines and return REPORT_DATA dict."""
    return {
        'graph': graph,
        'analysis': {
            'risk_scores': compute_risk_scores(graph),
            'reading_order': compute_reading_order(graph),
            'bus_factor': compute_bus_factor(graph),
            'patterns': detect_patterns(graph),
            'change_difficulty': compute_change_difficulty(graph),
            'questions': generate_questions(graph),
            'requirements': infer_requirements(graph),
            'timeline': compute_timeline(graph),
            'glossary': build_glossary(graph),
        },
        'meta': {
            'generated_at': datetime.now().isoformat(),
            'generator_version': '1.0.0',
            'project_name': Path(graph.get('source', 'project')).name,
            'project_path': graph.get('source', ''),
            'file_count': graph.get('files', 0),
            'fn_count': len(graph.get('nodes', [])),
            'edge_count': sum(len(v) for v in graph.get('edges', {}).values()),
            'module_count': len(graph.get('mods', [])),
            'race_count': len(graph.get('races', [])),
        },
    }


def build_html(report_data):
    """Inject REPORT_DATA into template.html and return the full HTML string."""
    template_path = Path(__file__).parent / "template.html"
    if not template_path.exists():
        raise FileNotFoundError(f"template.html not found at {template_path}")

    template = template_path.read_text(encoding='utf-8')
    data_json = json.dumps(report_data, separators=(',', ':'))

    # Replace the placeholder in template
    html = template.replace('/*__REPORT_DATA__*/', f'const REPORT_DATA = {data_json};')
    return html


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Callgraph Studio Report Generator')
    parser.add_argument('graph_json', help='Path to graph JSON file (from Callgraph Studio export)')
    parser.add_argument('-o', '--output', default='report.html', help='Output HTML file')
    args = parser.parse_args()

    graph = json.loads(Path(args.graph_json).read_text())
    report_data = generate_report_data(graph)
    html = build_html(report_data)
    Path(args.output).write_text(html, encoding='utf-8')
    print(f"Report generated: {args.output} ({len(html)} bytes)")
