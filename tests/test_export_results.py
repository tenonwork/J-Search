import json
import unittest
from io import BytesIO
from unittest import mock

from docx import Document

from app import export_results


def _payload(fmt='json'):
    return {
        'format': fmt,
        'scope': 'global',
        'strictness': 'balanced',
        'sort': 'recommended',
        'highlight_keywords': ['react', 'python'],
        'jobs': [
            {
                'title': 'Platform Engineer',
                'company': 'Example Co',
                'location': 'Remote',
                'url': 'https://example.com/jobs/1',
                'source': 'global',
                'score': 18,
                'description': 'Build platform tooling with Python and React.',
                'matches': ['python', 'react'],
                'red_flags': ['senior'],
                'highlights': ['react'],
            },
            {
                'title': 'Data Analyst',
                'company': 'Northwind',
                'location': 'Nairobi',
                'url': 'https://example.com/jobs/2',
                'source': 'global',
                'score': 8,
                'description': 'SQL reporting for the local team.',
                'matches': ['sql'],
                'red_flags': [],
                'highlights': [],
            },
        ],
    }


class ExportResultsTests(unittest.TestCase):
    def test_json_includes_description_matches_flags_and_highlights(self):
        filename, content_type, body = export_results.build_export(_payload())
        data = json.loads(body)

        self.assertTrue(filename.endswith('.json'))
        self.assertIn('json', content_type)
        self.assertEqual(data['view']['scope'], 'global')
        self.assertEqual(data['view']['count'], 2)
        self.assertEqual(data['highlight_keywords'], ['react', 'python'])

        role = data['jobs'][0]
        self.assertEqual(role['title'], 'Platform Engineer')
        self.assertIn('Python and React', role['description'])
        self.assertIn('python', role['matches'])
        self.assertIn('senior', role['red_flags'])
        self.assertIn('react', role['highlights'])

    def test_docx_includes_the_same_fields(self):
        filename, content_type, body = export_results.build_export(_payload('docx'))
        document = Document(BytesIO(body))
        text = '\n'.join(paragraph.text for paragraph in document.paragraphs)

        self.assertTrue(filename.endswith('.docx'))
        self.assertIn('wordprocessingml', content_type)
        self.assertIn('Platform Engineer', text)
        self.assertIn('Build platform tooling with Python and React.', text)
        self.assertIn('python', text)
        self.assertIn('senior', text)
        self.assertIn('react', text)
        self.assertIn('Data Analyst', text)

    def test_empty_view_is_rejected(self):
        payload = _payload()
        payload['jobs'] = []
        with self.assertRaises(export_results.ExportError):
            export_results.build_export(payload)

    def test_endpoint_returns_the_json_download(self):
        import run

        raw = json.dumps(_payload()).encode('utf-8')
        handler = run.DashboardHandler.__new__(run.DashboardHandler)
        handler.headers = {'Content-Length': str(len(raw))}
        handler.rfile = BytesIO(raw)
        handler.path = '/api/export'
        sent = {}

        def respond(code, body, content_type='text/plain', extra_headers=None):
            sent['code'] = code
            sent['body'] = body
            sent['type'] = content_type
            sent['headers'] = extra_headers

        handler._respond = respond
        handler._respond_json = mock.Mock()
        run.DashboardHandler._handle_export(handler)

        self.assertEqual(sent['code'], 200)
        self.assertIn('json', sent['type'])
        self.assertIn('jsearch-global-', sent['headers']['Content-Disposition'])
        data = json.loads(sent['body'])
        self.assertEqual(data['jobs'][0]['title'], 'Platform Engineer')


if __name__ == '__main__':
    unittest.main()
