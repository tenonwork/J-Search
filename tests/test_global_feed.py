import unittest
from pathlib import Path

from app.job_dashboard import _is_blocked, score_job
from fetchers.fetch_rss_jobs import is_global_noise, without_global_noise
import fetchers.fetch_live_jobs as live_jobs


class GlobalFeedFilterTests(unittest.TestCase):
    def test_arbeitnow_is_not_fetched(self):
        source = Path(live_jobs.__file__).read_text(encoding='utf-8').lower()
        self.assertNotIn('arbeitnow', source)

    def test_remotive_job_urls_are_not_blocked(self):
        self.assertFalse(_is_blocked('https://remotive.com/remote-jobs/software-engineer-123'))
        self.assertTrue(_is_blocked('https://www.linkedin.com/jobs/view/1'))

    def test_blog_posts_and_non_job_titles_are_dropped(self):
        jobs = [
            {'title': 'How to land a remote job', 'url': 'https://euremotejobs.com/blog/how-to-land'},
            {'title': 'Registered Nurse', 'url': 'https://jobicy.com/jobs/nurse'},
            {'title': 'Account Executive', 'url': 'https://example.com/ae'},
            {'title': 'Werkstudent Software', 'url': 'https://example.com/werk'},
            {'title': 'Forward Deployed Engineer', 'url': 'https://example.com/fde'},
        ]
        kept = without_global_noise(jobs)
        self.assertEqual([job['title'] for job in kept], ['Forward Deployed Engineer'])
        self.assertTrue(is_global_noise(jobs[0]))

    def test_teaser_scores_the_title_only(self):
        config = {
            'core_skills': ['react'],
            'core_weight': 10,
            'ai_skills': [],
            'good_matches': [],
            'pos_skills': [],
            'dealbreakers': [],
        }
        full = score_job({
            'title': 'Office Manager',
            'desc': 'We use React every day.',
        }, config)
        teaser = score_job({
            'title': 'Office Manager',
            'desc': 'We use React every day.',
            'teaser': True,
        }, config)
        self.assertEqual(full[0], 10)
        self.assertEqual(teaser[0], 0)
        titled = score_job({
            'title': 'React Engineer',
            'desc': 'Short teaser.',
            'teaser': True,
        }, config)
        self.assertEqual(titled[0], 10)


if __name__ == '__main__':
    unittest.main()
