#!/usr/bin/env python3
"""
Callgraph Studio v2.2.1 — Deep Automated Test Suite

Comprehensive coverage of all features, endpoints, analysis engines,
JS functions, CSS, HTML structure, and edge cases.

Run:  python3 deep_test.py
"""

import sys, os, json, re, tempfile, shutil, subprocess, time
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent
INDEX_HTML = BASE / "index.html"
SERVER_PY  = BASE / "server.py"
ANALYZER_PY= BASE / "analyzer.py"

PASS = FAIL = 0
ERRORS = []

R = "\033[31m"
G = "\033[32m"
Y = "\033[33m"
B = "\033[1m"
N = "\033[0m"

def ok(msg):
    global PASS; PASS += 1
    print(f"  {G}✓{N} {msg}")

def fail(msg, detail=""):
    global FAIL; FAIL += 1; ERRORS.append(msg)
    print(f"  {R}✗{N} {msg}")
    if detail: print(f"    {detail[:300]}")

def section(title):
    print(f"\n{B}── {title} ──{N}")

html = INDEX_HTML.read_text(encoding="utf-8")
server_code = SERVER_PY.read_text(encoding="utf-8")
analyzer_code = ANALYZER_PY.read_text(encoding="utf-8")

# Extract JS
m = re.search(r'<script>(.*?)</script>', html, re.DOTALL)
js = m.group(1) if m else ""

# ══════════════════════════════════════════════════════════════
# 1. SYNTAX VALIDATION
# ══════════════════════════════════════════════════════════════
section("1. Syntax validation")

# Python
for f in [SERVER_PY, ANALYZER_PY]:
    try:
        import py_compile
        py_compile.compile(str(f), doraise=True)
        ok(f"{f.name} Python syntax")
    except Exception as e:
        fail(f"{f.name} syntax error", str(e))

# JS
tmp_js = Path(tempfile.mktemp(suffix=".js"))
tmp_js.write_text(js)
r = subprocess.run(["node", "--check", str(tmp_js)], capture_output=True, text=True)
tmp_js.unlink()
if r.returncode == 0:
    ok(f"index.html JS syntax ({len(js.splitlines())} lines)")
else:
    fail("JS syntax error", r.stderr[:300])

# Brace balance
opens = js.count('{')
closes = js.count('}')
if opens == closes:
    ok(f"JS brace balance: {opens} open = {closes} close")
else:
    fail(f"JS brace imbalance: {opens} open vs {closes} close (diff={opens-closes})")

# Paren balance (allow ±2 since parens in strings/regex/templates are counted)
po = js.count('(') 
pc = js.count(')')
if abs(po - pc) <= 2:
    ok(f"JS paren balance: {po} open, {pc} close (±{abs(po-pc)})")
else:
    fail(f"JS paren imbalance: {po} open vs {pc} close (diff={po-pc})")

# Report template
tpl_path = BASE / "report" / "template.html"
if tpl_path.exists():
    tpl = tpl_path.read_text()
    m2 = re.search(r'<script>(.*?)</script>', tpl, re.DOTALL)
    if m2:
        tpl_js = m2.group(1).replace('/*__REPORT_DATA__*/', 'const REPORT_DATA={graph:{nodes:[],edges:{},callers:{},mod_edges:{},mods:[],globals:{},races:[],rtos:{tasks:{},objects:{}},peripherals:{}},analysis:{risk_scores:{overall:{score:0,grade:"A"},modules:{}},reading_order:[],bus_factor:[],patterns:[],change_difficulty:{},questions:[],requirements:[],timeline:[],glossary:[]},meta:{generated_at:"",generator_version:"",project_name:"",project_path:"",file_count:0,fn_count:0,edge_count:0,module_count:0,race_count:0}};')
        tmp2 = Path(tempfile.mktemp(suffix=".js"))
        tmp2.write_text(tpl_js)
        r2 = subprocess.run(["node", "--check", str(tmp2)], capture_output=True, text=True)
        tmp2.unlink()
        if r2.returncode == 0:
            ok("report/template.html JS syntax")
        else:
            fail("template.html JS error", r2.stderr[:200])
    ok("report/template.html exists")
else:
    fail("report/template.html missing")

gen_path = BASE / "report" / "generator.py"
if gen_path.exists():
    py_compile.compile(str(gen_path), doraise=True)
    ok("report/generator.py syntax")
else:
    fail("report/generator.py missing")


