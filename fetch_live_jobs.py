import requests
from concurrent.futures import ThreadPoolExecutor, as_completed


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def _fetch_remotive():
    """Fetch from Remotive API."""
    url = "https://remotive.com/api/remote-jobs"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            api_data = response.json()
            raw_jobs = api_data.get('jobs', [])
            jobs = []
            for job in raw_jobs:
                jobs.append({
                    "title": job.get("title", "Untitled Role"),
                    "company": job.get("company_name", "Unknown Company"),
                    "location": f"Remote ({job.get('candidate_required_location', 'Global')})",
                    "url": job.get("url", "#"),
                    "desc": job.get("description", "") or job.get("description_plain", "") or "",
                })
            return jobs
        return []
    except Exception as e:
        print(f"  [Remote Jobs][Remotive] Failed: {e}")
        return []


def _fetch_jobicy():
    """Fetch from Jobicy API."""
    url = "https://jobicy.com/api/v2/remote-jobs?count=50"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            data = response.json()
            raw_jobs = data.get('jobs', []) if isinstance(data, dict) else data
            jobs = []
            for job in raw_jobs:
                location = job.get('jobLocation') or job.get('location') or 'Global'
                jobs.append({
                    "title": job.get("jobTitle") or job.get("title", "Untitled Role"),
                    "company": job.get("companyName") or job.get("company", "Unknown Company"),
                    "location": f"Remote ({location})" if location and 'remote' not in str(location).lower() else str(location),
                    "url": job.get("url") or job.get("jobUrl") or job.get("applyUrl") or "#",
                    "desc": job.get("jobDescription") or job.get("description", "") or "",
                })
            return jobs
        return []
    except Exception as e:
        print(f"  [Remote Jobs][Jobicy] Failed: {e}")
        return []


def _fetch_arbeitnow():
    """Fetch from Arbeitnow API."""
    url = "https://www.arbeitnow.com/api/job-board-api"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            data = response.json()
            raw_jobs = data.get('data', []) if isinstance(data, dict) else data
            jobs = []
            for job in raw_jobs:
                location = job.get('location') or 'Remote'
                jobs.append({
                    "title": job.get("title", "Untitled Role"),
                    "company": job.get("company_name") or job.get("company", "Unknown Company"),
                    "location": f"Remote ({location})" if 'remote' not in str(location).lower() else str(location),
                    "url": job.get("url") or "#",
                    "desc": job.get("description", "") or "",
                })
            return jobs
        return []
    except Exception as e:
        print(f"  [Remote Jobs][Arbeitnow] Failed: {e}")
        return []


def get_live_remote_jobs():
    """Fetch and format live remote job listings from multiple sources."""
    print("  [Remote Jobs] Fetching from multiple sources...")

    all_jobs = []
    fetchers = [
        ("Remotive", _fetch_remotive),
        ("Jobicy", _fetch_jobicy),
        ("Arbeitnow", _fetch_arbeitnow),
    ]

    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_source = {executor.submit(fetcher): name for name, fetcher in fetchers}
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            try:
                jobs = future.result()
                if jobs:
                    print(f"  [Remote Jobs][{source}] Retrieved {len(jobs)} postings.")
                    all_jobs.extend(jobs)
            except Exception as e:
                print(f"  [Remote Jobs][{source}] Error: {e}")

    return all_jobs
