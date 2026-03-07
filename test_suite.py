#!/usr/bin/env python3
"""
Callgraph Studio v2.2.0 — Full Automated Test Suite

Tests:
  - Python syntax (server.py, analyzer.py)
  - JS syntax (index.html script block)
  - Server endpoints (Flask test client)
  - Analyzer with mock C files (tree-sitter)
  - Graph JSON schema validation
  - HTML structure validation
  - Feature completeness checks
  - Edge cases

Run:  python3 test_suite.py
"""

import sys, os, json, re, tempfile, shutil, subprocess
from pathlib import Path

# ── Config ────────────────────────────────────────────────────
BASE = Path(__file__).parent
INDEX_HTML = BASE / "index.html"
SERVER_PY  = BASE / "server.py"
ANALYZER_PY= BASE / "analyzer.py"
START_SH   = BASE / "start.sh"

PASS = 0
FAIL = 0
ERRORS = []

def ok(msg):
    global PASS; PASS += 1
    print(f"  \033[32m✓\033[0m {msg}")

def fail(msg, detail=""):
    global FAIL; FAIL += 1
    ERRORS.append(msg)
    print(f"  \033[31m✗\033[0m {msg}")
    if detail: print(f"    {detail}")

def section(title):
    print(f"\n\033[1m── {title} ──\033[0m")


# ══════════════════════════════════════════════════════════════
# 1. FILE EXISTENCE
# ══════════════════════════════════════════════════════════════
section("1. File existence")

for f, desc in [
    (INDEX_HTML, "index.html"),
    (SERVER_PY, "server.py"),
    (ANALYZER_PY, "analyzer.py"),
    (START_SH, "start.sh"),
]:
    if f.exists():
        ok(f"{desc} exists ({f.stat().st_size} bytes)")
    else:
        fail(f"{desc} missing")


# ══════════════════════════════════════════════════════════════
# 2. PYTHON SYNTAX
# ══════════════════════════════════════════════════════════════
section("2. Python syntax")

for f in [SERVER_PY, ANALYZER_PY]:
    try:
        import py_compile
        py_compile.compile(str(f), doraise=True)
        ok(f"{f.name} syntax valid")
    except py_compile.PyCompileError as e:
        fail(f"{f.name} syntax error", str(e))


# ══════════════════════════════════════════════════════════════
# 3. JS SYNTAX
# ══════════════════════════════════════════════════════════════
section("3. JS syntax")

html = INDEX_HTML.read_text(encoding="utf-8")
m = re.search(r'<script>(.*?)</script>', html, re.DOTALL)
if m:
    js_code = m.group(1)
    tmp_js = Path(tempfile.mktemp(suffix=".js"))
    tmp_js.write_text(js_code, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(tmp_js)], capture_output=True, text=True)
    tmp_js.unlink()
    if r.returncode == 0:
        ok(f"JS syntax valid ({len(js_code.splitlines())} lines)")
    else:
        fail("JS syntax error", r.stderr[:300])
else:
    fail("No <script> block found in index.html")


# ══════════════════════════════════════════════════════════════
# 4. HTML STRUCTURE
# ══════════════════════════════════════════════════════════════
section("4. HTML structure")

required_ids = [
    "launch", "app", "canvas", "minimap", "tooltip", "toast",
    "gbar", "gbar-title", "gbar-legend",
    "depth", "dv", "trace-inp", "btn-reset-trace",
    "fn-list", "fn-search", "analysis-result",
    "info", "info-name", "info-body",
    "globals-panel", "race-panel", "rtos-panel", "periph-panel",
    # v2.2.0 additions
    "tracedir-sect", "mod-legend", "source-panel", "src-panel-title",
    "src-panel-body", "bookmarks-panel", "bookmarks-body",
    "btn-bookmarks", "ana-diff-btn",
]

for eid in required_ids:
    if f'id="{eid}"' in html:
        ok(f'Element #{eid} present')
    else:
        fail(f'Element #{eid} missing from HTML')


# ══════════════════════════════════════════════════════════════
# 5. JS FUNCTIONS EXIST
# ══════════════════════════════════════════════════════════════
section("5. JS function completeness")