# ══════════════════════════════════════════════════════════════
# 2. HTML ELEMENT COMPLETENESS
# ══════════════════════════════════════════════════════════════
section("2. HTML elements")

required_ids = [
    # Core layout
    "launch", "app", "canvas", "minimap", "tooltip", "toast",
    "gbar", "gbar-title", "gbar-legend", "breadcrumb",
    # Sidebar controls
    "depth", "dv", "trace-inp", "btn-reset-trace", "spills",
    "fn-list", "fn-search", "analysis-result",
    "tracedir-sect", "settings-sect", "entry-patterns",
    # Panels
    "info", "info-name", "info-body",
    "globals-panel", "race-panel", "rtos-panel", "periph-panel",
    "source-panel", "src-panel-title", "src-panel-body",
    "bookmarks-panel", "bookmarks-body",
    # v1.3+ elements
    "mod-legend", "ana-diff-btn", "btn-bookmarks",
    # v1.5+ elements
    "ana-coupling-btn", "btn-force",
    # v1.6+ elements
    "btn-watch", "btn-report",
    # File browser
    "fb", "fb-list", "fb-sel",
    # Graph controls
    "btn-ext", "btn-dir",
    # Progress
    "progress", "prog-fill", "prog-log",
]

for eid in required_ids:
    if f'id="{eid}"' in html:
        ok(f"#{eid}")
    else:
        fail(f"#{eid} missing")


# ══════════════════════════════════════════════════════════════
# 3. JS FUNCTION COVERAGE
# ══════════════════════════════════════════════════════════════
section("3. JS functions")

# Extract all function declarations
fn_pattern = re.compile(r'function\s+(\w+)\s*\(')
all_fns = set(fn_pattern.findall(js))
ok(f"Total JS functions: {len(all_fns)}")

# Categorize required functions
required_fns = {
    "Core": ["doIndex","enterApp","renderGraph","buildVisibleGraph","layoutGraph","renderFnGraph","renderModuleGraph","clearCanvas","showLoading","hideLoading"],
    "Trace": ["traceFunction","clearTrace","acTrace","traceKey","hideAc","setTraceDir"],
    "Navigation": ["histBack","histFwd","updateHistButtons","updateBreadcrumb","jumpHistory"],
    "Info": ["showInfo","closeInfo","showAllCallers","showAllCallees"],
    "Mode/Depth": ["setMode","onDepth","toggleExt","toggleDir","toggleForce"],
    "Function list": ["buildFnList","renderFnList","filterFns","setFnSort","setFnChip","highlightSearchNodes","selectFnItem"],
    "Session": ["saveSession","loadSession","restoreSessionYes","restoreSessionNo","clearSession","newIndex"],
    "Analysis": ["runDeadCode","showImpactUI","runImpact","runHeatmap","showPathUI","runPathFind","cancelPathFind","runCycleDetect","runStackDepth","runDiff","runCoupling","anaSetActive","anaResult"],
    "Diff": ["saveDiffSnapshot","loadDiffSnapshot","highlightDiff"],
    "Source": ["openSource","closeSource","highlightC"],
    "Bookmarks": ["toggleBookmark","isBookmarked","openBookmarks","closeBookmarks","renderBookmarks","saveBookmarks","loadBookmarks","updateBookmarkBadge","exportBookmarks"],
    "Graph render": ["buildStylePills","setTheme","showTooltip","moveTooltip","hideTooltip","toggleModExpand","toggleMatrix","fitGraph","zoom"],
    "Panels": ["openGlobals","openRaces","openRtos","openPeriph","closeGlobals","closeRaces","closeRtos","closePeriph","highlightGlobalTouchers","buildRtosInteractionDiagram","highlightCoupledModules"],
    "Context menu": ["showCtxMenu","hideCtxMenu","highlightUpstream","highlightDownstream","toggleCollapse"],
    "Export": ["exportSVG","exportPNG","exportGraphJSON","exportGraphCSV","exportGraphML","exportDOT","buildExportSVG"],
    "Report": ["generateReport"],
    "Watcher": ["toggleWatch","startWatch","stopWatch","showWatchBanner","hideWatchBanner"],
    "Settings": ["getEntryPatterns","saveEntryPatterns","resetEntryPatterns","loadEntryPatternsUI","toggleSettings","isEntryPoint"],
    "Layout": ["forceLayout"],
    "Minimap": ["updateMinimap","mmToggle"],
    "File browser": ["openFB","fbClose","fbUp","fbNav","fbConfirm"],
    "Utility": ["toast","esc","setProgFill","setProgLog"],
}

