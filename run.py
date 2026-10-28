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

from fetchers.fetch_live_jobs import get_live_remote_jobs
from fetchers.fetch_local_merchants import get_local_merchants_ddg
from fetchers.fetch_rss_jobs import get_rss_remote_jobs
from app.job_dashboard import build_dashboard, get_scoring_config, score_job, _is_blocked, job_key
from app.applied_page import build_decisions_page
from app.paths import DASHBOARD_PATH
from app import db

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
        key = job_key(job.get('url', ''), job.get('title', ''),
                      job.get('company', ''), job.get('location', ''))
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique


def _load_jobs_from_db():
    """Load persisted jobs from SQLite when nothing is in memory."""
    global _global_jobs, _local_jobs
    try:
        if not _global_jobs:
            _global_jobs = db.get_jobs('global')
        if not _local_jobs:
            _local_jobs = db.get_jobs('local')
    except Exception as e:
        print('[DB] Could not load jobs:', e)


def _decision_keys():
    try:
        return db.get_decision_keys()
    except Exception as e:
        print('[DB] Could not load decisions:', e)
        return set()


def _decision_counts():
    try:
        counts = db.get_decision_counts()
        return {
            'applied_count': counts.get('applied', 0),
            'dismissed_count': counts.get('dismissed', 0),
        }
    except Exception as e:
        print('[DB] Could not count decisions:', e)
        return {'applied_count': 0, 'dismissed_count': 0}


def _build_dashboard():
    counts = _decision_counts()
    build_dashboard(
        remote_jobs=_global_jobs,
        local_leads=_local_jobs,
        config=_current_config,
        exclude_keys=_decision_keys(),
        applied_count=counts['applied_count'],
        dismissed_count=counts['dismissed_count'],
    )


def _api_jobs():
    """Scored jobs for the JSON endpoint, minus applied/hidden postings."""
    exclude = _decision_keys()
    all_jobs = []
    for source, jobs in (('global', _global_jobs), ('local', _local_jobs)):
        for job in jobs:
            url = job.get('url', '')
            if _is_blocked(url):
                continue
            key = job_key(url, job.get('title', ''), job.get('company', ''),
                          job.get('location', ''))
            if key in exclude:
                continue
            score, goods, bads = score_job(job, _current_config)
            all_jobs.append({
                "key": key,
                "title": job.get('title'),
                "company": job.get('company'),
                "location": job.get('location'),
                "url": job.get('url'),
                "desc": job.get('desc'),
                "score": score,
                "matches": goods,
                "redFlags": bads,
                "source": source
            })
    return all_jobs


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
        _build_dashboard()
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
        _build_dashboard()
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
        _build_dashboard()
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

    def _read_json(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode('utf-8'))
        except Exception:
            return {}

    def _serve_decisions_page(self, status):
        try:
            decisions = db.get_decisions(status)
        except Exception as e:
            print('[DB] Could not load decisions:', e)
            decisions = []
        counts = _decision_counts()
        page = build_decisions_page(
            decisions, status,
            applied_count=counts['applied_count'],
            dismissed_count=counts['dismissed_count'],
        )
        self._respond(200, page.encode('utf-8'), 'text/html; charset=utf-8')

    def do_GET(self):
        global _pipeline_running
        path = urlparse(self.path).path

        if path == '/':
            _load_jobs_from_db()
            try:
                _build_dashboard()
            except Exception as e:
                print('[Dashboard] Rebuild failed:', e)
            self._serve_file(DASHBOARD_PATH, 'text/html; charset=utf-8')
        elif path.startswith('/run'):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            mode = params.get('mode', ['all'])[0]
            _start_pipeline(mode)
            self._respond(200, LOADING_PAGE.encode('utf-8'), 'text/html; charset=utf-8')
        elif path == '/status':
            status = {"running": _pipeline_running}
            body = json.dumps(status).encode('utf-8')
            self._respond(200, body, 'application/json')
        elif path == '/applied':
            self._serve_decisions_page('applied')
        elif path == '/hidden':
            self._serve_decisions_page('dismissed')
        elif path == '/api/keywords':
            kws = db.get_keywords()
            body = json.dumps(kws).encode('utf-8')
            self._respond(200, body, 'application/json')
        elif path == '/api/jobs':
            _load_jobs_from_db()
            body = json.dumps(_api_jobs()).encode('utf-8')
            self._respond(200, body, 'application/json')
        elif path == '/api/decisions':
            status = parse_qs(urlparse(self.path).query).get('status', [None])[0]
            if status not in ('applied', 'dismissed'):
                status = None
            body = json.dumps(db.get_decisions(status)).encode('utf-8')
            self._respond(200, body, 'application/json')
        else:
            self._respond(404, b'Not found')

    def do_POST(self):
        path = urlparse(self.path).path

        if path == '/refresh':
            _start_pipeline('all')
            self._respond(200, b'{"status":"ok"}', 'application/json')
        elif path == '/api/keywords/add':
            data = self._read_json()
            try:
                kw_type = data.get('type', 'focus')
                value = data.get('value', '')
                if value:
                    db.add_keyword(kw_type, value)
            except Exception:
                pass
            self._respond(200, b'{"status":"ok"}', 'application/json')
        elif path == '/api/keywords/delete':
            data = self._read_json()
            try:
                kw_type = data.get('type', 'focus')
                values = data.get('values', [])
                if values:
                    db.delete_keywords(kw_type, values)
            except Exception:
                pass
            self._respond(200, b'{"status":"ok"}', 'application/json')
        elif path == '/api/keywords/state':
            data = self._read_json()
            try:
                kw_type = data.get('type', 'focus')
                states = data.get('states', {})
                db.set_keyword_states(kw_type, states)
            except Exception:
                pass
            self._respond(200, b'{"status":"ok"}', 'application/json')
        elif path == '/api/decisions':
            data = self._read_json()
            key = str(data.get('key') or '').strip()[:500]
            status = data.get('status')
            if not key or status not in ('applied', 'dismissed'):
                self._respond(400, b'{"error":"invalid decision"}', 'application/json')
                return
            reason = str(data.get('reason') or '').strip()
            note = str(data.get('note') or '').strip()
            job = data.get('job') if isinstance(data.get('job'), dict) else {}
            ok = db.set_decision(key, status, reason, note, job)
            if not ok:
                self._respond(500, b'{"error":"could not save decision"}', 'application/json')
                return
            payload = {'status': 'ok'}
            payload.update(_decision_counts())
            self._respond(200, json.dumps(payload).encode('utf-8'), 'application/json')
        elif path == '/api/decisions/delete':
            data = self._read_json()
            key = str(data.get('key') or '').strip()[:500]
            ok = db.delete_decision(key) if key else True
            if not ok:
                self._respond(500, b'{"error":"could not delete decision"}', 'application/json')
                return
            payload = {'status': 'ok'}
            payload.update(_decision_counts())
            self._respond(200, json.dumps(payload).encode('utf-8'), 'application/json')
        elif path == '/run':
            data = self._read_json()
            mode = data.get('mode', 'all')
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
    _load_jobs_from_db()
    _build_dashboard()

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