required_fns = [
    # Core
    "doIndex", "enterApp", "renderGraph", "buildVisibleGraph",
    "layoutGraph", "renderFnGraph", "renderModuleGraph",
    "traceFunction", "clearTrace", "showInfo", "closeInfo",
    "setMode", "onDepth", "toggleExt", "buildFnList", "filterFns",
    "saveSession", "loadSession", "restoreSessionYes", "newIndex",
    # v2.2.0 additions
    "setTraceDir",       # trace direction toggle
    "toggleBookmark", "openBookmarks", "closeBookmarks",
    "renderBookmarks", "isBookmarked", "loadBookmarks",
    "saveBookmarks", "updateBookmarkBadge", "exportBookmarks",
    "openSource", "closeSource",  # source annotation
    "runDiff", "saveDiffSnapshot", "loadDiffSnapshot",
    "highlightDiff",  # diff mode
    "esc",  # string escaper
    # Analysis
    "runDeadCode", "showImpactUI", "runImpact", "runHeatmap",
    "showPathUI", "runCycleDetect", "runStackDepth",
    # Graph interaction
    "showCtxMenu", "hideCtxMenu", "highlightUpstream", "highlightDownstream",
    "showTooltip", "hideTooltip", "fitGraph", "zoom",
    # Export
    "exportSVG", "exportPNG", "exportGraphJSON", "exportGraphCSV",
    # Navigation
    "histBack", "histFwd", "updateBreadcrumb",
]

for fn in required_fns:
    pattern = f"function {fn}("
    if pattern in js_code:
        ok(f"function {fn}() defined")
    else:
        # Also check for arrow/const pattern
        alt = f"{fn}=" 
        if alt in js_code:
            ok(f"{fn} defined (as variable)")
        else:
            fail(f"function {fn}() NOT FOUND")


# ══════════════════════════════════════════════════════════════
# 6. STATE VARIABLES
# ══════════════════════════════════════════════════════════════
section("6. State variables")

required_vars = [
    "let G ", "let mode ", "let depth ", "let tracedFn ",
    "let traceDir ", "let showExt ", "let layoutDir ",
    "let svgPan ", "let collapsedNodes ",
    "let _bookmarks ", "let _prevSnapshot ",
]

for v in required_vars:
    if v in js_code:
        ok(f"State: {v.strip()}")
    else:
        fail(f"State variable missing: {v.strip()}")


# ══════════════════════════════════════════════════════════════
# 7. CSS CLASSES
# ══════════════════════════════════════════════════════════════
section("7. CSS completeness")

required_css = [
    ".tdir-pills", ".tdir-pill", ".tdir-pill.active",
    ".mod-legend", ".mod-legend.on", ".mod-legend-item", ".mod-legend-dot",
    "#source-panel", "#source-panel.on", ".src-hdr", ".src-body",
    ".src-line", ".src-gutter", ".src-code", ".src-badge",
    ".src-badge.calls", ".src-badge.race", ".src-badge.dead",
    ".src-badge.periph", ".src-badge.isr",
    "#bookmarks-panel",
]

for cls in required_css:
    if cls in html:
        ok(f"CSS: {cls}")
    else:
        fail(f"CSS missing: {cls}")


# ══════════════════════════════════════════════════════════════
# 8. SERVER ENDPOINTS
# ══════════════════════════════════════════════════════════════
section("8. Server endpoints")

server_code = SERVER_PY.read_text(encoding="utf-8")

required_routes = [
    ("/api/browse", "GET"),
    ("/api/detect-includes", "GET"),
    ("/api/detect-roots", "GET"),
    ("/api/deps", "GET"),
    ("/api/install", "POST"),
    ("/api/stream/", "GET"),
    ("/api/upload", "POST"),
    ("/api/run", "POST"),
    ("/api/cancel/", "POST"),
    ("/api/runs", "GET"),
    ("/api/index", "POST"),
    ("/api/source", "GET"),  # v2.2.0
    ("/favicon.ico", "GET"),
]

for route, method in required_routes:
    if route in server_code:
        ok(f"Route {method} {route}")
    else:
        fail(f"Route missing: {method} {route}")

# Check route order: /api/index must be BEFORE __main__
idx_pos = server_code.find("def api_index")
main_pos = server_code.find('if __name__ == "__main__"')
if idx_pos > 0 and main_pos > 0:
    if idx_pos < main_pos:
        ok("/api/index is before __main__ (route registered)")
    else:
        fail("/api/index is AFTER __main__ — route won't register!")
else:
    fail("Could not find api_index or __main__")

