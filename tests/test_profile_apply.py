import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import db


def create_legacy_keywords_db(path):
    """Create the old schema that used a single-column UNIQUE(value)."""
    conn = sqlite3.connect(path)
    conn.execute('''CREATE TABLE keywords(
        id INTEGER PRIMARY KEY,
        type TEXT,
        value TEXT UNIQUE,
        enabled INTEGER NOT NULL DEFAULT 1
    )''')
    conn.execute(
        "INSERT INTO keywords(type, value, enabled) VALUES('focus', 'react', 1)"
    )
    conn.execute(
        "INSERT INTO keywords(type, value, enabled) VALUES('exclude', 'senior', 0)"
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

    def test_init_db_migrates_legacy_schema_and_preserves_rows(self):
        db.init_db()

        self.assertEqual(db.add_keywords_bulk('focus', ['python', 'senior']), 2)

        keywords = db.get_keywords()
        focus = {item['value']: item['enabled'] for item in keywords['focus']}
        exclude = {item['value']: item['enabled'] for item in keywords['exclude']}

        self.assertTrue(focus['react'])
        self.assertTrue(focus['python'])
        self.assertIn('senior', focus)
        self.assertFalse(exclude['senior'])

        # Running init_db again must not rebuild or lose anything.
        db.init_db()
        self.assertEqual(db.add_keywords_bulk('focus', ['typescript']), 1)


class ProfileApplyTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.tempdir.name) / 'apply.db'
        create_legacy_keywords_db(db.DB_PATH)

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

    def test_apply_writes_focus_and_exclude(self):
        import run

        payload = {
            'profile': {
                'core_skills': ['react'],
                'ai_skills': ['llm'],
                'good_matches': ['remote'],
                'dealbreakers': ['senior'],
                'core_weight': 9,
                'ai_weight': 5,
                'good_weight': 5,
                'dealbreaker_weight': -30,
            },
            'focus': ['react', 'llm'],
            'exclude': ['senior'],
            'strictness': 'balanced',
        }
        handler = self._handler(run, payload)

        with mock.patch.object(run, '_build_dashboard'), \
                mock.patch.object(run, '_load_scoring_profile'):
            run.DashboardHandler._handle_profile_apply(handler)

        self.assertEqual(handler.code, 200)
        self.assertEqual(handler.body['focus_count'], 2)
        self.assertEqual(handler.body['exclude_count'], 1)

        keywords = db.get_keywords()
        self.assertEqual(
            {item['value'] for item in keywords['focus']},
            {'react', 'llm'},
        )
        self.assertEqual(
            {item['value'] for item in keywords['exclude']},
            {'senior'},
        )
        self.assertEqual(db.get_scoring_profile()['core_weight'], 9)

    def test_apply_reports_keyword_write_failure(self):
        import run

        payload = {
            'profile': {'core_skills': ['react']},
            'focus': ['react'],
            'exclude': ['senior'],
            'strictness': 'balanced',
        }
        handler = self._handler(run, payload)

        with mock.patch.object(run, '_build_dashboard'), \
                mock.patch.object(run, '_load_scoring_profile'), \
                mock.patch.object(run.db, 'add_keywords_bulk', return_value=0):
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

        db.add_keywords_bulk('focus', ['react'])
        keywords_before = [item['value'] for item in db.get_keywords()['focus']]
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
        self.assertEqual(profile['core_skills'], ['haskell'])
        self.assertEqual(
            [item['value'] for item in db.get_keywords()['focus']],
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


class KeywordGroupTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.tempdir.name) / 'groups.db'
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old_path
        self.tempdir.cleanup()

    def _item(self, kw_type, value):
        return next(
            item for item in db.get_keywords()[kw_type] if item['value'] == value
        )

    def test_add_and_clear_a_group(self):
        self.assertTrue(db.add_keyword('focus', 'frontend', 'Frontend'))
        self.assertEqual(self._item('focus', 'frontend')['group'], 'Frontend')

        # Re-adding without a group must not erase the saved group.
        self.assertTrue(db.add_keyword('focus', 'frontend'))
        self.assertEqual(self._item('focus', 'frontend')['group'], 'Frontend')

        self.assertTrue(db.set_keyword_groups('focus', {'frontend': ''}))
        self.assertEqual(self._item('focus', 'frontend')['group'], '')

    def test_replace_keeps_groups_for_surviving_keywords(self):
        db.add_keyword('focus', 'react', 'UI')
        db.add_keyword('focus', 'python', 'Data')

        self.assertEqual(db.replace_keywords('focus', ['react', 'django']), 2)

        self.assertEqual(self._item('focus', 'react')['group'], 'UI')
        self.assertEqual(self._item('focus', 'django')['group'], '')

    def test_legacy_migration_adds_group_column(self):
        db.DB_PATH.unlink()
        create_legacy_keywords_db(db.DB_PATH)

        db.init_db()
        db.add_keyword('focus', 'react', 'Frontend')
        self.assertEqual(self._item('focus', 'react')['group'], 'Frontend')


if __name__ == '__main__':
    unittest.main()
