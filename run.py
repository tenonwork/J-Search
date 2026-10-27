"""
run.py — Unified J-Search pipeline entry point.

Starts a lightweight local HTTP server with a single-page dashboard.
Users can set filters/preferences, run Global/Local scrapes separately,
and filter/sort results client-side without re-scraping.

Usage:
    python run.py      (keep terminal open; Ctrl+C to stop)
"""

import threading
import time
import webbrowser
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from fetch_live_jobs import get_live_remote_jobs
from fetch_local_merchants import get_local_merchants_ddg
from fetch_rss_jobs import get_rss_remote_jobs
from job_dashboard import build_dashboard, get_scoring_config, score_job, _is_blocked
import db

PORT = 8765

_pipeline_lock = threading.Lock()
_pipeline_running = False
_global_jobs = []
_local_jobs = []
_current_config = get_scoring_config("balanced")


def _score_for_storage(jobs):
    """Attach score/matches/redFlags so the DB stores meaningful values."""
    scored = []
    for job in jobs:
        score, goods, bads = score_job(job, _current_config)
        enriched = dict(job)
        enriched['score'] = score
        enriched['matches'] = goods
        enriched['redFlags'] = bads
        scored.append(enriched)
    return scored


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


def run_pipeline_global():
    global _pipeline_running, _global_jobs
    _pipeline_running = True
    try:
        print("=" * 50)
        print("  J-Search Pipeline Starting (GLOBAL)")
        print("=" * 50)

        remote_jobs = get_live_remote_jobs()
        rss_jobs = get_rss_remote_jobs()

        all_remote_combined = remote_jobs + rss_jobs
        all_remote = _deduplicate_jobs(all_remote_combined)
        _global_jobs = all_remote
        try:
            db.save_jobs(_score_for_storage(_global_jobs), 'global')
        except Exception:
            pass

        print()
        print(f"  Global jobs fetched : {len(_global_jobs)} (unique)")
        print()
        build_dashboard(remote_jobs=_global_jobs, local_leads=_local_jobs, config=_current_config)
        print("  Pipeline complete.")
    finally:
        _pipeline_running = False


def run_pipeline_local():
    global _pipeline_running, _local_jobs
    _pipeline_running = True
    try:
        print("=" * 50)
        print("  J-Search Pipeline Starting (LOCAL)")
        print("=" * 50)

        local_leads = get_local_merchants_ddg()
        all_local = _deduplicate_jobs(local_leads)
        _local_jobs = all_local
        try:
            db.save_jobs(_score_for_storage(_local_jobs), 'local')
        except Exception:
            pass

        print()
        print(f"  Local jobs fetched : {len(_local_jobs)} (unique)")
        print()
        build_dashboard(remote_jobs=_global_jobs, local_leads=_local_jobs, config=_current_config)
        print("  Pipeline complete.")
    finally:
        _pipeline_running = False


def run_pipeline_all():
    global _pipeline_running, _global_jobs, _local_jobs
    _pipeline_running = True
    try:
        print("=" * 50)
        print("  J-Search Pipeline Starting (ALL)")
        print("=" * 50)

        remote_jobs = get_live_remote_jobs()
        rss_jobs = get_rss_remote_jobs()
        local_leads = get_local_merchants_ddg()

        all_remote_combined = remote_jobs + rss_jobs
        all_remote = _deduplicate_jobs(all_remote_combined)
        all_local = _deduplicate_jobs(local_leads)
        _global_jobs = all_remote
        _local_jobs = all_local
        try:
            db.save_jobs(_score_for_storage(_global_jobs), 'global')
            db.save_jobs(_score_for_storage(_local_jobs), 'local')
        except Exception:
            pass

        print()
        print(f"  Global jobs fetched : {len(_global_jobs)} (unique)")
        print(f"  Local jobs fetched : {len(_local_jobs)} (unique)")
        print()
        build_dashboard(remote_jobs=_global_jobs, local_leads=_local_jobs, config=_current_config)
        print("  Pipeline complete.")
    finally:
        _pipeline_running = False


