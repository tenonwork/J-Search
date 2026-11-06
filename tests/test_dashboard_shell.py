import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import job_dashboard


class DashboardShellTests(unittest.TestCase):
    def test_shell_embeds_static_assets_and_bootstrap(self):
        job = {
            'title': 'Platform Engineer',
            'company': 'Example Co',
            'location': 'Remote',
            'url': 'https://example.com/jobs/1',
            'desc': 'Build platform tooling with Python and React.',
        }

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'dashboard.html'
            with mock.patch.object(job_dashboard, 'DASHBOARD_PATH', target):
                job_dashboard.build_dashboard(
                    remote_jobs=[job],
                    local_leads=[],
                    config=job_dashboard.get_scoring_config('balanced'),
                    exclude_keys=set(),
                    applied_count=2,
                    dismissed_count=3,
                )

            html = target.read_text(encoding='utf-8')

        self.assertIn('/static/app.js', html)
        self.assertIn('/static/app.css', html)
        self.assertIn('/static/favicon-32.png', html)
        self.assertIn('window.__JSEARCH_BOOTSTRAP__ = ', html)
        self.assertNotIn('__BOOTSTRAP_JSON__', html)

        payload = html.split('window.__JSEARCH_BOOTSTRAP__ = ', 1)[1].split(
            ';</script>', 1
        )[0]
        data = json.loads(payload)

        self.assertEqual(data['appliedCount'], 2)
        self.assertEqual(data['dismissedCount'], 3)
        self.assertEqual(len(data['jobs']), 1)
        self.assertEqual(data['jobs'][0]['title'], 'Platform Engineer')
        self.assertEqual(data['jobs'][0]['source'], 'global')
        self.assertTrue(data['jobs'][0]['key'])

    def test_each_source_is_scored_with_its_own_config(self):
        job = {
            'title': 'Zebra Engineer',
            'company': 'Example Co',
            'location': 'Remote',
            'url': 'https://example.com/jobs/zebra',
            'desc': '',
        }
        global_config = job_dashboard.get_scoring_config('balanced', {
            'core_skills': ['react'],
            'ai_skills': [],
            'good_matches': [],
            'pos_skills': [],
            'dealbreakers': [],
            'core_weight': 10,
        })
        local_config = job_dashboard.get_scoring_config('balanced', {
            'core_skills': ['zebra'],
            'ai_skills': [],
            'good_matches': [],
            'pos_skills': [],
            'dealbreakers': [],
            'core_weight': 10,
        })

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'dashboard.html'
            with mock.patch.object(job_dashboard, 'DASHBOARD_PATH', target):
                job_dashboard.build_dashboard(
                    remote_jobs=[dict(job, url='https://example.com/jobs/global')],
                    local_leads=[dict(job, url='https://example.com/jobs/local')],
                    configs={'global': global_config, 'local': local_config},
                )

            html = target.read_text(encoding='utf-8')

        payload = html.split('window.__JSEARCH_BOOTSTRAP__ = ', 1)[1].split(
            ';</script>', 1
        )[0]
        data = json.loads(payload)
        scores = {item['source']: item['score'] for item in data['jobs']}
        self.assertEqual(scores['global'], 0)
        self.assertEqual(scores['local'], 10)


class AbortedDownloadTests(unittest.TestCase):
    def test_aborted_dashboard_write_does_not_propagate(self):
        import run

        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / 'dashboard.html'
            page.write_bytes(b'<html></html>')
            handler = run.DashboardHandler.__new__(run.DashboardHandler)
            handler.wfile = mock.Mock()
            handler.wfile.write.side_effect = ConnectionAbortedError()
            handler.send_response = mock.Mock()
            handler.send_header = mock.Mock()
            handler.end_headers = mock.Mock()

            run.DashboardHandler._serve_file(handler, page, 'text/html')

        handler.send_response.assert_called_once_with(200)
        handler.wfile.write.assert_called_once_with(b'<html></html>')


if __name__ == '__main__':
    unittest.main()
