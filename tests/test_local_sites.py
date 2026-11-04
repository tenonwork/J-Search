import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from app import db
from fetchers import fetch_career_sites as sites
from fetchers import fetch_local_merchants as local


COOP_ARCHIVE = 'https://www.co-opbank.co.ke/career_tax/co-op-bank/'
COOP_AI = 'https://www.co-opbank.co.ke/careers/co-op-bank/ai-integration-engineer/'
COOP_DATA = 'https://www.co-opbank.co.ke/careers/co-op-bank/data-engineer-8/'
COOP_MANAGER = 'https://www.co-opbank.co.ke/careers/co-op-bank/commercial-manager-youth-financial-services/'


def detail_page(title, description=''):
    return (
        '<!doctype html><html><head>'
        '<title>' + title + ' | Co-operative Bank of Kenya</title>'
        '<meta property="og:title" content="' + title + ' | Co-operative Bank of Kenya">'
        '<meta property="og:site_name" content="Co-operative Bank of Kenya">'
        '<meta name="description" content="' + description + '">'
        '</head><body><nav>Personal Banking Careers Contact</nav>'
        '<main><h1>' + title + '</h1><p>' + description + '</p></main></body></html>'
    )


ARCHIVE_PAGE = (
    '<!doctype html><html><head>'
    '<title>Co-op Bank Archives | Co-operative Bank of Kenya</title>'
    '<meta property="og:title" content="Co-op Bank Archives | Co-operative Bank of Kenya">'
    '</head><body>'
    '<nav><a href="/careers/">Careers</a><a href="/about">About us</a></nav>'
    '<main>'
    '<a href="/careers/co-op-bank/ai-integration-engineer/">Tell Me More</a>'
    '<a href="/careers/co-op-bank/data-engineer-8/">Tell Me More</a>'
    '<a href="/careers/co-op-bank/commercial-manager-youth-financial-services/">Tell Me More</a>'
    '<a href="/news/a-story">Read more</a>'
    '</main></body></html>'
)


class FakeResponse:
    def __init__(self, status, headers=None, body=b''):
        self.status_code = status
        self.headers = headers or {}
        self.body = body

    def iter_content(self, chunk_size=65536):
        if self.body:
            yield self.body

    def close(self):
        pass


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}

    def get(self, url, **kwargs):
        return self.responses.pop(0)

    def close(self):
        pass


class UrlTests(unittest.TestCase):
    def test_extract_urls_from_message(self):
        text = (
            'Apply here: https://shorturl.at/fRa0o.\n'
            'Another: https://example.com/jobs, and again https://shorturl.at/fRa0o'
        )
        self.assertEqual(
            sites.extract_urls(text),
            ['https://shorturl.at/fRa0o', 'https://example.com/jobs'],
        )

    def test_extract_bare_domain_and_limit(self):
        self.assertEqual(sites.extract_urls('shorturl.at/fRa0o'), ['shorturl.at/fRa0o'])
        text = '\n'.join('https://example.com/' + str(i) for i in range(6))
        self.assertEqual(len(sites.extract_urls(text)), 3)

    def test_normalize_url(self):
        self.assertEqual(
            sites.normalize_url('www.example.com/jobs#apply'),
            'https://www.example.com/jobs',
        )

    def test_rejects_unsafe_or_unusual_urls(self):
        for url in (
            'javascript:alert(1)',
            'file:///etc/passwd',
            'https://user:pass@example.com/jobs',
            'https://example.com:8080/jobs',
        ):
            with self.assertRaises(sites.SiteError):
                sites.normalize_url(url)

    def test_public_host_filter(self):
        self.assertFalse(sites.is_public_host('localhost'))
        self.assertFalse(sites.is_public_host('127.0.0.1'))
        self.assertFalse(sites.is_public_host('10.0.0.5'))
        self.assertFalse(sites.is_public_host('192.168.1.5'))
        self.assertFalse(sites.is_public_host('169.254.1.1'))

    @patch('fetchers.fetch_career_sites.socket.getaddrinfo')
    def test_public_and_private_dns(self, getaddrinfo):
        getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 0))
        ]
        self.assertTrue(sites.is_public_host('example.com'))

        getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.5', 0))
        ]
        self.assertFalse(sites.is_public_host('internal.example.com'))


class LinkFindingTests(unittest.TestCase):
    def test_finds_role_links_and_ignores_navigation(self):
        soup = BeautifulSoup(ARCHIVE_PAGE, 'html.parser')
        links = sites._find_job_links(soup, COOP_ARCHIVE)
        urls = [link['url'] for link in links]
        self.assertEqual(len(urls), 3)
        self.assertIn(
            'https://www.co-opbank.co.ke/careers/co-op-bank/ai-integration-engineer/',
            urls,
        )
        self.assertNotIn('https://www.co-opbank.co.ke/careers', urls)
        self.assertNotIn('https://www.co-opbank.co.ke/news/a-story', urls)

    def test_single_detail_title_is_not_a_listing(self):
        soup = BeautifulSoup(
            detail_page('AI Integration Engineer', 'Build integrations.'),
            'html.parser',
        )
        self.assertFalse(sites._is_listing_title(sites._page_title(soup)))
        self.assertTrue(sites._looks_like_job_title(sites._page_title(soup)))


