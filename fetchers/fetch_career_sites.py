"""Read job listings from user-managed company career pages.

Short links are resolved first. Listing pages are followed one level deep and
each role page is reduced to the same title/company/location/url/description
shape used by the other local fetchers.
"""

import ipaddress
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from .local_common import HEADERS, LOCAL_LOCATION, clean_text


REQUEST_TIMEOUT = 20
MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
MAX_DETAIL_PAGES = 25
MAX_SCAN_URLS = 3
DETAIL_WORKERS = 4

REDIRECT_CODES = {301, 302, 303, 307, 308}
ASSET_EXTENSIONS = (
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip',
    '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.mp4',
    '.mp3', '.css', '.js', '.xml', '.json',
)

URL_RE = re.compile(r'https?://[^\s<>"\']+', re.I)
BARE_URL_RE = re.compile(
    r'^(?:www\.)?[a-z0-9](?:[a-z0-9-]*[a-z0-9])?'
    r'(?:\.[a-z0-9-]+)+(?::\d+)?(?:/[^\s<>"\']*)?$',
    re.I,
)
ROLE_WORD_RE = re.compile(
    r'\b(engineer|developer|programmer|analyst|scientist|specialist|officer|'
    r'architect|manager|technician|administrator|consultant|intern|designer|'
    r'devops|sre|qa|lead|director|coordinator|assistant|accountant|clerk|'
    r'supervisor|head|sales|marketing|driver|nurse|teacher|lecturer|legal|'
    r'advocate|finance|financial|accounting|hr|operations|procurement|'
    r'logistics|customer|support|writer|editor|recruiter|research|'
    r'communications|secretary|receptionist|chef|security|pharmacist|clinical)\b',
    re.I,
)
LISTING_WORD_RE = re.compile(
    r'\b(careers?|jobs?|vacanc(?:y|ies)|openings?|positions?|opportunit(?:y|ies)|'
    r'archives?|search results|all roles|current openings)\b',
    re.I,
)
JOB_PATH_RE = re.compile(
    r'/(?:careers?|jobs?|vacanc(?:y|ies)|positions?|openings?|'
    r'opportunit(?:y|ies)|roles?|apply)(?:/|$)',
    re.I,
)
SECTION_PATHS = {
    '', '/', '/careers', '/career', '/jobs', '/job', '/vacancies',
    '/positions', '/openings', '/opportunities', '/about', '/contact',
    '/privacy', '/terms', '/login', '/search',
}


class SiteError(Exception):
    """A watched page could not be read safely."""


def _trim_url(url):
    return url.rstrip('.,;:!?)]}>}\'"’”').strip()


def extract_urls(text, limit=MAX_SCAN_URLS):
    """Pull links out of a pasted URL or a whole WhatsApp message."""
    text = str(text or '')
    matches = [_trim_url(match.group(0)) for match in URL_RE.finditer(text)]
    if not matches:
        candidate = _trim_url(text)
        if BARE_URL_RE.match(candidate):
            matches = [candidate]
    urls = []
    seen = set()
    for url in matches:
        key = url.lower()
        if not url or key in seen:
            continue
        seen.add(key)
        urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def normalize_url(value):
    """Return a clean public http(s) URL or raise SiteError."""
    if not isinstance(value, str):
        raise SiteError('Enter a link to scan.')
    url = value.strip()
    if not url:
        raise SiteError('Enter a link to scan.')
    if url.startswith('//'):
        url = 'https:' + url
    elif '://' not in url:
        url = 'https://' + url
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        raise SiteError('That link is not a valid URL.')

    if parsed.scheme.lower() not in ('http', 'https'):
        raise SiteError('Only http and https links are supported.')
    if not parsed.hostname:
        raise SiteError('That link has no host name.')
    if parsed.username or parsed.password:
        raise SiteError('Links with embedded usernames or passwords are not allowed.')
    if port not in (None, 80, 443):
        raise SiteError('Only standard web ports (80 and 443) are supported.')

    host = parsed.hostname.lower()
    netloc = host if port is None else host + ':' + str(port)
    if ':' in host and not host.startswith('['):
        netloc = '[' + host + ']' + ('' if port is None else ':' + str(port))
    return urlunparse((
        parsed.scheme.lower(), netloc, parsed.path or '/', '',
        parsed.query, '',
    ))


