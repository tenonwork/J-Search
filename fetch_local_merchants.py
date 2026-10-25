import requests
import re
from bs4 import BeautifulSoup


# Search queries targeting actual tech job postings in East Africa
_SEARCH_QUERIES = [
    "software developer jobs nairobi kenya 2024",
    "junior developer jobs kenya remote",
]


def _scrape_ddg(search_term, headers):
    """Run a single DDG search and return raw result elements."""
    url = "https://html.duckduckgo.com/html/"
    try:
        response = requests.post(url, data={'q': search_term}, headers=headers, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            return soup.find_all('div', class_='result')
    except Exception:
        pass
    return []


def get_local_merchants_ddg():
    """
    Scrape local East African tech job postings from DuckDuckGo
    and format them for the dashboard.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    print(f"  [Local Jobs] Searching for East African tech job postings...")

    seen_urls = set()
    local_listings = []

    for query in _SEARCH_QUERIES:
        results = _scrape_ddg(query, headers)

        for result in results:
            title_element   = result.find('a', class_='result__a')
            snippet_element = result.find('a', class_='result__snippet')

            if not (title_element and snippet_element):
                continue

            raw_url     = title_element['href']
            # Deduplicate across queries
            if raw_url in seen_urls:
                continue
            seen_urls.add(raw_url)

            job_title   = title_element.text.strip()
            description = snippet_element.text.strip()

            # Trim overly long titles
            if len(job_title) > 60:
                job_title = job_title[:57] + "..."

            formatted_job = {
                "title": job_title,
                "company": "Local / East Africa",
                "location": "Local (Kenya / East Africa)",
                "url": raw_url,
                "desc": description
            }
            local_listings.append(formatted_job)

    print(f"  [Local Jobs] Found {len(local_listings)} local postings.")
    return local_listings