class PageExtractionTests(unittest.TestCase):
    def test_extracts_clean_job_shape(self):
        soup = BeautifulSoup(
            detail_page('AI Integration Engineer', 'Build AI integrations with Python.'),
            'html.parser',
        )
        job = sites._job_from_page(COOP_AI, soup)
        self.assertEqual(job['title'], 'AI Integration Engineer')
        self.assertEqual(job['company'], 'Co-operative Bank of Kenya')
        self.assertEqual(job['location'], 'Local (Kenya / East Africa)')
        self.assertEqual(job['url'], COOP_AI)
        self.assertIn('Python', job['desc'])

    def test_all_role_types_are_kept(self):
        for title in (
            'Commercial Manager Youth Financial Services',
            'Human Resources Officer',
            'Data Engineer',
        ):
            soup = BeautifulSoup(
                detail_page(title, 'Hiring now.'),
                'html.parser',
            )
            job = sites._job_from_page(COOP_AI, soup)
            self.assertEqual(job['title'], title)


class ScanTests(unittest.TestCase):
    def _fake_fetch(self, pages):
        def fetch(url, session=None):
            if url not in pages:
                raise sites.SiteError('missing fixture: ' + url)
            return url, pages[url].encode('utf-8')
        return fetch

    def test_scan_listing_page_keeps_all_roles(self):
        pages = {
            COOP_ARCHIVE: ARCHIVE_PAGE,
            COOP_AI: detail_page('AI Integration Engineer', 'Python and APIs.'),
            COOP_DATA: detail_page('Data Engineer', 'SQL and Python.'),
            COOP_MANAGER: detail_page(
                'Commercial Manager Youth Financial Services', 'Sales leadership.'
            ),
        }
        with patch.object(sites, 'fetch_page', side_effect=self._fake_fetch(pages)):
            result = sites.scan_career_site({
                'url': COOP_ARCHIVE,
                'label': 'Co-operative Bank of Kenya',
            })
        self.assertEqual(result['resolved_url'], COOP_ARCHIVE)
        self.assertEqual(result['total_found'], 3)
        self.assertEqual(len(result['jobs']), 3)
        self.assertEqual(
            {job['title'] for job in result['jobs']},
            {
                'AI Integration Engineer',
                'Data Engineer',
                'Commercial Manager Youth Financial Services',
            },
        )
        self.assertEqual(result['warnings'], [])

    def test_single_job_link(self):
        pages = {COOP_AI: detail_page('AI Integration Engineer', 'Python.')}
        with patch.object(sites, 'fetch_page', side_effect=self._fake_fetch(pages)):
            result = sites.scan_career_site(COOP_AI)
        self.assertEqual(result['total_found'], 1)
        self.assertEqual(len(result['jobs']), 1)
        self.assertEqual(result['jobs'][0]['title'], 'AI Integration Engineer')

    def test_one_failed_detail_page_does_not_break_scan(self):
        pages = {
            COOP_ARCHIVE: ARCHIVE_PAGE,
            COOP_AI: detail_page('AI Integration Engineer', 'Python.'),
            COOP_DATA: detail_page('Data Engineer', 'SQL.'),
        }

        def fetch(url, session=None):
            if url == COOP_MANAGER:
                raise sites.SiteError('temporary failure')
            return self._fake_fetch(pages)(url, session)

        with patch.object(sites, 'fetch_page', side_effect=fetch):
            result = sites.scan_career_site(COOP_ARCHIVE)
        self.assertEqual(len(result['jobs']), 2)
        self.assertTrue(any('temporary failure' in warning for warning in result['warnings']))

    def test_no_job_links_returns_warning(self):
        page = '<html><head><title>Careers at Example</title></head><body><p>Nothing here.</p></body></html>'
        with patch.object(
            sites, 'fetch_page',
            side_effect=lambda url, session=None: (url, page.encode('utf-8')),
        ):
            result = sites.scan_career_site('https://example.com/careers')
        self.assertEqual(result['jobs'], [])
        self.assertTrue(result['warnings'])

    def test_private_url_is_rejected_before_fetch(self):
        with self.assertRaises(sites.SiteError):
            sites.fetch_page('http://127.0.0.1/secret')


