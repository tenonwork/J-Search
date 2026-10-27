import os
import re
import json
from urllib.parse import urlparse


# --- PAYWALLED / GATED DOMAIN BLOCKLIST ---
BLOCKED_DOMAINS = {
    "remotive.com",
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


DEFAULT_SCORING_CONFIG = {
    "preset": "balanced",
    "core_skills": ["postgresql", "supabase", "react native", "electron", "typescript", "react", "postgres", "expo", "fullstack", "full-stack", "backend"],
    "core_weight": 8,
    "ai_skills": ["mcp", "model context protocol", "llm", "ai agent", "claude", "sqlite", "data science", "python"],
    "ai_weight": 5,
    "good_matches": ["nairobi", "remote", "hybrid", "mid-level", "mid level", "contract", "point of sale"],
    "good_weight": 5,
    "pos_weight": 5,
    "dealbreakers": ["senior", "lead", "staff", "architect", "manager", "10+ years", "8+ years", "phd", "clearance required"],
    "dealbreaker_weight": -30,
    "enforce_dealbreakers_remote": True,
    "min_score_remote": 5,
    "enforce_dealbreakers_local": False,
    "min_score_local": 0,
}


PRESETS = {
    "strict": {
        "core_weight": 8,
        "ai_weight": 5,
        "good_weight": 5,
        "pos_weight": 5,
        "dealbreaker_weight": -30,
        "enforce_dealbreakers_remote": True,
        "min_score_remote": 10,
        "enforce_dealbreakers_local": True,
        "min_score_local": 3,
    },
    "balanced": {
        "core_weight": 8,
        "ai_weight": 5,
        "good_weight": 5,
        "pos_weight": 5,
        "dealbreaker_weight": -30,
        "enforce_dealbreakers_remote": True,
        "min_score_remote": 5,
        "enforce_dealbreakers_local": False,
        "min_score_local": 0,
    },
    "lenient": {
        "core_weight": 8,
        "ai_weight": 5,
        "good_weight": 5,
        "pos_weight": 5,
        "dealbreaker_weight": -15,
        "enforce_dealbreakers_remote": False,
        "min_score_remote": 0,
        "enforce_dealbreakers_local": False,
        "min_score_local": -10,
    },
}


def get_scoring_config(preset=None, overrides=None):
    config = DEFAULT_SCORING_CONFIG.copy()
    if preset and preset in PRESETS:
        preset_config = PRESETS[preset].copy()
        config.update(preset_config)
        config["preset"] = preset
    if overrides:
        config.update(overrides)
    return config


def _is_blocked(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        host = host.removeprefix("www.")
        return any(host == blocked or host.endswith("." + blocked) for blocked in BLOCKED_DOMAINS)
    except Exception:
        return False


# --- SCORING ENGINE ---

def score_job(job, config=None):
    if config is None:
        config = DEFAULT_SCORING_CONFIG
    
    score = 0
    text = ((job.get('title', '') or '') + " " + (job.get('desc', '') or '')).lower()

    matches_found = []
    red_flags_found = []

    core_skills = config.get('core_skills', DEFAULT_SCORING_CONFIG['core_skills'])
    core_weight = config.get('core_weight', 8)
    
    ai_skills = config.get('ai_skills', DEFAULT_SCORING_CONFIG['ai_skills'])
    ai_weight = config.get('ai_weight', 5)
    
    good_matches = config.get('good_matches', DEFAULT_SCORING_CONFIG['good_matches'])
    good_weight = config.get('good_weight', 5)
    
    pos_weight = config.get('pos_weight', 5)
    dealbreakers = config.get('dealbreakers', DEFAULT_SCORING_CONFIG['dealbreakers'])
    dealbreaker_weight = config.get('dealbreaker_weight', -30)

    if re.search(r'\bpos\b', text):
        score += pos_weight
        matches_found.append("pos (system)")

    for word in core_skills:
        if re.search(r'\b' + re.escape(word) + r'\b', text):
            score += core_weight
            matches_found.append(word)

    for word in ai_skills:
        if re.search(r'\b' + re.escape(word) + r'\b', text):
            score += ai_weight
            matches_found.append(word)

    for word in good_matches:
        if re.search(r'\b' + re.escape(word) + r'\b', text):
            score += good_weight
            matches_found.append(word)

    for word in dealbreakers:
        if re.search(r'\b' + re.escape(word) + r'\b', text):
            score += dealbreaker_weight
            red_flags_found.append(word)

    return score, matches_found, red_flags_found


# --- HTML CARD BUILDER ---

def _build_card(job, config=None):
    if config is None:
        config = DEFAULT_SCORING_CONFIG

    if _is_blocked(job.get('url', '')):
        return None

    score, goods, bads = score_job(job, config)
    is_local_lead = "Local" in str(job.get('location', ''))

    if is_local_lead:
        if config.get('enforce_dealbreakers_local') and len(bads) > 0:
            return None
        if score < config.get('min_score_local', 0):
            return None
    else:
        if config.get('enforce_dealbreakers_remote') and len(bads) > 0:
            return None
        if score < config.get('min_score_remote', 5):
            return None

    score_color = "#2563eb" if is_local_lead else (
        "#16a34a" if score >= 15 else "#ea580c" if score > 5 else "#dc2626"
    )

    good_badges = "".join([f'<span class="badge badge-good">{w}</span>' for w in goods])
    bad_badges = "".join([f'<span class="badge badge-bad">{w}</span>' for w in bads])

    return {
        "html": f"""
        <div class="card" data-score="{score}" data-local="{'true' if is_local_lead else 'false'}">
            <div class="info">
                <div class="title">{job['title']}</div>
                <div class="company">{job['company']} &bull; {job['location']}</div>
                <div>{good_badges}{bad_badges}</div>
                <a href="{job['url']}" target="_blank" rel="noopener noreferrer" class="btn">Review Entry &rarr;</a>
            </div>
            <div class="score-box">
                <div style="color: {score_color};" class="score">{score}</div>
                <div style="font-size: 12px; color: #64748b;">Match Rating</div>
            </div>
        </div>""",
        "score": score,
        "is_local": is_local_lead,
        "job": job
    }


def _build_section_from_cards(title, emoji, cards_data):
    cards_data = sorted(cards_data, key=lambda x: x["score"], reverse=True)
    cards_html = "\n".join([c["html"] for c in cards_data]) if cards_data else '<p class="empty">No qualifying entries found for this view.</p>'
    count_label = f"{len(cards_data)} match{'es' if len(cards_data) != 1 else ''}"
    return f"""
        <div class="section">
            <h2>{emoji} {title} <span class="section-count">{count_label}</span></h2>
            {cards_html}
        </div>"""


# --- DASHBOARD BUILDER ---

def build_dashboard(remote_jobs=None, local_leads=None, config=None):
    remote_jobs = remote_jobs or []
    local_leads = local_leads or []
    if config is None:
        config = DEFAULT_SCORING_CONFIG

    # Score all jobs
    all_scored = []
    for job in remote_jobs:
        card = _build_card(job, config)
        if card:
            all_scored.append(card)
    for job in local_leads:
        card = _build_card(job, config)
        if card:
            all_scored.append(card)

    # Create three views
    recommended = []  # Strict-ish - high scores, dealbreakers enforced
    strict_config = get_scoring_config("strict")
    for job in remote_jobs + local_leads:
        card = _build_card(job, strict_config)
        if card and card["score"] >= (10 if not card["is_local"] else 3):
            recommended.append(card)
    recommended = list({id(c): c for c in recommended}.values())  # dedupe
    recommended = sorted(recommended, key=lambda x: x["score"], reverse=True)

    flexible = []
    lenient_config = get_scoring_config("lenient")
    for job in remote_jobs + local_leads:
        card = _build_card(job, lenient_config)
        if card:
            flexible.append(card)
    flexible = list({id(c): c for c in flexible}.values())
    flexible = sorted(flexible, key=lambda x: x["score"], reverse=True)

    browse = sorted(all_scored, key=lambda x: x["score"], reverse=True)
    browse_remote = [c for c in browse if not c["is_local"]]
    browse_local = [c for c in browse if c["is_local"]]

    recommended_html = "\n".join([c["html"] for c in recommended]) if recommended else '<p class="empty">No recommended matches with strict filtering.</p>'
    flexible_html = "\n".join([c["html"] for c in flexible]) if flexible else '<p class="empty">No matches in flexible view.</p>'
    browse_html = "\n".join([c["html"] for c in browse]) if browse else '<p class="empty">No qualifying entries found.</p>'
    browse_remote_html = "\n".join([c["html"] for c in browse_remote]) if browse_remote else '<p class="empty">No remote matches.</p>'
    browse_local_html = "\n".join([c["html"] for c in browse_local]) if browse_local else '<p class="empty">No local matches.</p>'

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
        .subtitle {{ color: #64748b; font-size: 14px; margin-bottom: 24px; }}
        .header-row {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }}
        .actions {{ display: flex; gap: 10px; flex-wrap: wrap; }}
        .btn-link {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: white;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.2s;
        }}
        .btn-link:hover {{ background: #f8fafc; border-color: #94a3b8; }}
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
        }}
        .refresh-btn:hover {{ background: #1e293b; }}
        .tabs {{
            display: flex;
            gap: 8px;
            margin-bottom: 28px;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 0;
            flex-wrap: wrap;
        }}
        .tab-btn {{
            background: none;
            border: none;
            padding: 10px 20px;
            font-size: 14px;
            font-weight: 600;
            color: #64748b;
            cursor: pointer;
            border-bottom: 2px solid transparent;
            margin-bottom: -2px;
            transition: all 0.2s;
        }}
        .tab-btn.active {{
            color: #0f172a;
            border-bottom-color: #2563eb;
        }}
        .tab-btn:hover {{ color: #0f172a; }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        .section {{ margin-bottom: 48px; }}
        .section-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .subtabs {{
            display: flex;
            gap: 6px;
            background: #e2e8f0;
            padding: 4px;
            border-radius: 8px;
        }}
        .subtab-btn {{
            background: none;
            border: none;
            padding: 6px 14px;
            font-size: 12px;
            font-weight: 600;
            color: #475569;
            cursor: pointer;
            border-radius: 6px;
            transition: all 0.2s;
        }}
        .subtab-btn.active {{
            background: white;
            color: #0f172a;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }}
        .subtab-content {{ display: none; }}
        .subtab-content.active {{ display: block; }}
        h2 {{
            color: #1e293b;
            margin: 0;
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
        .badge-bad {{ background: #fee2e2; color: #b91c1c; }}
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
        .empty {{ color: #94a3b8; font-style: italic; padding: 20px; text-align: center; background: white; border-radius: 8px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header-row">
            <div>
                <h1>🎯 Job Triage Dashboard</h1>
                <p class="subtitle">All sources — review matches and click to open.</p>
            </div>
            <div class="actions">
                <a class="btn-link" href="/">⚙️ Adjust Filters</a>
                <button class="refresh-btn" onclick="window.location.href='/refresh'">
                    🔄 Refresh Results
                </button>
            </div>
        </div>

        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('recommended')">⭐ Recommended</button>
            <button class="tab-btn" onclick="switchTab('flexible')">✨ Flexible</button>
            <button class="tab-btn" onclick="switchTab('browse')">🔍 Browse All</button>
        </div>

        <div id="tab-recommended" class="tab-content active">
            <div class="section">
                <div class="section-header">
                    <h2>⭐ Most Recommended <span class="section-count">{len(recommended)} match{'es' if len(recommended) != 1 else ''}</span></h2>
                </div>
                {recommended_html}
            </div>
        </div>

        <div id="tab-flexible" class="tab-content">
            <div class="section">
                <div class="section-header">
                    <h2>✨ Flexible Matches <span class="section-count">{len(flexible)} match{'es' if len(flexible) != 1 else ''}</span></h2>
                </div>
                {flexible_html}
            </div>
        </div>

        <div id="tab-browse" class="tab-content">
            <div class="section">
                <div class="section-header">
                    <h2>🔍 Browse All <span class="section-count">{len(browse)} match{'es' if len(browse) != 1 else ''}</span></h2>
                    <div class="subtabs">
                        <button class="subtab-btn active" onclick="switchSubtab('all')">All</button>
                        <button class="subtab-btn" onclick="switchSubtab('remote')">🌐 Remote Only</button>
                        <button class="subtab-btn" onclick="switchSubtab('local')">📍 Local Only</button>
                    </div>
                </div>
                <div id="subtab-all" class="subtab-content active">{browse_html}</div>
                <div id="subtab-remote" class="subtab-content">{browse_remote_html}</div>
                <div id="subtab-local" class="subtab-content">{browse_local_html}</div>
            </div>
        </div>
    </div>

    <script>
        function switchTab(tab) {{
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById('tab-' + tab).classList.add('active');
        }}
        function switchSubtab(subtab) {{
            document.querySelectorAll('#tab-browse .subtab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('#tab-browse .subtab-content').forEach(content => content.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById('subtab-' + subtab).classList.add('active');
        }}
    </script>
</body>
</html>"""

    output_file = "dashboard.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    try:
        print(f"\n[OK] Dashboard compiled -> {os.path.realpath(output_file)}")
    except Exception:
        print(f"\n[OK] Dashboard compiled -> {output_file}")
