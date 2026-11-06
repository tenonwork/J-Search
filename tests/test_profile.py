import tempfile
import unittest
from pathlib import Path

from app import cv_profile, db, llm_client
from app.job_dashboard import (
    DEFAULT_SCORING_CONFIG,
    _matches_skill,
    get_scoring_config,
    merge_weight_overrides,
    normalize_scoring_profile,
    passes_filters,
    score_job,
    weights_view,
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


class WeightViewTests(unittest.TestCase):
    def test_view_exposes_every_weight_and_its_keywords(self):
        config = get_scoring_config('balanced', {
            'core_weight': 12,
            'dealbreaker_weight': -40,
        })
        view = weights_view(config)

        self.assertEqual(view['weights']['core_weight'], 12)
        self.assertEqual(view['weights']['dealbreaker_weight'], -40)
        self.assertEqual(len(view['groups']), 5)
        self.assertEqual(view['defaults']['core_weight'], 8)

        core = next(group for group in view['groups'] if group['key'] == 'core_weight')
        self.assertIn('react', core['keywords'])
        self.assertFalse(core['system'])

        pos = next(group for group in view['groups'] if group['key'] == 'pos_weight')
        self.assertFalse(pos['system'])
        self.assertEqual(pos['keywords'], ['pos'])

    def test_merge_changes_only_weights_and_keeps_lists(self):
        stored = {'core_skills': ['haskell'], 'core_weight': 4, 'ai_weight': 2}
        merged = merge_weight_overrides(stored, {
            'core_weight': 15,
            'ai_skills': ['ignored'],
            'unknown_field': 1,
        })
        self.assertEqual(merged['core_weight'], 15)
        self.assertEqual(merged['core_skills'], ['haskell'])
        self.assertEqual(merged['ai_weight'], 2)
        self.assertNotIn('ai_skills', merged)

    def test_merge_rejects_a_payload_without_weights(self):
        self.assertEqual(merge_weight_overrides({'core_weight': 4}, {'nope': 1}), {})
        self.assertEqual(merge_weight_overrides(None, 'not-a-dict'), {})


class SettingsTests(unittest.TestCase):
    def test_settings_round_trip_with_temp_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = db.DB_PATH
            db.DB_PATH = Path(tmp) / 'test.db'
            try:
                # A fresh database seeds the shared weights but no keyword lists.
                profile = db.get_scoring_profile()
                self.assertEqual(profile['core_weight'], 8)
                self.assertNotIn('core_skills', profile)

                self.assertTrue(db.save_scoring_profile({'core_weight': 12}))
                self.assertEqual(db.get_scoring_profile(), {'core_weight': 12})

                db.add_keywords_bulk('focus', ['Zzz React', 'zzz react', 'python'])
                values = [k['value'] for k in db.get_keywords('global')['focus']]
                self.assertEqual(values.count('zzz react'), 1)

                # The local set is independent.
                local_values = [k['value'] for k in db.get_keywords('local')['focus']]
                self.assertNotIn('zzz react', local_values)

                self.assertTrue(db.replace_keywords('exclude', ['senior']))
                self.assertEqual(
                    [k['value'] for k in db.get_keywords('global')['exclude']],
                    ['senior'],
                )

                self.assertTrue(db.delete_setting('scoring_profile'))
                self.assertIsNone(db.get_scoring_profile())
            finally:
                db.DB_PATH = old_path


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.tempdir.name) / 'workspace.db'
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old_path
        self.tempdir.cleanup()

    def _rows(self, scope):
        return {row['value']: row for row in db.get_keyword_rows(scope)}

    def test_add_keyword_under_a_weight_in_one_scope(self):
        self.assertTrue(db.add_keyword('focus', 'Zzz React', 'core_skills', 'local'))

        local = self._rows('local')['zzz react']
        self.assertEqual(local['weight_group'], 'core_skills')
        self.assertEqual(local['type'], 'focus')
        self.assertIn('zzz react', db.get_scoring_lists('local')['core_skills'])
        self.assertNotIn('zzz react', db.get_scoring_lists('global')['core_skills'])

    def test_pausing_stops_scoring_but_keeps_the_row(self):
        db.save_workspace(
            {'core_weight': 8},
            {
                'global': [
                    {'value': 'rust', 'weight_group': 'core_skills', 'type': 'focus',
                     'enabled': False},
                ],
                'local': [],
            },
        )
        self.assertIn('rust', self._rows('global'))
        self.assertNotIn('rust', db.get_scoring_lists('global')['core_skills'])
        self.assertFalse(self._rows('global')['rust']['enabled'])

    def test_save_workspace_replaces_both_scopes_atomically(self):
        weights = {
            'core_weight': 6,
            'ai_weight': 2,
            'good_weight': 1,
            'pos_weight': 3,
            'dealbreaker_weight': -20,
        }
        scopes = {
            'global': [
                {'value': 'react', 'weight_group': 'core_skills', 'type': 'focus'},
                {'value': 'react', 'weight_group': 'ai_skills', 'type': 'score'},
                {'value': 'senior', 'weight_group': 'dealbreakers', 'type': 'exclude'},
                {'value': 'remote', 'weight_group': '', 'type': 'focus'},
            ],
            'local': [
                {'value': 'till', 'weight_group': 'pos_skills', 'type': 'score'},
            ],
        }
        self.assertTrue(db.save_workspace(weights, scopes))

        global_rows = db.get_keyword_rows('global')
        local_rows = db.get_keyword_rows('local')
        self.assertEqual(len(global_rows), 3)
        self.assertEqual(len(local_rows), 1)
        self.assertEqual(db.get_keyword_rows('global')[0]['value'], 'react')
        self.assertNotIn('till', self._rows('global'))
        self.assertEqual(self._rows('local')['till']['weight_group'], 'pos_skills')
        self.assertEqual(db.get_scoring_profile(), weights)

    def test_save_workspace_rejects_a_payload_without_weights(self):
        self.assertFalse(db.save_workspace({}, {'global': [], 'local': []}))
        # The previous rows are untouched after a rejected save.
        self.assertTrue(db.get_keyword_rows('global'))

    def test_apply_profile_keywords_can_target_one_or_both_scopes(self):
        self.assertTrue(db.apply_profile_keywords(
            {'core_skills': ['haskell']},
            ['haskell'],
            ['cobol'],
            mode='add',
            scopes=['local'],
        ))
        self.assertIn('haskell', self._rows('local'))
        self.assertNotIn('haskell', self._rows('global'))
        self.assertIn('cobol', self._rows('local'))
        self.assertNotIn('cobol', self._rows('global'))

        self.assertTrue(db.apply_profile_keywords(
            {'core_skills': ['elixir']},
            ['elixir'],
            [],
            mode='add',
            scopes=['global', 'local'],
        ))
        self.assertIn('elixir', self._rows('global'))
        self.assertIn('elixir', self._rows('local'))

    def test_apply_profile_replace_only_clears_the_target_scope(self):
        db.add_keyword('focus', 'legacy-local', 'core_skills', 'local')
        db.add_keyword('focus', 'legacy-global', 'core_skills', 'global')

        self.assertTrue(db.apply_profile_keywords(
            {'core_skills': ['zig']},
            ['zig'],
            [],
            mode='replace',
            scopes=['local'],
        ))

        self.assertNotIn('legacy-local', self._rows('local'))
        self.assertIn('legacy-global', self._rows('global'))
        self.assertIn('zig', self._rows('local'))


class ScopedScoringTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.tempdir.name) / 'scoped.db'
        db.init_db()
        import run
        self.run = run
        self.old_profile = run._scoring_profile
        run._scoring_profile = db.get_scoring_profile()

    def tearDown(self):
        self.run._scoring_profile = self.old_profile
        db.DB_PATH = self.old_path
        self.tempdir.cleanup()

    def test_pos_is_an_editable_weight_group(self):
        self.assertTrue(db.add_keyword('focus', 'till', 'pos_skills', 'global'))

        config = self.run._config_for('global')
        self.assertIn('till', config['pos_skills'])
        score, matches, flags = score_job(
            {'title': 'Store assistant', 'desc': 'Work the till'}, config,
        )
        self.assertIn('till', matches)
        self.assertEqual(score, config['pos_weight'])
        self.assertFalse(flags)

        db.set_keyword_states('focus', {'till': False}, 'global')
        self.assertNotIn('till', self.run._config_for('global')['pos_skills'])

    def test_each_scope_uses_its_own_keyword_lists(self):
        self.assertTrue(db.save_workspace(
            {'core_weight': 9},
            {
                'global': [],
                'local': [
                    {'value': 'zebra', 'weight_group': 'core_skills', 'type': 'score'},
                ],
            },
        ))
        self.run._scoring_profile = db.get_scoring_profile()

        global_config = self.run._config_for('global')
        local_config = self.run._config_for('local')
        self.assertNotIn('zebra', global_config['core_skills'])
        self.assertIn('zebra', local_config['core_skills'])

        job = {'title': 'Zebra Engineer', 'desc': ''}
        self.assertEqual(score_job(job, global_config)[0], 0)
        self.assertEqual(score_job(job, local_config)[0], 9)


if __name__ == '__main__':
    unittest.main()
