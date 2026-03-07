# Callgraph Studio

Interactive call graph analyzer for C codebases. Designed for embedded systems handover — understand a new codebase fast.

## What it does

Point it at a C project directory → get an interactive call graph with:

- **8-pass tree-sitter analysis**: functions, calls, globals, ISRs, RTOS tasks, peripherals, races, modules
- **Interactive SVG graph**: trace from any function, pan/zoom, click for details, force-directed layout
- **4 generated reports** from one index:

| Button | Output | What you get |
|--------|--------|-------------|
| 📋 Report | HTML | 16-engine deep analysis: architecture narrative, requirements, risk scores, race analysis, boot tree, data flow diagrams |
| 📑 Docs | HTML or ZIP | Per-module/function documentation with mini call graphs |
| 📊 Data | HTML | Global/peripheral/RTOS data dependencies with flow diagrams |
| Export | CSV/GraphML/DOT | For yEd, Graphviz, spreadsheets |

## Quick start

```bash
git clone <repo> && cd callgraph
./start.sh
```

The launcher checks dependencies, installs if needed, and opens your browser.

**Requirements**: Python 3.8+, pip. The launcher installs Flask + tree-sitter automatically.

## Manual install

```bash
pip install flask tree-sitter tree-sitter-c
python3 server.py
# Open http://localhost:7411
```

## Usage

1. Enter your C project path in the source field
2. Click **Index** — tree-sitter parses all `.c` files
3. Explore the graph: click functions, trace call chains, run analysis
4. Generate reports: 📋 Report, 📑 Docs, 📊 Data

## Analysis tools

- **☠ Dead code** — functions with no callers
- **⚡ Impact** — blast radius if a function changes
- **🌡 Heatmap** — color nodes by fan-in/fan-out
- **⇢ Path find** — all paths between two functions (Web Worker, non-blocking)
- **↻ Cycles** — Tarjan's SCC detection
- **⬆ Stack depth** — memoized DFS from entry points
- **⚖ Diff** — save baseline, re-index, see what changed
- **🔗 Coupling** — inter-module coupling scores
- **⚡ Force layout** — spring simulation for tangled graphs

## Features

- **Source view** with C syntax highlighting (keywords, types, strings, comments, preprocessor)
- **Bookmarks** — save interesting functions, export as JSON
- **Trace direction** — follow calls down, up, or both
- **Module colors** — 18-color palette, legend, per-module subgraphs
- **Configurable entry points** — regex patterns for dead code / stack depth
- **Live file watcher** — auto-detect source changes, prompt re-index
- **4 themes** — Dark, Light, High-Contrast, Alhambra Gold
- **Export** — SVG, PNG, CSV, GraphML (yEd), DOT (Graphviz)
- **Keyboard shortcuts** — `?` for overlay

## Report engine (16 analyses)

The 📋 Report generates a self-contained HTML with:

1. Architecture narrative (auto-generated prose per module)
2. Exhaustive requirements (per-peripheral, per-ISR, per-race, per-global)
3. Function deep analysis (risk, complexity, impact per function)
4. Data flow narratives (ISR→global→task pipelines)
5. Block interaction map (every module pair's cross-calls)
6. Peripheral register map (every register, ISR vs task context)
7. Race condition analysis (all readers/writers, fix recommendations)
8. Risk scoring (per-module + per-function)
9. Reading order (topological + rationale)
10. Pattern detection (producer-consumer, polling, hub, accessor pairs)
11. Bus factor (single points of failure)
12. Change difficulty (per-module)
13. Dead code investigation (removal recommendations)
14. Handover questions (50-100 specific questions)
15. Glossary (every entity)
16. Recommended tools (context-aware)

Interactive diagrams: layer diagram, coupling matrix, data flow, boot call tree, ISR map, module subgraphs, dependency DAGs.

## Architecture

```
index.html        — UI + SVG renderer (5,000 lines)
server.py         — Flask backend, SSE streaming
analyzer.py       — 8-pass tree-sitter C analysis
start.sh          — TUI launcher with dependency management
report/
  generator.py    — 16 analysis engines
  template.html   — Interactive report template
docs/
  generator.py    — Function documentation generator
deps/
  generator.py    — Data dependencies report
```

## Tests

```bash
./run_tests.sh          # All 4 suites (~800 tests)
./run_tests.sh quick    # Skip smoke test (no server)
./run_tests.sh smoke    # End-to-end with real server
./run_tests.sh deep     # Deep coverage
```

## Supported

- **RTOS**: FreeRTOS, CMSIS-RTOS v2
- **Peripherals**: STM32-style memory-mapped registers
- **ISR patterns**: `*_IRQHandler`, `ISR_*`, `irq_*`
- **Platforms**: Linux, macOS, WSL

## License

MIT
