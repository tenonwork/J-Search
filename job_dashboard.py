import os
import re
import json
from urllib.parse import urlparse


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


def get_scoring_config(preset=None):
    config = DEFAULT_SCORING_CONFIG.copy()
    if preset == "strict":
        config["dealbreaker_weight"] = -30
        config["enforce_dealbreakers_remote"] = True
        config["min_score_remote"] = 10
        config["enforce_dealbreakers_local"] = True
        config["min_score_local"] = 3
        config["preset"] = "strict"
    elif preset == "lenient":
        config["dealbreaker_weight"] = -15
        config["enforce_dealbreakers_remote"] = False
        config["min_score_remote"] = 0
        config["enforce_dealbreakers_local"] = False
        config["min_score_local"] = -10
        config["preset"] = "lenient"
    else:
        config["preset"] = "balanced"
    return config


def _is_blocked(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        host = host.removeprefix("www.")
        return any(host == blocked or host.endswith("." + blocked) for blocked in BLOCKED_DOMAINS)
    except Exception:
        return False


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


def build_dashboard(remote_jobs=None, local_leads=None, config=None):
    remote_jobs = remote_jobs or []
    local_leads = local_leads or []
    if config is None:
        config = DEFAULT_SCORING_CONFIG

    all_jobs_data = []
    
    for job in remote_jobs:
        if _is_blocked(job.get('url', '')):
            continue
        score, goods, bads = score_job(job, config)
        all_jobs_data.append({
            "id": len(all_jobs_data),
            "title": job.get('title', ''),
            "company": job.get('company', ''),
            "location": job.get('location', ''),
            "url": job.get('url', '#'),
            "desc": job.get('desc', ''),
            "score": score,
            "matches": goods,
            "redFlags": bads,
            "source": "global",
            "isLocal": False
        })
    
    for job in local_leads:
        if _is_blocked(job.get('url', '')):
            continue
        score, goods, bads = score_job(job, config)
        all_jobs_data.append({
            "id": len(all_jobs_data),
            "title": job.get('title', ''),
            "company": job.get('company', ''),
            "location": job.get('location', ''),
            "url": job.get('url', '#'),
            "desc": job.get('desc', ''),
            "score": score,
            "matches": goods,
            "redFlags": bads,
            "source": "local",
            "isLocal": True
        })

    jobs_json = json.dumps(all_jobs_data)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>J-Search Dashboard</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f4f6f8;
            margin: 0;
            padding: 20px;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        header {{
            background: white;
            padding: 24px 32px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            margin-bottom: 20px;
        }}
        h1 {{ color: #0f172a; margin: 0 0 4px 0; font-size: 28px; }}
        .subtitle {{ color: #64748b; font-size: 14px; margin: 0; }}
        .top-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 16px;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .scrape-buttons {{ display: flex; gap: 8px; flex-wrap: wrap; }}
        .btn {{
            padding: 10px 18px;
            border: none;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .btn-primary {{ background: #2563eb; color: white; }}
        .btn-primary:hover {{ background: #1d4ed8; }}
        .btn-dark {{ background: #0f172a; color: white; }}
        .btn-dark:hover {{ background: #1e293b; }}
        .btn-outline {{ background: white; color: #0f172a; border: 1px solid #cbd5e1; }}
        .btn-outline:hover {{ background: #f8fafc; }}
        .filters-panel {{
            background: white;
            padding: 20px 24px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            margin-bottom: 20px;
        }}
        .filters-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }}
        .filters-header h3 {{ margin: 0; color: #0f172a; }}
        .filters-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 16px;
        }}
        .filter-group {{ display: flex; flex-direction: column; gap: 8px; }}
        .filter-group label {{ font-size: 12px; font-weight: 600; color: #475569; text-transform: uppercase; }}
        .filter-group input, .filter-group select {{
            padding: 10px 12px;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            font-size: 13px;
            font-family: inherit;
        }}
        .main-controls {{
            background: white;
            padding: 16px 24px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .tabs {{ display: flex; gap: 4px; background: #f1f5f9; padding: 4px; border-radius: 10px; }}
        .tab-btn {{
            padding: 10px 24px;
            border: none;
            background: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            color: #475569;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .tab-btn.active {{ background: white; color: #0f172a; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .view-controls {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
        .control-group {{ display: flex; align-items: center; gap: 8px; }}
        .control-group label {{ font-size: 13px; font-weight: 600; color: #475569; }}
        .toggle {{
            display: flex;
            background: #f1f5f9;
            padding: 4px;
            border-radius: 8px;
        }}
        .toggle-btn {{
            padding: 8px 16px;
            border: none;
            background: none;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            color: #475569;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .toggle-btn.active {{ background: white; color: #0f172a; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }}
        select {{
            padding: 8px 12px;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            font-size: 13px;
            font-family: inherit;
        }}
        .results-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }}
        .results-header h2 {{ margin: 0; color: #0f172a; }}
        .count {{ color: #64748b; font-size: 14px; }}
        .card {{
            background: white;
            padding: 24px;
            margin-bottom: 12px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            display: flex;
            justify-content: space-between;
            gap: 20px;
            transition: box-shadow 0.2s;
        }}
        .card:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
        .card-main {{ flex: 1; min-width: 0; }}
        .card-title {{ font-size: 18px; font-weight: 700; color: #0f172a; margin: 0 0 6px 0; }}
        .card-meta {{ color: #64748b; font-size: 13px; margin-bottom: 12px; }}
        .badges {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
        }}
        .badge-good {{ background: #dcfce7; color: #166534; }}
        .badge-bad {{ background: #fee2e2; color: #991b1b; }}
        .card-actions {{ display: flex; align-items: center; gap: 12px; }}
        .score-box {{ text-align: center; min-width: 70px; }}
        .score {{ font-size: 28px; font-weight: 700; }}
        .score-label {{ font-size: 11px; color: #64748b; }}
        .empty {{ text-align: center; padding: 60px 20px; color: #94a3b8; background: white; border-radius: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>🎯 J-Search</h1>
                <p class="subtitle">Smart Job Triage - Global & Local Markets</p>
            </div>
            <div class="top-bar">
                <div class="scrape-buttons">
                    <button class="btn btn-primary" onclick="runScrapers('all')">🔍 Run All Scrapers</button>
                    <button class="btn btn-outline" onclick="runScrapers('global')">🌐 Run Global Only</button>
                    <button class="btn btn-outline" onclick="runScrapers('local')">📍 Run Local Only</button>
                </div>
                <button class="btn btn-dark" onclick="window.location.href='/run?mode=all'">🔄 Refresh All</button>
            </div>
        </header>

        <div class="filters-panel">
            <div class="filters-header">
                <h3>⚙️ Filters & Preferences</h3>
                <button class="btn btn-outline" onclick="saveFilters()" style="padding: 6px 14px; font-size: 12px;">💾 Save Filters</button>
            </div>
            <div class="filters-grid">
                <div class="filter-group">
                    <label>Focus Keywords (comma separated)</label>
                    <input type="text" id="focusKeywords" placeholder="react, typescript, python, postgres">
                </div>
                <div class="filter-group">
                    <label>Exclude Keywords (comma separated)</label>
                    <input type="text" id="excludeKeywords" placeholder="senior, manager, lead">
                </div>
                <div class="filter-group">
                    <label>Location Preferences</label>
                    <input type="text" id="locationPref" placeholder="remote, nairobi, hybrid">
                </div>
            </div>
        </div>

        <div class="main-controls">
            <div class="tabs">
                <button class="tab-btn active" onclick="switchMainTab('global')">🌐 Global (<span id="count-global">0</span>)</button>
                <button class="tab-btn" onclick="switchMainTab('local')">📍 Local (<span id="count-local">0</span>)</button>
            </div>
            <div class="view-controls">
                <div class="control-group">
                    <label>Strictness:</label>
                    <div class="toggle">
                        <button class="toggle-btn" onclick="setStrictness('strict')">Strict</button>
                        <button class="toggle-btn active" onclick="setStrictness('balanced')">Balanced</button>
                        <button class="toggle-btn" onclick="setStrictness('lenient')">Lenient</button>
                    </div>
                </div>
                <div class="control-group">
                    <label>Sort:</label>
                    <select id="sortOrder" onchange="renderResults()">
                        <option value="desc">Most Recommended → Least</option>
                        <option value="asc">Least → Most Recommended</option>
                    </select>
                </div>
            </div>
        </div>

        <div class="results-header">
            <h2 id="resultsTitle">Global Results</h2>
            <span class="count" id="resultsCount">0 results</span>
        </div>

        <div id="results"></div>
    </div>

    <script>
        const ALL_JOBS = {jobs_json};
        let currentTab = 'global';
        let strictness = 'balanced';
        let filters = {{
            focus: [],
            exclude: [],
            location: []
        }};

        function loadFilters() {{
            const saved = localStorage.getItem('jsearch_filters');
            if (saved) {{
                filters = JSON.parse(saved);
                document.getElementById('focusKeywords').value = filters.focus.join(', ');
                document.getElementById('excludeKeywords').value = filters.exclude.join(', ');
                document.getElementById('locationPref').value = filters.location.join(', ');
            }}
        }}

        function saveFilters() {{
            filters.focus = document.getElementById('focusKeywords').value.split(',').map(s => s.trim().toLowerCase()).filter(s => s);
            filters.exclude = document.getElementById('excludeKeywords').value.split(',').map(s => s.trim().toLowerCase()).filter(s => s);
            filters.location = document.getElementById('locationPref').value.split(',').map(s => s.trim().toLowerCase()).filter(s => s);
            localStorage.setItem('jsearch_filters', JSON.stringify(filters));
            alert('Filters saved!');
            renderResults();
        }}

        function runScrapers(mode) {{
            window.location.href = '/run?mode=' + mode;
        }}

        function switchMainTab(tab) {{
            currentTab = tab;
            document.querySelectorAll('.tab-btn').forEach((btn, idx) => {{
                btn.classList.toggle('active', (tab === 'global' && idx === 0) || (tab === 'local' && idx === 1));
            }});
            document.getElementById('resultsTitle').textContent = tab === 'global' ? 'Global Results' : 'Local Results';
            renderResults();
        }}

        function setStrictness(level) {{
            strictness = level;
            document.querySelectorAll('.toggle-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            renderResults();
        }}

        function getScoreColor(score) {{
            if (score >= 15) return '#16a34a';
            if (score >= 10) return '#2563eb';
            if (score >= 5) return '#ea580c';
            return '#dc2626';
        }}

        function passesFilters(job) {{
            const text = (job.title + ' ' + job.desc).toLowerCase();
            
            // Check exclusions
            for (let ex of filters.exclude) {{
                if (text.includes(ex)) return false;
            }}
            
            // Apply strictness
            if (strictness === 'strict') {{
                if (job.redFlags && job.redFlags.length > 0) return false;
                if (job.source === 'global' && job.score < 10) return false;
                if (job.source === 'local' && job.score < 3) return false;
            }} else if (strictness === 'balanced') {{
                if (job.source === 'global' && job.redFlags && job.redFlags.length > 0) return false;
                if (job.source === 'global' && job.score < 5) return false;
                if (job.source === 'local' && job.score < 0) return false;
            }}
            // lenient - no strict filters
            
            return true;
        }}

        function renderResults() {{
            const sortOrder = document.getElementById('sortOrder').value;
            let jobs = ALL_JOBS.filter(j => j.source === currentTab && passesFilters(j));
            
            jobs.sort((a, b) => {{
                if (sortOrder === 'desc') return b.score - a.score;
                return a.score - b.score;
            }});
            
            document.getElementById('count-global').textContent = ALL_JOBS.filter(j => j.source === 'global').length;
            document.getElementById('count-local').textContent = ALL_JOBS.filter(j => j.source === 'local').length;
            document.getElementById('resultsCount').textContent = jobs.length + ' result' + (jobs.length !== 1 ? 's' : '');
            
            const container = document.getElementById('results');
            if (jobs.length === 0) {{
                container.innerHTML = '<div class="empty">No results match your current filters. Try adjusting strictness or running scrapers.</div>';
                return;
            }}
            
            container.innerHTML = jobs.map(job => {{
                const goodBadges = (job.matches || []).map(m => `<span class="badge badge-good">${{m}}</span>`).join('');
                const badBadges = (job.redFlags || []).map(m => `<span class="badge badge-bad">${{m}}</span>`).join('');
                return `
                    <div class="card">
                        <div class="card-main">
                            <h3 class="card-title">${{escapeHtml(job.title)}}</h3>
                            <div class="card-meta">${{escapeHtml(job.company)}} • ${{escapeHtml(job.location)}}</div>
                            <div class="badges">${{goodBadges}}${{badBadges}}</div>
                            <div class="card-actions">
                                <a href="${{job.url}}" target="_blank" rel="noopener noreferrer" class="btn btn-primary">Review Entry →</a>
                            </div>
                        </div>
                        <div class="score-box">
                            <div class="score" style="color: ${{getScoreColor(job.score)}}">${{job.score}}</div>
                            <div class="score-label">Match Rating</div>
                        </div>
                    </div>
                `;
            }}).join('');
        }}

        function escapeHtml(text) {{
            const div = document.createElement('div');
            div.textContent = text || '';
            return div.innerHTML;
        }}

        loadFilters();
        renderResults();
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
