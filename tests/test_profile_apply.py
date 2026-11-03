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


if __name__ == '__main__':
    unittest.main()