# Check /api/source is before __main__
src_pos = server_code.find("def api_source")
if src_pos > 0 and main_pos > 0:
    if src_pos < main_pos:
        ok("/api/source is before __main__")
    else:
        fail("/api/source is AFTER __main__!")

# Check source endpoint has path traversal protection
if "startswith(str(root_p))" in server_code or "startswith(str(root" in server_code:
    ok("/api/source has path traversal protection")
else:
    fail("/api/source missing path traversal check")


# ══════════════════════════════════════════════════════════════
# 9. ANALYZER PASSES
# ══════════════════════════════════════════════════════════════
section("9. Analyzer completeness")

analyzer_code = ANALYZER_PY.read_text(encoding="utf-8")

required_analyzer = [
    ("TS_AVAILABLE", "tree-sitter availability flag"),
    ("analyze_file", "per-file analysis function"),
    ("analyze_project", "project-level analysis function"),
    ("ISR_RE", "ISR pattern regex"),
    ("ENTRY_RE", "entry point pattern regex"),
    ("RTOS_API", "RTOS API dictionary"),
    ("PERIPHERAL_RE", "peripheral regex"),
    ("CRITICAL_SECTION_ENTER", "critical section enter set"),
    ("CRITICAL_SECTION_EXIT", "critical section exit set"),
]

for name, desc in required_analyzer:
    if name in analyzer_code:
        ok(f"Analyzer: {name} ({desc})")
    else:
        fail(f"Analyzer missing: {name}")

# Check return schema
if "'nodes'" in analyzer_code and "'edges'" in analyzer_code and "'callers'" in analyzer_code:
    ok("Analyzer returns nodes/edges/callers")
else:
    fail("Analyzer return schema incomplete")

for field in ["'races'", "'rtos'", "'peripherals'", "'globals'", "'mod_edges'", "'mods'"]:
    if field in analyzer_code:
        ok(f"Analyzer returns {field}")
    else:
        fail(f"Analyzer missing return field: {field}")


# ══════════════════════════════════════════════════════════════
# 10. ANALYZER RUNTIME TEST (with mock C code)
# ══════════════════════════════════════════════════════════════
section("10. Analyzer runtime test")

