import os
import re
from urllib.parse import urlparse



# --- PAYWALLED / GATED DOMAIN BLOCKLIST ---
# Any job whose URL resolves to one of these hosts is dropped before rendering.
BLOCKED_DOMAINS = {
    "remotive.com",       # API source — their own listing pages need a paid account
    "linkedin.com",
    "glassdoor.com",
    "ziprecruiter.com",
    "monster.com",
    "careerbuilder.com",
    "dice.com",
    "hired.com",
    "ladders.com",
    "simplyhired.com",
}


def _is_blocked(url: str) -> bool:
    """Return True if the URL's domain is on the blocklist."""
    try:
        host = urlparse(url).netloc.lower()
        # Strip leading 'www.' for a clean comparison
        host = host.removeprefix("www.")
        return any(host == blocked or host.endswith("." + blocked) for blocked in BLOCKED_DOMAINS)
    except Exception:
        return False



# --- SCORING ENGINE ---

def score_job(job):
    """Score a job listing using a weighted regex engine. Returns (score, good_matches, red_flags)."""
    score = 0
    text = (job['title'] + " " + job['desc']).lower()

    matches_found = []
    red_flags_found = []

    # Elite Core Stack (+8 points each)
    core_skills = [
        "postgresql", "supabase", "react native", "electron",
        "typescript", "react", "postgres", "expo", "fullstack", "full-stack", "backend"
    ]

    # Emerging & AI Stack (+5 points each)
    ai_and_infra = [
        "mcp", "model context protocol", "llm", "ai agent",
        "claude", "sqlite", "data science", "python"
    ]

    # Location & Level Preferences (+5 points each)
    good_matches = ["nairobi", "remote", "hybrid", "mid-level", "mid level", "contract", "point of sale"]

    # Hard Dealbreakers (-30 points each)
    dealbreakers = [
        "senior", "lead", "staff", "architect", "manager",
        "10+ years", "8+ years", "phd", "clearance required"
    ]

    # SPECIAL: Isolated "pos" word check
    if re.search(r'\bpos\b', text):
        score += 5
        matches_found.append("pos (system)")

    for word in core_skills:
        if re.search(r'\b' + re.escape(word) + r'\b', text):
            score += 8
            matches_found.append(word)

    for word in ai_and_infra:
        if re.search(r'\b' + re.escape(word) + r'\b', text):
            score += 5
            matches_found.append(word)

    for word in good_matches:
        if re.search(r'\b' + re.escape(word) + r'\b', text):
            score += 5
            matches_found.append(word)

    for word in dealbreakers:
        if re.search(r'\b' + re.escape(word) + r'\b', text):
            score -= 30
            red_flags_found.append(word)

    return score, matches_found, red_flags_found


# --- HTML CARD BUILDER ---

def _build_card(job):
    """Score a job and return an HTML card string, or None if it should be filtered out."""

    # Drop any listing sitting behind a paywalled / gated job board
    if _is_blocked(job.get('url', '')):
        return None

    score, goods, bads = score_job(job)

    is_local_lead = "Local" in job.get('location', '')

    # Hard drop for dealbreaker keywords on remote jobs
    if not is_local_lead and len(bads) > 0:
        return None

    # Minimum threshold: at least one positive keyword must match
    if not is_local_lead and score < 5:
        return None

    score_color = "#2563eb" if is_local_lead else (
        "#16a34a" if score >= 15 else "#ea580c" if score > 5 else "#dc2626"
    )

    good_badges = "".join([f'<span class="badge badge-good">{w}</span>' for w in goods])
    bad_badges  = "".join([f'<span class="badge badge-bad">{w}</span>'  for w in bads])

    return f"""
        <div class="card">
            <div class="info">
                <div class="title">{job['title']}</div>
                <div class="company">{job['company']} &bull; {job['location']}</div>
                <div>{good_badges}{bad_badges}</div>
                <a href="{job['url']}" target="_blank" class="btn">Review Entry &rarr;</a>
            </div>
            <div class="score-box">
                <div style="color: {score_color};" class="score">{score}</div>
                <div style="font-size: 12px; color: #64748b;">Match Rating</div>
            </div>
        </div>"""


def _build_section(title, emoji, jobs):
    """Return an HTML section string for a list of job/lead entries."""
    cards = [_build_card(j) for j in jobs]
    cards = [c for c in cards if c is not None]

    count_label = f"{len(cards)} match{'es' if len(cards) != 1 else ''}"

    cards_html = "\n".join(cards) if cards else '<p class="empty">No qualifying entries found for this source.</p>'

    return f"""
        <div class="section">
            <h2>{emoji} {title} <span class="section-count">{count_label}</span></h2>
            {cards_html}
        </div>"""