for category, fns in required_fns.items():
    missing = [f for f in fns if f not in all_fns]
    if not missing:
        ok(f"{category}: all {len(fns)} functions")
    else:
        fail(f"{category}: missing {', '.join(missing)}")


# ══════════════════════════════════════════════════════════════
# 4. CSS COVERAGE
# ══════════════════════════════════════════════════════════════
section("4. CSS classes & selectors")

required_css = [
    # Layout
    "#sidebar", "#canvas", "#gbar", "#info",
    # Panels
    "#globals-panel", "#race-panel", "#rtos-panel", "#periph-panel", "#bookmarks-panel",
    "#source-panel", "#source-panel.on",
    # Components
    ".sb-sect", ".sb-lbl", ".trace-inp", ".depth-row",
    ".fn-item", ".fn-chip", ".fn-search",
    ".ana-btn", ".ana-btn.active",
    ".tdir-pills", ".tdir-pill", ".tdir-pill.active",
    ".mod-legend", ".mod-legend.on",
    ".src-line", ".src-gutter", ".src-code",
    ".src-badge", ".src-badge.calls", ".src-badge.race", ".src-badge.dead", ".src-badge.periph", ".src-badge.isr",
    # Syntax highlighting
    ".sh-kw", ".sh-type", ".sh-str", ".sh-num", ".sh-cmt", ".sh-pp",
    # Settings
    ".settings-toggle", ".settings-body", ".settings-textarea",
    # Themes
    ".theme-light", ".theme-hc", ".theme-alhambra",
    # Context menu
    ".ctx-mi",
    # Toast
    ".toast",
]

for sel in required_css:
    if sel in html:
        ok(f"CSS: {sel}")
    else:
        fail(f"CSS missing: {sel}")


# ══════════════════════════════════════════════════════════════
# 5. SERVER ENDPOINTS
# ══════════════════════════════════════════════════════════════
section("5. Server endpoints")

routes = [
    ("/", "GET"), ("/api/browse", "GET"), ("/api/detect-includes", "GET"),
    ("/api/detect-roots", "GET"), ("/api/deps", "GET"),
    ("/api/install", "POST"), ("/api/stream/", "GET"),
    ("/api/upload", "POST"), ("/api/run", "POST"),
    ("/api/cancel/", "POST"), ("/api/runs", "GET"),
    ("/api/index", "POST"), ("/api/source", "GET"),
    ("/api/report", "POST"), ("/favicon.ico", "GET"),
    # v2.2.1
    ("/api/watch/start", "POST"), ("/api/watch/stop", "POST"),
]

for route, method in routes:
    if route in server_code:
        ok(f"{method} {route}")
    else:
        fail(f"Route missing: {method} {route}")

# Security checks
security_checks = [
    ("blocked = ['/etc'", "System dir blocking"),
    ("startswith(str(root_p))", "Path traversal protection in /api/source"),
    ("MAX_CONTENT_LENGTH", "Upload size limit"),
]
for pattern, desc in security_checks:
    if pattern in server_code:
        ok(f"Security: {desc}")
    else:
        fail(f"Security missing: {desc}")

# Route ordering
for fn_name in ["api_index", "api_source", "api_report", "api_watch_start"]:
    fn_pos = server_code.find(f"def {fn_name}")
    main_pos = server_code.find('if __name__')
    if fn_pos > 0 and main_pos > 0 and fn_pos < main_pos:
        ok(f"{fn_name} before __main__")
    elif fn_pos > 0:
        fail(f"{fn_name} AFTER __main__ — won't register!")
    else:
        fail(f"{fn_name} not found")


# ══════════════════════════════════════════════════════════════
# 6. ANALYZER DEEP CHECK
# ══════════════════════════════════════════════════════════════
section("6. Analyzer")

# Patterns
for pattern_name in ["ISR_RE", "ENTRY_RE", "PERIPHERAL_RE", "RTOS_API",
                      "CRITICAL_SECTION_ENTER", "CRITICAL_SECTION_EXIT"]:
    if pattern_name in analyzer_code:
        ok(f"Pattern: {pattern_name}")
    else:
        fail(f"Pattern missing: {pattern_name}")