try:
    sys.path.insert(0, str(BASE))
    from analyzer import TS_AVAILABLE, analyze_project
    
    if not TS_AVAILABLE:
        fail("tree-sitter not available — skipping runtime tests")
    else:
        ok("tree-sitter imported successfully")
        
        # Create mock C project
        tmp = Path(tempfile.mkdtemp())
        src_dir = tmp / "project"
        (src_dir / "main").mkdir(parents=True)
        (src_dir / "driver").mkdir(parents=True)
        
        # main.c — entry point with RTOS
        (src_dir / "main" / "main.c").write_text("""
#include <stdint.h>

volatile int g_sensor_data = 0;
int g_config = 42;

void driver_init(void);
void process_data(void);
void task_sensor(void *p);

int main(void) {
    driver_init();
    process_data();
    return 0;
}

void process_data(void) {
    int x = g_sensor_data;
    g_config = x + 1;
}
""")
        
        # driver.c — ISR + peripheral access
        (src_dir / "driver" / "driver.c").write_text("""
#include <stdint.h>

extern volatile int g_sensor_data;

typedef struct { volatile uint32_t ODR; volatile uint32_t IDR; } GPIO_TypeDef;
#define GPIOA ((GPIO_TypeDef*)0x40020000)

void driver_init(void) {
    GPIOA->ODR = 0;
}

void TIM2_IRQHandler(void) {
    g_sensor_data = GPIOA->IDR;
}

static void dead_function(void) {
    // never called
}

void recursive_a(void);
void recursive_b(void);

void recursive_a(void) {
    recursive_b();
}

void recursive_b(void) {
    recursive_a();
}
""")
        
        source_files = list(src_dir.rglob("*.c"))
        ok(f"Mock project: {len(source_files)} C files")
        
        messages = []
        graph = analyze_project(
            source_files,
            src_root=src_dir,
            push_fn=lambda m: messages.append(m)
        )
        
        if graph is None:
            fail("analyze_project returned None")
        else:
            ok(f"Analysis complete: {len(graph['nodes'])} nodes, {sum(len(v) for v in graph['edges'].values())} edges")
            
            # Validate schema
            for key in ['source', 'files', 'nodes', 'edges', 'callers', 'mod_edges', 'mods', 'globals', 'races', 'rtos', 'peripherals']:
                if key in graph:
                    ok(f"Graph schema: '{key}' present")
                else:
                    fail(f"Graph schema: '{key}' missing")
            
            # Check node fields
            if graph['nodes']:
                n0 = graph['nodes'][0]
                for field in ['id', 'file', 'mod', 'module', 'line', 'type', 'is_isr', 'is_entry',
                              'has_critical', 'delay_in_loop', 'out_degree', 'in_degree',
                              'reads', 'writes', 'rw', 'peripherals', 'rtos']:
                    if field in n0:
                        ok(f"Node field: '{field}'")
                    else:
                        fail(f"Node field missing: '{field}'")
            
            # Check specific detections
            node_ids = {n['id'] for n in graph['nodes']}
            
            if 'main' in node_ids:
                ok("Detected: main()")
            else:
                fail("main() not detected")
            
            if 'driver_init' in node_ids:
                ok("Detected: driver_init()")
            else:
                fail("driver_init() not detected")
            
            if 'TIM2_IRQHandler' in node_ids:
                ok("Detected: TIM2_IRQHandler()")
                isr_node = next((n for n in graph['nodes'] if n['id'] == 'TIM2_IRQHandler'), None)
                if isr_node and isr_node.get('is_isr'):
                    ok("TIM2_IRQHandler flagged as ISR")
                else:
                    fail("TIM2_IRQHandler NOT flagged as ISR")
            else:
                fail("TIM2_IRQHandler not detected")
            
            main_node = next((n for n in graph['nodes'] if n['id'] == 'main'), None)
            if main_node and main_node.get('is_entry'):
                ok("main() flagged as entry point")
            else:
                fail("main() not flagged as entry point")
            
            # Check call edges
            if 'main' in graph['edges'] and 'driver_init' in graph['edges']['main']:
                ok("Edge: main → driver_init")
            else:
                fail("Edge missing: main → driver_init")
            
            if 'main' in graph['edges'] and 'process_data' in graph['edges']['main']:
                ok("Edge: main → process_data")
            else:
                fail("Edge missing: main → process_data")
            
            # Check modules
            if len(graph['mods']) >= 2:
                ok(f"Multiple modules detected: {graph['mods']}")
            else:
                fail(f"Expected >=2 modules, got: {graph['mods']}")
            
            # Check globals
            if 'g_sensor_data' in graph.get('globals', {}):
                g = graph['globals']['g_sensor_data']
                if g.get('volatile'):
                    ok("g_sensor_data detected as volatile")
                else:
                    fail("g_sensor_data not marked volatile")
            else:
                fail("g_sensor_data not in globals")
            
            # Check race detection
            races = graph.get('races', [])
            race_vars = {r['var'] for r in races}
            if 'g_sensor_data' in race_vars:
                ok(f"Race detected on g_sensor_data ({len(races)} total races)")
            else:
                fail("Race on g_sensor_data not detected")
            
            # Check peripherals
            periph = graph.get('peripherals', {})
            if 'GPIOA' in periph:
                ok("Peripheral GPIOA detected")
            else:
                fail("Peripheral GPIOA not detected")
            
            # Check dead code candidate
            dead_node = next((n for n in graph['nodes'] if n['id'] == 'dead_function'), None)
            if dead_node and dead_node.get('in_degree', 0) == 0:
                ok("dead_function() has in_degree=0 (dead code candidate)")
            else:
                fail("dead_function() not properly detected as dead code")
            
            # Check mod_edges (cross-module calls)
            if graph.get('mod_edges'):
                ok(f"Cross-module edges: {len(graph['mod_edges'])} pairs")
            else:
                fail("No cross-module edges detected")
            
            # Check cycle: recursive_a ↔ recursive_b
            if 'recursive_a' in graph['edges'] and 'recursive_b' in graph['edges'].get('recursive_a', []):
                if 'recursive_a' in graph['edges'].get('recursive_b', []):
                    ok("Cycle detected: recursive_a ↔ recursive_b")
                else:
                    fail("recursive_b → recursive_a edge missing")
            else:
                fail("recursive_a → recursive_b edge missing")

        # Cleanup
        shutil.rmtree(tmp)

except ImportError as e:
    fail(f"Import error: {e}")
except Exception as e:
    fail(f"Runtime test error: {e}")
    import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════
# 11. FLASK SERVER TEST (test client)
# ══════════════════════════════════════════════════════════════
section("11. Flask server test")

