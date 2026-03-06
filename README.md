<div align="center">

<br>

```
بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ
```

<br>

# ✦ Callgraph Studio

**Interactive C call graph explorer for embedded firmware engineers**

*Index once. Trace anything. Understand everything.*

![version](https://img.shields.io/badge/version-1.0.0-c9a84c?style=flat-square&labelColor=1a1508)
![python](https://img.shields.io/badge/python-3.8+-4a7fa5?style=flat-square&labelColor=1a1508)
![parser](https://img.shields.io/badge/parser-tree--sitter-2a6b6b?style=flat-square&labelColor=1a1508)
![tests](https://img.shields.io/badge/tests-64%20passing-22c55e?style=flat-square&labelColor=1a1508)
![license](https://img.shields.io/badge/license-MIT-8b6914?style=flat-square&labelColor=1a1508)

</div>

---

## What is it?

A **local** web application that parses a C codebase with tree-sitter and renders its full call graph as an interactive SVG. No cloud. No telemetry. No system dependencies beyond Python and a browser.

Built for embedded firmware engineers who need to understand large codebases fast: dead code, race conditions, RTOS architecture, peripheral register ownership, change blast radius — all visible in one tool, indexed in under three seconds.

---

## Performance on real projects

| Project | Files | Functions | Edges | Globals | ISRs | RTOS tasks | Index time |
|---------|------:|----------:|------:|--------:|-----:|-----------:|-----------:|
| EVIC (embedded firmware) | 69 | 552 | 754 | 195 | 18 | 0 | **0.3 s** |
| HMI (RTOS + SDK) | 206 | 570 | 828 | 113 | 3 | 7 | **2.4 s** |

---

## Features

### Graph views

| View | Key | Description |
|------|-----|-------------|
| **ƒ Function** | sidebar | Full call graph — depth slider, trace mode, search/filter |
| **⬡ Module** | `M` | Directory-level architecture — circle layout, edge weight = coupling |
| **⊞ Expand** | mod options | Functions grouped inside module bubbles with cross-module wires |
| **▦ Matrix** | mod options | Module × module coupling heatmap — click cell to filter edges |

### Navigation & interaction

- **Trace** — click any node or type in the Trace box (autocomplete, 1 character) → callers left, function centre, callees right
- **History** — Back `◀` / Forward `▶` with breadcrumb trail (`Alt+←` / `Alt+→`)
- **Filter** — function list search box filters the sidebar list and highlights matching nodes
- **Intersection trace** — enter Function A + Function B → renders shared callees only
- **Pan** (drag) · **Zoom** (scroll / pinch / `+` / `−`) · **Fit** (`F`)
- **Minimap** — live thumbnail, click to jump
- **Depth slider** — limit visible hops from root functions (0 = all, 1–10 = fixed depth)
- **Ext toggle** — show / hide external library nodes
- **H/V layout** — toggle horizontal / vertical Sugiyama layout `⇆`
- **Session restore** — 24 h localStorage cache, auto-restored on page reload

### Analysis tools

| Tool | Description |
|------|-------------|
| **☠ Dead code** | Zero-project-in-degree functions. Excludes `main`, `ISR_*`, `irq_*`, `*_irq`, `*_isr`, `init_*`, `startup`. Export `.txt`. |
| **⚡ Impact** | Paste changed functions → reverse BFS through all callers → affected count by module. Graph overlay: red = changed, orange = affected. |
| **🌡 Heatmap** | Score = `(out×2) + in + depth`. Green < 33% < Yellow < 66% < Red. Top 10 listed with scores. |
| **⇢ Path find** | DFS all call paths between two functions. Max 20 paths, depth 12. Click any path → renders as numbered step graph. |
| **⊕ Intersect** | Shared callees of two functions via descendant BFS + set intersection. |

### Embedded analysis panels

| Panel | Button colour | What it shows |
|-------|--------------|---------------|
| **Globals** | Green | All file-scope variables: volatile flag, per-function reads / writes / RW counts. Click var → highlights writers red, readers green in graph. |
| **Races** | Red | ISR writers × non-ISR accessors of shared globals. Ranked HIGH / MEDIUM / LOW by severity + critical section detection. Click candidate → ISR red, task orange. |
| **RTOS** | Purple | FreeRTOS + CMSIS-RTOS v2 task/queue/mutex/semaphore graph. 44 APIs. Shared objects listed with all users. |
| **Periph** | Gold | Hardware register access map (`GPIOA->ODR`, `TIM2->ARR`). Write / read / RW per function. Click peripheral → highlights all touching functions. |

> Panels are hidden automatically when no data is available for that category.

### Node decorations

| Decoration | Meaning |
|------------|---------|
| Red `ISR` label (top-left) | Function classified as an interrupt handler |
| Amber dot (bottom-left) | `delay()` or `vTaskDelay()` found inside a loop |
| Number badge (top-right) | In-degree — how many functions call this one |

### Export

- **SVG** — full vector, crisp at any size
- **PNG** — 2× retina via canvas

---

## Requirements

| Dependency | Purpose |
|------------|---------|
| Python 3.8+ | Runtime |
| `flask` | HTTP server + SSE streaming |
| `tree-sitter` | AST parser engine |
| `tree-sitter-c` | C grammar |
| `ctags` | Optional — additional symbol metadata |

---

## Quick start

```bash
git clone https://github.com/youruser/callgraph-studio
cd callgraph-studio
chmod +x start.sh
./start.sh            # interactive menu: checks deps, pick port, launch
# → open http://localhost:7411
```

Type or paste your project path, click **◈ Index Project**, watch it stream.

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `F` | Fit graph to window |
| `+` / `−` | Zoom in / out |
| `M` | Toggle Function ↔ Module view |
| `Escape` | Clear trace / close info panel |
| `Alt + ←` | Back in trace history |
| `Alt + →` | Forward in trace history |
| `↑ / ↓` | Navigate autocomplete |
| `Enter` | Confirm autocomplete |

---

## Architecture

```
Browser  ←──────────────────────────────────────────►  Flask (server.py)
│                                                       │
│  index.html — 3 020 lines, zero external libs        │
│  ├─ SVG renderer (pure SVG, no canvas, no D3)        │  POST /api/index
│  ├─ Sugiyama-style layout engine (LR / TB)           │  ├─ analyzer.py
│  ├─ Pan / zoom / minimap                             │  │   Pass 1  globals scan
│  ├─ Trace · history · breadcrumbs                    │  │   Pass 2  function bodies
│  ├─ Dead / Impact / Heatmap / Path / Intersect       │  │   Pass 3  call graph
│  └─ Globals · Races · RTOS · Periph panels           │  │   Pass 4  global var deps
│                                                       │  │   Pass 5  race detection
│  ◄── SSE stream: progress + __GRAPH__:{json}         │  │   Pass 6  RTOS graph
│  localStorage ◄── 24h session cache                  │  │   Pass 7  peripheral map
```

---

## Files

```
callgraph-studio/
├── index.html      3 020 lines  — complete single-file frontend
├── server.py         480 lines  — Flask backend, SSE streaming
├── analyzer.py       648 lines  — tree-sitter 7-pass analyzer
├── start.sh          321 lines  — interactive launcher menu
├── README.md                    — this file
└── HELP.html                    — full guide, FAQ, cheat sheet
```

---

## License

MIT — use freely, attribution appreciated.

---

<div align="center">

<br>

```
وَقُل رَّبِّ زِدْنِى عِلْمًا
"My Lord, increase me in knowledge." — Quran 20:114
```

</div>