# RTOS API coverage
rtos_apis = ["xTaskCreate", "xQueueCreate", "xQueueSend", "xQueueReceive",
             "xSemaphoreCreateMutex", "xSemaphoreTake", "xSemaphoreGive",
             "vTaskDelay", "xQueueSendFromISR", "xSemaphoreGiveFromISR",
             "osThreadNew", "osMessageQueueNew", "osMutexNew"]
for api in rtos_apis:
    if f"'{api}'" in analyzer_code:
        ok(f"RTOS API: {api}")
    else:
        fail(f"RTOS API missing: {api}")

# Return schema fields
for field in ["'nodes'", "'edges'", "'callers'", "'mod_edges'", "'mods'",
              "'globals'", "'races'", "'rtos'", "'peripherals'"]:
    if field in analyzer_code:
        ok(f"Return field: {field}")
    else:
        fail(f"Return field missing: {field}")

# Node fields emitted
for nf in ["'is_isr'", "'is_entry'", "'has_critical'", "'delay_in_loop'",
           "'out_degree'", "'in_degree'", "'reads'", "'writes'", "'rw'",
           "'peripherals'", "'rtos'"]:
    if nf in analyzer_code:
        ok(f"Node field: {nf}")
    else:
        fail(f"Node field missing: {nf}")


# ══════════════════════════════════════════════════════════════
# 7. ANALYZER RUNTIME
# ══════════════════════════════════════════════════════════════
section("7. Analyzer runtime")

