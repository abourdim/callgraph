#!/usr/bin/env python3
"""
Callgraph Studio v1.3.0 — Smoke Test

Real end-to-end: starts the server, creates a mock C project,
indexes it via HTTP, validates the full graph, tests source API,
then shuts down. Proves the whole pipeline works.

Run:  python3 smoke_test.py
"""

import sys, os, json, time, tempfile, shutil, subprocess, urllib.request
from pathlib import Path

BASE = Path(__file__).parent
PORT = 7499

R, G, Y, B, N = "\033[31m", "\033[32m", "\033[33m", "\033[1m", "\033[0m"
PASS = FAIL = 0
ERRORS = []
proc = None
tmp_dir = None

def ok(msg):
    global PASS; PASS += 1; print(f"  {G}✓{N} {msg}")

def fail(msg, detail=""):
    global FAIL; FAIL += 1; ERRORS.append(msg)
    print(f"  {R}✗{N} {msg}")
    if detail: print(f"    {detail[:300]}")

def cleanup():
    if proc:
        try: proc.terminate(); proc.wait(3)
        except: proc.kill()
    if tmp_dir and Path(tmp_dir).exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)

def http_get(path, timeout=5):
    return urllib.request.urlopen(f"http://localhost:{PORT}{path}", timeout=timeout)

def http_post(path, data, timeout=10):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"http://localhost:{PORT}{path}", data=body,
        headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)

# ══════════════════════════════════════════════════════════════
print(f"\n{B}══ Callgraph Studio v1.3.0 — Smoke Test ══{N}\n")

# ── 1. Create mock C project ─────────────────────────────────
print(f"{B}1. Create mock project{N}")
tmp_dir = tempfile.mkdtemp(prefix="cg_smoke_")
src = Path(tmp_dir) / "project"
for d in ["app", "driver", "rtos"]:
    (src / d).mkdir(parents=True)

(src / "app" / "main.c").write_text("""
volatile int g_temperature = 0;
volatile int g_pressure = 0;
int g_config = 0;

void driver_init(void);
void sensor_read(void);
void comm_send(int val);

int main(void) {
    driver_init();
    g_config = 42;
    sensor_read();
    comm_send(g_temperature + g_pressure);
    return 0;
}
""")

(src / "driver" / "sensor.c").write_text("""
extern volatile int g_temperature;
extern volatile int g_pressure;

typedef struct { volatile unsigned DR; volatile unsigned CR; } ADC_TypeDef;
typedef struct { volatile unsigned ODR; } GPIO_TypeDef;
#define ADC1 ((ADC_TypeDef*)0x40012000)
#define GPIOB ((GPIO_TypeDef*)0x40020400)

void sensor_read(void) {
    ADC1->CR = 1;
    g_temperature = ADC1->DR;
    GPIOB->ODR = 1;
}

void ADC1_IRQHandler(void) {
    g_temperature = ADC1->DR;
    g_pressure = 100;
}

void driver_init(void) {
    ADC1->CR = 0;
    GPIOB->ODR = 0;
}

static void dead_helper(void) {
    int x = 0;
}
""")

(src / "driver" / "comm.c").write_text("""
typedef struct { volatile unsigned DR; volatile unsigned SR; } USART_TypeDef;
#define USART1 ((USART_TypeDef*)0x40011000)

void comm_send(int val) {
    USART1->DR = val;
}

void USART1_IRQHandler(void) {
    volatile int rx = USART1->DR;
}
""")

ok(f"Mock project: {len(list(src.rglob('*.c')))} files, 3 modules")

