"""
run.py — Unified J-Search pipeline entry point.

Starts a lightweight local HTTP server, serves a configuration landing page,
runs the pipeline based on user preferences, and displays results with
tabs for Recommended, Flexible, and Browse All views.

Usage:
    python run.py      (keep terminal open; Ctrl+C to stop)
"""

import threading
import time
import webbrowser
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from urllib.parse import unquote

from fetch_live_jobs import get_live_remote_jobs
from fetch_local_merchants import get_local_merchants_ddg
from fetch_rss_jobs import get_rss_remote_jobs
from job_dashboard import build_dashboard, get_scoring_config

PORT = 8765

_pipeline_lock = threading.Lock()
_pipeline_running = False
_current_config = get_scoring_config("balanced")


LANDING_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>J-Search - Configure Filters</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            min-height: 100vh;
            padding: 40px 20px;
        }
        .container {
            max-width: 700px;
            margin: 0 auto;
        }
        .card {
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }
        .header h1 {
            margin: 0 0 8px 0;
            font-size: 32px;
        }
        .header p {
            margin: 0;
            opacity: 0.9;
            font-size: 15px;
        }
        .content {
            padding: 40px;
        }
        .section {
            margin-bottom: 32px;
        }
        .section h2 {
            margin: 0 0 16px 0;
            font-size: 20px;
            color: #0f172a;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .presets {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
        }
        .preset-btn {
            padding: 16px;
            border: 2px solid #e2e8f0;
            background: white;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
            text-align: left;
        }
        .preset-btn:hover {
            border-color: #cbd5e1;
            background: #f8fafc;
        }
        .preset-btn.active {
            border-color: #2563eb;
            background: #eff6ff;
        }
        .preset-btn .title {
            font-weight: 600;
            color: #0f172a;
            margin-bottom: 4px;
        }
        .preset-btn .desc {
            font-size: 12px;
            color: #64748b;
        }
        .info-box {
            background: #f1f5f9;
            padding: 16px;
            border-radius: 8px;
            font-size: 13px;
            color: #475569;
            line-height: 1.6;
        }
        .submit-btn {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .submit-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(37, 99, 235, 0.3);
        }
        input[type="hidden"] { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <h1>🎯 J-Search</h1>
                <p>Smart Job Triage Pipeline - Configure Your Filters</p>
            </div>
            <div class="content">
                <form action="/start" method="GET">
                    <div class="section">
                        <h2>⚡ Filter Preset</h2>
                        <div class="presets">
                            <div class="preset-btn active" onclick="selectPreset('strict', this)">
                                <div class="title">🎯 Strict</div>
                                <div class="desc">High precision, senior roles filtered. Best matches only.</div>
                            </div>
                            <div class="preset-btn" onclick="selectPreset('balanced', this)">
                                <div class="title">⚖️ Balanced</div>
                                <div class="desc">Good balance of quality and quantity.</div>
                            </div>
                            <div class="preset-btn" onclick="selectPreset('lenient', this)">
                                <div class="title">🌐 Lenient</div>
                                <div class="desc">Cast a wider net, explore more opportunities.</div>
                            </div>
                        </div>
                        <input type="hidden" name="preset" id="preset" value="strict">
                    </div>

                    <div class="section">
                        <h2>ℹ️ How it works</h2>
                        <div class="info-box">
                            <strong>Recommended:</strong> Strict filtering with dealbreakers enforced - best for applying now<br>
                            <strong>Flexible:</strong> More permissive filtering - worth a look<br>
                            <strong>Browse All:</strong> See everything found, split by Remote/Local - pure discovery<br><br>
                            Scores are calculated server-side based on your preset. You can refresh anytime with the same settings.
                        </div>
                    </div>

                    <button type="submit" class="submit-btn">
                        🚀 Find Jobs with These Settings
                    </button>
                </form>
            </div>
        </div>
    </div>

    <script>
        function selectPreset(preset, btn) {
            document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('preset').value = preset;
        }
    </script>
</body>
</html>
"""


LOADING_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Searching for Jobs...</title>
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
                    window.location.href = '/results';
                }
            } catch (e) {}
        }
        checkStatus();
        setInterval(checkStatus, 1000);
    </script>
</body>
</html>
"""


def _deduplicate_jobs(jobs):
    seen = set()
    unique = []
    for job in jobs:
        url = job.get('url', '') or ''
        try:
            parsed = urlparse(url)
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".lower().rstrip('/')
        except Exception:
            normalized = url.lower().strip()
        if not normalized or normalized in ('http://', 'https://'):
            normalized = f"{job.get('title','')}|{job.get('company','')}".lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(job)
    return unique


def run_pipeline():
    global _pipeline_running
    _pipeline_running = True
    try:
        print("=" * 50)
        print("  J-Search Pipeline Starting")
        print("=" * 50)

        remote_jobs = get_live_remote_jobs()
        rss_jobs = get_rss_remote_jobs()
        local_leads = get_local_merchants_ddg()

        all_remote_combined = remote_jobs + rss_jobs
        all_remote = _deduplicate_jobs(all_remote_combined)
        all_local = _deduplicate_jobs(local_leads)

        print()
        print(f"  Remote jobs fetched : {len(remote_jobs) + len(rss_jobs)} (unique: {len(all_remote)})")
        print(f"  Local leads fetched : {len(local_leads)} (unique: {len(all_local)})")
        print()

        build_dashboard(remote_jobs=all_remote, local_leads=all_local, config=_current_config)
        print("  Pipeline complete.")
    finally:
        _pipeline_running = False


class DashboardHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        global _current_config, _pipeline_running
        
        if self.path == '/':
            self._respond(200, LANDING_PAGE.encode('utf-8'), 'text/html; charset=utf-8')
        elif self.path.startswith('/start'):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            preset = params.get('preset', ['balanced'])[0]
            if preset not in ['strict', 'balanced', 'lenient']:
                preset = 'balanced'
            _current_config = get_scoring_config(preset)
            print(f"\n[Config] Using preset: {preset}")
            
            if not _pipeline_running:
                if _pipeline_lock.acquire(blocking=False):
                    try:
                        thread = threading.Thread(target=run_pipeline, daemon=True)
                        thread.start()
                    finally:
                        _pipeline_lock.release()
                else:
                    thread = threading.Thread(target=run_pipeline, daemon=True)
                    thread.start()
            self._respond(200, LOADING_PAGE.encode('utf-8'), 'text/html; charset=utf-8')
        elif self.path in ('/results', '/dashboard.html'):
            self._serve_file('dashboard.html', 'text/html; charset=utf-8')
        elif self.path == '/refresh':
            if not _pipeline_running:
                if _pipeline_lock.acquire(blocking=False):
                    try:
                        thread = threading.Thread(target=run_pipeline, daemon=True)
                        thread.start()
                    finally:
                        _pipeline_lock.release()
            self._respond(200, LOADING_PAGE.encode('utf-8'), 'text/html; charset=utf-8')
        elif self.path == '/status':
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
                        thread = threading.Thread(target=run_pipeline, daemon=True)
                        thread.start()
                    finally:
                        _pipeline_lock.release()
            self._respond(200, b'{"status":"ok"}', 'application/json')
        else:
            self._respond(404, b'Not found')

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
            self._respond(404, b'Dashboard not found. Go to / to configure and start.')

    def _respond(self, code, body, content_type='text/plain'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == '__main__':
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

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('\nShutting down server...')
        server.shutdown()