def _start_pipeline(mode):
    """Start a pipeline run in the background. Sets the running flag before
    returning so the loading page never sees a false 'done' state."""
    global _pipeline_running
    if _pipeline_running:
        return False

    target = {
        'global': run_pipeline_global,
        'local': run_pipeline_local,
        'all': run_pipeline_all,
    }.get(mode, run_pipeline_all)

    _pipeline_running = True
    threading.Thread(target=target, daemon=True).start()
    return True


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
        h1 { font-size: 22px; font-weight: 600; margin: 0; opacity: 0.95; }
        p { font-size: 15px; margin: 0; opacity: 0.7; }
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
            } catch (e) {}
        }
        checkStatus();
        setInterval(checkStatus, 1000);
    </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):

    def _jobs_from_db(self):
        """Load persisted jobs from SQLite when nothing is in memory."""
        global _global_jobs, _local_jobs
        try:
            if not _global_jobs:
                _global_jobs = db.get_jobs('global')
            if not _local_jobs:
                _local_jobs = db.get_jobs('local')
        except Exception as e:
            print('[DB] Could not load jobs:', e)

    def do_GET(self):
        global _pipeline_running
        
        if self.path == '/':
            self._jobs_from_db()
            try:
                build_dashboard(remote_jobs=_global_jobs, local_leads=_local_jobs, config=_current_config)
            except Exception as e:
                print('[Dashboard] Rebuild failed:', e)
            self._serve_file('dashboard.html', 'text/html; charset=utf-8')
        elif self.path.startswith('/run'):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            mode = params.get('mode', ['all'])[0]
            _start_pipeline(mode)
            self._respond(200, LOADING_PAGE.encode('utf-8'), 'text/html; charset=utf-8')
        elif self.path == '/status':
            status = {"running": _pipeline_running}
            body = json.dumps(status).encode('utf-8')
            self._respond(200, body, 'application/json')
        elif self.path == '/api/keywords':
            kws = db.get_keywords()
            body = json.dumps(kws).encode('utf-8')
            self._respond(200, body, 'application/json')
        elif self.path == '/api/jobs':
            self._jobs_from_db()
            all_jobs = []
            for job in _global_jobs:
                score, goods, bads = score_job(job, _current_config)
                if _is_blocked(job.get('url', '')):
                    continue
                all_jobs.append({
                    "title": job.get('title'),
                    "company": job.get('company'),
                    "location": job.get('location'),
                    "url": job.get('url'),
                    "desc": job.get('desc'),
                    "score": score,
                    "matches": goods,
                    "redFlags": bads,
                    "source": "global"
                })
            for job in _local_jobs:
                score, goods, bads = score_job(job, _current_config)
                if _is_blocked(job.get('url', '')):
                    continue
                all_jobs.append({
                    "title": job.get('title'),
                    "company": job.get('company'),
                    "location": job.get('location'),
                    "url": job.get('url'),
                    "desc": job.get('desc'),
                    "score": score,
                    "matches": goods,
                    "redFlags": bads,
                    "source": "local"
                })
            body = json.dumps(all_jobs).encode('utf-8')
            self._respond(200, body, 'application/json')
        else:
            self._respond(404, b'Not found')

    def do_POST(self):
        if self.path == '/refresh':
            _start_pipeline('all')
            self._respond(200, b'{"status":"ok"}', 'application/json')
        elif self.path == '/api/keywords/add':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
            try:
                data = json.loads(body)
                kw_type = data.get('type', 'focus')
                value = data.get('value', '')
                if value:
                    db.add_keyword(kw_type, value)
            except Exception:
                pass
            self._respond(200, b'{"status":"ok"}', 'application/json')
        elif self.path == '/api/keywords/delete':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
            try:
                data = json.loads(body)
                kw_type = data.get('type', 'focus')
                values = data.get('values', [])
                if values:
                    db.delete_keywords(kw_type, values)
            except Exception:
                pass
            self._respond(200, b'{"status":"ok"}', 'application/json')
        elif self.path == '/run':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
            try:
                data = json.loads(body)
                mode = data.get('mode', 'all')
            except Exception:
                mode = 'all'
            _start_pipeline(mode)
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
            self.send_header('Cache-Control', 'no-store, max-age=0')
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self._respond(404, b'Dashboard not found. Run scrapers first.')

    def _respond(self, code, body, content_type='text/plain'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(body))
        self.send_header('Cache-Control', 'no-store, max-age=0')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == '__main__':
    build_dashboard(remote_jobs=[], local_leads=[], config=_current_config)
    
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