# ── 2. Start server ──────────────────────────────────────────
print(f"\n{B}2. Start server{N}")
env = os.environ.copy()
env["PORT"] = str(PORT)
proc = subprocess.Popen(
    [sys.executable, str(BASE / "server.py")],
    cwd=str(BASE), env=env,
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

ready = False
for _ in range(40):
    try:
        r = http_get("/api/deps")
        if r.status == 200: ready = True; break
    except: pass
    time.sleep(0.25)

if ready:
    ok(f"Server listening on :{PORT}")
else:
    fail("Server did not start in 10s")
    cleanup(); sys.exit(1)

# ── 3. Basic endpoints ───────────────────────────────────────
print(f"\n{B}3. Basic endpoints{N}")

try:
    body = http_get("/").read().decode()
    assert "Callgraph Studio" in body and "v1.3.0" in body
    ok("GET / → Callgraph Studio v1.3.0")
except Exception as e:
    fail(f"GET /: {e}")

try:
    d = json.loads(http_get("/api/deps").read())
    assert "_pkg_manager" in d
    ok(f"GET /api/deps → pkg_manager={d['_pkg_manager']}")
except Exception as e:
    fail(f"GET /api/deps: {e}")

try:
    d = json.loads(http_get(f"/api/browse?path={src}").read())
    assert len(d["entries"]) >= 3
    ok(f"GET /api/browse → {len(d['entries'])} entries")
except Exception as e:
    fail(f"GET /api/browse: {e}")

try:
    d = json.loads(http_get("/api/runs").read())
    ok(f"GET /api/runs → {len(d)} runs")
except Exception as e:
    fail(f"GET /api/runs: {e}")

# ── 4. Index the project (full pipeline) ─────────────────────
print(f"\n{B}4. Index pipeline{N}")

t0 = time.time()
try:
    d = json.loads(http_post("/api/index", {"source_path": str(src)}).read())
    stream_id = d["stream_id"]
    ok(f"POST /api/index → stream_id={stream_id[:12]}…")
except Exception as e:
    fail(f"POST /api/index: {e}")
    cleanup(); sys.exit(1)

# Poll SSE stream
graph = None
log_lines = []
for attempt in range(60):
    try:
        raw = http_get(f"/api/stream/{stream_id}", timeout=15).read().decode()
        for line in raw.split("\n"):
            if not line.startswith("data: "): continue
            payload = json.loads(line[6:])
            if not isinstance(payload, str): continue
            if payload.startswith("__GRAPH__:"):
                graph = json.loads(payload[10:])
            elif payload == "__DONE__":
                break
            else:
                log_lines.append(payload)
        if graph: break
    except: pass
    time.sleep(0.3)

elapsed = time.time() - t0

if not graph or "error" in graph:
    fail(f"Index failed: {graph}")
    for l in log_lines[-5:]: print(f"    {l}")
    cleanup(); sys.exit(1)

n_nodes = len(graph["nodes"])
n_edges = sum(len(v) for v in graph["edges"].values())
ok(f"Graph: {n_nodes} nodes, {n_edges} edges in {elapsed:.1f}s")

# ── 5. Validate graph contents ────────────────────────────────
print(f"\n{B}5. Graph validation{N}")

nodes = {n["id"]: n for n in graph["nodes"]}

# Functions exist
for fn in ["main", "driver_init", "sensor_read", "comm_send", "ADC1_IRQHandler", "USART1_IRQHandler", "dead_helper"]:
    if fn in nodes: ok(f"Found: {fn}()")
    else: fail(f"Missing: {fn}()")

# ISR flags
for isr in ["ADC1_IRQHandler", "USART1_IRQHandler"]:
    if nodes.get(isr, {}).get("is_isr"): ok(f"{isr} → is_isr=true")
    else: fail(f"{isr} not flagged as ISR")

# Entry point
if nodes.get("main", {}).get("is_entry"): ok("main → is_entry=true")
else: fail("main not flagged as entry")

# Modules (should have app + driver at minimum)
mods = set(graph["mods"])
if "app" in mods and "driver" in mods:
    ok(f"Modules: {sorted(mods)}")
else:
    fail(f"Expected app+driver modules, got: {mods}")

# Node has module label fields
sample = graph["nodes"][0]
if "mod" in sample and "module" in sample:
    ok("Nodes have mod + module fields")
else:
    fail("Nodes missing mod/module fields")

# Edges
for caller, callee in [("main","driver_init"), ("main","sensor_read"), ("main","comm_send")]:
    if callee in graph["edges"].get(caller, []): ok(f"Edge: {caller}→{callee}")
    else: fail(f"Edge missing: {caller}→{callee}")

# Reverse callers
for callee, caller in [("driver_init","main"), ("sensor_read","main")]:
    if caller in graph["callers"].get(callee, []): ok(f"Caller: {callee}←{caller}")
    else: fail(f"Caller missing: {callee}←{caller}")

# Cross-module edges
me = graph.get("mod_edges", {})
if me: ok(f"Cross-module edges: {len(me)} pairs")
else: fail("No cross-module edges")

# Globals
gl = graph.get("globals", {})
if gl.get("g_temperature", {}).get("volatile"): ok("g_temperature: volatile=true")
else: fail("g_temperature not volatile")

if "g_config" in gl: ok("g_config in globals")
else: fail("g_config missing from globals")

# Race detection (ISR writes g_temperature, non-ISR reads it)
race_vars = {r["var"] for r in graph.get("races", [])}
if "g_temperature" in race_vars: ok(f"Race: g_temperature (total: {len(graph['races'])})")
else: fail("Race on g_temperature not detected")

# Peripherals
periph = graph.get("peripherals", {})
for p in ["ADC1", "GPIOB", "USART1"]:
    if p in periph: ok(f"Peripheral: {p}")
    else: fail(f"Peripheral missing: {p}")

# Dead code candidate
dh = nodes.get("dead_helper", {})
if dh.get("in_degree", -1) == 0: ok("dead_helper: in_degree=0 (dead code)")
else: fail(f"dead_helper in_degree={dh.get('in_degree','?')}")

# ── 6. Source file API ────────────────────────────────────────
print(f"\n{B}6. Source API{N}")

try:
    d = json.loads(http_get(f"/api/source?file=app/main.c&root={src}").read())
    lines = d["lines"]
    assert len(lines) > 5
    has_main = any("main" in l for l in lines)
    ok(f"GET /api/source → {len(lines)} lines, has_main={has_main}")
except Exception as e:
    fail(f"Source API: {e}")

# Path traversal blocked
try:
    r = http_get(f"/api/source?file=../../etc/passwd&root={src}")
    fail(f"Path traversal NOT blocked (status {r.status})")
except urllib.request.HTTPError as e:
    if e.code in (403, 404): ok(f"Path traversal blocked → {e.code}")
    else: fail(f"Path traversal: unexpected {e.code}")
except Exception as e:
    fail(f"Path traversal test error: {e}")

# Missing file
try:
    r = http_get(f"/api/source?file=nonexistent.c&root={src}")
    fail("Missing file not caught")
except urllib.request.HTTPError as e:
    if e.code == 404: ok(f"Missing file → 404")
    else: fail(f"Missing file: {e.code}")

# ── 7. Security checks ───────────────────────────────────────
print(f"\n{B}7. Security{N}")

try:
    http_post("/api/index", {"source_path": "/etc"})
    fail("/etc not blocked!")
except urllib.request.HTTPError as e:
    if e.code == 403: ok(f"POST /api/index /etc → 403 blocked")
    else: fail(f"/etc returned {e.code}")

try:
    http_post("/api/index", {"source_path": "/nonexistent"})
    fail("Invalid path not rejected!")
except urllib.request.HTTPError as e:
    if e.code == 400: ok(f"Invalid path → 400")
    else: fail(f"Invalid path → {e.code}")

# ── 8. Shutdown ───────────────────────────────────────────────
print(f"\n{B}8. Cleanup{N}")
cleanup()
ok("Server terminated, temp files cleaned")

# ── Summary ───────────────────────────────────────────────────
print(f"\n{'='*52}")
total = PASS + FAIL
print(f"  {B}SMOKE TEST:{N}  {G}{PASS}{N}/{total} passed", end="")
if FAIL: print(f"  {R}{FAIL} FAILED{N}")
else: print(f"  {G}ALL GREEN{N}")
print(f"{'='*52}")

if ERRORS:
    print(f"\n  Failures:")
    for e in ERRORS: print(f"    {R}✗{N} {e}")

print()
sys.exit(0 if FAIL == 0 else 1)
