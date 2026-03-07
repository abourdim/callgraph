#!/usr/bin/env python3
"""
callgraph_web — Flask web interface for callgraph.sh
"""

import os, sys, json, subprocess, tempfile, shutil, threading, time, uuid, re, signal
from pathlib import Path
from flask import Flask, request, jsonify, Response, send_from_directory

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.resolve()
SCRIPT      = BASE_DIR / "callgraph.sh"
RUNS_DIR    = BASE_DIR / "runs"
UPLOAD_DIR  = BASE_DIR / "uploads"
RUNS_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__,
            template_folder=str(BASE_DIR / "templates"),
            static_folder=str(BASE_DIR / "static"))
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB

# ── Active SSE streams ────────────────────────────────────────────────────────
_streams: dict[str, list] = {}   # run_id → [lines]
_procs:   dict[str, subprocess.Popen] = {}

# ── Dependency management ─────────────────────────────────────────────────────
DEPS = {
    "cflow":   {"apt": "cflow",    "pacman": "cflow",  "dnf": "cflow",   "brew": "cflow"},
    "ctags":   {"apt": "universal-ctags", "pacman": "ctags", "dnf": "ctags", "brew": "universal-ctags"},
    "dot":     {"apt": "graphviz", "pacman": "graphviz","dnf": "graphviz","brew": "graphviz"},
    "gawk":    {"apt": "gawk",     "pacman": "gawk",   "dnf": "gawk",    "brew": "gawk"},
    "gcc":     {"apt": "gcc",      "pacman": "gcc",    "dnf": "gcc",     "brew": "gcc"},
}
EXTRA_ENGINES = ["neato", "fdp", "sfdp", "circo", "twopi"]

def detect_pkg_manager():
    for mgr in ["apt-get","pacman","dnf","yum","brew"]:
        if shutil.which(mgr):
            return mgr
    return None

def check_dep(cmd):
    return shutil.which(cmd) is not None

def check_all_deps():
    result = {}
    for name in DEPS:
        result[name] = check_dep(name)
    result["_extra_engines"] = {e: check_dep(e) for e in EXTRA_ENGINES}
    result["_pkg_manager"]   = detect_pkg_manager()
    result["_script_found"]  = SCRIPT.exists()
    return result

def install_dep(name, stream_id):
    mgr = detect_pkg_manager()
    if not mgr:
        _push(stream_id, f"[error] No package manager found")
        return False

    pkg_map = DEPS.get(name, {})
    mgr_key = mgr.replace("-get","")
    pkg = pkg_map.get(mgr_key, name)

    _push(stream_id, f"[install] {mgr} → {pkg}")

    if mgr == "apt-get":
        cmd = ["sudo","apt-get","install","-y", pkg]
    elif mgr == "pacman":
        cmd = ["sudo","pacman","-S","--noconfirm", pkg]
    elif mgr in ("dnf","yum"):
        cmd = ["sudo", mgr, "install","-y", pkg]
    elif mgr == "brew":
        cmd = ["brew","install", pkg]
    else:
        _push(stream_id, f"[error] Unknown manager: {mgr}")
        return False

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            _push(stream_id, line.rstrip())
        proc.wait()
        ok = proc.returncode == 0
        _push(stream_id, f"[{'ok' if ok else 'error'}] Install {'succeeded' if ok else 'failed'} for {name}")
        return ok
    except Exception as e:
        _push(stream_id, f"[error] {e}")
        return False

# ── SSE helpers ───────────────────────────────────────────────────────────────
def _push(stream_id, line):
    if stream_id not in _streams:
        _streams[stream_id] = []
    _streams[stream_id].append(line)

def _stream_gen(stream_id, poll=0.12):
    seen = 0
    timeout = 600  # 10 min max
    start = time.time()
    while time.time() - start < timeout:
        lines = _streams.get(stream_id, [])
        while seen < len(lines):
            yield f"data: {json.dumps(lines[seen])}\n\n"
            seen += 1
            if lines[seen-1] == "__DONE__":
                return
        time.sleep(poll)
    yield f"data: {json.dumps('__DONE__')}\n\n"

