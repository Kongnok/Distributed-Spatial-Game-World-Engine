#!/usr/bin/env python3
"""
run.py — Single-command launcher for the Distributed Spatial Game World Engine.

Usage:
    python run.py                  # 20 bots, default settings
    python run.py --bots 40        # spawn 40 bots
    python run.py --delay 100      # 100ms between spawns
    python run.py --no-browser     # skip auto-opening the dashboard
"""

import argparse
import os
import signal
import subprocess
import sys
import time
import threading
import socket
import webbrowser
import http.server
import functools
from pathlib import Path

# ---------------------------------------------------------------------------
# Colours for log prefixes
# ---------------------------------------------------------------------------
RESET  = "\033[0m"
BOLD   = "\033[1m"
COLORS = {
    "GATEWAY": "\033[95m",   # magenta
    "NODE 1":  "\033[94m",   # blue
    "NODE 2":  "\033[96m",   # cyan
    "NODE 3":  "\033[92m",   # green
    "NODE 4":  "\033[93m",   # yellow
    "SIM":     "\033[91m",   # red
    "LAUNCH":  "\033[97m",   # white
    "DASH":    "\033[90m",   # grey
}

def log(tag: str, msg: str):
    color = COLORS.get(tag, RESET)
    print(f"{color}{BOLD}[{tag}]{RESET} {msg}", flush=True)

# ---------------------------------------------------------------------------
# Process definitions
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent

# --- VENV DETECTION FIX ---
# Check if a local Windows virtual environment exists, otherwise default to system python
VENV_EXE = SCRIPT_DIR / "env" / "Scripts" / "python.exe"
DOT_VENV_EXE = SCRIPT_DIR / ".venv" / "Scripts" / "python.exe"

if VENV_EXE.exists():
    PYTHON_EXE = str(VENV_EXE)
elif DOT_VENV_EXE.exists():
    PYTHON_EXE = str(DOT_VENV_EXE)
else:
    PYTHON_EXE = sys.executable  # Fallback if no venv folder is found
# --------------------------

SERVICES = [
    ("GATEWAY", [PYTHON_EXE, str(SCRIPT_DIR / "gateway.py")]),
    ("NODE 1",  [PYTHON_EXE, str(SCRIPT_DIR / "server.py"),  "--node", "1"]),
    ("NODE 2",  [PYTHON_EXE, str(SCRIPT_DIR / "server.py"),  "--node", "2"]),
    ("NODE 3",  [PYTHON_EXE, str(SCRIPT_DIR / "server.py"),  "--node", "3"]),
    ("NODE 4",  [PYTHON_EXE, str(SCRIPT_DIR / "server.py"),  "--node", "4"]),
]

PORTS = {
    "GATEWAY": 8000,
    "NODE 1":  8001,
    "NODE 2":  8002,
    "NODE 3":  8003,
    "NODE 4":  8004,
}

DASHBOARD_PORT = 8080

# ---------------------------------------------------------------------------
# Stream a process's stdout/stderr with a coloured prefix
# ---------------------------------------------------------------------------
def stream_output(proc: subprocess.Popen, tag: str):
    color = COLORS.get(tag, RESET)
    for raw in proc.stdout:
        line = raw.rstrip()
        if line:
            print(f"{color}[{tag}]{RESET} {line}", flush=True)

# ---------------------------------------------------------------------------
# Wait until a TCP port accepts connections
# ---------------------------------------------------------------------------
def wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.15)
    return False

