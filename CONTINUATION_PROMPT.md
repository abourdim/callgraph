# Callgraph Studio — Continuation Prompt

Use this prompt to continue development in a new conversation.

---

## Context

You are continuing development of **Callgraph Studio v1.3.0**, a single-page embedded C call graph analyser. The app is a self-contained web tool: one `index.html` (4,188 lines), one `server.py` (502 lines), one `analyzer.py` (649 lines), one `start.sh` (322 lines). The user runs `./start.sh` and gets a browser-based interactive call graph.

---

## What is fully implemented (do not re-implement)

**Analyzer (analyzer.py) — 8 passes:**
- Pass 1: global variables (file-scope, volatile, extern, static)
- Pass 2: function definitions + call analysis
- Pass 3: call graph edges + reverse callers map
- Pass 4: global variable dependency graph
- Pass 5: race condition / interrupt safety
- Pass 6: RTOS architecture
- Pass 7: peripheral register map
- Pass 8: node assembly

**Server (server.py) — endpoints:**
- `/api/index` — tree-sitter index (POST, returns stream_id)
- `/api/source` — read source file (GET, ?file=&root=)
- `/api/browse`, `/api/detect-includes`, `/api/detect-roots`, `/api/deps`, `/api/install`, `/api/stream/<id>`, `/api/upload`, `/api/run`, `/api/cancel/<id>`, `/api/runs`

**UI features (index.html):**
- Module-aware nodes (color + label + legend)
- Trace direction toggle (Both / Down / Up)
- Auto-trace main on startup
- Diff mode, Source annotation view, Persistent bookmarks
- Stack depth (memoized DP), Cycle detection, Dead code, Impact, Heatmap, Path find
- Pan/zoom, minimap, collapse/expand, edge bundling, context menu, multi-trace
- Side panels: Globals, Races, RTOS, Peripherals, Bookmarks
- Export: SVG, PNG, JSON, CSV
- Session persistence, keyboard shortcuts, module graph views

---

## Next features (see ROADMAP_v1.3.md)

1. RTOS task→ISR interaction diagram
2. Inter-module coupling metrics
3. Path finder Web Worker + progress/cancel
4. Configurable entry point patterns
5. Force-directed layout option

---

## Development rules

- Check JS: `sed -n '/<script>/,/<\/script>/p' index.html | sed '1d;$d' > /tmp/extracted.js && node --check /tmp/extracted.js`
- Check Python: `python3 -c "import py_compile; py_compile.compile('server.py')"`
- Use `str_replace` for surgical edits — never rewrite the full file
- Version is `v1.3.0`; next release `v1.4.0`
