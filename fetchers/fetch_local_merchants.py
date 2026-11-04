import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

from .local_common import HEADERS, LOCAL_LOCATION, clean_text, is_tech_title

BRIGHTERMONDAY_PAGES = [
    "https://www.brightermonday.co.ke/jobs/software-data",
    "https://www.brightermonday.co.ke/jobs/it-software",
    "https://www.brightermonday.co.ke/jobs/engineering",
]

JOBSINKENYA_PAGES = [
    "https://www.jobsinkenya.co.ke/",
]

DDG_QUERIES = [
    "software developer jobs nairobi kenya",
    "junior developer jobs kenya remote",
    "react developer jobs nairobi",
]


def _scrape_brightermonday():
    """BrighterMonday Kenya - individual listing pages."""
    jobs = []
    seen = set()
    for page in BRIGHTERMONDAY_PAGES:
        try:
            r = requests.get(page, headers=HEADERS, timeout=20)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/listings/' not in href:
                    continue
                title = clean_text(a.get_text(' '))
                if len(title) < 6:
                    continue
                if not href.startswith('http'):
                    href = 'https://www.brightermonday.co.ke' + href
                if href in seen:
                    continue
                seen.add(href)
                jobs.append({
                    "title": title[:110],
                    "company": "BrighterMonday",
                    "location": LOCAL_LOCATION,
                    "url": href,
                    "desc": title,
                })
        except Exception as e:
            print("    [BrighterMonday] Failed: " + str(e))
    return jobs


def _scrape_jobsinkenya():
    """JobsInKenya - individual /job/ pages."""
    jobs = []
    seen = set()
    for page in JOBSINKENYA_PAGES:
        try:
            r = requests.get(page, headers=HEADERS, timeout=20)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/job/' not in href:
                    continue
                title = clean_text(a.get_text(' '))
                if len(title) < 6:
                    continue
                if not href.startswith('http'):
                    href = 'https://www.jobsinkenya.co.ke' + href
                if href in seen:
                    continue
                seen.add(href)
                jobs.append({
                    "title": title[:110],
                    "company": "JobsInKenya",
                    "location": LOCAL_LOCATION,
                    "url": href,
                    "desc": title,
                })
        except Exception as e:
            print("    [JobsInKenya] Failed: " + str(e))
    return jobs


def _scrape_ddg(query):
    """DuckDuckGo HTML search - optional extra source."""
    jobs = []
    try:
        r = requests.post("https://html.duckduckgo.com/html/",
                          data={'q': query}, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return jobs
        soup = BeautifulSoup(r.text, 'html.parser')
        for result in soup.find_all('div', class_='result'):
            a = result.find('a', class_='result__a')
            if not a:
                continue
            title = clean_text(a.get_text(' '))
            href = a.get('href', '')
            if not title or not href:
                continue
            snippet_el = result.find('a', class_='result__snippet')
            snippet = clean_text(snippet_el.get_text(' ')) if snippet_el else title
            jobs.append({
                "title": title[:110],
                "company": "Web search",
                "location": LOCAL_LOCATION,
                "url": href,
                "desc": snippet,
            })
    except Exception:
        pass
    return jobs


def get_local_merchants_ddg():
    """Fetch local East African job listings from all local sources."""
    print("  [Local] Searching for East African tech job postings...")

    seen_urls = set()
    local_listings = []

    def add(jobs):
        for job in jobs:
            if not is_tech_title(job['title']):
                continue
            if job['url'] in seen_urls:
                continue
            seen_urls.add(job['url'])
            local_listings.append(job)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_scrape_brightermonday): "BrighterMonday",
            executor.submit(_scrape_jobsinkenya): "JobsInKenya",
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                jobs = future.result()
                if jobs:
                    print("    [" + name + "] " + str(len(jobs)) + " listings.")
                add(jobs)
            except Exception as e:
                print("    [" + name + "] Error: " + str(e))

    # DuckDuckGo is rate-limited often - run it, but never depend on it
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_scrape_ddg, q) for q in DDG_QUERIES]
        for future in as_completed(futures):
            try:
                add(future.result())
            except Exception:
                pass

    print("  [Local] Found " + str(len(local_listings)) + " local postings.")
    return local_listings