def _is_public_ip(address):
    return not (
        address.is_private or address.is_loopback or address.is_link_local
        or address.is_multicast or address.is_reserved or address.is_unspecified
    )


def is_public_host(host):
    """Reject localhost, private networks and unresolvable hosts."""
    host = (host or '').strip().lower().strip('[]')
    if not host:
        return False
    if (
        host == 'localhost'
        or host.endswith('.localhost')
        or host.endswith('.local')
        or host.endswith('.internal')
        or host.endswith('.lan')
        or host.endswith('.home')
    ):
        return False

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        return _is_public_ip(address)

    try:
        records = socket.getaddrinfo(host, None)
    except (socket.gaierror, OSError):
        return False
    if not records:
        return False
    for record in records:
        try:
            address = ipaddress.ip_address(record[4][0])
        except ValueError:
            return False
        if not _is_public_ip(address):
            return False
    return True


def _validate_public_url(url):
    parsed = urlparse(url)
    if not is_public_host(parsed.hostname or ''):
        raise SiteError('That address is not a public website.')
    return url


def _read_body(response):
    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_BYTES:
            raise SiteError('That page is larger than 2 MB.')
        chunks.append(chunk)
    return b''.join(chunks)


def fetch_page(url, session=None):
    """Fetch one HTML page, validating every redirect hop.

    Returns ``(final_url, body_bytes)``. Redirects are followed manually so a
    public short link cannot bounce the request into a private address.
    """
    current = normalize_url(url)
    owns_session = session is None
    if owns_session:
        session = requests.Session()
    session.headers.update(HEADERS)

    try:
        for _ in range(MAX_REDIRECTS + 1):
            _validate_public_url(current)
            try:
                response = session.get(
                    current,
                    headers=HEADERS,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=False,
                    stream=True,
                )
            except requests.RequestException as exc:
                raise SiteError('Could not reach that site (' + exc.__class__.__name__ + ').')

            try:
                if response.status_code in REDIRECT_CODES:
                    location = response.headers.get('Location')
                    if not location:
                        raise SiteError('The link redirected without a destination.')
                    current = normalize_url(urljoin(current, location))
                    continue
                if response.status_code != 200:
                    raise SiteError('The site returned HTTP ' + str(response.status_code) + '.')
                content_type = (response.headers.get('Content-Type') or '').split(';')[0].strip().lower()
                if content_type and not (
                    content_type.startswith('text/')
                    or content_type in ('application/xhtml+xml', 'application/xml')
                ):
                    raise SiteError('That link is not an HTML page.')
                return current, _read_body(response)
            finally:
                response.close()
    finally:
        if owns_session:
            session.close()

    raise SiteError('The link redirected too many times.')


def _meta_content(soup, *names):
    for name in names:
        tag = soup.find('meta', attrs={'property': name})
        if tag is None:
            tag = soup.find('meta', attrs={'name': name})
        if tag is not None:
            value = clean_text(tag.get('content') or '')
            if value:
                return value
    return ''


def _page_title(soup):
    title = _meta_content(soup, 'og:title', 'twitter:title')
    if not title and soup.title is not None:
        title = clean_text(soup.title.get_text(' '))
    if not title:
        heading = soup.find('h1')
        if heading is not None:
            title = clean_text(heading.get_text(' '))
    return clean_text(title)


def _title_suffix(title):
    if ' | ' in title:
        return title.rsplit(' | ', 1)[1].strip()
    for separator in (' – ', ' — '):
        if separator in title:
            return title.rsplit(separator, 1)[1].strip()
    return ''


