import requests
import re
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed


# Search queries targeting tech job postings in East Africa
_SEARCH_QUERIES = [
    "software developer jobs nairobi kenya",
    "junior developer jobs kenya remote",
    "web developer jobs kenya",
    "it jobs nairobi kenya",
    "software engineer jobs kenya",
    "react developer jobs nairobi",
    "python developer jobs kenya",
    "full stack developer jobs nairobi",
]


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _scrape_ddg(search_term):
    """Run a single DDG search and return raw result elements."""
    url = "https://html.duckduckgo.com/html/"
    try:
        response = requests.post(url, data={'q': search_term}, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            return soup.find_all('div', class_='result')
    except Exception as e:
        print(f"    [DDG] Failed for '{search_term[:30]}...': {e}")
    return []


def _scrape_brightermonday():
    """Scrape BrighterMonday Kenya for tech jobs."""
    jobs = []
    try:
        url = "https://www.brightermonday.co.ke/jobs/software-data"
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # Try common patterns
            for card in soup.find_all(['div', 'article'], class_=re.compile(r'job|listing|card', re.I))[:15]:
                title_elem = card.find(['h2', 'h3', 'a'], class_=re.compile(r'title|job.*title', re.I))
                if not title_elem:
                    title_elem = card.find('a')
                link_elem = card.find('a', href=True)
                if title_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    href = link_elem['href']
                    if href and title and len(title) > 5:
                        if not href.startswith('http'):
                            href = 'https://www.brightermonday.co.ke' + href
                        jobs.append({
                            "title": title[:80],
                            "company": "BrighterMonday",
                            "location": "Local (Kenya / East Africa)",
                            "url": href,
                            "desc": title,
                        })
    except Exception as e:
        print(f"    [BrighterMonday] Failed: {e}")
    return jobs


def _scrape_myjobmag():
    """Scrape MyJobMag Kenya for tech jobs."""
    jobs = []
    try:
        url = "https://www.myjobmag.co.ke/jobs-by-category/information-technology"
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            for card in soup.find_all(['li', 'div'], class_=re.compile(r'job|listing', re.I))[:15]:
                title_elem = card.find(['h2', 'h3', 'a'])
                link_elem = card.find('a', href=True)
                if title_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    href = link_elem['href']
                    if href and title and len(title) > 5 and 'job' in href.lower():
                        if not href.startswith('http'):
                            href = 'https://www.myjobmag.co.ke' + href
                        jobs.append({
                            "title": title[:80],
                            "company": "MyJobMag",
                            "location": "Local (Kenya / East Africa)",
                            "url": href,
                            "desc": title,
                        })
    except Exception as e:
        print(f"    [MyJobMag] Failed: {e}")
    return jobs


def get_local_merchants_ddg():
    """
    Scrape local East African tech job postings from multiple sources.
    """
    print(f"  [Local Jobs] Searching for East African tech job postings...")

    seen_urls = set()
    local_listings = []

    # Scrape via DuckDuckGo in parallel
    def scrape_query(query):
        return _scrape_ddg(query)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(scrape_query, q) for q in _SEARCH_QUERIES]
        for future in as_completed(futures):
            try:
                results = future.result()
                for result in results:
                    title_element = result.find('a', class_='result__a')
                    snippet_element = result.find('a', class_='result__snippet')
                    
                    if not title_element:
                        continue
                    
                    raw_url = title_element.get('href', '')
                    if not raw_url or raw_url in seen_urls:
                        continue
                    seen_urls.add(raw_url)
                    
                    job_title = title_element.text.strip()
                    description = snippet_element.text.strip() if snippet_element else job_title
                    
                    if len(job_title) > 80:
                        job_title = job_title[:77] + "..."
                    
                    local_listings.append({
                        "title": job_title,
                        "company": "Local / East Africa",
                        "location": "Local (Kenya / East Africa)",
                        "url": raw_url,
                        "desc": description
                    })
            except Exception:
                pass

    # Also try direct site scraping
    try:
        bm_jobs = _scrape_brightermonday()
        for job in bm_jobs:
            if job['url'] not in seen_urls:
                seen_urls.add(job['url'])
                local_listings.append(job)
    except Exception:
        pass

    try:
        mjm_jobs = _scrape_myjobmag()
        for job in mjm_jobs:
            if job['url'] not in seen_urls:
                seen_urls.add(job['url'])
                local_listings.append(job)
    except Exception:
        pass

    print(f"  [Local Jobs] Found {len(local_listings)} local postings.")
    return local_listings
