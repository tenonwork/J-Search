"""
run.py — Unified J-Search pipeline entry point.

Starts a lightweight local HTTP server with a single-page dashboard.
Users can set filters/preferences, run Global/Local scrapes separately,
and filter/sort results client-side without re-scraping.

Usage:
    python run.py      (keep terminal open; Ctrl+C to stop)
"""

import os
import threading
import time
import webbrowser
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from fetchers.fetch_live_jobs import get_live_remote_jobs
from fetchers.fetch_local_merchants import get_local_merchants_ddg
from fetchers.fetch_rss_jobs import get_rss_remote_jobs
from app.job_dashboard import (
    build_dashboard, get_scoring_config, score_job, _is_blocked, _matches_skill,
    job_key, passes_filters, effective_profile,
)
from app.applied_page import build_decisions_page
from app.paths import DASHBOARD_PATH
from app import cv_import, cv_profile, db, llm_client

PORT = 8765
HOST = os.environ.get('JSEARCH_HOST', '127.0.0.1')

_pipeline_lock = threading.Lock()
_dashboard_lock = threading.Lock()
_pipeline_running = False
_global_jobs = []
_local_jobs = []
_scoring_profile = None
_current_config = get_scoring_config("balanced")


def _load_scoring_profile():
    global _scoring_profile, _current_config
    try:
        _scoring_profile = db.get_scoring_profile()
    except Exception as e:
        print('[DB] Could not load scoring profile:', e)
        _scoring_profile = None
    _current_config = get_scoring_config("balanced", _scoring_profile)


_load_scoring_profile()


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
    with _dashboard_lock:
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


def _enabled_keywords(kind):
    try:
        return [
            item['value'] for item in db.get_keywords().get(kind, [])
            if item.get('enabled')
        ]
    except Exception:
        return []


def _impact(profile, exclude, focus, strictness='balanced'):
    """Compare visibility under the current and proposed configurations."""
    if strictness not in ('strict', 'balanced', 'lenient'):
        strictness = 'balanced'
    current_config = get_scoring_config(strictness, _scoring_profile)
    proposed = get_scoring_config(strictness, profile)
    current_exclude = _enabled_keywords('exclude')
    current_focus = _enabled_keywords('focus')
    exclude = [value for value in (exclude or []) if value]
    focus = [value for value in (focus or []) if value]

    def visible(job, source, config, excludes):
        item = dict(job)
        item['source'] = source
        return passes_filters(item, config, strictness, excludes)

    def focused(job, keywords):
        text = ((job.get('title') or '') + ' ' + (job.get('desc') or '')).lower()
        return any(_matches_skill(text, keyword) for keyword in keywords)

    before = after = scoring_only = newly_highlighted = 0
    per_source = {}
    for source, jobs in (('global', _global_jobs), ('local', _local_jobs)):
        usable = [job for job in jobs if not _is_blocked(job.get('url', ''))]
        source_before = sum(
            1 for job in usable
            if visible(job, source, current_config, current_exclude)
        )
        source_scoring = sum(
            1 for job in usable
            if visible(job, source, proposed, current_exclude)
        )
        source_after = sum(
            1 for job in usable
            if visible(job, source, proposed, exclude)
        )
        per_source[source] = {'before': source_before, 'after': source_after}
        before += source_before
        scoring_only += source_scoring
        after += source_after
        for job in usable:
            if (
                visible(job, source, proposed, exclude)
                and focused(job, focus)
                and not focused(job, current_focus)
            ):
                newly_highlighted += 1

    return {
        'before': before,
        'after': after,
        'hidden_by_score': max(0, before - scoring_only),
        'hidden_by_exclude': max(0, scoring_only - after),
        'newly_visible': max(0, after - before),
        'newly_highlighted': newly_highlighted,
        'global': per_source['global'],
        'local': per_source['local'],
    }