# ── Filesystem browser ────────────────────────────────────────────────────────
@app.route("/api/browse")
def browse():
    path = request.args.get("path", str(Path.home()))
    try:
        p = Path(path).resolve()
        if not p.exists():
            p = Path.home()
        entries = []
        # Parent
        if p != p.parent:
            entries.append({"name": "..", "path": str(p.parent), "type": "dir"})
        for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            try:
                entries.append({
                    "name": child.name,
                    "path": str(child),
                    "type": "dir" if child.is_dir() else "file",
                    "ext":  child.suffix.lower()
                })
            except PermissionError:
                pass
        return jsonify({"path": str(p), "entries": entries})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ── Auto-detect include paths ─────────────────────────────────────────────────
@app.route("/api/detect-includes")
def detect_includes():
    src = request.args.get("path","")
    if not src or not Path(src).is_dir():
        return jsonify({"includes": []})
    includes = set()
    for f in Path(src).rglob("*.c"):
        try:
            for line in f.read_text(errors="ignore").splitlines():
                m = re.match(r'#\s*include\s+"([^"]+)"', line)
                if m:
                    inc_path = (f.parent / Path(m.group(1))).parent.resolve()
                    if inc_path.exists():
                        includes.add(str(inc_path))
        except Exception:
            pass
    # Also look for obvious include dirs
    src_p = Path(src)
    for candidate in ["include","inc","headers","src"]:
        d = src_p / candidate
        if d.is_dir():
            includes.add(str(d))
    return jsonify({"includes": sorted(includes)})

# ── Detect root functions ─────────────────────────────────────────────────────
@app.route("/api/detect-roots")
def detect_roots():
    src = request.args.get("path","")
    if not src or not Path(src).is_dir():
        return jsonify({"roots": []})
    roots = []
    try:
        result = subprocess.run(
            ["ctags", "--c-kinds=f", "-f", "-", "-R", src],
            capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.splitlines():
            if line.startswith("!"):
                continue
            parts = line.split("\t")
            if parts:
                roots.append(parts[0])
        roots = sorted(set(roots))
    except Exception:
        pass
    return jsonify({"roots": roots[:200]})

# ── Dependency status + install ───────────────────────────────────────────────
@app.route("/api/deps")
def api_deps():
    return jsonify(check_all_deps())

@app.route("/api/install", methods=["POST"])
def api_install():
    deps = request.json.get("deps", [])
    stream_id = str(uuid.uuid4())
    _streams[stream_id] = []

    def _run():
        for dep in deps:
            install_dep(dep, stream_id)
        _push(stream_id, "__DONE__")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"stream_id": stream_id})

@app.route("/api/stream/<stream_id>")
def api_stream(stream_id):
    def _cleanup_gen():
        yield from _stream_gen(stream_id)
        _streams.pop(stream_id, None)  # cleanup after consumed
    return Response(_cleanup_gen(),
                    mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

# ── Upload .c files ───────────────────────────────────────────────────────────
@app.route("/api/upload", methods=["POST"])
def api_upload():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "no files"}), 400
    run_id  = str(uuid.uuid4())
    dst_dir = UPLOAD_DIR / run_id
    dst_dir.mkdir(parents=True)
    saved = []
    for f in files:
        if f.filename.endswith(".c") or f.filename.endswith(".h"):
            dest = dst_dir / Path(f.filename).name
            f.save(dest)
            saved.append(str(dest))
    if not saved:
        shutil.rmtree(dst_dir, ignore_errors=True)
        return jsonify({"error": "no .c/.h files found"}), 400
    return jsonify({"upload_id": run_id, "path": str(dst_dir), "count": len(saved)})

