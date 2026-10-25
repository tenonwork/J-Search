import requests
import json
from job_dashboard import build_dashboard # Imports your UI generator

def get_live_remote_jobs():
    url = "https://arbeitnow.com"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ToolingScraper/1.0"
    }
    
    all_formatted_jobs = []
    print("Connecting to live remote job feed...")
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            api_data = response.json()
            raw_jobs = api_data.get('data', [])
            
            print(f"Successfully retrieved {len(raw_jobs)} live job postings!")
            
            # Map the external API fields to match your Dashboard's structure
            for job in raw_jobs:
                formatted_job = {
                    "title": job.get("title", "Untitled Role"),
                    "company": job.get("company_name", "Unknown Company"),
                    "location": "Remote (" + ", ".join(job.get("location", ["Global"])) + ")",
                    "url": job.get("url", "#"),
                    "desc": job.get("description", "") # Full HTML/Text description for your scoring engine
                }
                all_formatted_jobs.append(formatted_job)
                
            return all_formatted_jobs
        else:
            print(f"Server responded with error code: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"An error occurred while connecting: {e}")
        return []

if __name__ == "__main__":
    # 1. Fetch live jobs from the network
    live_jobs = get_live_remote_jobs()
    
    if live_jobs:
        # 2. Feed them directly into your existing Dashboard UI and scoring engine!
        print("Processing jobs through your custom scoring engine...")
        build_dashboard(live_jobs)
    else:
        print("No jobs found to display.")
