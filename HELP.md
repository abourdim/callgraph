# ✦ Callgraph Studio — Help

> **FAQ · Cheat Sheet · How-To Guide**  
> Version 1.0.0

---

## Table of contents

1. [Quick cheat sheet](#quick-cheat-sheet)
2. [Getting started](#getting-started)
3. [FAQ](#faq)
4. [How-to guides](#how-to-guides)
5. [Understanding the graph](#understanding-the-graph)
6. [Analysis tools](#analysis-tools)
7. [Troubleshooting](#troubleshooting)

---

## Quick cheat sheet

### Keyboard shortcuts
```
F           Fit graph to window
+ / -       Zoom in / out
M           Toggle Function ↔ Module view
Escape      Clear trace, close panels
Alt + ←     Back in trace history
Alt + →     Forward in trace history
↑ / ↓       Navigate autocomplete
Enter       Confirm autocomplete
```

### Mouse
```
Drag          Pan the graph
Scroll        Zoom in/out
Pinch         Zoom (trackpad / touchscreen)
Click node    Trace that function
Click minimap Jump to that area
```

### Graph bar buttons
```
◀ ▶     History back / forward
Fit     Fit graph to screen
⇆       Toggle Horizontal / Vertical layout
+ −     Zoom buttons
Ext     Show/hide external (library) functions
SVG     Export current view as SVG
PNG     Export current view as PNG (2× retina)
✕ Trace Clear trace, return to full graph
```

---

## Getting started

### Step 1 — Start the server
```bash
./start.sh
# Then open: http://localhost:7411
```

### Step 2 — Index your project
1. Type or paste the **absolute path** to your C source directory
2. Click **Browse** to use the file browser
3. Click **◈ Index Project**
4. Wait for the progress bar — large projects take 5–30 seconds

### Step 3 — Explore
- The **function list** on the left shows all functions ranked by call count
- Click any function in the list to **trace** it
- Or type in the **Trace function** box with autocomplete
- Click any **node** in the graph to trace it
- Use **◀ ▶** to navigate your history

### Step 4 — Switch views
- **ƒ Function** — individual function call graph
- **⬡ Module** — directory-level architecture
  - **⊞ Expand** — see functions inside module bubbles
  - **▦ Matrix** — coupling heatmap grid

---

## FAQ

**Q: What C projects does this work with?**  
Any C project that can be compiled with GCC. Works best with embedded firmware, RTOS code, drivers, and libraries. Does not support C++ (`.cpp` files are ignored).

**Q: How long does indexing take?**  
About 1 second per 10 source files. A 70-file project indexes in ~5 seconds. Results are cached in the browser for 24 hours — re-opening the page restores your last session instantly.

**Q: My graph has 500+ nodes and is slow to render.**  
Use **Depth** slider to limit the graph. Set it to 2–4 to show only the most connected parts. Or use **Trace** mode on a specific function — trace mode shows only the subgraph around one function, which stays fast regardless of project size.

**Q: Some functions are missing.**  
`cflow` follows call chains through your source. Functions that are only referenced through function pointers, macros, or inline assembly may not appear. External library functions appear as gray "external" nodes — hide them with the **Ext** button.

**Q: The layout looks wrong / nodes overlap.**  
Click **Fit** to re-fit. Try toggling **⇆ H/V** — some graphs read better vertically. For trace mode, the traced function is always the center-left column, callers to the left, callees to the right.

**Q: Can I save my graph?**  
Yes — two ways:
- **SVG / PNG** export buttons save the current view as an image
- The session is automatically saved to browser `localStorage` and restored on next visit (expires after 24 hours)
- Click **✕ Session** in the topbar to clear the saved session

**Q: What does "Re-index" vs "+ New" do?**  
- **⟳ Re-index** — re-parses the same source directory (useful after code changes)
- **＋ New** — clears everything and lets you index a different project

**Q: The server won't start.**  
Check that Flask is installed: `python3 -c "import flask"`. If missing: `pip install flask`. Also check that port 7411 is free: `lsof -i :7411`.

**Q: Can I run this on a remote server and access it in my browser?**  
Yes. Run `./start.sh` on the server, then SSH tunnel: `ssh -L 7411:localhost:7411 user@server`. Open `http://localhost:7411` locally.

**Q: Is my source code sent anywhere?**  
No. Everything runs locally. The server runs on your machine, the browser connects to `localhost`. No analytics, no telemetry, no external requests.

---

## How-to guides

### How to find dead code

1. Open **Function** mode
2. In the **Analysis** section, click **☠ Dead code**
3. The panel shows unreachable functions with their files
4. Click **Show in graph** to highlight them red in the full graph
5. Click **Export list** to save a `.txt` file for review

> **Note:** Entry points are automatically excluded: `main`, functions matching `ISR_*`, `irq_*`, `interrupt_*`, `handler_*`, `init_*`, `_init`, `startup`.

### How to analyse change impact

1. In the **Analysis** section, click **⚡ Impact**
2. Enter the names of functions you changed (one per line or comma-separated)
3. Click **⚡ Analyse impact**
4. The panel shows how many functions are affected per module
5. Click **Show in graph** — red = your changed functions, orange = affected callers

### How to trace a call path

1. In the **Analysis** section, click **⇢ Path find**
2. Enter the **From** function (e.g. `main`)
3. Enter the **To** function (e.g. `memset`)
4. Click **⇢ Find paths**
5. Results appear ranked shortest-first — click any path to render it as a step-numbered graph
6. Click any node in the path graph to trace it further

### How to find the most complex functions

1. In the **Analysis** section, click **🌡 Heatmap**
2. The top 10 riskiest functions are listed (score = `out_degree×2 + in_degree + call_depth`)
3. Click **Apply to graph** to recolor all nodes: green = simple, yellow = medium, red = complex
4. Click any function name to trace it
5. Click **Clear** to restore normal colors

### How to compare two call trees

1. In the **Intersection trace** section, enter **Function A** and **Function B**
2. Click **⊕ Intersect**
3. The graph shows only functions shared by both call trees
   - Blue = Function A root
   - Purple = Function B root  
   - Green = shared callees
4. Click any shared node to trace it

### How to understand module architecture

1. Click **⬡ Module** in the sidebar
2. The circle diagram shows modules (directories) as nodes, edge thickness = call count
3. Click any module node → jumps to Function view filtered to that module
4. Click **⊞ Expand** to see all functions inside each module bubble
5. Click **▦ Matrix** to see the coupling heatmap (rows = callers, columns = callees)
6. In Matrix view: hover a cell to see exact call count, click to filter to those two modules

### How to export for documentation

1. Navigate to the view you want (trace a function, apply heatmap, etc.)
2. Click **SVG** for a vector file — scales perfectly in Word, Notion, Confluence
3. Click **PNG** for a raster file — 2× resolution, dark background included
4. Files are named `{function_name}_{timestamp}.svg/png`

### How to restrict which paths the server can index

Set `ALLOWED_PATHS` before starting:
```bash
ALLOWED_PATHS=/home/user/projects,/opt/firmware ./start.sh
```
Any path outside these prefixes will be rejected with an error.

---

## Understanding the graph

### Node colors (default style)

| Color | Meaning |
|-------|---------|
| Blue border | Project function (defined in your source) |
| Dark gray border | External function (from library or system) |
| Gold border | Macro-defined function |
| White border | Currently focused / traced function |
| Red border | Caller of the traced function |
| Green border | Callee of the traced function |

### Edge colors (in trace mode)

| Color | Meaning |
|-------|---------|
| Red → | Calls going **out** from the traced function |
| Green → | Calls coming **in** to the traced function |
| Dark blue → | Other edges in the graph |

### The number badge (top-right of node)
Shows **in-degree** — how many other functions call this one. Higher = more central to the codebase.

### Depth slider
Controls how many call levels to show in the full graph:
- `∞` (0) — show all reachable functions
- `1` — show only root functions and their direct children
- `2–4` — good for large projects

### Module view edge thickness
Proportional to `log(call_count)`. Thick edges = tight coupling between modules.

---

## Analysis tools reference

### ☠ Dead code
- **Algorithm:** finds all project functions where no project-level function calls them
- **Exclusions:** `main`, `ISR_*`, `irq_*`, `interrupt_*`, `handler_*`, `init_*`, `_init`, `startup` (case-insensitive)
- **Limitation:** functions only called via function pointers won't be detected as live
- **Output:** count, percentage, scrollable list, graph overlay, `.txt` export

### ⚡ Change impact  
- **Algorithm:** reverse BFS — starts from changed functions and walks up through all callers
- **Input:** function names, one per line or comma-separated
- **Output:** total affected count, breakdown by module, graph overlay

### 🌡 Heatmap
- **Score formula:** `(out_degree × 2) + in_degree + call_depth`
  - `out_degree` weighted 2× because fan-out drives complexity more than fan-in
  - `call_depth` from any root via BFS
- **Visualization:** green (#22c55e) at score=0, yellow (#f59e0b) at 50%, red (#ef4444) at 100%

### ⇢ Path finder
- **Algorithm:** DFS with backtracking
- **Limits:** max 20 paths returned, max depth 12 hops
- **Output:** paths sorted by length (shortest first), rendered as step-numbered graph
- **Tip:** if no path found, the functions may be in separate call trees (try swapping From/To)

### ⊕ Intersection trace
- **Algorithm:** computes full descendant sets for both functions via BFS, then intersects
- **Output:** renders only the shared subgraph with color-coded roots

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "No functions found" after indexing | `cflow` found no C files | Check the path is correct and contains `.c` files |
| Graph shows 0 edges | `cflow` version too old | `apt install cflow` (need v1.6+) |
| PNG export shows black image | Browser canvas taint | Use SVG export instead; PNG works in Chrome/Firefox but not all browsers |
| Session not restored on reload | localStorage disabled | Enable cookies/storage in browser settings |
| Server: "Address already in use" | Port 7411 taken | `kill $(lsof -t -i:7411)` then restart |
| Nodes cut off on left | Happens with many callers in trace mode | Click **Fit** — layout auto-centers |
| "cflow: command not found" | Dependency missing | Run `sudo apt install cflow` |
| Graph freezes at 500+ nodes | Too many nodes to render | Use Depth slider (set to 2–3) or use Trace mode |

---

<div align="center">
<sub>✦ Callgraph Studio v1.0.0 · Built for C · Runs locally · No telemetry</sub>
</div>
