#!/usr/bin/env python3
"""
Report Generator — Test Suite

Tests all 9 analysis engines + HTML assembly with a mock graph.
"""

import sys, json, tempfile, shutil
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE / "report"))

R, G, N = "\033[31m", "\033[32m", "\033[0m"
PASS = FAIL = 0

def ok(msg):
    global PASS; PASS += 1; print(f"  {G}✓{N} {msg}")
def fail(msg, detail=""):
    global FAIL; FAIL += 1; print(f"  {R}✗{N} {msg}")
    if detail: print(f"    {detail[:200]}")
def section(t): print(f"\n\033[1m── {t} ──\033[0m")

# ── Mock graph ───────────────────────────────────────────
MOCK_GRAPH = {
    "source": "/home/user/project",
    "files": 5,
    "nodes": [
        {"id":"main","file":"app/main.c","mod":"app","module":"app","line":10,"type":"project","is_isr":False,"is_entry":True,"has_critical":False,"delay_in_loop":False,"out_degree":3,"in_degree":0,"reads":["g_config"],"writes":["g_config"],"rw":[],"peripherals":[],"rtos":[]},
        {"id":"driver_init","file":"driver/init.c","mod":"driver","module":"driver","line":5,"type":"project","is_isr":False,"is_entry":False,"has_critical":False,"delay_in_loop":False,"out_degree":1,"in_degree":1,"reads":[],"writes":["g_hw_ready"],"rw":[],"peripherals":["GPIOA->ODR"],"rtos":[]},
        {"id":"sensor_read","file":"driver/sensor.c","mod":"driver","module":"driver","line":12,"type":"project","is_isr":False,"is_entry":False,"has_critical":True,"delay_in_loop":False,"out_degree":0,"in_degree":2,"reads":["g_temperature"],"writes":[],"rw":[],"peripherals":["ADC1->DR"],"rtos":[]},
        {"id":"TIM2_IRQHandler","file":"driver/isr.c","mod":"driver","module":"driver","line":30,"type":"project","is_isr":True,"is_entry":False,"has_critical":False,"delay_in_loop":False,"out_degree":0,"in_degree":0,"reads":[],"writes":["g_temperature"],"rw":[],"peripherals":["ADC1->DR"],"rtos":[]},
        {"id":"task_process","file":"app/task.c","mod":"app","module":"app","line":20,"type":"project","is_isr":False,"is_entry":False,"has_critical":False,"delay_in_loop":True,"out_degree":2,"in_degree":1,"reads":["g_temperature"],"writes":[],"rw":[],"peripherals":[],"rtos":[{"api":"xQueueSend","kind":"queue_send","target":"sensorQ","line":25}]},
        {"id":"comm_send","file":"comm/comm.c","mod":"comm","module":"comm","line":8,"type":"project","is_isr":False,"is_entry":False,"has_critical":False,"delay_in_loop":False,"out_degree":0,"in_degree":1,"reads":[],"writes":[],"rw":[],"peripherals":["USART1->DR"],"rtos":[]},
        {"id":"dead_fn","file":"app/unused.c","mod":"app","module":"app","line":1,"type":"project","is_isr":False,"is_entry":False,"has_critical":False,"delay_in_loop":False,"out_degree":0,"in_degree":0,"reads":[],"writes":[],"rw":[],"peripherals":[],"rtos":[]},
    ],
    "edges": {
        "main": ["driver_init", "sensor_read", "task_process"],
        "driver_init": ["sensor_read"],
        "task_process": ["sensor_read", "comm_send"],
    },
    "callers": {
        "driver_init": ["main"],
        "sensor_read": ["main", "driver_init", "task_process"],
        "task_process": ["main"],
        "comm_send": ["task_process"],
    },
    "mod_edges": {"app→driver": 3, "app→comm": 1, "driver→driver": 1},
    "mods": ["app", "comm", "driver"],
    "globals": {
        "g_temperature": {"file":"driver/sensor.c","line":1,"volatile":True,"extern":False,"static":False},
        "g_config": {"file":"app/main.c","line":2,"volatile":False,"extern":False,"static":False},
        "g_hw_ready": {"file":"driver/init.c","line":1,"volatile":False,"extern":True,"static":False},
    },
    "races": [
        {"var":"g_temperature","isr_writers":["TIM2_IRQHandler"],"task_fn":"task_process","task_access":"read","protected":False,"volatile":True,"severity":"high","file":"driver/sensor.c"},
        {"var":"g_temperature","isr_writers":["TIM2_IRQHandler"],"task_fn":"sensor_read","task_access":"read","protected":True,"volatile":True,"severity":"low","file":"driver/sensor.c"},
    ],
    "rtos": {
        "tasks": {
            "task_process": {"creates":[],"sends_to":["sensorQ"],"recvs_from":[],"takes":[],"gives":[],"delays":[]},
        },
        "objects": {
            "sensorQ": {"kind":"queue","users":["task_process"]},
        },
    },
    "peripherals": {
        "ADC1": {"readers":["sensor_read","TIM2_IRQHandler"],"writers":[],"rw":[]},
        "GPIOA": {"readers":[],"writers":["driver_init"],"rw":[]},
        "USART1": {"readers":[],"writers":["comm_send"],"rw":[]},
    },
}