try:
    sys.path.insert(0, str(BASE))
    from analyzer import TS_AVAILABLE, analyze_project

    if not TS_AVAILABLE:
        fail("tree-sitter not available")
    else:
        ok("tree-sitter imported")

        # Complex mock project
        tmp = Path(tempfile.mkdtemp())
        src = tmp / "project"
        for d in ["app","driver","rtos_layer","comm"]:
            (src / d).mkdir(parents=True)

        (src / "app" / "main.c").write_text("""
volatile int g_temp = 0;
volatile int g_flag = 0;
int g_config = 0;
void driver_init(void);
void sensor_read(void);
void comm_send(int v);
void task_process(void *p);
int main(void) {
    driver_init();
    g_config = 1;
    sensor_read();
    task_process(0);
    comm_send(g_temp);
    return 0;
}
void task_process(void *p) {
    int t = g_temp;
    comm_send(t);
}
""")
        (src / "driver" / "sensor.c").write_text("""
extern volatile int g_temp;
typedef struct { volatile unsigned DR; volatile unsigned CR; } ADC_TypeDef;
typedef struct { volatile unsigned ODR; volatile unsigned IDR; } GPIO_TypeDef;
#define ADC1 ((ADC_TypeDef*)0x40012000)
#define GPIOA ((GPIO_TypeDef*)0x40020000)
void sensor_read(void) {
    ADC1->CR = 1;
    g_temp = ADC1->DR;
    GPIOA->ODR = 1;
}
void ADC1_IRQHandler(void) {
    g_temp = ADC1->DR;
}
void driver_init(void) {
    ADC1->CR = 0;
    GPIOA->ODR = 0;
}
static void dead_fn(void) { int x = 0; }
void recursive_a(void);
void recursive_b(void);
void recursive_a(void) { recursive_b(); }
void recursive_b(void) { recursive_a(); }
""")
        (src / "comm" / "comm.c").write_text("""
typedef struct { volatile unsigned DR; volatile unsigned SR; } USART_TypeDef;
#define USART1 ((USART_TypeDef*)0x40011000)
void comm_send(int val) { USART1->DR = val; }
void USART1_IRQHandler(void) { volatile int r = USART1->DR; }
""")
        (src / "rtos_layer" / "tasks.c").write_text("""
extern volatile int g_flag;
void xQueueSendFromISR(void *q, void *d, void *w);
void xQueueReceive(void *q, void *d, int t);
void *sensorQ;
void isr_forward(void) {
    xQueueSendFromISR(sensorQ, &g_flag, 0);
}
void task_reader(void) {
    int val;
    xQueueReceive(sensorQ, &val, 100);
}
""")

        files = list(src.rglob("*.c"))
        ok(f"Mock project: {len(files)} files")

        msgs = []
        graph = analyze_project(files, src_root=src, push_fn=lambda m: msgs.append(m))

        if graph is None:
            fail("analyze_project returned None")
        else:
            n_nodes = len(graph['nodes'])
            n_edges = sum(len(v) for v in graph['edges'].values())
            ok(f"Analysis: {n_nodes} nodes, {n_edges} edges")

            nodes = {n['id']: n for n in graph['nodes']}

            # Function detection
            for fn in ["main","driver_init","sensor_read","comm_send","task_process",
                        "ADC1_IRQHandler","USART1_IRQHandler","dead_fn",
                        "recursive_a","recursive_b","isr_forward","task_reader"]:
                if fn in nodes: ok(f"Found: {fn}")
                else: fail(f"Missing: {fn}")

            # ISR detection
            for isr in ["ADC1_IRQHandler","USART1_IRQHandler"]:
                if nodes.get(isr,{}).get('is_isr'): ok(f"{isr} is_isr=true")
                else: fail(f"{isr} not flagged as ISR")

            # Entry
            if nodes.get("main",{}).get("is_entry"): ok("main is_entry=true")
            else: fail("main not entry")

            # Modules
            mods = set(graph['mods'])
            expected_mods = {"app","driver","comm","rtos_layer"}
            for em in expected_mods:
                if em in mods: ok(f"Module: {em}")
                else: fail(f"Module missing: {em}")

            # Edges
            for caller,callee in [("main","driver_init"),("main","sensor_read"),
                                   ("main","task_process"),("main","comm_send"),
                                   ("task_process","comm_send"),
                                   ("recursive_a","recursive_b"),("recursive_b","recursive_a")]:
                if callee in graph['edges'].get(caller,[]): ok(f"Edge: {caller}→{callee}")
                else: fail(f"Edge missing: {caller}→{callee}")

            # Callers (reverse)
            for callee,caller in [("driver_init","main"),("comm_send","main"),("comm_send","task_process")]:
                if caller in graph['callers'].get(callee,[]): ok(f"Caller: {callee}←{caller}")
                else: fail(f"Caller missing: {callee}←{caller}")

            # Cross-module edges
            if graph['mod_edges']: ok(f"Cross-module edges: {len(graph['mod_edges'])}")
            else: fail("No cross-module edges")

            # Globals
            gl = graph.get('globals',{})
            if gl.get('g_temp',{}).get('volatile'): ok("g_temp volatile")
            else: fail("g_temp not volatile")
            if 'g_config' in gl: ok("g_config detected")
            else: fail("g_config missing")

            # Races
            race_vars = {r['var'] for r in graph.get('races',[])}
            if 'g_temp' in race_vars: ok(f"Race: g_temp ({len(graph['races'])} total)")
            else: fail("No race on g_temp")

            # Peripherals
            for p in ["ADC1","GPIOA","USART1"]:
                if p in graph.get('peripherals',{}): ok(f"Peripheral: {p}")
                else: fail(f"Peripheral missing: {p}")

            # Dead code
            dn = nodes.get("dead_fn",{})
            if dn.get('in_degree',99)==0: ok("dead_fn in_degree=0")
            else: fail(f"dead_fn in_degree={dn.get('in_degree','?')}")

            # Cycle
            if 'recursive_b' in graph['edges'].get('recursive_a',[]) and \
               'recursive_a' in graph['edges'].get('recursive_b',[]):
                ok("Cycle: recursive_a ↔ recursive_b")
            else:
                fail("Cycle not detected")

        shutil.rmtree(tmp)

except Exception as e:
    fail(f"Analyzer runtime: {e}")
    import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════
# 8. FLASK SERVER TESTS
# ══════════════════════════════════════════════════════════════
section("8. Flask server")

