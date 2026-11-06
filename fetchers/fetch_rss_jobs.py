import re
import feedparser
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# RSS summaries shorter than this are teasers, not full descriptions.
TEASER_DESCRIPTION_LIMIT = 400

_TITLE_NOISE = re.compile(
    r"\b(?:nurse|therapist|internship|werkstudent|sales|account executive)\b",
    re.IGNORECASE,
)
_HOW_TO = re.compile(r"\bhow to\b", re.IGNORECASE)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


RSS_FEEDS = [
    # We Work Remotely
    ("WeWorkRemotely", "https://weworkremotely.com/categories/remote-jobs.rss"),
    # Jobspresso
    ("Jobspresso", "https://jobspresso.co/feed/?post_type=job_listing"),
    # Remotive has RSS sometimes
    ("RemotiveRSS", "https://remotive.com/remote-jobs/rss"),
    # Otta/Welcome to the Jungle alternatives
    ("JobServe", "https://www.jobserve.com/gb/en/JobSearch.aspx?shid=RSS"),
    # EU Remote
    ("EU-Remote", "https://euremotejobs.com/rss/"),
]


def _clean_html(text):
    if not text:
        return ""
    # Basic cleanup
    import re
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _fetch_feed(source_name, feed_url):
    try:
        response = requests.get(feed_url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return []
        feed = feedparser.parse(response.content)
        jobs = []
        for entry in feed.entries[:30]:  # Limit per feed
            title = entry.get('title', 'Untitled Role')
            link = entry.get('link', '#')
            summary = entry.get('summary') or entry.get('description') or entry.get('content', [{}])[0].get('value', '') if entry.get('content') else ''
            if isinstance(summary, list):
                summary = summary[0].get('value', '') if summary else ''
            desc = _clean_html(summary)
            
            # Try to extract company from title or author
            company = entry.get('author') or entry.get('dc_creator') or source_name
            # Some feeds have "Company: Title" format
            if ':' in title and len(title.split(':')) == 2:
                company, title = title.split(':', 1)
                company = company.strip()
                title = title.strip()
            
            jobs.append({
                "title": title.strip(),
                "company": company.strip() if company else source_name,
                "location": "Remote",
                "url": link,
                "desc": desc,
                "teaser": len(desc) < TEASER_DESCRIPTION_LIMIT,
            })
        return jobs
    except Exception as e:
        print(f"  [RSS][{source_name}] Failed: {e}")
        return []


def get_rss_remote_jobs():
    """Fetch remote jobs from RSS feeds."""
    print("  [RSS Jobs] Fetching from RSS feeds...")
    
    all_jobs = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_source = {executor.submit(_fetch_feed, name, url): name for name, url in RSS_FEEDS}
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            try:
                jobs = future.result()
                if jobs:
                    print(f"  [RSS Jobs][{source}] Retrieved {len(jobs)} postings.")
                    all_jobs.extend(jobs)
            except Exception as e:
                print(f"  [RSS Jobs][{source}] Error: {e}")
    
    return all_jobs


def is_global_noise(job):
    """Drop blog posts and titles that are not software roles.

    EU Remote Jobs mixes articles into its feed. Nurse, sales and internship
    titles show up on the other boards too, so those are checked everywhere.
    """
    title = job.get('title') or ''
    url = (job.get('url') or '').lower()
    if 'euremotejobs.com' in url and ('/blog/' in url or _HOW_TO.search(title)):
        return True
    return _TITLE_NOISE.search(title) is not None


def without_global_noise(jobs):
    return [job for job in jobs if not is_global_noise(job)]
