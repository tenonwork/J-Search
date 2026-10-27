"""
run.py — Unified J-Search pipeline entry point.

Starts a lightweight local HTTP server, runs both ingestion pipelines on
startup, and serves the unified dashboard at http://localhost:8765.

The dashboard's Refresh button POSTs to /refresh, which re-runs the
pipeline and regenerates dashboard.html — the page then reloads itself.

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


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline():
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


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

class DashboardHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path in ('/', '/dashboard.html'):
            self._serve_file('dashboard.html', 'text/html; charset=utf-8')
        else:
            self._respond(404, b'Not found')

    def do_POST(self):
        if self.path == '/refresh':
            acquired = _pipeline_lock.acquire(blocking=False)
            if acquired:
                try:
                    print("\n🔄 Refresh triggered from dashboard...")
                    run_pipeline()
                finally:
                    _pipeline_lock.release()
                self._respond(200, b'{"status":"ok"}', 'application/json')
            else:
                # Pipeline already running — tell the browser to wait and retry
                self._respond(429, b'{"status":"busy"}', 'application/json')
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
    print(f'🌐 Dashboard live at {url}')
    print('   Press Ctrl+C to stop.\n')

    webbrowser.open(url)

    # 3. Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('\nShutting down server...')
        server.shutdown()