from generator import (
    compute_risk_scores, compute_reading_order, compute_bus_factor,
    detect_patterns, compute_change_difficulty, generate_questions,
    infer_requirements, compute_timeline, build_glossary,
    generate_report_data, build_html
)

# ── Engine 1: Risk scores ─────────────────────────────────
section("1. Risk scorer")
risk = compute_risk_scores(MOCK_GRAPH)

if 'overall' in risk and 'modules' in risk:
    ok(f"Overall score: {risk['overall']['score']} grade: {risk['overall']['grade']}")
else:
    fail("Missing overall or modules")

for mod in ['app', 'driver', 'comm']:
    if mod in risk['modules']:
        r = risk['modules'][mod]
        ok(f"Module {mod}: score={r['score']} grade={r['grade']} fns={r.get('fn_count',0)}")
    else:
        fail(f"Module {mod} missing")

if risk['modules']['driver']['score'] > risk['modules']['comm']['score']:
    ok("Driver riskier than comm (has ISR + races)")
else:
    fail("Risk ordering wrong: driver should be riskier than comm")

# ── Engine 2: Reading order ───────────────────────────────
section("2. Reading order")
order = compute_reading_order(MOCK_GRAPH)

if len(order) >= 3:
    ok(f"Reading order: {len(order)} modules")
    mods_ordered = [r['module'] for r in order]
    ok(f"Order: {' → '.join(mods_ordered)}")
else:
    fail(f"Expected >=3 modules, got {len(order)}")

if order[0].get('files'):
    ok(f"First module has files: {order[0]['files']}")
else:
    fail("No files in reading order")

# ── Engine 3: Bus factor ─────────────────────────────────
section("3. Bus factor")
bus = compute_bus_factor(MOCK_GRAPH)

if bus:
    ok(f"Bus factor: {len(bus)} critical functions")
    top = bus[0]
    ok(f"Most critical: {top['fn']} (impact: {top['impact']})")
    if top['fn'] == 'main':
        ok("main() correctly identified as highest impact")
    else:
        fail(f"Expected main as top, got {top['fn']}")
else:
    fail("No bus factor results")

# ── Engine 4: Pattern detector ────────────────────────────
section("4. Pattern detector")
patterns = detect_patterns(MOCK_GRAPH)

if patterns:
    ok(f"Detected {len(patterns)} patterns")
    types = {p['type'] for p in patterns}
    for expected in ['isr_pipeline']:
        if expected in types:
            ok(f"Pattern: {expected}")
        else:
            fail(f"Pattern missing: {expected}")
else:
    fail("No patterns detected")

# ── Engine 5: Change difficulty ───────────────────────────
section("5. Change difficulty")
diff = compute_change_difficulty(MOCK_GRAPH)