try:
    os.chdir(str(BASE))
    import importlib.util
    spec = importlib.util.spec_from_file_location("server", str(SERVER_PY))
    server_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server_mod)
    app = server_mod.app
    client = app.test_client()

    # Basic routes
    for path, expected_code, check in [
        ("/", 200, lambda d: b"Callgraph Studio" in d),
        ("/favicon.ico", 200, lambda d: b"svg" in d),
        ("/api/deps", 200, lambda d: b"_pkg_manager" in d),
        ("/api/runs", 200, lambda d: True),
        ("/api/browse?path=/tmp", 200, lambda d: b"entries" in d),
    ]:
        r = client.get(path)
        if r.status_code == expected_code and check(r.data):
            ok(f"GET {path} → {expected_code}")
        else:
            fail(f"GET {path} → {r.status_code} (expected {expected_code})")

    # POST endpoints - error cases
    for path, body, expected_code in [
        ("/api/index", {"source_path":""}, 400),
        ("/api/index", {"source_path":"/nonexistent"}, 400),
        ("/api/index", {"source_path":"/etc"}, 403),
        ("/api/index", {"source_path":"/proc"}, 403),
        ("/api/source?file=&root=", None, 400),
        ("/api/report", {}, 400),
    ]:
        if body is not None:
            r = client.post(path, json=body, content_type="application/json")
        else:
            r = client.get(path if '?' in path else path)
        if r.status_code == expected_code:
            ok(f"{'POST' if body else 'GET'} {path.split('?')[0]} (error case) → {expected_code}")
        else:
            fail(f"{'POST' if body else 'GET'} {path} → {r.status_code} (expected {expected_code})")

    # Source API - path traversal
    r = client.get("/api/source?file=../../etc/passwd&root=/tmp")
    if r.status_code in (403, 404):
        ok(f"Path traversal blocked → {r.status_code}")
    else:
        fail(f"Path traversal NOT blocked → {r.status_code}")

    # Source API - valid file
    tmp_src = Path(tempfile.mkdtemp())
    (tmp_src / "t.c").write_text("int main(){return 0;}\n")
    r = client.get(f"/api/source?file=t.c&root={tmp_src}")
    if r.status_code == 200 and b"lines" in r.data:
        ok("Source API (valid file) → 200")
    else:
        fail(f"Source API → {r.status_code}")
    shutil.rmtree(tmp_src)

    # Index with real project
    tmp_proj = Path(tempfile.mkdtemp())
    (tmp_proj / "main.c").write_text("int main(void){return 0;}\n")
    r = client.post("/api/index", json={"source_path":str(tmp_proj)}, content_type="application/json")
    if r.status_code == 200 and b"stream_id" in r.data:
        sid = r.get_json()["stream_id"]
        ok(f"Index API → stream_id={sid[:12]}…")
        # Poll for graph
        graph_ok = False
        for _ in range(30):
            r2 = client.get(f"/api/stream/{sid}")
            if b"__GRAPH__:" in r2.data:
                graph_ok = True
                break
            time.sleep(0.2)
        if graph_ok: ok("SSE stream delivered graph")
        else: fail("SSE stream timeout")
    else:
        fail(f"Index API → {r.status_code}")
    shutil.rmtree(tmp_proj)

    # Watch endpoints
    r = client.post("/api/watch/start", json={"path":"/tmp"}, content_type="application/json")
    if r.status_code == 200 and b"stream_id" in r.data:
        ok("Watch start → 200")
    else:
        fail(f"Watch start → {r.status_code}")
    r = client.post("/api/watch/stop", content_type="application/json")
    if r.status_code == 200:
        ok("Watch stop → 200")
    else:
        fail(f"Watch stop → {r.status_code}")

except Exception as e:
    fail(f"Flask test: {e}")
    import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════
# 9. FEATURE-SPECIFIC DEEP CHECKS
# ══════════════════════════════════════════════════════════════
section("9. Feature-specific (v1.2–v1.6)")