# ── Generate ──────────────────────────────────────────────────────────────────
@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.json or {}

    src_path  = data.get("source_path","").strip()
    upload_id = data.get("upload_id","").strip()

    # Resolve source dir
    if upload_id:
        src_dir = UPLOAD_DIR / upload_id
    elif src_path:
        src_dir = Path(src_path)
    else:
        return jsonify({"error": "No source directory provided"}), 400

    if not src_dir.is_dir():
        return jsonify({"error": f"Not a directory: {src_dir}"}), 400

    run_id  = str(uuid.uuid4())
    out_dir = RUNS_DIR / run_id
    out_dir.mkdir(parents=True)

    # Build args from UI params or raw CLI override
    raw_cli = data.get("raw_cli","").strip()
    if raw_cli:
        import shlex
        extra_args = shlex.split(raw_cli)
        # Strip script name if present (e.g. "./callgraph.sh" or "callgraph.sh")
        if extra_args and extra_args[0].endswith('callgraph.sh'):
            extra_args = extra_args[1:]
        # Strip any trailing source path (last non-flag arg) and -O / --module
        # to avoid duplication — server appends them cleanly
        clean = []
        skip_next = False
        for a in extra_args:
            if skip_next: skip_next=False; continue
            if a in ('-O', '--output-dir'): skip_next=True; continue
            if a == str(src_dir) or a == str(out_dir): continue
            clean.append(a)
        cmd = ["bash", str(SCRIPT)] + clean + ["-O", str(out_dir), str(src_dir)]
    else:
        cmd = ["bash", str(SCRIPT)]
        # Mode
        if data.get("generate_all"):
            cmd += ["-A"]
        # Depth
        depth = int(data.get("depth", 0))
        if depth > 0:
            cmd += ["-d", str(depth)]
        # Output name
        out_name = data.get("output_name","callgraph").strip() or "callgraph"
        cmd += ["-o", out_name]
        # Output dir
        cmd += ["-O", str(out_dir)]
        # Flags
        if data.get("exclude_ext"):
            cmd += ["-x"]
        if data.get("macro_mode"):
            cmd += ["-m"]
        # Root function
        root = data.get("root_func","").strip()
        if root:
            cmd += ["-r", root]
        # Exclude dirs
        for exc in data.get("excludes", []):
            if exc.strip():
                cmd += ["-e", exc.strip()]
        # Include paths
        for inc in data.get("includes", []):
            if inc.strip():
                cmd += ["-I", inc.strip()]
        # Module mode
        if data.get("module_mode"):
            cmd += ["-M"]
        # Trace function
        trace = data.get("trace_func", "").strip()
        if trace:
            cmd += ["-t", trace]
        cmd += [str(src_dir)]

    stream_id = run_id
    _streams[stream_id] = []

    # Persist run metadata
    meta = {
        "run_id":    run_id,
        "ts":        time.strftime("%Y-%m-%d %H:%M:%S"),
        "source":    str(src_dir),
        "cmd":       " ".join(cmd),
        "params":    data,
        "out_dir":   str(out_dir),
        "status":    "running"
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    def _run():
        _push(stream_id, f"[run] {' '.join(cmd)}")
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=str(out_dir)
            )
            _procs[run_id] = proc
            for line in proc.stdout:
                _push(stream_id, line.rstrip())
            proc.wait()
            rc = proc.returncode
            meta["status"] = "ok" if rc == 0 else "error"
            meta["rc"] = rc
            (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
            _push(stream_id, f"__STATUS__:{rc}")
        except Exception as e:
            _push(stream_id, f"[error] {e}")
            meta["status"] = "error"
            (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
        finally:
            _procs.pop(run_id, None)
            _push(stream_id, "__DONE__")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"run_id": run_id, "stream_id": stream_id})

@app.route("/api/cancel/<run_id>", methods=["POST"])
def api_cancel(run_id):
    proc = _procs.get(run_id)
    if proc:
        proc.terminate()
        return jsonify({"ok": True})
    return jsonify({"ok": False})

