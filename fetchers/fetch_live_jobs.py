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


def _himalayas_job(job):
    """One Himalayas API job, using the apply link the API requires."""
    restrictions = job.get('locationRestrictions') or []
    places = [
        item.get('name') for item in restrictions
        if isinstance(item, dict) and item.get('name')
    ]
    description = _strip_html(job.get('description') or job.get('excerpt') or '')
    return {
        "title": job.get("title") or "Untitled Role",
        "company": job.get("companyName") or "Unknown Company",
        "location": "Remote (" + (", ".join(places) or "Worldwide") + ")",
        "url": job.get("applicationLink") or job.get("guid") or "#",
        "desc": description,
    }


def _fetch_himalayas():
    """Himalayas search API: recent worldwide roles with full descriptions.

    Five pages is enough to change the pool without walking the whole board.
    """
    url = "https://himalayas.app/jobs/api/search"
    jobs = []
    try:
        for page in range(1, 6):
            response = requests.get(url, headers=HEADERS, params={
                "worldwide": "true",
                "sort": "recent",
                "page": page,
            }, timeout=20)
            if response.status_code != 200:
                break
            batch = response.json().get('jobs') or []
            jobs.extend(_himalayas_job(job) for job in batch)
            if len(batch) < 20:
                break
        return jobs
    except Exception as e:
        print("  [Global][Himalayas] Failed: " + str(e))
        return jobs


def _remoteok_jobs(payload):
    """Remote OK's first JSON item is a legal banner, not a job."""
    jobs = []
    for job in payload or []:
        if not isinstance(job, dict) or not job.get('position'):
            continue
        tags = job.get('tags') or []
        if not isinstance(tags, list):
            tags = []
        jobs.append({
            "title": job.get("position") or "Untitled Role",
            "company": job.get("company") or "Unknown Company",
            "location": "Remote (" + str(job.get("location") or "Worldwide") + ")",
            "url": job.get("url") or job.get("apply_url") or "#",
            "desc": _strip_html(job.get("description") or "") + " " + " ".join(str(tag) for tag in tags),
        })
    return jobs


def _fetch_remoteok():
    """Remote OK public JSON. Descriptions are the full posting."""
    url = "https://remoteok.com/api"
    try:
        response = requests.get(url, headers=HEADERS, timeout=25)
        if response.status_code != 200:
            return []
        return _remoteok_jobs(response.json())
    except Exception as e:
        print("  [Global][RemoteOK] Failed: " + str(e))
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
        ("Himalayas", _fetch_himalayas),
        ("RemoteOK", _fetch_remoteok),
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