if len(diff) >= 3:
    ok(f"Difficulty for {len(diff)} modules")
    for mod in ['app', 'driver', 'comm']:
        d = diff.get(mod, {})
        ok(f"{mod}: {d.get('difficulty','?')} (score={d.get('score',0)}) — {len(d.get('reasons',[]))} reasons")
else:
    fail(f"Expected >=3 modules, got {len(diff)}")

# ── Engine 6: Question generator ──────────────────────────
section("6. Question generator")
questions = generate_questions(MOCK_GRAPH)

if questions:
    ok(f"Generated {len(questions)} questions")
    cats = {q['category'] for q in questions}
    for expected in ['safety', 'hardware']:
        if expected in cats:
            ok(f"Category: {expected}")
        else:
            fail(f"Category missing: {expected}")
    high = [q for q in questions if q['priority'] == 'high']
    ok(f"High priority: {len(high)}")
    # First question should be high priority (sorted)
    if questions[0]['priority'] == 'high':
        ok("Questions sorted by priority")
    else:
        fail("Questions not sorted by priority")
else:
    fail("No questions generated")

# ── Engine 7: Requirements ────────────────────────────────
section("7. Inferred requirements")
reqs = infer_requirements(MOCK_GRAPH)

if reqs:
    ok(f"Inferred {len(reqs)} requirements")
    cats = {r['category'] for r in reqs}
    for expected in ['functional', 'hardware', 'concurrency']:
        if expected in cats:
            ok(f"Category: {expected}")
        else:
            fail(f"Category missing: {expected}")
    # Check all have IDs
    ids = [r['id'] for r in reqs]
    if all(id.startswith('REQ-') for id in ids):
        ok("All requirements have REQ-xxx IDs")
    else:
        fail("Some requirements missing IDs")
else:
    fail("No requirements inferred")

# ── Engine 8: Timeline ────────────────────────────────────
section("8. Dependency timeline")
timeline = compute_timeline(MOCK_GRAPH)

if timeline:
    ok(f"Timeline: {len(timeline)} steps")
    if timeline[0]['label'] == 'Entry':
        ok("First step is Entry")
    else:
        fail(f"First step should be Entry, got {timeline[0]['label']}")
    total_fns = sum(len(s['functions']) for s in timeline)
    ok(f"Total functions in timeline: {total_fns}")
else:
    fail("No timeline generated")

# ── Engine 9: Glossary ────────────────────────────────────
section("9. Glossary")
glossary = build_glossary(MOCK_GRAPH)

if glossary:
    ok(f"Glossary: {len(glossary)} entries")
    kinds = {e['kind'] for e in glossary}
    for expected in ['function', 'module', 'global', 'peripheral']:
        if expected in kinds:
            ok(f"Kind: {expected}")
        else:
            fail(f"Kind missing: {expected}")
    fn_entries = [e for e in glossary if e['kind'] == 'function']
    ok(f"Functions in glossary: {len(fn_entries)}")
else:
    fail("No glossary entries")

# ── Full report assembly ──────────────────────────────────
section("10. Report assembly")

report_data = generate_report_data(MOCK_GRAPH)

if 'graph' in report_data and 'analysis' in report_data and 'meta' in report_data:
    ok("Report data has graph + analysis + meta")
else:
    fail("Report data missing sections")

for key in ['risk_scores','reading_order','bus_factor','patterns','change_difficulty','questions','requirements','timeline','glossary']:
    if key in report_data['analysis']:
        ok(f"Analysis: {key}")
    else:
        fail(f"Analysis missing: {key}")

meta = report_data['meta']
if meta.get('fn_count') == 7 and meta.get('module_count') == 3:
    ok(f"Meta: {meta['fn_count']} fns, {meta['module_count']} mods")
else:
    fail(f"Meta wrong: fn_count={meta.get('fn_count')}, module_count={meta.get('module_count')}")

# ── HTML build ────────────────────────────────────────────
section("11. HTML build")