try:
    sys.path.insert(0, str(BASE))
    # Import the Flask app
    os.chdir(str(BASE))
    
    # Need to import carefully to avoid running the server
    import importlib.util
    spec = importlib.util.spec_from_file_location("server", str(SERVER_PY))
    server_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server_mod)
    app = server_mod.app
    
    client = app.test_client()
    
    # Test: GET /
    r = client.get("/")
    if r.status_code == 200 and b"Callgraph Studio" in r.data:
        ok("GET / → 200 with Callgraph Studio")
    else:
        fail(f"GET / → {r.status_code}")
    
    # Test: GET /favicon.ico
    r = client.get("/favicon.ico")
    if r.status_code == 200:
        ok("GET /favicon.ico → 200")
    else:
        fail(f"GET /favicon.ico → {r.status_code}")
    
    # Test: GET /api/deps
    r = client.get("/api/deps")
    if r.status_code == 200:
        d = r.get_json()
        if '_pkg_manager' in d:
            ok(f"GET /api/deps → 200 (pkg_manager: {d['_pkg_manager']})")
        else:
            fail("GET /api/deps missing _pkg_manager")
    else:
        fail(f"GET /api/deps → {r.status_code}")
    
    # Test: GET /api/browse
    r = client.get("/api/browse?path=/tmp")
    if r.status_code == 200:
        d = r.get_json()
        if 'entries' in d:
            ok(f"GET /api/browse → 200 ({len(d['entries'])} entries)")
        else:
            fail("GET /api/browse missing 'entries'")
    else:
        fail(f"GET /api/browse → {r.status_code}")
    
    # Test: GET /api/runs
    r = client.get("/api/runs")
    if r.status_code == 200:
        ok("GET /api/runs → 200")
    else:
        fail(f"GET /api/runs → {r.status_code}")
    
    # Test: POST /api/index with invalid path
    r = client.post("/api/index",
                     json={"source_path": "/nonexistent/path"},
                     content_type="application/json")
    if r.status_code == 400:
        ok("POST /api/index (invalid path) → 400")
    else:
        fail(f"POST /api/index (invalid path) → {r.status_code}")
    
    # Test: POST /api/index with blocked path
    r = client.post("/api/index",
                     json={"source_path": "/etc"},
                     content_type="application/json")
    if r.status_code == 403:
        ok("POST /api/index (blocked /etc) → 403")
    else:
        fail(f"POST /api/index (blocked /etc) → {r.status_code}")
    
    # Test: GET /api/source without params
    r = client.get("/api/source")
    if r.status_code == 400:
        ok("GET /api/source (no params) → 400")
    else:
        fail(f"GET /api/source (no params) → {r.status_code}")
    
    # Test: GET /api/source with path traversal attempt
    r = client.get("/api/source?file=../../etc/passwd&root=/tmp")
    if r.status_code in (403, 404):
        ok(f"GET /api/source (path traversal) → {r.status_code} (blocked)")
    else:
        fail(f"GET /api/source (path traversal) → {r.status_code} (should be 403/404)")
    
    # Test: GET /api/source with valid file
    tmp_src = Path(tempfile.mkdtemp())
    (tmp_src / "test.c").write_text("int main(void) { return 0; }\n")
    r = client.get(f"/api/source?file=test.c&root={tmp_src}")
    if r.status_code == 200:
        d = r.get_json()
        if 'lines' in d and len(d['lines']) > 0:
            ok("GET /api/source (valid file) → 200 with lines")
        else:
            fail("GET /api/source returned empty")
    else:
        fail(f"GET /api/source (valid file) → {r.status_code}")
    shutil.rmtree(tmp_src)
    
    # Test: POST /api/index with real mock project
    tmp2 = Path(tempfile.mkdtemp())
    (tmp2 / "main.c").write_text("int main(void) { return 0; }\n")
    r = client.post("/api/index",
                     json={"source_path": str(tmp2)},
                     content_type="application/json")
    if r.status_code == 200:
        d = r.get_json()
        if 'stream_id' in d:
            ok(f"POST /api/index (valid project) → 200 (stream_id: {d['stream_id'][:8]}...)")
            
            # Poll stream for graph
            import time
            graph_found = False
            for _ in range(50):
                r2 = client.get(f"/api/stream/{d['stream_id']}")
                if r2.status_code == 200:
                    data = r2.data.decode('utf-8')
                    if '__GRAPH__:' in data:
                        graph_found = True
                        break
                time.sleep(0.2)
            
            if graph_found:
                ok("SSE stream delivered __GRAPH__")
            else:
                fail("SSE stream did not deliver __GRAPH__ within timeout")
        else:
            fail("POST /api/index missing stream_id")
    else:
        fail(f"POST /api/index (valid project) → {r.status_code}")
    shutil.rmtree(tmp2)

