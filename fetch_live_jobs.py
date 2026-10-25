import requests

def get_live_remote_jobs():
    """Fetch and format all live remote job listings from the Remotive API."""
    url = "https://remotive.com/api/remote-jobs"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    print("  [Remote Jobs] Connecting to Remotive API...")

    try:
        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            api_data = response.json()
            raw_jobs = api_data.get('jobs', [])

            print(f"  [Remote Jobs] Retrieved {len(raw_jobs)} live postings.")
            all_formatted_jobs = []

            for job in raw_jobs:
                formatted_job = {
                    "title": job.get("title", "Untitled Role"),
                    "company": job.get("company_name", "Unknown Company"),
                    "location": f"Remote ({job.get('candidate_required_location', 'Global')})",
                    "url": job.get("url", "#"),
                    "desc": job.get("description", "")
                }
                all_formatted_jobs.append(formatted_job)

            return all_formatted_jobs
        else:
            print(f"  [Remote Jobs] Server error. Status: {response.status_code}")
            return []

    except Exception as e:
        print(f"  [Remote Jobs] Connection failed: {e}")
        return []