try:
    html = build_html(report_data)
    ok(f"HTML generated: {len(html)} bytes")

    if 'REPORT_DATA' in html:
        ok("REPORT_DATA embedded in HTML")
    else:
        fail("REPORT_DATA not found in HTML")

    if '<!DOCTYPE html>' in html:
        ok("Valid HTML doctype")
    else:
        fail("Missing doctype")

    if 'Callgraph Report' in html:
        ok("Title present")
    else:
        fail("Title missing")

    if '@media print' in html:
        ok("Print CSS present")
    else:
        fail("Print CSS missing")

    if 'toggleTheme' in html:
        ok("Theme toggle present")
    else:
        fail("Theme toggle missing")

    for sect_id in ['header','reading','requirements','questions','layers','coupling','dataflow','boot','interrupts','hardware','modules','patterns','races','rtos','health','index','tools','glossary']:
        if f"'{sect_id}'" in html or f'"{sect_id}"' in html:
            ok(f"Section: {sect_id}")
        else:
            fail(f"Section missing: {sect_id}")

    # Write to temp file and verify it's valid
    tmp = tempfile.mktemp(suffix='.html')
    Path(tmp).write_text(html)
    ok(f"Written to {tmp} ({Path(tmp).stat().st_size} bytes)")
    Path(tmp).unlink()

    # Check interactive features present
    for feat in ['pzInit', 'pzFit', 'pzZoom', 'pzApply',
                 'showHoverPopup', 'hideHoverPopup', 'highlightConnections',
                 'whatifRun', 'whatifAutocomplete', 'whatifKey',
                 'filterTimeline', 'initTimelineSlider',
                 'sortTable', 'makeSvgNodesInteractive', 'addDataFnToSvgNodes']:
        if feat in html:
            ok(f"Interactive: {feat}")
        else:
            fail(f"Interactive missing: {feat}")

    # Check SVG generators present
    for gen in ['buildLayerDiagram', 'buildCouplingMatrix', 'buildDataFlowDiagram',
                'buildIsrMapDiagram', 'buildHwDiagram', 'buildModuleSubgraph']:
        if gen in html:
            ok(f"SVG generator: {gen}")
        else:
            fail(f"SVG generator missing: {gen}")

    # Check CSS for interactive elements
    for cls in ['diagram-pz', 'pz-controls', 'hover-popup', 'whatif-panel',
                'whatif-input', 'tl-slider', 'sort-bar', 'sort-btn']:
        if cls in html:
            ok(f"Interactive CSS: {cls}")
        else:
            fail(f"Interactive CSS missing: {cls}")

except Exception as e:
    fail(f"HTML build error: {e}")
    import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════
# 12. EDGE CASES
# ══════════════════════════════════════════════════════════════
section("12. Edge cases")

def make_graph(**overrides):
    base = {
        'source':'/tmp/test','files':0,'nodes':[],'edges':{},'callers':{},
        'mod_edges':{},'mods':[],'globals':{},'races':[],
        'rtos':{'tasks':{},'objects':{}},'peripherals':{},
    }
    base.update(overrides)
    return base

# Empty graph
try:
    rd = generate_report_data(make_graph())
    html = build_html(rd)
    ok(f"Empty graph: {len(html)} bytes")
except Exception as e:
    fail(f"Empty graph: {e}")

# Single function, single module
try:
    n = [{'id':'main','file':'m.c','mod':'.','module':'.','line':1,'type':'project',
          'is_isr':False,'is_entry':True,'has_critical':False,'delay_in_loop':False,
          'out_degree':0,'in_degree':0,'reads':[],'writes':[],'rw':[],'peripherals':[],'rtos':[]}]
    rd = generate_report_data(make_graph(nodes=n, mods=['.'], files=1))
    html = build_html(rd)
    ok(f"Single function: {len(html)} bytes")
except Exception as e:
    fail(f"Single function: {e}")

