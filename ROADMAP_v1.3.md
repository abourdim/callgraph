# Callgraph Studio — Roadmap after v1.3.0

## Completed in v1.3.0

- ✓ Stack depth DFS performance fix (memoized DP)
- ✓ Diff mode (snapshot + compare)
- ✓ Source annotation view
- ✓ Persistent bookmarks
- ✓ Auto-trace main on startup
- ✓ Trace direction toggle (Both/Down/Up)
- ✓ Module-aware trace nodes (color + label)

---

## Planned features

### High value

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

### Medium value

**Configurable entry point patterns**
- Currently hard-coded regex in dead code + stack depth
- Let user add/remove patterns in a settings panel

**Force-directed graph layout option**
- Alternative to hierarchical layout
- Better for non-tree-like graphs (tangled modules, cyclic code)
- Toggle: hierarchical ↔ force-directed

**Live file watcher**
- Watch source directory for changes
- Auto-re-index and show diff overlay
- Use inotify/fsevents via server endpoint

### Lower value / deferred

- Themes (dark/light/high-contrast/Alhambra)
- Touch/mobile support for pan and zoom
- Configurable session TTL (currently fixed 24h)
- Export: GraphML / DOT format for Graphviz/yEd import
- Source view: syntax highlighting (keyword coloring)
- Source view: inline diff markers when diff mode is active
