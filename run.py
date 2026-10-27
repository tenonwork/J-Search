"""
run.py — Unified J-Search pipeline entry point.

Starts a lightweight local HTTP server, runs both ingestion pipelines on
startup, and serves the unified dashboard at http://localhost:8765.

The dashboard's Refresh button navigates to a full-page loading screen
while the pipeline re-runs in the background, then redirects back to
the dashboard with fresh results.

Usage:
    python run.py      (keep terminal open; Ctrl+C to stop)
"""

import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from fetch_live_jobs import get_live_remote_jobs
from fetch_local_merchants import get_local_merchants_ddg
from job_dashboard import build_dashboard

PORT = 8765

# Prevents two refresh requests from running the pipeline simultaneously
_pipeline_lock = threading.Lock()
_pipeline_running = False


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline():
    global _pipeline_running
    _pipeline_running = True
    try:
        print("=" * 50)
        print("  J-Search Pipeline Starting")
        print("=" * 50)

        remote_jobs = get_live_remote_jobs()
        local_leads = get_local_merchants_ddg()

        print()
        print(f"  Remote jobs fetched : {len(remote_jobs)}")
        print(f"  Local leads fetched : {len(local_leads)}")
        print()

        build_dashboard(remote_jobs=remote_jobs, local_leads=local_leads)
        print("  Pipeline complete.")
    finally:
        _pipeline_running = False


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

LOADING_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Refreshing Dashboard...</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0f172a;
            margin: 0;
            height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 24px;
            color: white;
        }
        .spinner {
            width: 64px;
            height: 64px;
            border: 6px solid rgba(255,255,255,0.15);
            border-top-color: #60a5fa;
            border-radius: 50%;
            animation: spin 0.9s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        h1 {
            font-size: 22px;
            font-weight: 600;
            margin: 0;
            opacity: 0.95;
        }
        p {
            font-size: 15px;
            margin: 0;
            opacity: 0.7;
        }
    </style>
</head>
<body>
    <div class="spinner"></div>
    <h1>Fetching new results...</h1>
    <p>This may take a moment while the scrapers run.</p>
    <script>
        async function checkStatus() {
            try {
                const res = await fetch('/status');
                if (!res.ok) return;
                const data = await res.json();
                if (!data.running) {
                    window.location.href = '/';
                }
            } catch (e) {
                // Ignore errors and keep polling
            }
        }
        checkStatus();
        setInterval(checkStatus, 1000);
    </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path in ('/', '/dashboard.html', '/index.html'):
            self._serve_file('dashboard.html', 'text/html; charset=utf-8')
        elif self.path == '/refresh':
            global _pipeline_running
            if not _pipeline_running:
                if _pipeline_lock.acquire(blocking=False):
                    try:
                        try:
                            print("\n[Refresh] Triggered from dashboard...")
                        except Exception:
                            print("\nRefresh triggered from dashboard...")
                        thread = threading.Thread(target=run_pipeline, daemon=True)
                        thread.start()
                    finally:
                        _pipeline_lock.release()
                else:
                    # Shouldn't happen often, but just in case
                    thread = threading.Thread(target=run_pipeline, daemon=True)
                    thread.start()
            self._respond(200, LOADING_PAGE.encode('utf-8'), 'text/html; charset=utf-8')
        elif self.path == '/status':
            import json
            status = {"running": _pipeline_running}
            body = json.dumps(status).encode('utf-8')
            self._respond(200, body, 'application/json')
        else:
            self._respond(404, b'Not found')

    def do_POST(self):
        if self.path == '/refresh':
            global _pipeline_running
            if not _pipeline_running:
                if _pipeline_lock.acquire(blocking=False):
                    try:
                        try:
                            print("\n[Refresh] Triggered from dashboard...")
                        except Exception:
                            print("\nRefresh triggered from dashboard...")
                        thread = threading.Thread(target=run_pipeline, daemon=True)
                        thread.start()
                    finally:
                        _pipeline_lock.release()
            self._respond(200, b'{"status":"ok"}', 'application/json')
        else:
            self._respond(404, b'Not found')

    # ---- helpers ----

    def _serve_file(self, filename, content_type):
        try:
            with open(filename, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', len(data))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self._respond(404, b'Dashboard not found - run the pipeline first.')

    def _respond(self, code, body, content_type='text/plain'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Suppress per-request noise; pipeline prints its own status
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # 1. Run pipeline immediately so the dashboard exists before opening browser
    run_pipeline()

    # 2. Start HTTP server in a background daemon thread
    server = HTTPServer(('', PORT), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f'http://localhost:{PORT}'
    try:
        print(f'[Web] Dashboard live at {url}')
    except Exception:
        print(f'Dashboard live at {url}')
    print('   Press Ctrl+C to stop.\n')

    webbrowser.open(url)

    # 3. Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('\nShutting down server...')
        server.shutdown()