except Exception as e:
    fail(f"Flask test error: {e}")
    import traceback; traceback.print_exc()


# ══════════════════════════════════════════════════════════════
# 12. v2.2.0 FEATURE-SPECIFIC TESTS
# ══════════════════════════════════════════════════════════════
section("12. v2.2.0 feature checks")

# Stack depth: memoized DFS (not exponential)
if "const _memo = {}" in js_code and "function dfs(node)" in js_code:
    ok("Stack depth: uses memoized DFS")
else:
    fail("Stack depth: memoized DFS not found")

if "onStack.has(node)" in js_code:
    ok("Stack depth: cycle-breaking via onStack")
else:
    fail("Stack depth: no cycle-breaking logic")

# Auto-trace main
if "autoTarget" in js_code and "G.nodes.find(n=>n.id==='main')" in js_code:
    ok("Auto-trace: looks for main()")
else:
    fail("Auto-trace: main detection missing")

if "isEntryPoint(n)" in js_code or "G.nodes.find(n=>n.is_entry" in js_code:
    ok("Auto-trace: falls back to entry point check")
else:
    fail("Auto-trace: no entry point fallback")

if "G.nodes.length > 20" in js_code:
    ok("Auto-trace: gated on >20 nodes")
else:
    fail("Auto-trace: no size gate")

# Trace direction
if "traceDir !== 'down'" in js_code:
    ok("Trace direction: skips ancestors when 'down'")
else:
    fail("Trace direction: 'down' filter missing")

if "traceDir !== 'up'" in js_code:
    ok("Trace direction: skips descendants when 'up'")
else:
    fail("Trace direction: 'up' filter missing")

# Module colors
if "MOD_PALETTE" in js_code:
    ok("Module colors: palette defined")
else:
    fail("Module colors: no palette")

if "mod-legend" in html:
    ok("Module legend: HTML element present")
else:
    fail("Module legend: missing")

# Module label on nodes
if "modText" in js_code and "'y','34'" in js_code:
    ok("Module label: second line text at y=34")
else:
    fail("Module label: not found")

# Node height = 46
nh_count = js_code.count("NH=46")
if nh_count >= 3:
    ok(f"Node height: NH=46 in {nh_count} places")
else:
    fail(f"Node height: NH=46 in only {nh_count} places (need >=3)")

# Diff mode
if "function runDiff()" in js_code:
    ok("Diff mode: runDiff() defined")
else:
    fail("Diff mode: runDiff() missing")

if "cg_diff_snap" in js_code:
    ok("Diff mode: localStorage key for snapshot")
else:
    fail("Diff mode: no snapshot storage")

# Source panel
if "function openSource(" in js_code:
    ok("Source panel: openSource() defined")
else:
    fail("Source panel: openSource() missing")

if "/api/source" in js_code:
    ok("Source panel: fetches from /api/source")
else:
    fail("Source panel: no API call")

if "src-badge" in js_code:
    ok("Source panel: uses badge classes")
else:
    fail("Source panel: no badge rendering")

# Bookmarks
if "cg_bookmarks" in js_code:
    ok("Bookmarks: localStorage key")
else:
    fail("Bookmarks: no localStorage key")

if "function toggleBookmark(" in js_code:
    ok("Bookmarks: toggleBookmark() defined")
else:
    fail("Bookmarks: toggleBookmark() missing")

if "exportBookmarks" in js_code:
    ok("Bookmarks: export function")
else:
    fail("Bookmarks: no export")

# Session persistence includes traceDir
if "traceDir:traceDir" in js_code or "traceDir:traceDir||'both'" in js_code:
    ok("Session: saves traceDir")
else:
    fail("Session: traceDir not saved")

if "sess.traceDir" in js_code:
    ok("Session: restores traceDir")
else:
    fail("Session: traceDir not restored")

# String escaper
if "function esc(" in js_code:
    ok("String escaper: esc() defined")
else:
    fail("String escaper: esc() missing")