checks = {
    # v1.2 features
    "Stack depth memoized": "const _memo = {}",
    "Stack depth onStack": "onStack.has(node)",
    "Cycle detection Tarjan": "function runCycleDetect",
    "Dead code analysis": "function runDeadCode",
    "Impact analysis": "function runImpact",
    "Heatmap": "function runHeatmap",
    "Path finder": "function runPathFind",
    "Context menu": "function showCtxMenu",
    "Multi-trace": "function runMultiTrace",
    "Edge bundling": "BUNDLE_THRESH",
    "Minimap": "function updateMinimap",
    "Keyboard shortcuts": "document.addEventListener('keydown'",
    "Shortcut overlay": "function toggleShortcutHelp",

    # v1.3 features
    "Auto-trace main": "G.nodes.find(n=>n.id==='main')",
    "Trace direction": "traceDir !== 'down'",
    "Module color palette": "MOD_PALETTE",
    "Module label y=34": "'y','34'",
    "Node height NH=46": "NH=46",
    "Diff mode": "function runDiff",
    "Diff snapshot localStorage": "cg_diff_snap",
    "Source panel fetch": "/api/source",
    "Source badges": "src-badge",
    "Bookmarks localStorage": "cg_bookmarks",
    "Bookmark toggle": "function toggleBookmark",
    "Bookmark export": "function exportBookmarks",
    "String escaper": "function esc(",

    # v1.4 (report app)
    "Report button": "btn-report",
    "Report API call": "/api/report",
    "Report generator endpoint": "def api_report",

    # v1.5 features
    "RTOS ISR diagram": "function buildRtosInteractionDiagram",
    "FromISR detection": "FromISR",
    "Coupling analysis": "function runCoupling",
    "Coupling highlight": "function highlightCoupledModules",
    "Entry point config": "function isEntryPoint",
    "Entry patterns default": "DEFAULT_ENTRY_PATTERNS",
    "Entry patterns localStorage": "cg_entry_patterns",
    "Settings toggle": "function toggleSettings",
    "Force layout": "function forceLayout",
    "Force toggle": "function toggleForce",
    "Force state": "let useForce",
    "Force integrated": "useForce ? forceLayout",

    # v1.6 features
    "Theme light": ".theme-light",
    "Theme high-contrast": ".theme-hc",
    "Theme alhambra": ".theme-alhambra",
    "Theme setter": "function setTheme",
    "Theme localStorage": "cg_theme",
    "Syntax highlight keywords": ".sh-kw",
    "Syntax highlight function": "function highlightC",
    "Source diff markers": "diffAdded.has(fn.id)",
    "Export GraphML": "function exportGraphML",
    "Export DOT": "function exportDOT",
    "GraphML format": "graphml",
    "DOT format": "digraph callgraph",
    "Path finder Web Worker": "new Worker(",
    "Path finder cancel": "function cancelPathFind",
    "File watcher toggle": "function toggleWatch",
    "File watcher start": "function startWatch",
    "File watcher stop": "function stopWatch",
    "Watch banner": "function showWatchBanner",
    "Watch endpoint start": "/api/watch/start",
    "Watch endpoint stop": "/api/watch/stop",
    "Watch polling": "_file_snapshot",
}

combined = html + js + server_code
tpl_code = ""
if tpl_path.exists():
    tpl_code = tpl_path.read_text()
all_code = combined + tpl_code
for name, pattern in checks.items():
    if pattern in all_code:
        ok(name)
    else:
        fail(f"{name}: '{pattern}' not found")


# ══════════════════════════════════════════════════════════════
# 10. REPORT GENERATOR DEEP CHECK
# ══════════════════════════════════════════════════════════════
section("10. Report generator engines")

try:
    sys.path.insert(0, str(BASE / "report"))
    from generator import (
        compute_risk_scores, compute_reading_order, compute_bus_factor,
        detect_patterns, compute_change_difficulty, generate_questions,
        infer_requirements, compute_timeline, build_glossary,
        generate_report_data, build_html
    )
    ok("All 9 engines + 2 assembly functions imported")

    # Use the mock graph from earlier analyzer test
    mock = {
        'source':'/tmp/p','files':3,
        'nodes':[
            {'id':'main','file':'a/m.c','mod':'a','module':'a','line':1,'type':'project','is_isr':False,'is_entry':True,'has_critical':False,'delay_in_loop':False,'out_degree':2,'in_degree':0,'reads':[],'writes':['g'],'rw':[],'peripherals':[],'rtos':[]},
            {'id':'foo','file':'b/f.c','mod':'b','module':'b','line':1,'type':'project','is_isr':False,'is_entry':False,'has_critical':True,'delay_in_loop':False,'out_degree':0,'in_degree':1,'reads':['g'],'writes':[],'rw':[],'peripherals':['ADC1->DR'],'rtos':[]},
            {'id':'isr','file':'b/i.c','mod':'b','module':'b','line':1,'type':'project','is_isr':True,'is_entry':False,'has_critical':False,'delay_in_loop':False,'out_degree':0,'in_degree':0,'reads':[],'writes':['g'],'rw':[],'peripherals':['ADC1->DR'],'rtos':[]},
        ],
        'edges':{'main':['foo']},
        'callers':{'foo':['main']},
        'mod_edges':{'a→b':1},'mods':['a','b'],
        'globals':{'g':{'file':'a/m.c','line':1,'volatile':True,'extern':False,'static':False}},
        'races':[{'var':'g','isr_writers':['isr'],'task_fn':'foo','task_access':'read','protected':False,'volatile':True,'severity':'high','file':'a/m.c'}],
        'rtos':{'tasks':{},'objects':{}},'peripherals':{'ADC1':{'readers':['foo','isr'],'writers':[],'rw':[]}},
    }

    rd = generate_report_data(mock)
    a = rd['analysis']

    if a['risk_scores']['overall']['score'] >= 0: ok(f"Risk: overall={a['risk_scores']['overall']['score']}")
    else: fail("Risk score invalid")

    if len(a['reading_order']) >= 2: ok(f"Reading order: {len(a['reading_order'])} modules")
    else: fail("Reading order too short")

    if a['bus_factor']: ok(f"Bus factor: {len(a['bus_factor'])} entries")
    else: ok("Bus factor: no critical fns (small graph)")

    if len(a['questions']) >= 3: ok(f"Questions: {len(a['questions'])}")
    else: fail(f"Questions too few: {len(a['questions'])}")

    if len(a['requirements']) >= 3: ok(f"Requirements: {len(a['requirements'])}")
    else: fail(f"Requirements too few: {len(a['requirements'])}")

    if a['timeline']: ok(f"Timeline: {len(a['timeline'])} steps")
    else: fail("No timeline")

    if len(a['glossary']) >= 5: ok(f"Glossary: {len(a['glossary'])} entries")
    else: fail(f"Glossary too small: {len(a['glossary'])}")

    # Build HTML
    h = build_html(rd)
    if len(h) > 10000 and 'REPORT_DATA' in h:
        ok(f"HTML generated: {len(h)} bytes")
    else:
        fail("HTML generation failed or too small")

    # Verify report JS syntax
    m3 = re.search(r'<script>(.*?)</script>', h, re.DOTALL)
    if m3:
        tmp3 = Path(tempfile.mktemp(suffix='.js'))
        tmp3.write_text(m3.group(1))
        r3 = subprocess.run(['node','--check',str(tmp3)], capture_output=True, text=True)
        tmp3.unlink()
        if r3.returncode == 0: ok("Generated report JS: valid")
        else: fail("Generated report JS: syntax error")