# ── Run history ───────────────────────────────────────────────────────────────
@app.route("/api/runs")
def api_runs():
    runs = []
    for d in sorted(RUNS_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
        meta_f = d / "meta.json"
        if meta_f.exists():
            try:
                m = json.loads(meta_f.read_text())
                html = d / "index.html"
                m["has_report"] = html.exists()
                runs.append(m)
            except Exception:
                pass
    return jsonify(runs)

# ── Serve run outputs ─────────────────────────────────────────────────────────
@app.route("/runs/<run_id>/")
@app.route("/runs/<run_id>/<path:filename>")
def serve_run(run_id, filename="index.html"):
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        return "Not found", 404
    return send_from_directory(str(run_dir), filename)


# ── Favicon (prevent 404 noise) ──────────────────────────────────────────────
@app.route("/favicon.ico")
def favicon():
    # Return a minimal inline SVG favicon as ICO placeholder
    svg = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="6" fill="#080c14"/>
  <circle cx="8" cy="8" r="3" fill="#3d8ef0"/>
  <circle cx="24" cy="8" r="3" fill="#3d8ef0"/>
  <circle cx="16" cy="24" r="3" fill="#f0c060"/>
  <line x1="11" y1="8" x2="21" y2="8" stroke="#3d8ef0" stroke-width="1.5"/>
  <line x1="9.5" y1="11" x2="14.5" y2="21" stroke="#7a90b8" stroke-width="1.5"/>
  <line x1="22.5" y1="11" x2="17.5" y2="21" stroke="#7a90b8" stroke-width="1.5"/>
</svg>'''
    from flask import Response
    return Response(svg, mimetype="image/svg+xml")

# ── Main UI ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    # Serve HTML directly — works regardless of working directory
    for candidate in [
        BASE_DIR / "templates" / "index.html",
        BASE_DIR / "index.html",
    ]:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8"), 200, {"Content-Type": "text/html; charset=utf-8"}
    return "<h1>index.html not found. Place it in templates/ next to server.py</h1>", 404

# ── Index source: parse once, return full graph JSON ─────────────────────────
@app.route("/api/index", methods=["POST"])
def api_index():
    src = request.json.get("source_path", "").strip()
    if not src or not Path(src).is_dir():
        return jsonify({"error": "invalid source path"}), 400
    # Basic path safety: block obviously dangerous system dirs
    abs_src = str(Path(src).resolve())
    blocked = ['/etc', '/sys', '/proc', '/dev', '/boot', '/root']
    if any(abs_src == b or abs_src.startswith(b+'/') for b in blocked):
        return jsonify({"error": "access to system directories not allowed"}), 403

    stream_id = str(uuid.uuid4())
    _streams[stream_id] = []

    def _run():
        try:
            from pathlib import Path as _Path
            from analyzer import analyze_project, TS_AVAILABLE

            # Find C sources
            _push(stream_id, "[info] Scanning sources...")
            result = subprocess.run(
                ["find", src, "-name", "*.c", "-not", "-path", "*/.*"],
                capture_output=True, text=True, timeout=30
            )
            sources = [_Path(l) for l in result.stdout.splitlines() if l.strip()]
            _push(stream_id, f"[info] Found {len(sources)} source files")
            if not sources:
                _push(stream_id, "__GRAPH__:" + json.dumps({"error": "no .c files found"}))
                return

            if not TS_AVAILABLE:
                _push(stream_id, "[error] tree-sitter not installed")
                _push(stream_id, "[error] Run: pip install tree-sitter tree-sitter-c")
                _push(stream_id, "__GRAPH__:" + json.dumps({"error": "tree-sitter not available — pip install tree-sitter tree-sitter-c"}))
                return

            graph = analyze_project(
                sources,
                src_root=_Path(src),
                push_fn=lambda m: _push(stream_id, m)
            )
            if graph is None:
                _push(stream_id, "__GRAPH__:" + json.dumps({"error": "analysis failed"}))
                return

            _push(stream_id, "__GRAPH__:" + json.dumps(graph))

        except Exception as e:
            import traceback
            _push(stream_id, f"[error] {e}")
            _push(stream_id, f"[error] {traceback.format_exc()}")
            _push(stream_id, "__GRAPH__:" + json.dumps({"error": str(e)}))
        finally:
            _push(stream_id, "__DONE__")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"stream_id": stream_id})

# ── Source file reader ───────────────────────────────────────────
@app.route("/api/source")
def api_source():
    filepath = request.args.get("file", "")
    root = request.args.get("root", "")
    if not filepath or not root:
        return jsonify({"error": "file and root params required"}), 400
    # Resolve and validate
    root_p = Path(root).resolve()
    file_p = (root_p / filepath).resolve()
    # Security: must be under root
    if not str(file_p).startswith(str(root_p)):
        return jsonify({"error": "path traversal not allowed"}), 403
    if not file_p.exists():
        return jsonify({"error": f"file not found: {filepath}"}), 404
    try:
        lines = file_p.read_text(encoding='utf-8', errors='replace').splitlines()
        return jsonify({"file": filepath, "lines": lines, "total": len(lines)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Report generator ─────────────────────────────────────────
@app.route("/api/report", methods=["POST"])
def api_report():
    graph = request.get_json(force=True, silent=True)
    if not graph or 'nodes' not in graph:
        return jsonify({"error": "invalid graph data", "detail": f"got type={type(graph).__name__}, keys={list(graph.keys()) if isinstance(graph,dict) else 'N/A'}"}), 400
    try:
        import importlib.util
        gen_path = str(BASE_DIR / "report" / "generator.py")
        tpl_path = str(BASE_DIR / "report" / "template.html")
        print(f"[report] Generating for {len(graph.get('nodes',[]))} nodes, gen={gen_path}, tpl={tpl_path}")

        if not Path(gen_path).exists():
            return jsonify({"error": f"generator.py not found at {gen_path}"}), 500
        if not Path(tpl_path).exists():
            return jsonify({"error": f"template.html not found at {tpl_path}"}), 500

        spec = importlib.util.spec_from_file_location("report_gen", gen_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        print("[report] Running analysis engines...")
        report_data = mod.generate_report_data(graph)
        print(f"[report] Analysis complete, building HTML...")
        html = mod.build_html(report_data, template_path=tpl_path)
        print(f"[report] Done: {len(html)} bytes")

        return Response(html, mimetype="text/html",
                       headers={"Content-Disposition": f"attachment; filename={Path(graph.get('source','project')).name}-report.html"})
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[report] ERROR: {e}\n{tb}")
        return jsonify({"error": str(e), "trace": tb}), 500

# ── Function documentation generator ─────────────────────────
@app.route("/api/docs", methods=["POST"])
def api_docs():
    graph = request.get_json()
    if not graph or 'nodes' not in graph:
        return jsonify({"error": "invalid graph data"}), 400
    mode = request.args.get("mode", "single")
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("docs_gen", str(BASE_DIR / "docs" / "generator.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if mode == "multi":
            data = mod.build_multi(graph)
            proj_name = Path(graph.get('source','project')).name
            return Response(data, mimetype="application/zip",
                           headers={"Content-Disposition": f"attachment; filename={proj_name}-docs.zip"})
        else:
            html = mod.build_single(graph)
            proj_name = Path(graph.get('source','project')).name
            return Response(html, mimetype="text/html",
                           headers={"Content-Disposition": f"attachment; filename={proj_name}-docs.html"})
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500

# ── Live file watcher ────────────────────────────────────────
_watch_state = {"active": False, "path": None, "stream_id": None, "snapshot": {}}

def _file_snapshot(src_path):
    """Get mtime snapshot of all .c/.h files under src_path."""
    snap = {}
    try:
        for f in Path(src_path).rglob("*.[ch]"):
            try:
                snap[str(f)] = f.stat().st_mtime
            except:
                pass
    except:
        pass
    return snap

@app.route("/api/watch/start", methods=["POST"])
def api_watch_start():
    src = request.json.get("path", "").strip()
    if not src or not Path(src).is_dir():
        return jsonify({"error": "invalid path"}), 400

    stream_id = str(uuid.uuid4())
    _streams[stream_id] = []
    _watch_state["active"] = True
    _watch_state["path"] = src
    _watch_state["stream_id"] = stream_id
    _watch_state["snapshot"] = _file_snapshot(src)

    def _poll():
        while _watch_state["active"] and _watch_state["stream_id"] == stream_id:
            time.sleep(2)
            new_snap = _file_snapshot(src)
            old_snap = _watch_state["snapshot"]

            changed = []
            for f, mt in new_snap.items():
                if f not in old_snap:
                    changed.append({"file": f, "type": "added"})
                elif mt != old_snap[f]:
                    changed.append({"file": f, "type": "modified"})
            for f in old_snap:
                if f not in new_snap:
                    changed.append({"file": f, "type": "deleted"})

            if changed:
                _watch_state["snapshot"] = new_snap
                _push(stream_id, json.dumps({"changes": changed}))

        _push(stream_id, "__DONE__")

    threading.Thread(target=_poll, daemon=True).start()
    return jsonify({"stream_id": stream_id})

@app.route("/api/watch/stop", methods=["POST"])
def api_watch_stop():
    _watch_state["active"] = False
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7411))
    print(f"\n  ✦ Callgraph Web  →  http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
