import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import db


def create_legacy_keywords_db(path, rows=None, profile=None, with_group=False):
    """Create a pre-workspace keywords table.

    ``with_group`` reproduces the retired custom-group schema. Both variants
    store one row per keyword and must migrate into Global and Local sets.
    """
    rows = rows or [
        ('focus', 'react', 1),
        ('exclude', 'senior', 0),
    ]
    conn = sqlite3.connect(path)
    if with_group:
        conn.execute('''CREATE TABLE keywords(
            id INTEGER PRIMARY KEY,
            type TEXT NOT NULL,
            value TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            keyword_group TEXT NOT NULL DEFAULT '',
            UNIQUE(type, value)
        )''')
        conn.executemany(
            'INSERT INTO keywords(type, value, enabled) VALUES(?, ?, ?)',
            rows,
        )
        conn.execute(
            "UPDATE keywords SET keyword_group='Frontend' WHERE value='react'"
        )
    else:
        conn.execute('''CREATE TABLE keywords(
            id INTEGER PRIMARY KEY,
            type TEXT,
            value TEXT UNIQUE,
            enabled INTEGER NOT NULL DEFAULT 1
        )''')
        conn.executemany(
            'INSERT INTO keywords(type, value, enabled) VALUES(?, ?, ?)',
            rows,
        )
    if profile is not None:
        conn.execute('''CREATE TABLE settings(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT ''
        )''')
        conn.execute(
            'INSERT INTO settings(key, value, updated_at) VALUES(?, ?, ?)',
            ('scoring_profile', json.dumps(profile), ''),
        )
    conn.commit()
    conn.close()


class LegacyKeywordMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.tempdir.name) / 'legacy.db'
        create_legacy_keywords_db(db.DB_PATH)

    def tearDown(self):
        db.DB_PATH = self.old_path
        self.tempdir.cleanup()

    def test_init_db_migrates_legacy_rows_into_both_scopes(self):
        db.init_db()

        global_rows = {row['value']: row for row in db.get_keyword_rows('global')}
        local_rows = {row['value']: row for row in db.get_keyword_rows('local')}

        self.assertTrue(global_rows['react']['enabled'])
        self.assertEqual(global_rows['react']['type'], 'focus')
        self.assertFalse(global_rows['senior']['enabled'])
        self.assertEqual(global_rows['senior']['type'], 'exclude')

        self.assertTrue(
            {'react', 'senior'} <= {row['value'] for row in local_rows.values()}
        )

        # Running init_db again must not rebuild or lose anything.
        db.init_db()
        self.assertEqual(db.add_keywords_bulk('focus', ['typescript']), 1)
        self.assertIn('typescript', {row['value'] for row in db.get_keyword_rows('global')})

    def test_duplicate_scoring_memberships_use_the_largest_absolute_weight(self):
        self.tempdir.cleanup()
        self.tempdir = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tempdir.name) / 'weights.db'
        create_legacy_keywords_db(
            db.DB_PATH,
            rows=[
                ('focus', 'react', 1),
                ('focus', 'python', 0),
                ('exclude', 'senior', 0),
            ],
            profile={
                'core_skills': ['react', 'python'],
                'core_weight': 5,
                'ai_skills': ['python'],
                'ai_weight': 10,
                'good_matches': ['react'],
                'good_weight': 5,
                'dealbreakers': ['senior'],
                'dealbreaker_weight': -30,
            },
        )

        db.init_db()

        rows = {row['value']: row for row in db.get_keyword_rows('global')}
        # python is in Core (5) and AI (10): AI wins.
        self.assertEqual(rows['python']['weight_group'], 'ai_skills')
        self.assertFalse(rows['python']['enabled'])
        # react ties at 5: Core wins the canonical order.
        self.assertEqual(rows['react']['weight_group'], 'core_skills')
        self.assertEqual(rows['senior']['weight_group'], 'dealbreakers')

        profile = db.get_scoring_profile()
        self.assertEqual(profile['core_weight'], 5)
        self.assertEqual(profile['ai_weight'], 10)
        self.assertNotIn('core_skills', profile)
        self.assertEqual(db.get_setting('keyword_workspace_version'), 2)

    def test_custom_keyword_groups_are_retired(self):
        self.tempdir.cleanup()
        self.tempdir = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.tempdir.name) / 'groups.db'
        create_legacy_keywords_db(db.DB_PATH, with_group=True)

        db.init_db()

        row = next(
            item for item in db.get_keyword_rows('global') if item['value'] == 'react'
        )
        self.assertNotIn('group', row)
        self.assertNotIn('keyword_group', row)
        self.assertEqual(row['weight_group'], 'core_skills')


class ProfileApplyTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.tempdir.name) / 'apply.db'
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old_path
        self.tempdir.cleanup()

    @staticmethod
    def _handler(run, payload):
        class FakeHandler:
            def _read_json(self):
                return payload

            def _respond_json(self, code, body):
                self.code = code
                self.body = body

        return FakeHandler()

    def _apply(self, run, payload):
        handler = self._handler(run, payload)
        with mock.patch.object(run, '_build_dashboard'), \
                mock.patch.object(run, '_load_scoring_profile'):
            run.DashboardHandler._handle_profile_apply(handler)
        return handler

    def test_apply_writes_only_the_selected_scope(self):
        import run

        handler = self._apply(run, {
            'profile': {
                'core_skills': ['zzz-skill'],
                'core_weight': 9,
            },
            'focus': ['zzz-skill'],
            'exclude': ['zzz-hide'],
            'scope': 'local',
            'strictness': 'balanced',
        })

        self.assertEqual(handler.code, 200)
        self.assertEqual(handler.body['scope'], 'local')
        self.assertEqual(handler.body['scopes'], ['local'])
        self.assertEqual(handler.body['focus_count'], 1)
        self.assertEqual(handler.body['exclude_count'], 1)

        local = {row['value']: row for row in db.get_keyword_rows('local')}
        global_rows = {row['value']: row for row in db.get_keyword_rows('global')}
        self.assertIn('zzz-skill', local)
        self.assertIn('zzz-hide', local)
        self.assertNotIn('zzz-skill', global_rows)
        self.assertNotIn('zzz-hide', global_rows)
        self.assertEqual(db.get_scoring_profile()['core_weight'], 9)
        self.assertNotIn('core_skills', db.get_scoring_profile())

    def test_apply_writes_both_scopes_when_requested(self):
        import run

        handler = self._apply(run, {
            'profile': {'core_skills': ['zzz-both'], 'core_weight': 7},
            'focus': ['zzz-both'],
            'exclude': [],
            'scope': 'both',
        })

        self.assertEqual(handler.code, 200)
        for scope in ('global', 'local'):
            values = {row['value'] for row in db.get_keyword_rows(scope)}
            self.assertIn('zzz-both', values)

    def test_replace_mode_clears_only_the_target_scope(self):
        import run

        db.add_keyword('focus', 'zzz-old-local', 'core_skills', 'local')
        db.add_keyword('focus', 'zzz-old-global', 'core_skills', 'global')

        handler = self._apply(run, {
            'profile': {'core_skills': ['zzz-new'], 'core_weight': 7},
            'focus': ['zzz-new'],
            'exclude': [],
            'scope': 'local',
            'mode': 'replace',
        })

        self.assertEqual(handler.code, 200)
        local = {row['value'] for row in db.get_keyword_rows('local')}
        global_rows = {row['value'] for row in db.get_keyword_rows('global')}
        self.assertNotIn('zzz-old-local', local)
        self.assertIn('zzz-new', local)
        self.assertIn('zzz-old-global', global_rows)

    def test_apply_reports_keyword_write_failure(self):
        import run

        handler = self._handler(run, {
            'profile': {'core_skills': ['react']},
            'focus': ['react'],
            'exclude': ['senior'],
            'scope': 'global',
        })

        with mock.patch.object(run, '_build_dashboard'), \
                mock.patch.object(run, '_load_scoring_profile'), \
                mock.patch.object(run.db, 'apply_profile_keywords', return_value=False):
            run.DashboardHandler._handle_profile_apply(handler)

        self.assertEqual(handler.code, 500)
        self.assertIn('Could not save', handler.body['error'])


class WeightSaveTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.tempdir.name) / 'weights.db'
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old_path
        self.tempdir.cleanup()

    @staticmethod
    def _handler(run, payload):
        class FakeHandler:
            def _read_json(self):
                return payload

            def _respond_json(self, code, body):
                self.code = code
                self.body = body

        return FakeHandler()

    def test_save_persists_weights_without_touching_keywords(self):
        import run

        db.add_keyword('focus', 'react', 'core_skills')
        keywords_before = [row['value'] for row in db.get_keyword_rows('global')]
        db.save_scoring_profile({'core_skills': ['haskell'], 'core_weight': 4})
        handler = self._handler(run, {'weights': {'core_weight': 12, 'dealbreaker_weight': -45}})

        with mock.patch.object(run, '_build_dashboard'), \
                mock.patch.object(run, '_load_scoring_profile'), \
                mock.patch.object(run, '_weights_payload', return_value={'status': 'ok'}):
            run.DashboardHandler._handle_weights_save(handler)

        self.assertEqual(handler.code, 200)
        profile = db.get_scoring_profile()
        self.assertEqual(profile['core_weight'], 12)
        self.assertEqual(profile['dealbreaker_weight'], -45)
        self.assertNotIn('core_skills', profile)
        self.assertEqual(
            [row['value'] for row in db.get_keyword_rows('global')],
            keywords_before,
        )

    def test_invalid_weight_payload_is_rejected(self):
        import run

        handler = self._handler(run, {'weights': {'core_skills': ['react'], 'unknown': 5}})

        with mock.patch.object(run, '_build_dashboard'), \
                mock.patch.object(run, '_load_scoring_profile'):
            run.DashboardHandler._handle_weights_save(handler)

        self.assertEqual(handler.code, 400)
        self.assertIn('numeric weight', handler.body['error'])


class WorkspaceEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.tempdir.name) / 'endpoint.db'
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old_path
        self.tempdir.cleanup()

    @staticmethod
    def _handler(run, payload=None, path='/api/keyword-workspace'):
        class FakeHandler:
            def __init__(self):
                self.path = path

            def _read_json(self):
                return payload

            def _respond_json(self, code, body):
                self.code = code
                self.body = body

        return FakeHandler()

    def test_get_returns_both_scopes_and_shared_weights(self):
        import run

        handler = self._handler(run)
        with mock.patch.object(run, '_workspace_payload', return_value={
            'weights': {'core_weight': 8},
            'scopes': {'global': [], 'local': []},
        }):
            run.DashboardHandler.do_GET(handler)

        self.assertEqual(handler.code, 200)
        self.assertEqual(handler.body['weights']['core_weight'], 8)
        self.assertEqual(set(handler.body['scopes']), {'global', 'local'})

    def test_post_rejects_a_missing_scope(self):
        import run

        handler = self._handler(run, {'weights': {'core_weight': 8}, 'scopes': {'global': []}})
        run.DashboardHandler.do_POST(handler)
        self.assertEqual(handler.code, 400)

    def test_post_saves_both_scopes(self):
        import run

        handler = self._handler(run, {
            'weights': {'core_weight': 6},
            'scopes': {
                'global': [{'value': 'zzz-g', 'weight_group': 'core_skills', 'type': 'focus'}],
                'local': [{'value': 'zzz-l', 'weight_group': 'core_skills', 'type': 'focus'}],
            },
        })
        with mock.patch.object(run, '_load_scoring_profile'), \
                mock.patch.object(run, '_build_dashboard'):
            run.DashboardHandler.do_POST(handler)

        self.assertEqual(handler.code, 200)
        self.assertEqual(
            [row['value'] for row in db.get_keyword_rows('global')],
            ['zzz-g'],
        )
        self.assertEqual(
            [row['value'] for row in db.get_keyword_rows('local')],
            ['zzz-l'],
        )
        self.assertEqual(db.get_scoring_profile()['core_weight'], 6)


if __name__ == '__main__':
    unittest.main()