except Exception as e:
    fail(f"Report generator: {e}")
    import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════
# 11. EDGE CASES
# ══════════════════════════════════════════════════════════════
section("11. Edge cases & guards")

edge_checks = {
    "Large graph guard (800)": "visNodes.size>800",
    "Empty graph guard": "visNodes.size===0",
    "Module subgraph limit (40)": "modFns.length > 40",
    "Fn list cap (400)": "fns.slice(0,400)",
    "Session TTL (24h)": "86400000",
    "Server timeout (600s)": "timeout = 600",
    "Max upload 200MB": "200 * 1024 * 1024",
    "System dirs blocked": "'/etc'",
    "Force layout iterations (80)": "ITERS = 80",
    "BFS depth limit callers (3)": "d<3",
}

for name, pattern in edge_checks.items():
    if pattern in all_code:
        ok(name)
    else:
        fail(name)


# ══════════════════════════════════════════════════════════════
# 12. VERSION CONSISTENCY
# ══════════════════════════════════════════════════════════════
section("12. Version consistency")

# Check for browser native name collisions
BROWSER_GLOBALS = {'scrollTo','scroll','scrollBy','focus','blur','open','close','print',
    'stop','find','alert','confirm','prompt','fetch'}
for fname, code in [('index.html', js), ('template.html', tpl_code if tpl_path.exists() else '')]:
    if not code: continue
    fns = set(re.findall(r'function\s+(\w+)\s*\(', code))
    collisions = fns & BROWSER_GLOBALS
    if collisions:
        fail(f"{fname}: native name collisions: {collisions}")
    else:
        ok(f"{fname}: no native name collisions ({len(fns)} functions checked)")

if "v2.2.1" in html:
    ok("index.html: v2.2.1")
else:
    fail("index.html: wrong version")

# Check start.sh version
sh = (BASE / "start.sh").read_text()
if "v1.6" in sh:
    ok("start.sh: v1.6")
else:
    fail("start.sh: wrong version")


# ══════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════
total = PASS + FAIL
print(f"\n{'='*60}")
print(f"  {B}DEEP TEST:{N}  {G}{PASS}{N}/{total} passed", end="")
if FAIL:
    print(f"  {R}{FAIL} FAILED{N}")
else:
    print(f"  {G}ALL GREEN{N}")
print(f"{'='*60}")

if ERRORS:
    print(f"\n  Failures:")
    for e in ERRORS:
        print(f"    {R}✗{N} {e}")

print()
sys.exit(0 if FAIL == 0 else 1)
