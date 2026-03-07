# Callgraph Studio — Continuation Prompt

Use this prompt to continue development in a new conversation.

---

## Context

You are continuing development of **Callgraph Studio v1.2.0**, a single-page embedded C call graph analyser. The app is a self-contained web tool: one `index.html` (3,789 lines), one `server.py`, one `analyzer.py`, one `start.sh`. The user runs `./start.sh /path/to/project` and gets a browser-based interactive call graph.

**Working file locations (in your Linux container):**
- `/mnt/user-data/outputs/callgraph_web/index.html` — main app (3,789 lines)
- `/mnt/user-data/outputs/callgraph_web/analyzer.py` — 7-pass tree-sitter C analyzer (649 lines)
- `/mnt/user-data/outputs/callgraph_web/server.py` — Flask SSE server (480 lines)
- `/mnt/user-data/outputs/callgraph_web/start.sh` — launcher with dependency checks (321 lines)
- `/mnt/user-data/outputs/callgraph-studio-v1.2.0.zip` — delivery zip
- `/mnt/user-data/outputs/ROADMAP_v1.2.md` — full prioritised roadmap
- `/mnt/user-data/outputs/COMMIT_MSG_v1.2.0.txt` — full v1.2.0 changelog

**Copy to working dir first:**
```bash
cp /mnt/user-data/outputs/callgraph_web/* /home/claude/callgraph_web/
```

---

## What is fully implemented (do not re-implement)

**Analyzer (analyzer.py) — 7 passes:**
- Pass 1: function definitions (file, module, line, type)
- Pass 2: call graph edges
- Pass 3: global variable reads/writes/rw per function
- Pass 4: peripheral register access (PERIPH->REG pattern, STM32 etc.)
- Pass 5: RTOS API detection (FreeRTOS + CMSIS-RTOS v2)
- Pass 6: ISR detection, entry point detection, critical sections, delay-in-loop
- Pass 7: race candidate detection (globals accessed from both ISR and non-ISR)

**Node data fields:** `id, file, mod, module, line, type, is_isr, is_entry, has_critical, delay_in_loop, out_degree, in_degree, reads, writes, rw, peripherals, rtos`

**UI features:**
- Graph: pan/zoom, minimap (draggable, collapsible), collapse/expand subtrees, edge bundling, heatmap legend, node label expansion on hover
- Function list: search (name+file+module), filter chips (ISR/Entry/Critical/Periph), 4 sort orders, module badge, empty state
- Trace: breadcrumb history, back/forward, multi-trace (A→B path), depth slider (0=all)
- Right-click context menu: trace, info, copy name, copy file:line, highlight callers/callees (3-level BFS), collapse, find in list
- Info panel: file:line, flags, globals R/W, peripherals, RTOS APIs, callers/callees (clickable), copy name, trace button
- Analysis: Dead code (☠), Change impact (⚡), Heatmap (🌡), Path find (⇢), Cycle detection (↻), Stack depth (⬆)
- Side panels: Globals (filterable), Races (expandable detail), RTOS (tasks+objects), Peripherals (filterable, highlight)
- Export: SVG, PNG, JSON (full graph+metadata), CSV (edges)
- Session: save/restore with tracedFn + depth + mode; restore prompt on reload
- Keyboard shortcuts: F/+/-/M/Esc/Alt←/Alt→/G/R/T/P/D/H/? (overlay)
- Module graph: function view, module bubble view, matrix view, drill-down

---

## Known bugs to fix first

1. **Stack depth performance** — `longestPath()` in `runStackDepth()` is exponential DFS without memoization. Will hang on 500+ function codebases. Fix with topological sort + DP (DAG case) or memoized DFS.

---

## Next features to build (priority order)

1. **Fix stack depth performance** (bug, do this first)
2. **Diff mode** — re-index and highlight new/removed/changed vs previous snapshot
3. **Source annotation view** — render a .c file with inline call count badges, race markers, dead code indicators
4. **Persistent bookmarks** — star functions, survive session expiry, bookmarks panel

---

## Development rules

- Always copy output files to `/mnt/user-data/outputs/callgraph_web/` after changes
- Run the test suite (`python3 /tmp/full_test.py`) after every patch — must stay 64/64
- Check JS syntax with `node --check /tmp/extracted.js` after every JS change
- Use `str_replace` or patch scripts for surgical edits — never rewrite the full file
- Version is currently `v1.2.0`; next release should be `v1.3.0`
- Delivery: zip to `/mnt/user-data/outputs/callgraph-studio-v1.3.0.zip`, commit msg to `COMMIT_MSG_v1.3.0.txt`

---

## Test suite location

The test file at `/tmp/full_test.py` is ephemeral — it won't survive to a new conversation. Reconstruct it by running:

```bash
# The tests are embedded in start.sh — extract and run:
grep -A5 "def test_" /home/claude/callgraph_web/start.sh
```

Or ask the assistant to reconstruct the full 64-test suite from the transcript at:
`/mnt/transcripts/` (check `journal.txt` for the relevant transcript filename)
