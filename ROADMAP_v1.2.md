# Callgraph Studio — Roadmap after v1.2.0

## Known bugs / correctness issues

1. **Stack depth is exponential on dense graphs**
   - `longestPath()` is DFS without memoization
   - Will hang on codebases with 500+ functions and high fan-out
   - Fix: topological sort + DP for DAGs; memoized DFS for graphs with cycles
   - Priority: HIGH — will cause real hangs in production use

2. **Module graph `n.mod` vs `n.module` inconsistency**
   - Analyzer emits both fields; some render paths use one, some the other
   - Low risk (both are set identically) but should be unified

---

## Planned features

### High value

**Diff mode**
- Re-index and compare to previous snapshot stored in session
- Show: new functions (green), removed functions (red), changed call edges (amber)
- Use case: confirm a refactor only touched what you expected

**Source annotation view**
- Given a file path, render it as highlighted text with inline overlays:
  - Call count badge on each function signature
  - Race warning icon if function appears in races list
  - Peripheral access markers
  - Dead code strikethrough
- Bridges the graph ↔ source gap; most useful feature for code review

**Persistent bookmarks**
- Star any function to save it to localStorage
- Bookmarks panel: click to jump directly to trace
- Survives session expiry (stored separately from graph cache)

### Medium value

**RTOS task→ISR interaction**
- Currently RTOS panel shows tasks and queues but not ISR→task unblocking
- Add: which ISRs call xQueueSendFromISR / xSemaphoreGiveFromISR
- Show ISR→queue→task data flow as a small dedicated diagram

**Inter-module coupling metrics**
- For each pair of modules: count of cross-module edges
- Coupling score = edges / (fns_A × fns_B)
- Flag highly coupled module pairs; useful for architectural review

**Path finder progress + cancellation**
- Currently blocks the UI thread on large graphs
- Move BFS to a Web Worker; show progress bar; add Cancel button

**Configurable entry point patterns**
- Currently hard-coded regex in dead code + stack depth
- Let user add/remove patterns in a settings panel

### Lower value / deferred

- Themes (dark/light/high-contrast/Alhambra)
- Force-directed graph layout option
- Touch/mobile support for pan and zoom
- Configurable session TTL (currently fixed 24h)
- Export: GraphML / DOT format for Graphviz/yEd import