# ---------------------------------------------------------------------------
# Serve dashboard via HTTP so CORS is not an issue (file:// triggers CORS)
# ---------------------------------------------------------------------------
def serve_dashboard(directory: Path, port: int):
    """Run a simple HTTP server in a daemon thread."""
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)
        def log_message(self, format, *args):
            pass   # suppress access logs

    server = http.server.HTTPServer(("127.0.0.1", port), QuietHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Launch the full distributed game world.")
    parser.add_argument("--bots",       type=int, default=20,  help="Number of bots (default: 20)")
    parser.add_argument("--delay",      type=int, default=50,  help="ms between bot spawns (default: 50)")
    parser.add_argument("--no-browser", action="store_true",   help="Do not auto-open the dashboard")
    args = parser.parse_args()

    log("LAUNCH", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log("LAUNCH", "  Distributed Spatial Game World Engine")
    log("LAUNCH", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log("LAUNCH", f"  Bots: {args.bots}  |  Spawn delay: {args.delay}ms")
    log("LAUNCH", "  Press Ctrl+C to stop everything")
    log("LAUNCH", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()

    procs: list[subprocess.Popen] = []

    def shutdown(signum=None, frame=None):
        print()
        log("LAUNCH", "Shutting down all processes…")
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        for p in procs:
            try:
                p.wait(timeout=4)
            except subprocess.TimeoutExpired:
                p.kill()
        log("LAUNCH", "All processes stopped. Goodbye.")
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # -----------------------------------------------------------------------
    # 1. Start gateway + 4 nodes
    # -----------------------------------------------------------------------
    for tag, cmd in SERVICES:
        log("LAUNCH", f"Starting {tag}…")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(SCRIPT_DIR),
        )
        procs.append(proc)
        t = threading.Thread(target=stream_output, args=(proc, tag), daemon=True)
        t.start()
        time.sleep(0.1)

    # -----------------------------------------------------------------------
    # 2. Wait for all services to be ready
    # -----------------------------------------------------------------------
    print()
    log("LAUNCH", "Waiting for all services to come online…")
    all_ready = True
    for tag, port in PORTS.items():
        ok = wait_for_port(port)
        if ok:
            log("LAUNCH", f"  ✓ {tag} (:{port}) ready")
        else:
            log("LAUNCH", f"  ✗ {tag} (:{port}) did NOT start — check logs above")
            all_ready = False

    if not all_ready:
        log("LAUNCH", "One or more services failed to start. Aborting.")
        shutdown()

    print()
    log("LAUNCH", "All services up!")

    # -----------------------------------------------------------------------
    # 3. Serve dashboard over HTTP (avoids file:// CORS block)
    # -----------------------------------------------------------------------
    # Support both flat layout (index.html next to run.py) and dashboard/ subdir
    dashboard_dir = SCRIPT_DIR
    if not (SCRIPT_DIR / "index.html").exists():
        candidate = SCRIPT_DIR / "dashboard"
        if (candidate / "index.html").exists():
            dashboard_dir = candidate

    if (dashboard_dir / "index.html").exists():
        serve_dashboard(dashboard_dir, DASHBOARD_PORT)
        dashboard_url = f"http://127.0.0.1:{DASHBOARD_PORT}/index.html"
        log("DASH", f"Dashboard served at {dashboard_url}")
        if not args.no_browser:
            time.sleep(0.3)
            webbrowser.open(dashboard_url)
    else:
        log("LAUNCH", "index.html not found — open it manually.")

    # -----------------------------------------------------------------------
    # 4. Run bot simulator
    # -----------------------------------------------------------------------
    print()
    log("LAUNCH", f"Spawning {args.bots} bots via simulator…")
    time.sleep(0.3)

    sim_cmd = [
        PYTHON_EXE, str(SCRIPT_DIR / "bot_simulator.py"),
        "--bots",  str(args.bots),
        "--delay", str(args.delay),
    ]
    sim = subprocess.Popen(
        sim_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(SCRIPT_DIR),
    )
    for raw in sim.stdout:
        line = raw.rstrip()
        if line:
            color = COLORS["SIM"]
            print(f"{color}[SIM]{RESET} {line}", flush=True)
    sim.wait()

    print()
    log("LAUNCH", "Bots spawned. System is live. Ctrl+C to stop.")
    log("LAUNCH", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # -----------------------------------------------------------------------
    # 5. Keep running — watch for unexpected exits
    # -----------------------------------------------------------------------
    while True:
        for i, (tag, _) in enumerate(SERVICES):
            if procs[i].poll() is not None:
                log("LAUNCH", f"⚠  {tag} exited unexpectedly (code {procs[i].returncode})")
        time.sleep(2)


if __name__ == "__main__":
    main()