class RedirectTests(unittest.TestCase):
    @patch('fetchers.fetch_career_sites.is_public_host', return_value=True)
    def test_follows_public_redirect(self, _public):
        session = FakeSession([
            FakeResponse(302, {'Location': 'https://example.com/jobs'}),
            FakeResponse(200, {'Content-Type': 'text/html'}, b'<html>ok</html>'),
        ])
        final_url, body = sites.fetch_page('https://shorturl.at/abc', session=session)
        self.assertEqual(final_url, 'https://example.com/jobs')
        self.assertEqual(body, b'<html>ok</html>')

    @patch('fetchers.fetch_career_sites.is_public_host')
    def test_rejects_redirect_to_private_address(self, public):
        public.side_effect = lambda host: host != '127.0.0.1'
        session = FakeSession([
            FakeResponse(302, {'Location': 'http://127.0.0.1/secret'}),
        ])
        with self.assertRaises(sites.SiteError):
            sites.fetch_page('https://shorturl.at/abc', session=session)


class DiscoveryQueryTests(unittest.TestCase):
    def test_queries_are_clean_deduplicated_and_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = db.DB_PATH
            db.DB_PATH = Path(tmp) / 'queries.db'
            try:
                self.assertEqual(db.get_discovery_queries(), [])
                self.assertTrue(db.save_discovery_queries([
                    '  Accounting jobs   Nairobi ',
                    'accounting jobs nairobi',
                    '',
                    42,
                    'x' * 200,
                ]))
                queries = db.get_discovery_queries()
                self.assertEqual(queries[0], 'Accounting jobs Nairobi')
                self.assertEqual(len(queries[-1]), 120)
                self.assertEqual(len(queries), 2)
            finally:
                db.DB_PATH = old_path

    def test_query_text_is_accepted(self):
        self.assertEqual(
            db.normalize_discovery_queries('sales jobs mombasa'),
            ['sales jobs mombasa'],
        )


class LocalBoardTests(unittest.TestCase):
    @staticmethod
    def _job(title, url):
        return {
            'title': title,
            'company': 'Board',
            'location': 'Local (Kenya / East Africa)',
            'url': url,
            'desc': title,
        }

    def test_board_results_keep_every_role_type_and_use_user_queries(self):
        board_jobs = [
            self._job('Commercial Manager', 'https://example.com/jobs/1'),
            self._job('Human Resources Officer', 'https://example.com/jobs/2'),
            self._job('Software Engineer', 'https://example.com/jobs/3'),
        ]
        with patch.object(local, '_scrape_brightermonday', return_value=board_jobs), \
                patch.object(local, '_scrape_jobsinkenya', return_value=[]), \
                patch.object(local, '_scrape_ddg', return_value=[]) as ddg:
            jobs = local.get_local_board_jobs(['sales jobs', 'accounting jobs'])

        self.assertEqual({job['title'] for job in jobs}, {job['title'] for job in board_jobs})
        self.assertEqual(ddg.call_count, 2)
        self.assertEqual(
            {call.args[0] for call in ddg.call_args_list},
            {'sales jobs', 'accounting jobs'},
        )

    def test_empty_queries_skip_web_search(self):
        with patch.object(local, '_scrape_brightermonday', return_value=[]), \
                patch.object(local, '_scrape_jobsinkenya', return_value=[]), \
                patch.object(local, '_scrape_ddg', return_value=[]) as ddg:
            self.assertEqual(local.get_local_board_jobs(), [])
        self.assertEqual(ddg.call_count, 0)


class LocalSiteSettingsTests(unittest.TestCase):
    def test_default_watchlist_and_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = db.DB_PATH
            db.DB_PATH = Path(tmp) / 'test.db'
            try:
                defaults = db.get_local_sites()
                self.assertEqual(len(defaults), 1)
                self.assertEqual(defaults[0]['url'], COOP_ARCHIVE)
                self.assertTrue(defaults[0]['enabled'])

                self.assertTrue(db.save_local_sites([]))
                self.assertEqual(db.get_local_sites(), [])

                saved = db.normalize_local_sites([
                    {'url': 'https://www.example.com/jobs/', 'label': 'Example'},
                    {'url': 'http://example.com/jobs', 'enabled': False},
                    {'url': 'javascript:alert(1)'},
                ])
                self.assertEqual(len(saved), 1)
                self.assertEqual(saved[0]['url'], 'https://www.example.com/jobs/')
                self.assertTrue(saved[0]['enabled'])
                self.assertTrue(db.save_local_sites(saved))
                self.assertEqual(db.get_local_sites(), saved)
            finally:
                db.DB_PATH = old_path


class LocalPipelineTests(unittest.TestCase):
    def test_saved_queries_are_passed_to_the_board_fetcher(self):
        import run

        with patch.object(run.db, 'get_discovery_queries', return_value=['accounting jobs']), \
                patch.object(run.db, 'get_local_sites', return_value=[]), \
                patch.object(run, 'get_local_board_jobs', return_value=[]) as board:
            self.assertEqual(run._fetch_local_jobs(), [])
        board.assert_called_once_with(['accounting jobs'])


if __name__ == '__main__':
    unittest.main()