# Mutual exclusion: source panel closed by other panels
if "closeSource();\n  if(!G||!G.globals)" in js_code.replace(' ',''):
    ok("Panel mutex: openGlobals closes source")
elif "closeSource()" in js_code and js_code.count("closeSource()") >= 5:
    ok(f"Panel mutex: closeSource() called {js_code.count('closeSource()')} times")
else:
    fail("Panel mutex: source panel not closed by other panels")

# anaSetActive includes all buttons
if "'ana-diff-btn'" in js_code:
    ok("anaSetActive: includes ana-diff-btn")
else:
    fail("anaSetActive: missing ana-diff-btn")

if "'ana-cycle-btn'" in js_code and "'ana-stack-btn'" in js_code:
    ok("anaSetActive: includes cycle and stack buttons")
else:
    fail("anaSetActive: missing cycle/stack buttons")

# Module color alpha fix
if "fnModCol+'1a'" in js_code:
    ok("Module color: proper hex alpha (1a)")
elif "fnModCol+'12'" in js_code:
    fail("Module color: broken alpha (12 instead of 1a)")
else:
    fail("Module color: no alpha fill found")

# ── v2.2.0 features ─────────────────────────────────────────
section("12b. v2.2.0 features")

# RTOS ISR interaction diagram
if "function buildRtosInteractionDiagram(" in js_code:
    ok("RTOS: ISR interaction diagram function")
else:
    fail("RTOS: ISR interaction diagram missing")

if "FromISR" in js_code:
    ok("RTOS: detects FromISR API calls")
else:
    fail("RTOS: no FromISR detection")

# Coupling analysis
if "function runCoupling(" in js_code:
    ok("Coupling: runCoupling() defined")
else:
    fail("Coupling: runCoupling() missing")

if "'ana-coupling-btn'" in js_code:
    ok("Coupling: button in anaSetActive")
else:
    fail("Coupling: button missing from anaSetActive")

if "function highlightCoupledModules(" in js_code:
    ok("Coupling: highlight function defined")
else:
    fail("Coupling: highlight missing")

# Configurable entry points
if "function isEntryPoint(" in js_code:
    ok("Entry points: isEntryPoint() defined")
else:
    fail("Entry points: isEntryPoint() missing")

if "DEFAULT_ENTRY_PATTERNS" in js_code:
    ok("Entry points: default patterns defined")
else:
    fail("Entry points: no defaults")

if "cg_entry_patterns" in js_code:
    ok("Entry points: localStorage persistence")
else:
    fail("Entry points: no localStorage")

if "function toggleSettings(" in js_code:
    ok("Entry points: settings toggle")
else:
    fail("Entry points: no settings toggle")

# Force-directed layout
if "function forceLayout(" in js_code:
    ok("Force layout: forceLayout() defined")
else:
    fail("Force layout: missing")

if "function toggleForce(" in js_code:
    ok("Force layout: toggle function")
else:
    fail("Force layout: no toggle")

if "let useForce" in js_code:
    ok("Force layout: state variable")
else:
    fail("Force layout: no state")

if "useForce ? forceLayout" in js_code:
    ok("Force layout: integrated in renderFnGraph")
else:
    fail("Force layout: not integrated")


# ══════════════════════════════════════════════════════════════
# 13. EDGE CASES
# ══════════════════════════════════════════════════════════════
section("13. Edge cases")

# Check graph too large guard
if "visNodes.size>800" in js_code:
    ok("Guard: graph >800 nodes shows error")
else:
    fail("Guard: no large graph protection")

# Check empty graph handling
if "visNodes.size===0" in js_code:
    ok("Guard: empty graph handled")
else:
    fail("Guard: no empty graph check")

# Check server blocked paths
if "blocked = ['/etc'" in server_code or "'/etc'" in server_code:
    ok("Server: /etc blocked in /api/index")
else:
    fail("Server: system paths not blocked")

# Version check
if "v2.2.0" in html:
    ok("Version: v2.2.0 in index.html")
else:
    fail("Version: v2.2.0 not found in index.html")


# ══════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*56}")
print(f"  RESULTS:  {PASS} passed  /  {FAIL} failed")
print(f"{'='*56}")

if ERRORS:
    print(f"\n  Failures:")
    for e in ERRORS:
        print(f"    ✗ {e}")

print()
sys.exit(0 if FAIL == 0 else 1)