def _strip_title_suffix(title, site_name=''):
    title = clean_text(title)
    if ' | ' in title:
        first = title.split(' | ', 1)[0].strip()
        if len(first) >= 4:
            title = first
    for separator in (' – ', ' — '):
        if separator in title:
            first = title.split(separator, 1)[0].strip()
            if len(first) >= 4:
                title = first
    if site_name:
        suffix = ' - ' + site_name
        if title.lower().endswith(suffix.lower()):
            title = title[:-len(suffix)].strip()
    return title


def _is_listing_title(title):
    return bool(LISTING_WORD_RE.search(title or ''))


def _looks_like_job_title(title):
    return bool(ROLE_WORD_RE.search(title or ''))


def _main_text(soup):
    """Readable page text with chrome removed, capped at 2,500 characters."""
    for tag in soup.find_all(['script', 'style', 'noscript', 'svg', 'form', 'header', 'footer', 'nav']):
        tag.decompose()
    container = None
    for selector in ('main', 'article', '[role="main"]', '.entry-content', '.job-description'):
        container = soup.select_one(selector)
        if container is not None:
            break
    container = container or soup.body or soup
    text = clean_text(container.get_text(' ', strip=True))
    return text[:2500]


def _host_key(host):
    host = (host or '').lower().removeprefix('www.')
    parts = host.split('.')
    if len(parts) >= 3 and parts[-2] in ('co', 'com', 'org', 'net', 'ac', 'gov', 'edu'):
        return '.'.join(parts[-3:])
    return '.'.join(parts[-2:])


def _path_depth(path):
    return len([part for part in (path or '').split('/') if part])


def _canonical_link(url):
    parsed = urlparse(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith('utm_')
        and key.lower() not in ('fbclid', 'gclid', 'mc_cid', 'mc_eid')
    ]
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path or '/',
        '',
        urlencode(query),
        '',
    ))


def _find_job_links(soup, base_url):
    """Find same-site links that look like individual role pages."""
    base = urlparse(base_url)
    base_host = _host_key(base.hostname or '')
    base_depth = _path_depth(base.path)
    links = []
    seen = set()

    for anchor in soup.find_all('a', href=True):
        href = (anchor.get('href') or '').strip()
        if not href or href.startswith(('#', 'mailto:', 'tel:', 'javascript:')):
            continue
        absolute = urljoin(base_url, href)
        try:
            parsed = urlparse(absolute)
        except ValueError:
            continue
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            continue
        if _host_key(parsed.hostname) != base_host:
            continue
        path = parsed.path or '/'
        if path.rstrip('/') == (base.path or '/').rstrip('/'):
            continue
        if path.lower().endswith(ASSET_EXTENSIONS):
            continue
        if path.rstrip('/') in SECTION_PATHS:
            continue

        text = clean_text(anchor.get_text(' '))[:200]
        depth = _path_depth(path)
        signal = bool(JOB_PATH_RE.search(path.lower()))
        role_word = bool(ROLE_WORD_RE.search(text))
        if depth <= base_depth and not role_word:
            continue

        score = (3 if signal else 0) + (2 if role_word else 0) + (1 if depth > base_depth else 0)
        if score < 3:
            continue

        canonical = _canonical_link(absolute)
        if canonical in seen:
            continue
        seen.add(canonical)
        links.append({'url': canonical, 'text': text})
        if len(links) >= 60:
            break
    return links