def _api_profile():
    return {
        'profile': effective_profile(_scoring_profile),
        'effective': _current_config,
        'candidate': db.get_candidate_profile(),
        'reason_counts': db.get_decision_reason_counts(),
        'llm': llm_client.public_config(),
    }


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

    def _read_raw_body(self, limit):
        """Read a binary request body, refusing anything above ``limit``.

        Returns ``(body, error)`` where ``error`` is one of ``empty``,
        ``too_large`` or ``invalid``.
        """
        try:
            length = int(self.headers.get('Content-Length', 0))
        except (TypeError, ValueError):
            return None, 'invalid'
        if length <= 0:
            return None, 'empty'
        if length > limit:
            return None, 'too_large'
        try:
            return self.rfile.read(length), None
        except OSError:
            return None, 'invalid'

    def _handle_profile_extract(self):
        body, error = self._read_raw_body(cv_import.MAX_UPLOAD_BYTES)
        if error == 'too_large':
            self._respond_json(413, {'error': 'That file is larger than 10 MB.'})
            return
        if error == 'empty':
            self._respond_json(400, {'error': 'Choose a PDF, DOCX or TXT file first.'})
            return
        if error:
            self._respond_json(400, {'error': 'Could not read that upload.'})
            return

        try:
            result = cv_import.extract_text(body)
        except cv_import.ExtractError as exc:
            self._respond_json(400, {'error': str(exc)})
            return
        except Exception:
            # Never include parser details or file content in the response.
            self._respond_json(500, {'error': 'Could not read that file.'})
            return

        self._respond_json(200, result)

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

    def _respond_json(self, code, payload):
        body = json.dumps(payload).encode('utf-8')
        self._respond(code, body, 'application/json')

    def _handle_profile_analyze(self):
        data = self._read_json()
        cv_text = str(data.get('cv_text') or '')
        preferences = str(data.get('preferences') or '')
        if len(cv_text.strip()) < 40:
            self._respond_json(400, {'error': 'Paste a few lines of your CV first.'})
            return

        try:
            analysis, warnings = cv_profile.analyze_cv(cv_text)
        except llm_client.LLMError as exc:
            self._respond_json(503, {'error': str(exc)})
            return
        except Exception as exc:
            self._respond_json(500, {'error': 'Analysis failed: ' + str(exc)})
            return

        try:
            reason_counts = db.get_decision_reason_counts()
            proposal = cv_profile.build_proposal(
                analysis,
                preferences=preferences,
                current_profile=_scoring_profile,
                current_focus=_enabled_keywords('focus'),
                current_exclude=_enabled_keywords('exclude'),
                reason_counts=reason_counts,
            )
            proposal['warnings'] = warnings + proposal.get('warnings', [])
            db.save_candidate_profile(analysis)
            impact = _impact(
                proposal['profile'],
                [item['value'] for item in proposal['exclude'] if item['checked']],
                proposal['focus'],
                strictness=data.get('strictness', 'balanced'),
            )
        except Exception as exc:
            self._respond_json(500, {'error': 'Could not build the proposal: ' + str(exc)})
            return

        self._respond_json(200, {
            'proposal': proposal,
            'impact': impact,
            'reason_counts': reason_counts,
            'warnings': warnings,
        })

    def _handle_profile_preview(self):
        data = self._read_json()
        try:
            profile = cv_profile.clean_profile(data.get('profile') or {})
            focus = cv_profile.clean_keyword_list(data.get('focus') or [])
            exclude = cv_profile.clean_keyword_list(data.get('exclude') or [])
            impact = _impact(
                profile, exclude, focus,
                strictness=data.get('strictness', 'balanced'),
            )
        except Exception as exc:
            self._respond_json(400, {'error': 'Could not preview that profile: ' + str(exc)})
            return
        self._respond_json(200, {'impact': impact})

    def _handle_profile_apply(self):
        data = self._read_json()
        try:
            profile = cv_profile.clean_profile(data.get('profile') or {})
            focus = cv_profile.clean_keyword_list(data.get('focus') or [])
            exclude = cv_profile.clean_keyword_list(data.get('exclude') or [])
        except Exception as exc:
            self._respond_json(400, {'error': 'Invalid profile: ' + str(exc)})
            return

        if not db.save_scoring_profile(profile):
            self._respond_json(500, {'error': 'Could not save the scoring profile.'})
            return

        if data.get('mode') == 'replace':
            db.replace_keywords('focus', focus)
            db.replace_keywords('exclude', exclude)
        else:
            db.add_keywords_bulk('focus', focus)
            db.add_keywords_bulk('exclude', exclude)

        _load_scoring_profile()
        _build_dashboard()
        self._respond_json(200, {
            'status': 'ok',
            'reload': True,
            'focus_count': len(focus),
            'exclude_count': len(exclude),
        })

    def _handle_profile_reset(self):
        db.delete_setting('scoring_profile')
        _load_scoring_profile()
        _build_dashboard()
        self._respond_json(200, {'status': 'ok', 'reload': True})

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
        elif path == '/api/profile':
            self._respond_json(200, _api_profile())
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
        elif path == '/api/profile/extract':
            self._handle_profile_extract()
        elif path == '/api/profile/analyze':
            self._handle_profile_analyze()
        elif path == '/api/profile/preview':
            self._handle_profile_preview()
        elif path == '/api/profile/apply':
            self._handle_profile_apply()
        elif path == '/api/profile/reset':
            self._handle_profile_reset()
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

    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f'http://localhost:{PORT}'
    try:
        print(f'[Web] Dashboard live at {url} (bound to {HOST})')
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
