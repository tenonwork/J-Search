import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def _strip_html(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _fetch_workingnomads():
    """Working Nomads - public JSON feed (most reliable global source)."""
    url = "https://www.workingnomads.com/api/exposed_jobs/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return []
        jobs = []
        for job in r.json():
            location = job.get('location') or 'Remote'
            jobs.append({
                "title": job.get("title", "Untitled Role"),
                "company": job.get("company_name", "Unknown Company"),
                "location": "Remote (" + location + ")",
                "url": job.get("url", "#"),
                "desc": _strip_html(job.get("description", "")) + " " + (job.get("tags") or ""),
            })
        return jobs
    except Exception as e:
        print("  [Global][WorkingNomads] Failed: " + str(e))
        return []


def _fetch_remotive():
    """Remotive API."""
    url = "https://remotive.com/api/remote-jobs"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return []
        jobs = []
        for job in r.json().get('jobs', []):
            jobs.append({
                "title": job.get("title", "Untitled Role"),
                "company": job.get("company_name", "Unknown Company"),
                "location": "Remote (" + str(job.get('candidate_required_location', 'Global')) + ")",
                "url": job.get("url", "#"),
                "desc": job.get("description", "") or "",
            })
        return jobs
    except Exception as e:
        print("  [Global][Remotive] Failed: " + str(e))
        return []


def _fetch_jobicy():
    """Jobicy API."""
    url = "https://jobicy.com/api/v2/remote-jobs?count=50"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return []
        data = r.json()
        raw = data.get('jobs', []) if isinstance(data, dict) else data
        jobs = []
        for job in raw:
            location = job.get('jobLocation') or job.get('location') or 'Global'
            jobs.append({
                "title": job.get("jobTitle") or job.get("title", "Untitled Role"),
                "company": job.get("companyName") or job.get("company", "Unknown Company"),
                "location": "Remote (" + str(location) + ")",
                "url": job.get("url") or job.get("jobUrl") or "#",
                "desc": _strip_html(job.get("jobDescription") or job.get("description", "")),
            })
        return jobs
    except Exception as e:
        print("  [Global][Jobicy] Failed: " + str(e))
        return []


def get_live_remote_jobs():
    """Fetch live remote jobs from every reachable global source, in parallel."""
    print("  [Global] Fetching from remote job sources...")

    fetchers = [
        ("WorkingNomads", _fetch_workingnomads),
        ("Remotive", _fetch_remotive),
        ("Jobicy", _fetch_jobicy),
    ]

    all_jobs = []
    with ThreadPoolExecutor(max_workers=len(fetchers)) as executor:
        futures = {executor.submit(fn): name for name, fn in fetchers}
        for future in as_completed(futures):
            name = futures[future]
            try:
                jobs = future.result()
                if jobs:
                    print("  [Global][" + name + "] Retrieved " + str(len(jobs)) + " postings.")
                    all_jobs.extend(jobs)
            except Exception as e:
                print("  [Global][" + name + "] Error: " + str(e))

    return all_jobs
