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


if __name__ == '__main__':
    unittest.main()
