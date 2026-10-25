import requests
from job_dashboard import build_dashboard # Keeps your dashboard interface perfectly intact

def get_live_remote_jobs():
    # Switching to Remotive's highly stable, open endpoint
    url = "https://remotive.com/api/remote-jobs"
    
    # Standard desktop browser identity
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print("Connecting to live remote job feed (via Remotive)...")
    
    try:
        # Requesting data with a 15-second timeout window
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            api_data = response.json()
            raw_jobs = api_data.get('jobs', []) # Remotive nests listings under 'jobs'
            
            print(f"Successfully retrieved {len(raw_jobs)} live job postings!")
            all_formatted_jobs = []
            
            # Map Remotive's fields cleanly to your dashboard interface requirements
            for job in raw_jobs:
                formatted_job = {
                    "title": job.get("title", "Untitled Role"),
                    "company": job.get("company_name", "Unknown Company"),
                    "location": f"Remote ({job.get('candidate_required_location', 'Global')})",
                    "url": job.get("url", "#"),
                    "desc": job.get("description", "") # Feeds full HTML body text into your scorer
                }
                all_formatted_jobs.append(formatted_job)
                
            return all_formatted_jobs
        else:
            print(f"Server rejected connection. Status code: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"An error occurred while connecting: {e}")
        return []

if __name__ == "__main__":
    # Fetch live jobs from the network
    live_jobs = get_live_remote_jobs()
    
    if live_jobs:
        print("Processing jobs through your custom scoring engine...")
        build_dashboard(live_jobs)
    else:
        print("No jobs found to display. Double-check your internet connection.")
