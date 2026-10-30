import tempfile
import unittest
from pathlib import Path

from app import cv_profile, db, llm_client
from app.job_dashboard import (
    DEFAULT_SCORING_CONFIG,
    _matches_skill,
    get_scoring_config,
    normalize_scoring_profile,
    passes_filters,
    score_job,
)


class ScoringConfigTests(unittest.TestCase):
    def test_config_does_not_share_lists_with_defaults(self):
        config = get_scoring_config('balanced', {'core_skills': ['haskell']})
        config['core_skills'].append('rust')
        self.assertNotIn('rust', DEFAULT_SCORING_CONFIG['core_skills'])
        self.assertNotIn('haskell', DEFAULT_SCORING_CONFIG['core_skills'])

    def test_normalize_rejects_bad_values(self):
        clean = normalize_scoring_profile({
            'core_skills': ['React', 'react', '', None, 42, 'x' * 61, 'C++'],
            'core_weight': '999',
            'dealbreaker_weight': -1000,
            'min_score_remote': 1,
            'unknown': ['a'],
        })
        self.assertEqual(clean['core_skills'], ['react', 'c++'])
        self.assertEqual(clean['core_weight'], 100)
        self.assertEqual(clean['dealbreaker_weight'], -100)
        self.assertNotIn('min_score_remote', clean)
        self.assertNotIn('unknown', clean)

    def test_presets_own_thresholds_not_lists(self):
        config = get_scoring_config('strict', {'min_score_remote': 1})
        self.assertEqual(config['min_score_remote'], 10)
        self.assertTrue(config['enforce_dealbreakers_remote'])


class MatchingTests(unittest.TestCase):
    def test_word_boundary(self):
        self.assertTrue(_matches_skill('postgres and redis', 'postgres'))
        self.assertFalse(_matches_skill('postgresql only', 'postgres'))
        self.assertFalse(_matches_skill('position of trust', 'pos'))

    def test_literal_skills(self):
        self.assertTrue(_matches_skill('we use c++ daily', 'c++'))
        self.assertTrue(_matches_skill('we use .net daily', '.net'))
        self.assertTrue(_matches_skill('node.js and react', 'node.js'))

    def test_score_and_filters(self):
        job = {'title': 'Backend Engineer', 'desc': 'Python, postgres, remote', 'source': 'global'}
        score, matches, flags = score_job(job)
        self.assertGreater(score, 0)
        self.assertIn('python', matches)
        self.assertTrue(passes_filters(job))
        self.assertFalse(passes_filters(job, exclude_keywords=['python']))
        senior = {'title': 'Senior Backend Engineer', 'desc': 'Python', 'source': 'global'}
        self.assertFalse(passes_filters(senior))


class ScrubTests(unittest.TestCase):
    def test_contact_details_are_masked(self):
        text = 'Jane\njane@example.com\n+254 712 345 678\nhttps://github.com/jane\n@jane'
        clean = cv_profile.scrub_pii(text)
        self.assertIn('[email]', clean)
        self.assertIn('[phone]', clean)
        self.assertIn('[link]', clean)
        self.assertNotIn('jane@example.com', clean)

    def test_years_are_not_masked_as_phones(self):
        self.assertIn('2019 - 2023', cv_profile.scrub_pii('2019 - 2023'))

    def test_bare_profile_urls_are_masked(self):
        text = 'Portfolio: linkedin.com/in/jane-doe and github.com/janedoe'
        clean = cv_profile.scrub_pii(text)
        self.assertNotIn('linkedin.com/in', clean)
        self.assertNotIn('github.com/janedoe', clean)
        self.assertEqual(clean.count('[link]'), 2)


class ValidationTests(unittest.TestCase):
    def test_alias_and_blocklist(self):
        self.assertEqual(cv_profile.normalize_skill('ReactJS'), 'react')
        self.assertEqual(cv_profile.normalize_skill('ML'), 'machine learning')
        self.assertIsNone(cv_profile.normalize_skill('AI'))
        self.assertIsNone(cv_profile.normalize_skill('nonsense'))

    def test_validate_drops_unknown_and_unevidenced(self):
        raw = {'skills': [
            {'name': 'react', 'evidence': 'built ui'},
            {'name': 'react.js', 'evidence': 'duplicate'},
            {'name': 'nonsense', 'evidence': 'x'},
            {'name': 'python', 'evidence': ''},
        ]}
        analysis, warnings = cv_profile.validate_analysis(raw)
        self.assertEqual([s['name'] for s in analysis['skills']], ['react'])
        self.assertTrue(any('nonsense' in w.lower() for w in warnings))

    def test_parse_json_handles_fences(self):
        parsed = llm_client._parse_json('```json\n{"skills": []}\n```')
        self.assertEqual(parsed, {'skills': []})

    def test_parse_json_ignores_trailing_prose(self):
        parsed = llm_client._parse_json(
            'Here you go: {"skills": [{"name": "react"}]} Hope that helps.'
        )
        self.assertEqual(parsed['skills'][0]['name'], 'react')

    def test_parse_json_skips_stray_braces(self):
        parsed = llm_client._parse_json(
            'Use {curly braces} in JSON. Result: {"skills": []}'
        )
        self.assertEqual(parsed, {'skills': []})


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.analysis = {
            'skills': [
                {'name': 'react', 'evidence': 'ui', 'category': 'frontend'},
                {'name': 'llm', 'evidence': 'agents', 'category': 'ai'},
            ],
            'role_families': ['frontend'],
            'seniority': 'mid',
            'years_experience': 4,
        }

    def test_focus_and_exclude(self):
        proposal = cv_profile.build_proposal(
            self.analysis,
            preferences='no PHP, on-site only',
            current_focus=['react'],
            current_exclude=['senior'],
            reason_counts={'Not remote / location': 3},
        )
        self.assertIn('react', proposal['focus'])
        self.assertIn('llm', proposal['focus'])
        exclude = {item['value']: item for item in proposal['exclude']}
        self.assertIn('php', exclude)
        self.assertTrue(exclude['php']['checked'])
        self.assertIn('onsite', exclude)
        self.assertFalse(exclude['onsite']['checked'])
        self.assertIn('senior', exclude)

    def test_empty_analysis_keeps_existing_lists(self):
        proposal = cv_profile.build_proposal(
            {'skills': [], 'role_families': [], 'seniority': 'unknown', 'years_experience': None},
            current_profile={'core_skills': ['python']},
            current_focus=['python'],
        )
        self.assertEqual(proposal['profile']['core_skills'][0], 'python')
        self.assertIn('python', proposal['focus'])


class SettingsTests(unittest.TestCase):
    def test_settings_round_trip_with_temp_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = db.DB_PATH
            db.DB_PATH = Path(tmp) / 'test.db'
            try:
                self.assertIsNone(db.get_scoring_profile())
                self.assertTrue(db.save_scoring_profile({'core_skills': ['react']}))
                self.assertEqual(db.get_scoring_profile(), {'core_skills': ['react']})

                db.add_keywords_bulk('focus', ['React', 'react', 'python'])
                values = [k['value'] for k in db.get_keywords()['focus']]
                self.assertEqual(values.count('react'), 1)

                self.assertTrue(db.replace_keywords('exclude', ['senior']))
                self.assertEqual(
                    [k['value'] for k in db.get_keywords()['exclude']],
                    ['senior'],
                )

                self.assertTrue(db.delete_setting('scoring_profile'))
                self.assertIsNone(db.get_scoring_profile())
            finally:
                db.DB_PATH = old_path


if __name__ == '__main__':
    unittest.main()
