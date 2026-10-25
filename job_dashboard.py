import os
import webbrowser

# 1. Mock Data: This simulates what your scraper will eventually pull
mock_scraped_jobs = [
    {
        "title": "Junior Python Developer",
        "company": "TechStart Inc.",
        "location": "Remote (US)",
        "url": "https://indeed.com",
        "desc": "Looking for a junior engineer skilled in Python, SQL, and Git. No senior experience required."
    },
    {
        "title": "Senior Backend Architect",
        "company": "MegaCorp",
        "location": "Onsite - New York",
        "url": "https://indeed.com",
        "desc": "Requires 10+ years of experience leading teams. Expert Python and cloud systems architecture."
    },
    {
        "title": "Software Engineer Intern (Python)",
        "company": "DataFlow LLC",
        "location": "Remote",
        "url": "https://indeed.com",
        "desc": "Great opportunity for beginners. Learn Django, REST APIs, and Python development."
    }
]

# 2. The Smart Filter Engine
def score_job(job):
    score = 0
    text = (job['title'] + " " + job['desc']).lower()
    
    matches_found = []
    red_flags_found = []
    
    # 1. High Value - AI Native & Autonomy (+10 points each)
    # These match your pro-AI stance and self-directed building capabilities
    high_value_keywords = [
        "founding engineer", "sole developer", "mcp", "model context protocol", 
        "ai agent", "agentic", "ai tooling", "llm infrastructure", "mvp", "greenfield"
    ]
    
    # 2. Functional Full-Stack Stack (+6 points each)
    core_stack = [
        "postgresql", "supabase", "react native", "electron", "typescript", 
        "react", "postgres", "expo", "fullstack", "full-stack", "backend"
    ]
    
    # 3. Contextual Verticals (+5 points each)
    # Target spaces that match what you built for the retail system
    target_verticals = [
        "logistics", "supply chain", "pos", "point of sale", "retail tech", 
        "wholesale", "remote", "hybrid", "mombasa", "kisumu", "east africa"
    ]
    
    # 4. Corporate Filtering Red Flags (-15 points each)
    # Things that indicate corporate bureaucracy or anti-AI sentiment
    corporate_barriers = [
        "enterprise architecture", "agile scrum master", "5+ years corporate", 
        "10+ years corporate", "legacy migration", "manager of engineers",
        "phd required", "strict corporate", "no generative ai"
    ]
    
    # --- CALIBRATION ENGINE ---
    for word in high_value_keywords:
        if word in text:
            score += 10
            matches_found.append(word)
            
    for word in core_stack:
        if word in text:
            score += 6
            matches_found.append(word)
            
    for word in target_verticals:
        if word in text:
            score += 5
            matches_found.append(word)
            
    for word in corporate_barriers:
        if word in text:
            score -= 15
            red_flags_found.append(word)
            
    return score, matches_found, red_flags_found




# 3. The Dashboard Generator
def build_dashboard(jobs):
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>My Job Triage Dashboard</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f4f6f8; margin: 0; padding: 40px; }
            .container { max-width: 900px; margin: auto; }
            h1 { color: #1e293b; }
            .card { background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); display: flex; justify-content: space-between; align-items: center; }
            .info { flex-grow: 1; }
            .title { font-size: 18px; font-weight: bold; color: #0f172a; margin: 0 0 5px 0; }
            .company { color: #64748b; font-size: 14px; margin-bottom: 10px; }
            .badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-right: 5px; }
            .badge-good { background: #dcfce7; color: #15803d; }
            .badge-bad { background: #fee2e2; color: #b91c1c; }
            .score-box { text-align: center; margin-left: 20px; min-width: 80px; }
            .score { font-size: 24px; font-weight: bold; }
            .btn { display: inline-block; background: #2563eb; color: white; text-decoration: none; padding: 10px 16px; border-radius: 6px; font-weight: 500; margin-top: 10px; }
            .btn:hover { background: #1d4ed8; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎯 Job Match Dashboard</h1>
            <p>Review matches, click to open, and let your browser extension autofill the application safely.</p>
    """
    
    # Process each job and add it to the HTML layout
    for job in jobs:
        score, goods, bads = score_job(job)
        
        # Determine color based on score
        score_color = "#16a34a" if score > 0 else "#dc2626"
        
        good_badges = "".join([f'<span class="badge badge-good">{w}</span>' for w in goods])
        bad_badges = "".join([f'<span class="badge badge-bad">{w}</span>' for w in bads])
        
        html_content += f"""
            <div class="card">
                <div class="info">
                    <div class="title">{job['title']}</div>
                    <div class="company">{job['company']} • {job['location']}</div>
                    <div>{good_badges}{bad_badges}</div>
                    <a href="{job['url']}" target="_blank" class="btn">Review & Apply →</a>
                </div>
                <div class="score-box">
                    <div style="color: {score_color};" class="score">{score}</div>
                    <div style="font-size: 12px; color: #64748b;">Match Rating</div>
                </div>
            </div>
        """
        
    html_content += """
        </div>
    </body>
    </html>
    """
    
    # Save the file locally
    output_file = "dashboard.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    # Automatically open it in your default web browser
    webbrowser.open('file://' + os.path.realpath(output_file))

if __name__ == "__main__":
    build_dashboard(mock_scraped_jobs)