# --- DASHBOARD BUILDER ---

def build_dashboard(remote_jobs=None, local_leads=None):
    """
    Compile and open the unified job triage dashboard.

    Args:
        remote_jobs: List of job dicts from the Remotive API.
        local_leads:  List of business dicts from the local merchant scraper.
    """
    remote_jobs = remote_jobs or []
    local_leads  = local_leads  or []

    remote_section = _build_section("Remote Job Matches", "🌐", remote_jobs) if remote_jobs else ""
    local_section  = _build_section("Local Job Listings",  "📍", local_leads)  if local_leads  else ""

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Job Triage Dashboard</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f4f6f8;
            margin: 0;
            padding: 40px;
        }}
        .container {{ max-width: 960px; margin: auto; }}
        h1 {{ color: #1e293b; margin-bottom: 4px; }}
        .subtitle {{ color: #64748b; font-size: 14px; margin-bottom: 32px; }}
        .section {{ margin-bottom: 48px; }}
        h2 {{
            color: #1e293b;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 8px;
            margin-bottom: 16px;
            font-size: 20px;
        }}
        .section-count {{
            font-size: 13px;
            font-weight: normal;
            color: #64748b;
            margin-left: 8px;
        }}
        .card {{
            background: white;
            padding: 20px;
            margin-bottom: 16px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .info {{ flex-grow: 1; }}
        .title {{ font-size: 17px; font-weight: bold; color: #0f172a; margin: 0 0 4px 0; }}
        .company {{ color: #64748b; font-size: 13px; margin-bottom: 10px; }}
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
            margin-right: 4px;
        }}
        .badge-good {{ background: #dcfce7; color: #15803d; }}
        .badge-bad  {{ background: #fee2e2; color: #b91c1c; }}
        .score-box {{ text-align: center; margin-left: 24px; min-width: 72px; }}
        .score {{ font-size: 26px; font-weight: bold; }}
        .btn {{
            display: inline-block;
            background: #2563eb;
            color: white;
            text-decoration: none;
            padding: 8px 14px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            margin-top: 10px;
        }}
        .btn:hover {{ background: #1d4ed8; }}
        .empty {{ color: #94a3b8; font-style: italic; }}

        /* --- Refresh button --- */
        .refresh-btn {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #0f172a;
            color: white;
            border: none;
            padding: 9px 18px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
            margin-bottom: 28px;
        }}
        .refresh-btn:hover  {{ background: #1e293b; }}
        .refresh-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}

        /* --- Full-page loader overlay --- */
        #loader {{
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(15, 23, 42, 0.65);
            backdrop-filter: blur(4px);
            z-index: 999;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 20px;
            color: white;
        }}
        .spinner {{
            width: 52px;
            height: 52px;
            border: 5px solid rgba(255,255,255,0.2);
            border-top-color: #60a5fa;
            border-radius: 50%;
            animation: spin 0.9s linear infinite;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        #loader p {{ font-size: 16px; font-weight: 500; margin: 0; opacity: 0.9; }}
    </style>
</head>
<body>
    <!-- Full-page loader shown during refresh -->
    <div id="loader">
        <div class="spinner"></div>
        <p>Fetching new results&hellip;</p>
    </div>

    <div class="container">
        <h1>🎯 Job Triage Dashboard</h1>
        <p class="subtitle">All sources — review matches and click to open.</p>

        <button class="refresh-btn" id="refresh-btn" onclick="triggerRefresh()">
            🔄 Refresh Results
        </button>

        {remote_section}
        {local_section}
    </div>

    <script>
        async function triggerRefresh() {{
            const btn    = document.getElementById('refresh-btn');
            const loader = document.getElementById('loader');

            btn.disabled = true;
            loader.style.display = 'flex';

            const tryRefresh = async () => {{
                const res = await fetch('/refresh', {{ method: 'POST' }});
                if (res.status === 429) {{
                    // Pipeline already running — retry after 2 s
                    await new Promise(r => setTimeout(r, 2000));
                    return tryRefresh();
                }}
                if (!res.ok) throw new Error('Server error: ' + res.status);
            }};

            try {{
                await tryRefresh();
                location.reload();
            }} catch (e) {{
                loader.style.display = 'none';
                btn.disabled = false;
                alert('Refresh failed — is the server still running?\n\n' + e.message);
            }}
        }}
    </script>
</body>
</html>"""

    output_file = "dashboard.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\n✅ Dashboard compiled → {os.path.realpath(output_file)}")
