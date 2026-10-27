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


DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>J-Search Dashboard</title>
<style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f4f6f8; margin: 0; padding: 20px; }
    .container { max-width: 1100px; margin: 0 auto; }
    header { background: #fff; padding: 24px 32px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); margin-bottom: 20px; }
    h1 { color: #0f172a; margin: 0 0 4px 0; font-size: 28px; }
    .subtitle { color: #64748b; font-size: 14px; margin: 0; }
    .top-bar { display: flex; justify-content: space-between; align-items: center; margin-top: 16px; flex-wrap: wrap; gap: 12px; }
    .scrape-buttons { display: flex; gap: 8px; flex-wrap: wrap; }
    .btn { padding: 10px 18px; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s; text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }
    .btn-primary { background: #2563eb; color: #fff; }
    .btn-primary:hover { background: #1d4ed8; }
    .btn-dark { background: #0f172a; color: #fff; }
    .btn-dark:hover { background: #1e293b; }
    .btn-outline { background: #fff; color: #0f172a; border: 1px solid #cbd5e1; }
    .btn-outline:hover { background: #f8fafc; }
    .btn-danger { background: #dc2626; color: #fff; }
    .btn-danger:hover { background: #b91c1c; }
    .btn-sm { padding: 6px 12px; font-size: 12px; }
    .panel { background: #fff; padding: 20px 24px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); margin-bottom: 20px; }
    .panel-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .panel-head h3 { margin: 0; color: #0f172a; font-size: 17px; }
    .kw-section { margin-bottom: 18px; }
    .kw-section:last-child { margin-bottom: 0; }
    .kw-section h4 { margin: 0 0 10px 0; color: #334155; font-size: 13px; font-weight: 600; }
    .kw-list { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; min-height: 34px; }
    .kw-tag { display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px 6px 12px; background: #eff6ff; color: #1e40af; border-radius: 6px; font-size: 13px; font-weight: 500; }
    .kw-tag.exclude { background: #fef2f2; color: #991b1b; }
    .kw-tag .x { cursor: pointer; font-weight: 700; font-size: 15px; line-height: 1; padding: 0 2px; opacity: 0.6; }
    .kw-tag .x:hover { opacity: 1; }
    .kw-empty { color: #94a3b8; font-size: 13px; font-style: italic; }
    .kw-input-row { display: flex; gap: 8px; }
    .kw-input-row input { flex: 1; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; font-family: inherit; }
    .kw-input-row input:focus { outline: 2px solid #bfdbfe; border-color: #2563eb; }
    .modal { display: none; position: fixed; inset: 0; background: rgba(15,23,42,0.55); z-index: 1000; align-items: center; justify-content: center; }
    .modal.active { display: flex; }
    .modal-box { background: #fff; border-radius: 12px; width: 90%; max-width: 480px; max-height: 80vh; display: flex; flex-direction: column; }
    .modal-head { padding: 18px 24px; border-bottom: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center; }
    .modal-head h3 { margin: 0; font-size: 17px; color: #0f172a; }
    .modal-body { padding: 20px 24px; overflow-y: auto; }
    .modal-foot { padding: 14px 24px; border-top: 1px solid #e2e8f0; display: flex; gap: 8px; justify-content: flex-end; }
    .bulk-actions { display: flex; gap: 8px; margin-bottom: 14px; }
    .cb-list { display: flex; flex-direction: column; gap: 8px; }
    .cb-item { display: flex; align-items: center; gap: 10px; padding: 9px 12px; background: #f8fafc; border-radius: 7px; font-size: 13px; color: #0f172a; cursor: pointer; }
    .cb-item input { width: 16px; height: 16px; cursor: pointer; }
    .controls { background: #fff; padding: 16px 24px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; }
    .tabs { display: flex; gap: 4px; background: #f1f5f9; padding: 4px; border-radius: 10px; }
    .tab-btn { padding: 10px 24px; border: none; background: none; border-radius: 8px; font-size: 14px; font-weight: 600; color: #475569; cursor: pointer; }
    .tab-btn.active { background: #fff; color: #0f172a; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .view-controls { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
    .control-group { display: flex; align-items: center; gap: 8px; }
    .control-group label { font-size: 13px; font-weight: 600; color: #475569; }
    .toggle { display: flex; background: #f1f5f9; padding: 4px; border-radius: 8px; }
    .toggle-btn { padding: 8px 16px; border: none; background: none; border-radius: 6px; font-size: 13px; font-weight: 600; color: #475569; cursor: pointer; }
    .toggle-btn.active { background: #fff; color: #0f172a; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
    select { padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; font-family: inherit; background: #fff; }
    .results-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
    .results-head h2 { margin: 0; color: #0f172a; font-size: 20px; }
    .count { color: #64748b; font-size: 14px; }
    .card { background: #fff; padding: 22px 24px; margin-bottom: 12px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); display: flex; justify-content: space-between; gap: 20px; }
    .card.focused { box-shadow: 0 0 0 2px #93c5fd, 0 2px 8px rgba(0,0,0,0.04); }
    .card-main { flex: 1; min-width: 0; }
    .card-title { font-size: 17px; font-weight: 700; color: #0f172a; margin: 0 0 5px 0; }
    .card-meta { color: #64748b; font-size: 13px; margin-bottom: 10px; }
    .badges { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
    .badge { display: inline-block; padding: 3px 9px; border-radius: 6px; font-size: 11px; font-weight: 600; }
    .badge-good { background: #dcfce7; color: #166534; }
    .badge-bad { background: #fee2e2; color: #991b1b; }
    .badge-focus { background: #dbeafe; color: #1e40af; }
    .score-box { text-align: center; min-width: 68px; }
    .score { font-size: 26px; font-weight: 700; }
    .score-label { font-size: 11px; color: #64748b; }
    .empty { text-align: center; padding: 60px 20px; color: #94a3b8; background: #fff; border-radius: 12px; font-size: 14px; }
    .toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%) translateY(80px); background: #0f172a; color: #fff; padding: 12px 22px; border-radius: 9px; font-size: 13px; font-weight: 500; opacity: 0; transition: all 0.25s; z-index: 2000; }
    .toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
</style>
</head>
<body>
<div class="container">
    <header>
        <h1>J-Search</h1>
        <p class="subtitle">Smart job triage &mdash; global and local markets</p>
        <div class="top-bar">
            <div class="scrape-buttons">
                <button class="btn btn-primary" onclick="runScrapers('all')">Run All Scrapers</button>
                <button class="btn btn-outline" onclick="runScrapers('global')">Run Global Only</button>
                <button class="btn btn-outline" onclick="runScrapers('local')">Run Local Only</button>
            </div>
        </div>
    </header>

    <div class="panel">
        <div class="panel-head">
            <h3>Keywords &amp; Preferences</h3>
            <span class="count" id="kwStatus">loading...</span>
        </div>

        <div class="kw-section">
            <h4>Focus keywords &mdash; jobs containing these are highlighted</h4>
            <div class="kw-list" id="focusList"></div>
            <div class="kw-input-row">
                <input type="text" id="focusInput" placeholder="Add a focus keyword, e.g. react">
                <button class="btn btn-primary btn-sm" onclick="addKeyword('focus')">+ Add</button>
                <button class="btn btn-outline btn-sm" onclick="openKeywordManager('focus')">Manage</button>
            </div>
        </div>

        <div class="kw-section">
            <h4>Exclude keywords &mdash; jobs containing these are hidden</h4>
            <div class="kw-list" id="excludeList"></div>
            <div class="kw-input-row">
                <input type="text" id="excludeInput" placeholder="Add an exclude keyword, e.g. senior">
                <button class="btn btn-primary btn-sm" onclick="addKeyword('exclude')">+ Add</button>
                <button class="btn btn-outline btn-sm" onclick="openKeywordManager('exclude')">Manage</button>
            </div>
        </div>
    </div>

    <div class="controls">
        <div class="tabs">
            <button class="tab-btn active" data-tab="global" onclick="switchMainTab('global', this)">Global (<span id="count-global">0</span>)</button>
            <button class="tab-btn" data-tab="local" onclick="switchMainTab('local', this)">Local (<span id="count-local">0</span>)</button>
        </div>
        <div class="view-controls">
            <div class="control-group">
                <label>Strictness:</label>
                <div class="toggle">
                    <button class="toggle-btn" data-level="strict" onclick="setStrictness('strict', this)">Strict</button>
                    <button class="toggle-btn active" data-level="balanced" onclick="setStrictness('balanced', this)">Balanced</button>
                    <button class="toggle-btn" data-level="lenient" onclick="setStrictness('lenient', this)">Lenient</button>
                </div>
            </div>
            <div class="control-group">
                <label>Sort:</label>
                <select id="sortOrder" onchange="renderResults()">
                    <option value="desc">Most recommended first</option>
                    <option value="asc">Least recommended first</option>
                </select>
            </div>
        </div>
    </div>

    <div class="results-head">
        <h2 id="resultsTitle">Global Results</h2>
        <span class="count" id="resultsCount">0 results</span>
    </div>

    <div id="results"></div>
</div>

<div id="keywordModal" class="modal">
    <div class="modal-box">
        <div class="modal-head">
            <h3 id="modalTitle">Manage keywords</h3>
            <button class="btn btn-outline btn-sm" onclick="closeKeywordManager()">Close</button>
        </div>
        <div class="modal-body">
            <div class="bulk-actions">
                <button class="btn btn-outline btn-sm" onclick="selectAllKeywords(true)">Select all</button>
                <button class="btn btn-outline btn-sm" onclick="selectAllKeywords(false)">Select none</button>
            </div>
            <div class="cb-list" id="keywordCheckboxList"></div>
        </div>
        <div class="modal-foot">
            <button class="btn btn-outline" onclick="closeKeywordManager()">Cancel</button>
            <button class="btn btn-danger" onclick="deleteSelectedKeywords()">Delete selected</button>
        </div>
    </div>
</div>

<div id="toast" class="toast"></div>

<script>
const ALL_JOBS = __JOBS_JSON__;

let filters = { focus: [], exclude: [] };
let currentTab = 'global';
let strictness = 'balanced';
let manageType = 'focus';

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

function toast(msg) {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.classList.add('show');
    setTimeout(() => el.classList.remove('show'), 2200);
}

async function api(path, method, body) {
    const opts = { method: method || 'GET', headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.headers.get('content-type') && res.headers.get('content-type').includes('json') ? res.json() : null;
}

async function loadKeywords() {
    try {
        const data = await api('/api/keywords');
        filters.focus = data.focus || [];
        filters.exclude = data.exclude || [];
        document.getElementById('kwStatus').textContent = 'saved to database';
    } catch (e) {
        document.getElementById('kwStatus').textContent = 'offline';
    }
    renderKeywordLists();
    renderResults();
}

function renderKeywordLists() {
    const focusEl = document.getElementById('focusList');
    const excludeEl = document.getElementById('excludeList');

    function tagHtml(type, k, extraClass) {
        return '<span class="kw-tag' + extraClass + '">' + escapeHtml(k) +
            ' <span class="x" title="Remove" data-type="' + type +
            '" data-value="' + encodeURIComponent(k) + '">&times;</span></span>';
    }

    focusEl.innerHTML = filters.focus.length
        ? filters.focus.map(k => tagHtml('focus', k, '')).join('')
        : '<span class="kw-empty">No focus keywords yet</span>';

    excludeEl.innerHTML = filters.exclude.length
        ? filters.exclude.map(k => tagHtml('exclude', k, ' exclude')).join('')
        : '<span class="kw-empty">No exclude keywords yet</span>';
}

async function addKeyword(type) {
    const input = document.getElementById(type + 'Input');
    const value = input.value.trim().toLowerCase();
    if (!value) return;
    try {
        await api('/api/keywords/add', 'POST', { type: type, value: value });
        input.value = '';
        await loadKeywords();
        toast('Added "' + value + '"');
    } catch (e) {
        toast('Could not add keyword');
    }
}

async function removeKeyword(type, value) {
    try {
        await api('/api/keywords/delete', 'POST', { type: type, values: [value] });
        await loadKeywords();
        toast('Removed "' + value + '"');
    } catch (e) {
        toast('Could not remove keyword');
    }
}

function openKeywordManager(type) {
    manageType = type;
    document.getElementById('modalTitle').textContent =
        type === 'focus' ? 'Manage focus keywords' : 'Manage exclude keywords';
    const list = document.getElementById('keywordCheckboxList');
    if (!filters[type].length) {
        list.innerHTML = '<p class="kw-empty">No keywords to manage</p>';
    } else {
        list.innerHTML = filters[type].map(k =>
            '<label class="cb-item"><input type="checkbox" class="kw-checkbox" value="' +
            escapeHtml(k).replace(/"/g, '&quot;') + '" checked><span>' + escapeHtml(k) + '</span></label>'
        ).join('');
    }
    document.getElementById('keywordModal').classList.add('active');
}

function closeKeywordManager() {
    document.getElementById('keywordModal').classList.remove('active');
}

function selectAllKeywords(state) {
    document.querySelectorAll('.kw-checkbox').forEach(cb => { cb.checked = state; });
}

async function deleteSelectedKeywords() {
    const values = Array.from(document.querySelectorAll('.kw-checkbox:checked')).map(cb => cb.value);
    if (!values.length) { closeKeywordManager(); return; }
    try {
        await api('/api/keywords/delete', 'POST', { type: manageType, values: values });
        closeKeywordManager();
        await loadKeywords();
        toast('Deleted ' + values.length + ' keyword' + (values.length === 1 ? '' : 's'));
    } catch (e) {
        toast('Could not delete keywords');
    }
}

function runScrapers(mode) {
    window.location.href = '/run?mode=' + mode;
}

function switchMainTab(tab, el) {
    currentTab = tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    if (el) el.classList.add('active');
    document.getElementById('resultsTitle').textContent = tab === 'global' ? 'Global Results' : 'Local Results';
    renderResults();
}

function setStrictness(level, el) {
    strictness = level;
    document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
    if (el) el.classList.add('active');
    renderResults();
}

function scoreColor(score) {
    if (score >= 15) return '#16a34a';
    if (score >= 10) return '#2563eb';
    if (score >= 5) return '#ea580c';
    return '#dc2626';
}

function passesFilters(job) {
    const text = ((job.title || '') + ' ' + (job.desc || '')).toLowerCase();

    for (const ex of filters.exclude) {
        if (ex && text.includes(ex)) return false;
    }

    if (strictness === 'strict') {
        if (job.redFlags && job.redFlags.length) return false;
        if (job.source === 'global' && job.score < 10) return false;
        if (job.source === 'local' && job.score < 3) return false;
    } else if (strictness === 'balanced') {
        if (job.source === 'global' && job.redFlags && job.redFlags.length) return false;
        if (job.source === 'global' && job.score < 5) return false;
        if (job.source === 'local' && job.score < 0) return false;
    }
    return true;
}

function isFocused(job) {
    const text = ((job.title || '') + ' ' + (job.desc || '')).toLowerCase();
    return filters.focus.some(k => k && text.includes(k));
}

function renderResults() {
    const sortOrder = document.getElementById('sortOrder').value;

    document.getElementById('count-global').textContent = ALL_JOBS.filter(j => j.source === 'global').length;
    document.getElementById('count-local').textContent = ALL_JOBS.filter(j => j.source === 'local').length;

    let jobs = ALL_JOBS.filter(j => j.source === currentTab && passesFilters(j));
    jobs.sort((a, b) => sortOrder === 'desc' ? b.score - a.score : a.score - b.score);

    document.getElementById('resultsCount').textContent =
        jobs.length + ' result' + (jobs.length === 1 ? '' : 's');

    const container = document.getElementById('results');
    if (!jobs.length) {
        container.innerHTML = '<div class="empty">No results match the current filters. Try a more lenient setting or run the scrapers.</div>';
        return;
    }

    container.innerHTML = jobs.map(job => {
        const good = (job.matches || []).map(m => '<span class="badge badge-good">' + escapeHtml(m) + '</span>').join('');
        const bad = (job.redFlags || []).map(m => '<span class="badge badge-bad">' + escapeHtml(m) + '</span>').join('');
        const focusBadge = isFocused(job) ? '<span class="badge badge-focus">focus match</span>' : '';
        const focusClass = isFocused(job) ? ' focused' : '';
        return '<div class="card' + focusClass + '">' +
            '<div class="card-main">' +
                '<h3 class="card-title">' + escapeHtml(job.title) + '</h3>' +
                '<div class="card-meta">' + escapeHtml(job.company) + ' &bull; ' + escapeHtml(job.location) + '</div>' +
                '<div class="badges">' + focusBadge + good + bad + '</div>' +
                '<a href="' + escapeHtml(job.url) + '" target="_blank" rel="noopener noreferrer" class="btn btn-primary">Review Entry &rarr;</a>' +
            '</div>' +
            '<div class="score-box">' +
                '<div class="score" style="color: ' + scoreColor(job.score) + '">' + job.score + '</div>' +
                '<div class="score-label">Match Rating</div>' +
            '</div>' +
        '</div>';
    }).join('');
}

document.getElementById('focusInput').addEventListener('keydown', e => { if (e.key === 'Enter') addKeyword('focus'); });
document.getElementById('excludeInput').addEventListener('keydown', e => { if (e.key === 'Enter') addKeyword('exclude'); });
document.getElementById('keywordModal').addEventListener('click', e => {
    if (e.target.id === 'keywordModal') closeKeywordManager();
});

document.addEventListener('click', function (e) {
    const x = e.target.closest('.kw-tag .x');
    if (x) {
        removeKeyword(x.dataset.type, decodeURIComponent(x.dataset.value));
    }
});

loadKeywords();
</script>
</body>
</html>"""


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
        })

    jobs_json = json.dumps(all_jobs_data).replace('</', '<\\/')
    html_content = DASHBOARD_TEMPLATE.replace('__JOBS_JSON__', jobs_json)

    output_file = "dashboard.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    print("[OK] Dashboard compiled -> " + os.path.realpath(output_file))
