<div align="center">

```
بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ
```

# ✦ Callgraph Studio

**Interactive C call graph explorer for embedded systems**

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS-lightgrey)
![Language](https://img.shields.io/badge/language-C-orange)

*Index once. Explore instantly.*

</div>

---

## What is it?

Callgraph Studio is a local web application that parses a C codebase and renders its call graph as an interactive SVG. Built for embedded firmware engineers who need to understand large codebases quickly — dead code, change impact, call paths, module coupling — without leaving the browser.

Tested on a real 69-file embedded firmware project (EVIC): **189 nodes, 298 edges, 8 modules** — renders in under 2 seconds.

---

## Features

### Graph exploration
- **Function view** — full call graph or depth-limited subgraph
- **Module view** — architectural overview with edge-count heatmap
- **Trace mode** — click any function to see its callers and callees
- **Expand view** — functions grouped inside module bubbles with cross-module wires
- **Matrix view** — coupling heatmap (modules × modules), click cell to filter

### Navigation
- **Back / Forward** history with breadcrumb trail (`Alt+←` / `Alt+→`)
- **Pan** (drag), **zoom** (scroll wheel, pinch, `+`/`-`), **fit** (`F`)
- **Minimap** — live thumbnail, click to jump anywhere
- **Search & highlight** — type to filter list and glow matching nodes

### Analysis tools
| Tool | What it does |
|------|-------------|
| ☠ **Dead code** | Finds functions with no project-level callers. Skips `main`, `ISR_*`, `irq_*`, `init_*` patterns. Export list as `.txt`. |
| ⚡ **Change impact** | Paste changed function names → BFS forward through all callers → shows affected count per module |
| 🌡 **Heatmap** | Scores every function by `out×2 + in + depth`. Overlay on graph: green=simple → red=complex |
| ⇢ **Path finder** | DFS finds all call paths between two functions (up to 20 paths, depth 12). Click any path to render it. |
| ⊕ **Intersection trace** | Enter two functions → renders only their shared callees |

### Export & persistence
- **SVG export** — vector, dark background, ready for docs
- **PNG export** — 2× retina resolution
- **Session save** — graph persists in `localStorage` for 24 hours; auto-restored on next visit

---

## Requirements

| Dependency | Purpose | Install |
|------------|---------|---------|
| `python3` + `flask` | Web server | `pip install flask` |
| `cflow` | Call graph extraction | `apt install cflow` |
| `ctags` (universal) | Function metadata | `apt install universal-ctags` |
| `graphviz` (`dot`) | Layout engine | `apt install graphviz` |
| `gawk` | Stream processing | `apt install gawk` |

---

## Quick start

```bash
# Clone
git clone https://github.com/youruser/callgraph-studio.git
cd callgraph-studio

# Start (installs Flask automatically if missing)
./start.sh

# Open browser
http://localhost:7411
```

Then enter your project path (e.g. `/home/you/firmware/src`) and click **Index Project**.

---

## Project structure

```
callgraph-studio/
├── index.html       # Single-file frontend (SVG renderer, all UI)
├── server.py        # Flask backend (indexing, SSE streaming, file browser)
├── start.sh         # Launch script (checks deps, starts server)
├── README.md        # This file
├── HELP.md          # FAQ, cheat sheet, how-to
└── runs/            # Temporary indexing workfiles (auto-cleaned)
```

---

## Architecture

```
Browser                          Server (Flask)
  │                                    │
  │  POST /api/index  ─────────────►  │  runs cflow + ctags
  │                                    │  parses output → JSON graph
  │  GET  /api/stream/{id}  ◄────────  │  SSE: progress lines
  │                                    │        __GRAPH__:{...}
  │                                    │
  │  localStorage ◄── session save     │
  │  SVG render    ◄── graph JSON      │
  │  Analysis      ◄── client-side     │
```

The backend does one thing: parse C source with `cflow` + `ctags`, build a graph JSON, and stream it back. All rendering, layout, analysis, and navigation runs entirely in the browser.

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `F` | Fit graph to window |
| `+` / `-` | Zoom in / out |
| `M` | Toggle Function ↔ Module view |
| `Escape` | Clear trace / close panel |
| `Alt + ←` | Navigate back in trace history |
| `Alt + →` | Navigate forward in trace history |
| `↑` / `↓` | Navigate autocomplete in trace input |
| `Enter` | Confirm trace autocomplete selection |

---

## Configuration

The server reads these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `7411` | HTTP port |
| `ALLOWED_PATHS` | (none) | Comma-separated path prefixes allowed for indexing. Leave unset to allow all. |

```bash
PORT=8080 ALLOWED_PATHS=/home/user/projects ./start.sh
```

---

## License

MIT — do whatever you want, attribution appreciated.

---

<div align="center">
<sub>Built for embedded systems engineers who read code for a living.</sub>
</div>