# No RTOS, no races, no ISRs, no peripherals (pure app code)
try:
    nodes = [
        {'id':'main','file':'a/m.c','mod':'a','module':'a','line':1,'type':'project','is_isr':False,'is_entry':True,'has_critical':False,'delay_in_loop':False,'out_degree':2,'in_degree':0,'reads':[],'writes':[],'rw':[],'peripherals':[],'rtos':[]},
        {'id':'foo','file':'b/f.c','mod':'b','module':'b','line':1,'type':'project','is_isr':False,'is_entry':False,'has_critical':False,'delay_in_loop':False,'out_degree':0,'in_degree':1,'reads':[],'writes':[],'rw':[],'peripherals':[],'rtos':[]},
        {'id':'bar','file':'b/b.c','mod':'b','module':'b','line':1,'type':'project','is_isr':False,'is_entry':False,'has_critical':False,'delay_in_loop':False,'out_degree':0,'in_degree':1,'reads':[],'writes':[],'rw':[],'peripherals':[],'rtos':[]},
    ]
    rd = generate_report_data(make_graph(nodes=nodes, edges={'main':['foo','bar']},
         callers={'foo':['main'],'bar':['main']}, mods=['a','b'],
         mod_edges={'a→b':2}, files=3))
    html = build_html(rd)
    ok(f"Pure app (no ISR/RTOS/periph): {len(html)} bytes")
except Exception as e:
    fail(f"Pure app: {e}")

# Large graph (200 nodes)
try:
    nodes = []
    edges = {}
    callers = {}
    for i in range(200):
        fn = f'fn_{i:03d}'
        nodes.append({'id':fn,'file':'big.c','mod':'big','module':'big','line':i,'type':'project','is_isr':False,'is_entry':i==0,'has_critical':False,'delay_in_loop':False,'out_degree':0,'in_degree':0,'reads':[],'writes':[],'rw':[],'peripherals':[],'rtos':[]})
        if i > 0:
            p = f'fn_{i-1:03d}'
            edges.setdefault(p,[]).append(fn)
            callers.setdefault(fn,[]).append(p)
    rd = generate_report_data(make_graph(nodes=nodes, edges=edges, callers=callers, mods=['big'], files=1))
    html = build_html(rd)
    ok(f"Large graph (200 nodes): {len(html)} bytes")
except Exception as e:
    fail(f"Large graph: {e}")

# Many isolated modules
try:
    nodes = []
    mods = []
    for m in range(10):
        mod = f'mod{m}'
        mods.append(mod)
        for i in range(3):
            nodes.append({'id':f'{mod}_f{i}','file':f'{mod}/f.c','mod':mod,'module':mod,'line':i,'type':'project','is_isr':False,'is_entry':False,'has_critical':False,'delay_in_loop':False,'out_degree':0,'in_degree':0,'reads':[],'writes':[],'rw':[],'peripherals':[],'rtos':[]})
    rd = generate_report_data(make_graph(nodes=nodes, mods=mods, files=10))
    html = build_html(rd)
    ok(f"10 isolated modules: {len(html)} bytes")
except Exception as e:
    fail(f"Isolated modules: {e}")

# JS syntax check on generated edge case reports
import subprocess as sp
for case_name, graph in [
    ('empty', make_graph()),
    ('minimal', make_graph(nodes=[{'id':'x','file':'x.c','mod':'.','module':'.','line':1,'type':'project','is_isr':False,'is_entry':True,'has_critical':False,'delay_in_loop':False,'out_degree':0,'in_degree':0,'reads':[],'writes':[],'rw':[],'peripherals':[],'rtos':[]}], mods=['.'], files=1)),
]:
    try:
        rd = generate_report_data(graph)
        html = build_html(rd)
        import re as _re
        m = _re.search(r'<script>(.*?)</script>', html, _re.DOTALL)
        if m:
            tmp = tempfile.mktemp(suffix='.js')
            Path(tmp).write_text(m.group(1))
            r = sp.run(['node','--check',tmp], capture_output=True, text=True)
            Path(tmp).unlink()
            if r.returncode == 0:
                ok(f"JS syntax ({case_name}): OK")
            else:
                fail(f"JS syntax ({case_name}): {r.stderr[:150]}")
    except Exception as e:
        fail(f"JS check ({case_name}): {e}")


# ── Summary ───────────────────────────────────────────────
print(f"\n{'='*52}")
print(f"  RESULTS:  {PASS} passed  /  {FAIL} failed")
print(f"{'='*52}\n")
sys.exit(0 if FAIL == 0 else 1)