def _job_from_page(url, soup, fallback_label=''):
    raw_title = _page_title(soup)
    if not raw_title:
        return None
    site_name = _meta_content(soup, 'og:site_name') or _title_suffix(raw_title)
    title = _strip_title_suffix(raw_title, site_name)
    if not title or _is_listing_title(title):
        return None

    description = _meta_content(
        soup, 'og:description', 'twitter:description', 'description'
    )
    if not description:
        description = _main_text(soup)
        index = description.lower().find(title.lower())
        if index > 0:
            description = description[index:]
    host = urlparse(url).netloc.lower().removeprefix('www.')
    company = clean_text(site_name or fallback_label or host)[:200]
    return {
        'title': title[:200],
        'company': company or host,
        'location': LOCAL_LOCATION,
        'url': url,
        'desc': clean_text(description)[:3000],
    }


def scan_career_site(site, max_jobs=MAX_DETAIL_PAGES):
    """Resolve one link and return a reviewable list of roles.

    ``site`` may be a URL or a ``{"url", "label"}`` dictionary. The result is
    JSON-safe and contains no raw HTML.
    """
    if isinstance(site, str):
        site = {'url': site}
    if not isinstance(site, dict):
        raise SiteError('Enter a link to scan.')

    input_url = normalize_url(site.get('url'))
    final_url, body = fetch_page(input_url)
    soup = BeautifulSoup(body, 'html.parser')
    page_title = _page_title(soup)
    site_name = _meta_content(soup, 'og:site_name') or _title_suffix(page_title)
    label = clean_text(site.get('label') or site_name or '')[:120]
    if not label:
        label = urlparse(final_url).netloc.lower().removeprefix('www.')

    links = _find_job_links(soup, final_url)
    single_page = _looks_like_job_title(page_title) and not _is_listing_title(page_title)
    warnings = []
    jobs = []
    total_found = 0
    seen_jobs = set()

    def add_job(job):
        nonlocal total_found
        if not job:
            return
        total_found += 1
        key = _canonical_link(job['url'])
        if key in seen_jobs:
            return
        seen_jobs.add(key)
        jobs.append(job)

    if single_page:
        add_job(_job_from_page(final_url, soup, label))
    elif links:
        if len(links) > max_jobs:
            warnings.append(
                'Found ' + str(len(links)) + ' role links; scanned the first '
                + str(max_jobs) + '.'
            )
        with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
            futures = {
                executor.submit(fetch_page, link['url']): link['url']
                for link in links[:max_jobs]
            }
            for future in as_completed(futures):
                link_url = futures[future]
                try:
                    detail_url, detail_body = future.result()
                    detail_soup = BeautifulSoup(detail_body, 'html.parser')
                    add_job(_job_from_page(detail_url, detail_soup, label))
                except Exception as exc:
                    warnings.append(link_url + ': ' + str(exc))
    else:
        warnings.append(
            'No job links were found. Add a careers listing page or an individual role link.'
        )

    if not total_found and not warnings:
        warnings.append('No job roles were found on that page.')

    return {
        'input_url': input_url,
        'resolved_url': final_url,
        'domain': urlparse(final_url).netloc.lower().removeprefix('www.'),
        'label': label,
        'page_title': page_title,
        'jobs': jobs,
        'total_found': total_found,
        'warnings': warnings[:8],
    }


def get_career_site_jobs(sites):
    """Fetch every enabled watched page, isolating failures per site."""
    print('  [Local sites] Reading watched career pages...')
    all_jobs = []
    seen = set()
    for site in sites or []:
        if not isinstance(site, dict) or not site.get('enabled', True):
            continue
        label = site.get('label') or site.get('url') or 'Local site'
        try:
            result = scan_career_site(site)
        except Exception as exc:
            print('    [' + str(label) + '] Failed: ' + str(exc))
            continue
        for job in result['jobs']:
            key = _canonical_link(job.get('url', ''))
            if key in seen:
                continue
            seen.add(key)
            all_jobs.append(job)
        if result['jobs']:
            print('    [' + str(label) + '] ' + str(len(result['jobs'])) + ' role(s).')
        else:
            print('    [' + str(label) + '] No roles found.')
    print('  [Local sites] Found ' + str(len(all_jobs)) + ' role(s).')
    return all_jobs
