import os
import re
import json
from urllib.parse import urlparse

from .paths import DASHBOARD_PATH


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


PROFILE_VERSION = 1

# Fields that can be stored in the settings table. Presets own thresholds and
# enforcement; the profile owns only the vocabulary and weights.
PROFILE_FIELDS = (
    "core_skills", "core_weight",
    "ai_skills", "ai_weight",
    "good_matches", "good_weight",
    "pos_weight",
    "dealbreakers", "dealbreaker_weight",
)

_PROFILE_LIST_FIELDS = {
    "core_skills": 60,
    "ai_skills": 40,
    "good_matches": 40,
    "dealbreakers": 40,
}

_PROFILE_WEIGHT_RANGES = {
    "core_weight": (0, 100),
    "ai_weight": (0, 100),
    "good_weight": (0, 100),
    "pos_weight": (0, 100),
    "dealbreaker_weight": (-100, 0),
}


def normalize_scoring_profile(profile):
    """Return only valid, normalised profile overrides.

    Unknown keys, wrong types and empty strings are dropped. This is the
    boundary between stored/HTTP data and the scoring engine.
    """
    if not isinstance(profile, dict):
        return {}

    clean = {}
    for field, limit in _PROFILE_LIST_FIELDS.items():
        if field not in profile:
            continue
        values = profile[field]
        if not isinstance(values, (list, tuple)):
            continue
        out = []
        seen = set()
        for value in values:
            if not isinstance(value, str):
                continue
            value = " ".join(value.lower().split()).strip(" ,;:")
            if not value or len(value) > 60 or value in seen:
                continue
            seen.add(value)
            out.append(value)
            if len(out) >= limit:
                break
        clean[field] = out

    for field, (low, high) in _PROFILE_WEIGHT_RANGES.items():
        if field not in profile:
            continue
        try:
            value = int(profile[field])
        except (TypeError, ValueError):
            continue
        clean[field] = max(low, min(high, value))

    return clean


def get_scoring_config(preset=None, profile=None):
    """Build a scoring config from defaults, a saved profile and a preset.

    Every list is rebuilt so callers can never mutate DEFAULT_SCORING_CONFIG
    through a returned config.
    """
    config = {}
    for key, value in DEFAULT_SCORING_CONFIG.items():
        config[key] = list(value) if isinstance(value, list) else value

    for key, value in normalize_scoring_profile(profile or {}).items():
        config[key] = list(value) if isinstance(value, list) else value

    if preset == "strict":
        config["enforce_dealbreakers_remote"] = True
        config["min_score_remote"] = 10
        config["enforce_dealbreakers_local"] = True
        config["min_score_local"] = 3
    elif preset == "lenient":
        config["enforce_dealbreakers_remote"] = False
        config["min_score_remote"] = 0
        config["enforce_dealbreakers_local"] = False
        config["min_score_local"] = -10
    else:
        preset = "balanced"

    config["preset"] = preset
    return config


def effective_profile(profile=None):
    """A full, JSON-safe profile for the UI and the settings table."""
    config = get_scoring_config("balanced", profile)
    result = {"version": PROFILE_VERSION}
    for field in PROFILE_FIELDS:
        value = config[field]
        result[field] = list(value) if isinstance(value, list) else value
    return result


def _is_blocked(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
        host = host.removeprefix("www.")
        return any(host == blocked or host.endswith("." + blocked) for blocked in BLOCKED_DOMAINS)
    except Exception:
        return False


def job_key(url, title='', company='', location=''):
    """Stable identity for a posting across scrapes.

    jobs.id is not stable because save_jobs() uses INSERT OR REPLACE, so
    decisions are keyed on this value instead. Scheme, query string, fragment
    and a leading www. are ignored; URL-less jobs fall back to their details.
    """
    url = (url or '').strip()
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith('www.'):
            host = host[4:]
        scheme = parsed.scheme.lower()
        if scheme in ('http', 'https') and host:
            normalized = (host + parsed.path).lower().rstrip('/')
        else:
            normalized = ''
    except Exception:
        normalized = ''

    if not normalized:
        normalized = f"{title or ''}|{company or ''}|{location or ''}".lower().strip()
    return normalized or 'unknown'


_WORD_SAFE = re.compile(r"^[a-z0-9]+(?:[ \-/][a-z0-9]+)*$")


def _matches_skill(text, skill):
    """Match one configured keyword against lower-cased job text.

    Plain words use word boundaries, preserving the existing protection
    against "pos" matching "position". Terms with punctuation that \\b cannot
    express (c++, c#, .net, node.js) fall back to literal matching.
    """
    skill = " ".join(str(skill or "").lower().split())
    if not skill:
        return False
    if _WORD_SAFE.match(skill):
        return re.search(r"\b" + re.escape(skill) + r"\b", text) is not None
    return skill in text


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
        if _matches_skill(text, word):
            score += core_weight
            matches_found.append(word)

    for word in ai_skills:
        if _matches_skill(text, word):
            score += ai_weight
            matches_found.append(word)

    for word in good_matches:
        if _matches_skill(text, word):
            score += good_weight
            matches_found.append(word)

    for word in dealbreakers:
        if _matches_skill(text, word):
            score += dealbreaker_weight
            red_flags_found.append(word)

    return score, matches_found, red_flags_found


def passes_filters(job, config=None, strictness="balanced", exclude_keywords=()):
    """Python mirror of the dashboard's client-side visibility rules.

    Used for the profile impact preview so the numbers shown in the modal
    match what the dashboard will actually display.
    """
    if config is None:
        config = DEFAULT_SCORING_CONFIG

    text = (
        (job.get("title", "") or "") + " " + (job.get("desc", "") or "")
    ).lower()

    for keyword in exclude_keywords:
        if _matches_skill(text, keyword):
            return False

    source = job.get("source")
    score, _, red_flags = score_job(job, config)

    if strictness == "strict":
        if red_flags:
            return False
        if source == "global" and score < config.get("min_score_remote", 10):
            return False
        if source == "local" and score < config.get("min_score_local", 3):
            return False
    elif strictness == "balanced":
        if source == "global" and red_flags:
            return False
        if source == "global" and score < config.get("min_score_remote", 5):
            return False
        if source == "local" and score < config.get("min_score_local", 0):
            return False

    return True


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
    .kw-tag.paused { background: #f1f5f9; color: #64748b; opacity: 0.7; }
    .kw-paused { font-size: 9px; text-transform: uppercase; letter-spacing: 0.05em; background: #e2e8f0; color: #475569; padding: 2px 5px; border-radius: 4px; font-weight: 700; }
    .kw-note { color: #64748b; font-size: 12px; margin: -6px 0 14px 0; }
    .kw-empty { color: #94a3b8; font-size: 13px; font-style: italic; }
    .kw-input-row { display: flex; gap: 8px; }
    .kw-input-row input { flex: 1; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; font-family: inherit; }
    .kw-input-row input:focus { outline: 2px solid #bfdbfe; border-color: #2563eb; }
    .modal { display: none; position: fixed; inset: 0; background: rgba(15,23,42,0.55); z-index: 1000; align-items: center; justify-content: center; }
    .modal.active { display: flex; }
    .modal.confirm-modal { z-index: 1100; }
    .modal-box { background: #fff; border-radius: 12px; width: 90%; max-width: 480px; max-height: 80vh; display: flex; flex-direction: column; }
    .modal-head { padding: 18px 24px; border-bottom: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center; }
    .modal-head h3 { margin: 0; font-size: 17px; color: #0f172a; }
    .modal-body { padding: 20px 24px; overflow-y: auto; }
    .modal-foot { padding: 14px 24px; border-top: 1px solid #e2e8f0; display: flex; gap: 8px; justify-content: flex-end; }
    .modal-sm { max-width: 400px; }
    .confirm-warning { margin: 0; color: #991b1b; font-size: 13px; font-weight: 600; }
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
    .toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%) translateY(80px); background: #0f172a; color: #fff; padding: 12px 22px; border-radius: 9px; font-size: 13px; font-weight: 500; opacity: 0; transition: all 0.25s; z-index: 2000; display: flex; align-items: center; gap: 10px; }
    .toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
    .toast-action { background: #fff; color: #0f172a; border: none; border-radius: 6px; padding: 5px 10px; font-size: 12px; font-weight: 700; cursor: pointer; }
    .tracker-links { display: flex; gap: 8px; flex-wrap: wrap; }
    .tracker-links .btn { gap: 0; }
    .card-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .btn-apply { background: #dcfce7; color: #166534; border: 1px solid #86efac; }
    .btn-apply:hover { background: #bbf7d0; }
    .btn-dismiss { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
    .btn-dismiss:hover { background: #fee2e2; }
    .modal-intro { margin: 0 0 14px 0; color: #475569; font-size: 13px; }
    .reason-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
    .reason-item { display: flex; align-items: center; gap: 10px; padding: 9px 12px; background: #f8fafc; border-radius: 7px; font-size: 13px; color: #0f172a; cursor: pointer; }
    .reason-item input { width: 16px; height: 16px; cursor: pointer; }
    textarea { width: 100%; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; font-family: inherit; resize: vertical; }
    textarea:focus { outline: 2px solid #bfdbfe; border-color: #2563eb; }
    .modal-lg { max-width: 720px; }
    .field-label { display: block; font-size: 12px; font-weight: 700; color: #334155; margin: 16px 0 6px 0; text-transform: uppercase; letter-spacing: 0.04em; }
    .field-hint { font-weight: 500; text-transform: none; letter-spacing: 0; color: #94a3b8; }
    .llm-status { display: flex; gap: 9px; align-items: flex-start; margin: 14px 0 0 0; padding: 11px 12px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }
    .llm-badge { flex: 0 0 auto; padding: 3px 8px; border-radius: 999px; font-size: 10px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; margin-top: 1px; }
    .llm-badge.local { background: #dcfce7; color: #166534; }
    .llm-badge.remote { background: #fef3c7; color: #92400e; }
    .llm-badge.unknown { background: #e2e8f0; color: #475569; }
    .llm-copy { min-width: 0; }
    .llm-model { font-size: 12px; font-weight: 700; color: #334155; overflow-wrap: anywhere; }
    .llm-detail { font-size: 12px; color: #64748b; line-height: 1.5; margin-top: 2px; }
    .llm-actions { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; margin-top: 8px; }
    .llm-test-status { font-size: 12px; color: #64748b; line-height: 1.45; }
    .llm-test-status.ok { color: #166534; }
    .llm-test-status.error { color: #991b1b; font-weight: 600; }
    .profile-error { font-size: 13px; color: #991b1b; font-weight: 600; margin: 10px 0 0 0; min-height: 18px; }
    .profile-loading { text-align: center; padding: 44px 10px; color: #475569; font-size: 14px; }
    .spinner.small { width: 36px; height: 36px; border: 4px solid #e2e8f0; border-top-color: #2563eb; border-radius: 50%; margin: 0 auto 16px auto; animation: spin 0.9s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .impact-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 14px; font-size: 13px; color: #334155; margin-bottom: 18px; line-height: 1.55; }
    .impact-box strong { color: #0f172a; }
    .impact-warn { color: #991b1b; font-weight: 600; }
    .profile-weights { display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 18px; padding: 12px 14px; background: #f8fafc; border-radius: 8px; }
    .profile-weights label { display: flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 600; color: #475569; }
    .profile-weights input { width: 62px; padding: 6px 8px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 12px; font-family: inherit; }
    .profile-group { margin-bottom: 20px; }
    .profile-group h4 { margin: 0 0 8px 0; font-size: 13px; color: #334155; }
    .profile-group .hint { font-weight: 500; color: #94a3b8; }
    .profile-chips { display: flex; flex-wrap: wrap; gap: 8px; }
    .profile-chip { display: inline-flex; align-items: center; gap: 7px; padding: 7px 11px; border-radius: 7px; background: #eff6ff; color: #1e40af; font-size: 13px; font-weight: 500; cursor: pointer; border: 1px solid transparent; }
    .profile-chip input { width: 15px; height: 15px; cursor: pointer; }
    .profile-chip.checked { border-color: #93c5fd; }
    .profile-chip.exclude { background: #fef2f2; color: #991b1b; }
    .profile-chip.exclude.checked { border-color: #fecaca; }
    .profile-chip.dealbreaker { background: #fff7ed; color: #9a3412; }
    .profile-chip.dealbreaker.checked { border-color: #fdba74; }
    .profile-chip .why { font-size: 11px; color: #64748b; font-weight: 400; }
    .profile-empty { color: #94a3b8; font-size: 13px; font-style: italic; }
    .profile-focus { margin: 0; font-size: 13px; color: #1e40af; line-height: 1.6; }
    .profile-notes { margin: 0; padding-left: 20px; font-size: 13px; color: #64748b; line-height: 1.6; }
    .profile-mode { margin: 0 0 16px 0; font-size: 12px; font-weight: 600; color: #475569; }
    .profile-mode select { margin-left: 8px; }
    .cv-drop { display: flex; flex-direction: column; align-items: center; gap: 3px; padding: 18px 16px; margin: 4px 0 0 0; border: 1.5px dashed #cbd5e1; border-radius: 10px; background: #f8fafc; text-align: center; cursor: pointer; transition: border-color 0.15s, background 0.15s; }
    .cv-drop:hover, .cv-drop:focus-visible, .cv-drop.dragover { border-color: #2563eb; background: #eff6ff; outline: none; }
    .cv-drop.busy { opacity: 0.6; pointer-events: none; }
    .cv-drop input[type="file"] { display: none; }
    .cv-drop-title { font-size: 13px; font-weight: 600; color: #334155; }
    .cv-drop-link { color: #2563eb; text-decoration: underline; }
    .cv-drop-hint { font-size: 11px; color: #64748b; }
    .cv-file-status { min-height: 17px; margin: 7px 0 0 0; font-size: 12px; color: #166534; line-height: 1.45; }
    .cv-file-error { margin: 4px 0 0 0; font-size: 12px; color: #991b1b; font-weight: 600; line-height: 1.45; }
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
            <div class="tracker-links">
                <a class="btn btn-outline" href="/applied">Applied (<span id="appliedCount">__APPLIED_COUNT__</span>)</a>
                <a class="btn btn-outline" href="/hidden">Hidden (<span id="hiddenCount">__DISMISSED_COUNT__</span>)</a>
            </div>
        </div>
    </header>

    <div class="panel">
        <div class="panel-head">
            <h3>Keywords &amp; Preferences</h3>
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                <span class="count" id="kwStatus">loading...</span>
                <button class="btn btn-dark btn-sm" onclick="openProfileModal()">Import from CV</button>
            </div>
        </div>
        <p class="kw-note">Scrapers fetch a broad set of jobs. These keywords only change what is shown here, not what is fetched.</p>

        <div class="kw-section">
            <h4>Highlight keywords &mdash; matching jobs get a blue outline</h4>
            <div class="kw-list" id="focusList"></div>
            <div class="kw-input-row">
                <input type="text" id="focusInput" placeholder="Add a highlight keyword, e.g. react">
                <button class="btn btn-primary btn-sm" onclick="addKeyword('focus')">+ Add</button>
                <button class="btn btn-outline btn-sm" onclick="openKeywordManager('focus')">Manage</button>
            </div>
        </div>

        <div class="kw-section">
            <h4>Hide keywords &mdash; matching jobs disappear from results</h4>
            <div class="kw-list" id="excludeList"></div>
            <div class="kw-input-row">
                <input type="text" id="excludeInput" placeholder="Add a hide keyword, e.g. senior">
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
            <p class="modal-intro" id="keywordModalIntro"></p>
            <div class="bulk-actions">
                <button class="btn btn-outline btn-sm" onclick="selectAllKeywords(true)">Enable all</button>
                <button class="btn btn-outline btn-sm" onclick="selectAllKeywords(false)">Disable all</button>
            </div>
            <div class="cb-list" id="keywordCheckboxList"></div>
        </div>
        <div class="modal-foot">
            <button class="btn btn-outline" onclick="closeKeywordManager()">Cancel</button>
            <button class="btn btn-primary" onclick="saveKeywordStates()">Save changes</button>
        </div>
    </div>
</div>

<div id="confirmKeywordModal" class="modal confirm-modal">
    <div class="modal-box modal-sm">
        <div class="modal-head">
            <h3>Delete keyword?</h3>
            <button class="btn btn-outline btn-sm" onclick="closeConfirmKeyword()">Close</button>
        </div>
        <div class="modal-body">
            <p class="modal-intro" id="confirmKeywordText"></p>
            <p class="confirm-warning">This cannot be undone.</p>
        </div>
        <div class="modal-foot">
            <button class="btn btn-outline" onclick="closeConfirmKeyword()">Cancel</button>
            <button class="btn btn-danger" onclick="confirmDeleteKeyword()">Delete keyword</button>
        </div>
    </div>
</div>

<div id="profileModal" class="modal">
    <div class="modal-box modal-lg">
        <div class="modal-head">
            <h3>Import from CV</h3>
            <button class="btn btn-outline btn-sm" onclick="closeProfileModal()">Close</button>
        </div>
        <div class="modal-body">
            <div id="profileStepInput">
                <p class="modal-intro">Upload a PDF, DOCX or TXT file, or paste your CV below. Nothing changes until you review and apply the proposal.</p>
                <div class="llm-status">
                    <span class="llm-badge unknown" id="llmBadge">Model</span>
                    <div class="llm-copy">
                        <div class="llm-model" id="llmTarget">Checking model configuration...</div>
                        <div class="llm-detail" id="llmWarning"></div>
                        <div class="llm-actions">
                            <button class="btn btn-outline btn-sm" id="llmTestBtn" onclick="testLlm()">Test model connection</button>
                            <span class="llm-test-status" id="llmTestStatus"></span>
                        </div>
                    </div>
                </div>
                <label class="cv-drop" id="cvDrop" for="cvFile" role="button" tabindex="0">
                    <input type="file" id="cvFile" accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain">
                    <span class="cv-drop-title">Drop a CV here or <span class="cv-drop-link">browse</span></span>
                    <span class="cv-drop-hint">PDF, DOCX or TXT &middot; up to 10 MB &middot; read on this machine, never stored</span>
                </label>
                <p class="cv-file-status" id="cvFileStatus"></p>
                <p class="cv-file-error" id="cvFileError"></p>
                <label class="field-label" for="cvText">CV text</label>
                <textarea id="cvText" rows="10" placeholder="Upload a file above or paste your CV here. Contact details are removed before the model sees it."></textarea>
                <label class="field-label" for="cvPreferences">Things to avoid <span class="field-hint">comma or newline separated</span></label>
                <textarea id="cvPreferences" rows="3" placeholder="e.g. PHP, on-site only, staffing agencies, 24/7 on-call"></textarea>
                <p class="profile-error" id="profileError"></p>
            </div>
            <div id="profileStepLoading" class="profile-loading" style="display:none;">
                <div class="spinner small"></div>
                <p>Analysing the CV. This can take 10&ndash;60 seconds depending on the model.</p>
            </div>
            <div id="profileStepReview" style="display:none;">
                <div id="profileImpact" class="impact-box"></div>
                <div id="profileSections"></div>
                <p class="profile-mode">When applying: <span class="field-hint">keywords are added to the existing lists; nothing is deleted.</span></p>
                <p class="profile-error" id="profileReviewError"></p>
            </div>
        </div>
        <div class="modal-foot">
            <button class="btn btn-outline" onclick="closeProfileModal()">Cancel</button>
            <button class="btn btn-primary" id="profileAnalyzeBtn" onclick="analyzeCv()">Analyse CV</button>
            <button class="btn btn-outline" id="profileBackBtn" style="display:none;" onclick="backToProfileInput()">Back</button>
            <button class="btn btn-primary" id="profileApplyBtn" style="display:none;" onclick="applyProfile()">Apply selected</button>
        </div>
    </div>
</div>

<div id="decisionModal" class="modal">
    <div class="modal-box">
        <div class="modal-head">
            <h3>Not for me</h3>
            <button class="btn btn-outline btn-sm" onclick="closeDecisionModal()">Close</button>
        </div>
        <div class="modal-body">
            <p class="modal-intro" id="decisionJobTitle"></p>
            <div class="reason-list">
                <label class="reason-item"><input type="radio" name="decisionReason" class="reason-radio" value="Too senior / leadership"> <span>Too senior / leadership</span></label>
                <label class="reason-item"><input type="radio" name="decisionReason" class="reason-radio" value="Wrong tech stack"> <span>Wrong tech stack</span></label>
                <label class="reason-item"><input type="radio" name="decisionReason" class="reason-radio" value="Not remote / location"> <span>Not remote / location</span></label>
                <label class="reason-item"><input type="radio" name="decisionReason" class="reason-radio" value="Compensation too low"> <span>Compensation too low</span></label>
                <label class="reason-item"><input type="radio" name="decisionReason" class="reason-radio" value="Company / industry"> <span>Company / industry</span></label>
                <label class="reason-item"><input type="radio" name="decisionReason" class="reason-radio" value="Duplicate / stale"> <span>Duplicate / stale</span></label>
                <label class="reason-item"><input type="radio" name="decisionReason" class="reason-radio" value="Other"> <span>Other</span></label>
            </div>
            <textarea id="decisionNote" rows="3" placeholder="Optional note (e.g. salary too low, on-site only)"></textarea>
        </div>
        <div class="modal-foot">
            <button class="btn btn-outline" onclick="closeDecisionModal()">Cancel</button>
            <button class="btn btn-danger" onclick="submitDismissal()">Hide job</button>
        </div>
    </div>
</div>

<div id="toast" class="toast"></div>

<script>
let ALL_JOBS = __JOBS_JSON__;

let filters = { focus: [], exclude: [] };
let currentTab = 'global';
let strictness = 'balanced';
let manageType = 'focus';
let pendingKeywordDelete = null;
let pendingDismissJob = null;
let lastDecision = null;
let toastTimer = null;
let profileProposal = null;
let profilePreviewTimer = null;

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

function toast(msg, actionLabel, actionFn) {
    const el = document.getElementById('toast');
    el.innerHTML = '<span>' + escapeHtml(msg) + '</span>';
    if (actionLabel && actionFn) {
        const btn = document.createElement('button');
        btn.className = 'toast-action';
        btn.textContent = actionLabel;
        btn.addEventListener('click', () => {
            el.classList.remove('show');
            actionFn();
        });
        el.appendChild(btn);
    }
    el.classList.add('show');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show'), actionLabel ? 6000 : 2200);
}

async function api(path, method, body) {
    const opts = { method: method || 'GET', headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    const isJson = res.headers.get('content-type') && res.headers.get('content-type').includes('json');
    const data = isJson ? await res.json() : null;
    if (!res.ok) {
        throw new Error((data && (data.error || data.message)) || ('HTTP ' + res.status));
    }
    return data;
}

async function loadKeywords() {
    try {
        const data = await api('/api/keywords');
        filters.focus = data.focus || [];
        filters.exclude = data.exclude || [];
        const activeFocus = filters.focus.filter(k => k.enabled).length;
        const activeExclude = filters.exclude.filter(k => k.enabled).length;
        const paused = filters.focus.filter(k => !k.enabled).length +
            filters.exclude.filter(k => !k.enabled).length;
        let status = activeFocus + ' highlight / ' + activeExclude + ' hide active';
        if (paused) status += ' (' + paused + ' paused)';
        document.getElementById('kwStatus').textContent = status;
    } catch (e) {
        document.getElementById('kwStatus').textContent = 'offline';
    }
    renderKeywordLists();
    renderResults();
}

function renderKeywordLists() {
    const focusEl = document.getElementById('focusList');
    const excludeEl = document.getElementById('excludeList');

    function tagHtml(type, item, extraClass) {
        const paused = item.enabled ? '' : ' paused';
        const pausedBadge = item.enabled ? '' : '<span class="kw-paused">paused</span>';
        return '<span class="kw-tag' + extraClass + paused + '">' + escapeHtml(item.value) +
            pausedBadge +
            ' <span class="x" title="Delete keyword" data-type="' + type +
            '" data-value="' + encodeURIComponent(item.value) + '">&times;</span></span>';
    }

    focusEl.innerHTML = filters.focus.length
        ? filters.focus.map(k => tagHtml('focus', k, '')).join('')
        : '<span class="kw-empty">No highlight keywords yet</span>';

    excludeEl.innerHTML = filters.exclude.length
        ? filters.exclude.map(k => tagHtml('exclude', k, ' exclude')).join('')
        : '<span class="kw-empty">No hide keywords yet</span>';
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

function openDeleteKeyword(type, value) {
    pendingKeywordDelete = { type: type, value: value };
    const label = type === 'focus' ? 'highlight' : 'hide';
    document.getElementById('confirmKeywordText').textContent =
        'Delete "' + value + '" from your ' + label + ' keywords?';
    document.getElementById('confirmKeywordModal').classList.add('active');
}

function closeConfirmKeyword() {
    document.getElementById('confirmKeywordModal').classList.remove('active');
    pendingKeywordDelete = null;
}

async function confirmDeleteKeyword() {
    if (!pendingKeywordDelete) return;
    const pending = pendingKeywordDelete;
    pendingKeywordDelete = null;
    document.getElementById('confirmKeywordModal').classList.remove('active');
    try {
        await api('/api/keywords/delete', 'POST', { type: pending.type, values: [pending.value] });
        await loadKeywords();
        toast('Deleted "' + pending.value + '"');
    } catch (e) {
        toast('Could not delete keyword');
    }
}

function openKeywordManager(type) {
    manageType = type;
    const label = type === 'focus' ? 'highlight' : 'hide';
    document.getElementById('modalTitle').textContent = 'Manage ' + label + ' keywords';
    document.getElementById('keywordModalIntro').textContent =
        'Uncheck a keyword to pause it. Paused keywords stay saved and can be re-enabled. ' +
        'Use the x on a tag to delete it permanently.';
    const list = document.getElementById('keywordCheckboxList');
    if (!filters[type].length) {
        list.innerHTML = '<p class="kw-empty">No keywords to manage</p>';
    } else {
        list.innerHTML = filters[type].map(item =>
            '<label class="cb-item"><input type="checkbox" class="kw-checkbox" value="' +
            escapeHtml(item.value).replace(/"/g, '&quot;') + '"' +
            (item.enabled ? ' checked' : '') + '><span>' + escapeHtml(item.value) + '</span></label>'
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

async function saveKeywordStates() {
    const states = {};
    document.querySelectorAll('.kw-checkbox').forEach(cb => {
        states[cb.value] = cb.checked;
    });
    if (!Object.keys(states).length) {
        closeKeywordManager();
        return;
    }
    try {
        await api('/api/keywords/state', 'POST', { type: manageType, states: states });
        closeKeywordManager();
        await loadKeywords();
        toast('Keyword settings saved');
    } catch (e) {
        toast('Could not save keyword settings');
    }
}

/* ---------------------------------------------------------------------
   CV import
   --------------------------------------------------------------------- */

function openProfileModal() {
    profileProposal = null;
    document.getElementById('profileError').textContent = '';
    document.getElementById('profileReviewError').textContent = '';
    document.getElementById('cvFileStatus').textContent = '';
    document.getElementById('cvFileError').textContent = '';
    document.getElementById('llmTestStatus').textContent = '';
    document.getElementById('llmTestStatus').className = 'llm-test-status';
    document.getElementById('llmTestBtn').disabled = false;
    document.getElementById('profileStepInput').style.display = '';
    document.getElementById('profileStepLoading').style.display = 'none';
    document.getElementById('profileStepReview').style.display = 'none';
    document.getElementById('profileAnalyzeBtn').style.display = '';
    document.getElementById('profileBackBtn').style.display = 'none';
    document.getElementById('profileApplyBtn').style.display = 'none';
    document.getElementById('profileApplyBtn').disabled = false;
    document.getElementById('profileModal').classList.add('active');
    refreshLlmTarget();
}

function closeProfileModal() {
    document.getElementById('profileModal').classList.remove('active');
}

async function refreshLlmTarget() {
    const badge = document.getElementById('llmBadge');
    const target = document.getElementById('llmTarget');
    const warning = document.getElementById('llmWarning');
    try {
        const data = await api('/api/profile');
        const llm = data.llm || {};
        if (!llm.configured) {
            badge.className = 'llm-badge unknown';
            badge.textContent = 'No model';
            target.textContent = 'No model configured.';
            warning.textContent = 'Set JSEARCH_LLM_BASE_URL, JSEARCH_LLM_MODEL and JSEARCH_LLM_API_KEY in .env, then restart J-Search.';
            return;
        }

        const host = llm.host || llm.base_url;
        badge.className = 'llm-badge ' + (llm.local ? 'local' : 'remote');
        badge.textContent = llm.local ? 'Local' : 'Remote';
        target.textContent = 'Model: ' + llm.model + ' @ ' + host;

        if (llm.local) {
            warning.textContent = llm.default_config
                ? 'Local default. If Ollama is not installed, set a hosted endpoint in .env.'
                : 'CV text stays on this machine.';
        } else {
            warning.textContent = 'CV text is sent to ' + host +
                '. Email, phone, URLs and handles are masked; your name, employers, education and dates are not.';
            if (!llm.has_api_key) {
                warning.textContent += ' No API key is set; add JSEARCH_LLM_API_KEY to .env.';
            }
        }
    } catch (e) {
        badge.className = 'llm-badge unknown';
        badge.textContent = 'Model';
        target.textContent = 'Could not read the model configuration.';
        warning.textContent = '';
    }
}

async function testLlm() {
    const btn = document.getElementById('llmTestBtn');
    const status = document.getElementById('llmTestStatus');
    status.className = 'llm-test-status';
    status.textContent = 'Testing...';
    btn.disabled = true;
    try {
        const data = await api('/api/llm/test', 'POST');
        status.className = 'llm-test-status ok';
        status.textContent = 'Connected to ' + data.model + ' at ' + data.host +
            ' in ' + data.latency_ms + ' ms.';
    } catch (e) {
        status.className = 'llm-test-status error';
        status.textContent = e.message;
    } finally {
        btn.disabled = false;
    }
}

const CV_MAX_BYTES = 10 * 1024 * 1024;

function setupCvDrop() {
    const drop = document.getElementById('cvDrop');
    const input = document.getElementById('cvFile');

    input.addEventListener('change', () => {
        const file = input.files && input.files[0];
        if (file) extractCvFile(file);
    });

    ['dragenter', 'dragover'].forEach(name => {
        drop.addEventListener(name, e => {
            e.preventDefault();
            drop.classList.add('dragover');
        });
    });

    drop.addEventListener('dragleave', () => drop.classList.remove('dragover'));

    drop.addEventListener('drop', e => {
        e.preventDefault();
        drop.classList.remove('dragover');
        const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        if (file) extractCvFile(file);
    });

    drop.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            input.click();
        }
    });
}

async function extractCvFile(file) {
    const errorEl = document.getElementById('cvFileError');
    const statusEl = document.getElementById('cvFileStatus');
    const drop = document.getElementById('cvDrop');
    document.getElementById('profileError').textContent = '';
    errorEl.textContent = '';
    statusEl.textContent = '';

    const name = file.name || 'CV';
    if (file.size > CV_MAX_BYTES) {
        errorEl.textContent = 'That file is larger than 10 MB.';
        return;
    }

    document.getElementById('cvText').value = '';
    drop.classList.add('busy');
    statusEl.textContent = 'Reading ' + name + '...';
    try {
        const res = await fetch('/api/profile/extract', {
            method: 'POST',
            headers: { 'Content-Type': 'application/octet-stream' },
            body: file
        });
        const data = await res.json().catch(() => null);
        if (!res.ok) throw new Error((data && data.error) || ('HTTP ' + res.status));

        document.getElementById('cvText').value = data.text || '';
        const pages = data.pages
            ? ' (' + data.pages + ' page' + (data.pages === 1 ? '' : 's') + ')'
            : '';
        let message = 'Extracted text from ' + name + pages + '. Review it before analysing.';
        (data.warnings || []).forEach(warning => { message += ' ' + warning; });
        statusEl.textContent = message;
    } catch (e) {
        statusEl.textContent = '';
        errorEl.textContent = e.message;
    } finally {
        drop.classList.remove('busy');
        document.getElementById('cvFile').value = '';
    }
}

async function analyzeCv() {
    const cv = document.getElementById('cvText').value.trim();
    const preferences = document.getElementById('cvPreferences').value.trim();
    const errorEl = document.getElementById('profileError');
    errorEl.textContent = '';
    if (cv.length < 40) {
        errorEl.textContent = 'Add a few lines of your CV first.';
        document.getElementById('cvText').focus();
        return;
    }

    document.getElementById('profileStepInput').style.display = 'none';
    document.getElementById('profileStepReview').style.display = 'none';
    document.getElementById('profileStepLoading').style.display = '';
    document.getElementById('profileAnalyzeBtn').style.display = 'none';

    try {
        const data = await api('/api/profile/analyze', 'POST', {
            cv_text: cv,
            preferences: preferences,
            strictness: strictness
        });
        profileProposal = data.proposal;
        renderProfileProposal(data);
        document.getElementById('profileStepLoading').style.display = 'none';
        document.getElementById('profileStepReview').style.display = '';
        document.getElementById('profileBackBtn').style.display = '';
        document.getElementById('profileApplyBtn').style.display = '';
    } catch (e) {
        document.getElementById('profileStepLoading').style.display = 'none';
        document.getElementById('profileStepInput').style.display = '';
        document.getElementById('profileAnalyzeBtn').style.display = '';
        errorEl.textContent = e.message;
    }
}

function backToProfileInput() {
    document.getElementById('profileStepReview').style.display = 'none';
    document.getElementById('profileStepInput').style.display = '';
    document.getElementById('profileAnalyzeBtn').style.display = '';
    document.getElementById('profileBackBtn').style.display = 'none';
    document.getElementById('profileApplyBtn').style.display = 'none';
}

function weightInput(id, label, value, min, max) {
    const number = Number(value);
    const safe = Number.isFinite(number) ? number : 0;
    return '<label>' + escapeHtml(label) + ' <input type="number" id="' + id +
        '" value="' + safe + '" min="' + min + '" max="' + max + '"></label>';
}

function renderChip(style, value, checked, source) {
    const safe = escapeHtml(value).replace(/"/g, '&quot;');
    return '<label class="profile-chip ' + style + (checked ? ' checked' : '') + '">' +
        '<input type="checkbox"' + (checked ? ' checked' : '') + ' value="' + safe + '">' +
        '<span>' + escapeHtml(value) + '</span>' +
        (source ? '<span class="why">' + escapeHtml(source) + '</span>' : '') +
        '</label>';
}

function renderChipGroup(title, field, style, values, checked, hint) {
    const chips = (values && values.length)
        ? values.map(value => renderChip(style, value, checked, '')).join('')
        : '<span class="profile-empty">None</span>';
    return '<div class="profile-group"><h4>' + escapeHtml(title) +
        (hint ? ' <span class="hint">' + escapeHtml(hint) + '</span>' : '') +
        '</h4><div class="profile-chips" data-field="' + field + '">' + chips + '</div></div>';
}

function renderExcludeGroup(items) {
    if (!items || !items.length) return '';
    return '<div class="profile-group"><h4>Hide keywords <span class="hint">matching jobs disappear</span></h4>' +
        '<div class="profile-chips" data-field="exclude">' +
        items.map(item => renderChip('exclude', item.value, !!item.checked, item.source)).join('') +
        '</div></div>';
}

function renderProfileProposal(data) {
    const proposal = data.proposal || {};
    const profile = proposal.profile || {};
    const parts = [];

    parts.push('<div class="profile-weights">' +
        weightInput('weightCore', 'Core', profile.core_weight, 0, 100) +
        weightInput('weightAI', 'AI', profile.ai_weight, 0, 100) +
        weightInput('weightGood', 'Match', profile.good_weight, 0, 100) +
        weightInput('weightBad', 'Dealbreaker', profile.dealbreaker_weight, -100, 0) +
        '</div>');
    parts.push(renderChipGroup('Core skills', 'core_skills', 'core', profile.core_skills || [], true, ''));
    parts.push(renderChipGroup('AI & infrastructure', 'ai_skills', 'core', profile.ai_skills || [], true, ''));
    parts.push(renderChipGroup('Dealbreakers', 'dealbreakers', 'dealbreaker', profile.dealbreakers || [], true, 'hard drop under Strict and Balanced'));
    parts.push(renderExcludeGroup(proposal.exclude || []));
    parts.push('<div class="profile-group"><h4>Highlight keywords <span class="hint">derived from the selected CV skills</span></h4><p class="profile-focus" id="profileFocusPreview"></p></div>');

    const warnings = proposal.warnings || [];
    if (warnings.length) {
        parts.push('<div class="profile-group"><h4>Notes</h4><ul class="profile-notes">' +
            warnings.map(w => '<li>' + escapeHtml(w) + '</li>').join('') + '</ul></div>');
    }

    const reasons = data.reason_counts || {};
    const reasonKeys = Object.keys(reasons);
    if (reasonKeys.length) {
        parts.push('<div class="profile-group"><h4>Dismissal history <span class="hint">used for suggestions only</span></h4><ul class="profile-notes">' +
            reasonKeys.map(reason => '<li>' + escapeHtml(reason) + ': ' + reasons[reason] + '</li>').join('') +
            '</ul></div>');
    }

    document.getElementById('profileSections').innerHTML = parts.join('');
    updateFocusPreview();
    renderImpact(data.impact);
}

function selectedValues(field) {
    const box = document.querySelector('#profileSections [data-field="' + field + '"]');
    if (!box) return [];
    return Array.from(box.querySelectorAll('input:checked')).map(cb => cb.value);
}

function currentFocus() {
    const seen = new Set();
    const out = [];
    selectedValues('core_skills').concat(selectedValues('ai_skills')).forEach(value => {
        if (!seen.has(value)) {
            seen.add(value);
            out.push(value);
        }
    });
    return out.slice(0, 25);
}

function updateFocusPreview() {
    const el = document.getElementById('profileFocusPreview');
    if (!el) return;
    const values = currentFocus();
    el.textContent = values.length ? values.join(', ') : 'None - select at least one skill.';
}

function clampNumber(id, fallback, min, max) {
    const el = document.getElementById(id);
    let value = el ? parseInt(el.value, 10) : fallback;
    if (!Number.isFinite(value)) value = fallback;
    return Math.max(min, Math.min(max, value));
}

function collectProfile() {
    const profile = Object.assign({}, profileProposal.profile);
    profile.core_skills = selectedValues('core_skills');
    profile.ai_skills = selectedValues('ai_skills');
    profile.dealbreakers = selectedValues('dealbreakers');
    profile.core_weight = clampNumber('weightCore', profile.core_weight, 0, 100);
    profile.ai_weight = clampNumber('weightAI', profile.ai_weight, 0, 100);
    profile.good_weight = clampNumber('weightGood', profile.good_weight, 0, 100);
    profile.dealbreaker_weight = clampNumber('weightBad', profile.dealbreaker_weight, -100, 0);
    return {
        profile: profile,
        focus: currentFocus(),
        exclude: selectedValues('exclude'),
        strictness: strictness
    };
}

function renderImpact(impact) {
    const el = document.getElementById('profileImpact');
    if (!el || !impact) return;
    const before = Number(impact.before) || 0;
    const after = Number(impact.after) || 0;
    const labels = { strict: 'Strict', balanced: 'Balanced', lenient: 'Lenient' };
    let html = '<strong>' + before + '</strong> jobs visible now &rarr; <strong>' + after +
        '</strong> after applying (' + (labels[strictness] || 'Balanced') + ').';
    if (impact.hidden_by_exclude) {
        html += '<br><span class="impact-warn">' + impact.hidden_by_exclude + ' hidden by the new hide keywords.</span>';
    }
    if (impact.hidden_by_score) {
        html += '<br>' + impact.hidden_by_score + ' drop out because of scoring changes.';
    }
    if (impact.newly_visible) {
        html += '<br>' + impact.newly_visible + ' become visible again.';
    }
    if (impact.newly_highlighted) {
        html += '<br>' + impact.newly_highlighted + ' will get a highlight outline.';
    }
    el.innerHTML = html;
}

function schedulePreview() {
    if (profilePreviewTimer) clearTimeout(profilePreviewTimer);
    profilePreviewTimer = setTimeout(previewProfile, 450);
}

async function previewProfile() {
    if (!profileProposal) return;
    try {
        const data = await api('/api/profile/preview', 'POST', collectProfile());
        renderImpact(data.impact);
    } catch (e) {
        /* Keep the last good preview if a request fails. */
    }
}

async function applyProfile() {
    if (!profileProposal) return;
    const button = document.getElementById('profileApplyBtn');
    const errorEl = document.getElementById('profileReviewError');
    errorEl.textContent = '';
    button.disabled = true;
    try {
        await api('/api/profile/apply', 'POST', collectProfile());
        toast('Profile applied');
        window.location.reload();
    } catch (e) {
        errorEl.textContent = e.message;
        button.disabled = false;
    }
}

function updateCounts(data) {
    if (!data) return;
    if (typeof data.applied_count === 'number') {
        document.getElementById('appliedCount').textContent = data.applied_count;
    }
    if (typeof data.dismissed_count === 'number') {
        document.getElementById('hiddenCount').textContent = data.dismissed_count;
    }
}

async function decide(job, status, reason, note) {
    try {
        const data = await api('/api/decisions', 'POST', {
            key: job.key,
            status: status,
            reason: reason || '',
            note: note || '',
            job: {
                title: job.title,
                company: job.company,
                location: job.location,
                url: job.url,
                source: job.source,
                score: job.score
            }
        });
        ALL_JOBS = ALL_JOBS.filter(j => j.key !== job.key);
        lastDecision = { job: job, status: status };
        renderResults();
        updateCounts(data);
        toast(status === 'applied' ? 'Marked as applied' : 'Hidden from results', 'Undo', undoLastDecision);
    } catch (e) {
        toast('Could not save that decision');
        renderResults();
    }
}

async function undoLastDecision() {
    if (!lastDecision) return;
    const job = lastDecision.job;
    lastDecision = null;
    try {
        const data = await api('/api/decisions/delete', 'POST', { key: job.key });
        if (!ALL_JOBS.some(j => j.key === job.key)) {
            ALL_JOBS.push(job);
        }
        renderResults();
        updateCounts(data);
        toast('Restored to results');
    } catch (e) {
        toast('Could not undo');
    }
}

function openDecisionModal(job) {
    pendingDismissJob = job;
    document.getElementById('decisionJobTitle').textContent = job.title + ' - ' + job.company;
    document.querySelectorAll('.reason-radio').forEach(r => { r.checked = false; });
    document.getElementById('decisionNote').value = '';
    document.getElementById('decisionModal').classList.add('active');
}

function closeDecisionModal() {
    document.getElementById('decisionModal').classList.remove('active');
    pendingDismissJob = null;
}

async function submitDismissal() {
    const selected = document.querySelector('.reason-radio:checked');
    if (!selected) {
        toast('Pick a reason first');
        return;
    }
    const job = pendingDismissJob;
    if (!job) {
        closeDecisionModal();
        return;
    }
    const reason = selected.value;
    const note = document.getElementById('decisionNote').value.trim();
    closeDecisionModal();
    await decide(job, 'dismissed', reason, note);
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

function enabledKeywordValues(type) {
    return filters[type].filter(k => k.enabled).map(k => k.value);
}

function skillMatches(text, skill) {
    skill = String(skill || '').toLowerCase().trim();
    if (!skill) return false;
    if (/^[a-z0-9]+(?:[ /-][a-z0-9]+)*$/.test(skill)) {
        try {
            return new RegExp('\\\\b' + skill + '\\\\b').test(text);
        } catch (e) {
            return text.includes(skill);
        }
    }
    return text.includes(skill);
}

function passesFilters(job) {
    const text = ((job.title || '') + ' ' + (job.desc || '')).toLowerCase();

    for (const ex of enabledKeywordValues('exclude')) {
        if (skillMatches(text, ex)) return false;
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
    return enabledKeywordValues('focus').some(k => skillMatches(text, k));
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
        const keyAttr = encodeURIComponent(job.key || '');
        return '<div class="card' + focusClass + '">' +
            '<div class="card-main">' +
                '<h3 class="card-title">' + escapeHtml(job.title) + '</h3>' +
                '<div class="card-meta">' + escapeHtml(job.company) + ' &bull; ' + escapeHtml(job.location) + '</div>' +
                '<div class="badges">' + focusBadge + good + bad + '</div>' +
                '<div class="card-actions">' +
                    '<a href="' + escapeHtml(job.url) + '" target="_blank" rel="noopener noreferrer" class="btn btn-primary">Review Entry &rarr;</a>' +
                    '<button class="btn btn-apply" data-decision="applied" data-key="' + keyAttr + '">&#10003; Applied</button>' +
                    '<button class="btn btn-dismiss" data-decision="dismissed" data-key="' + keyAttr + '">&#10005; Not for me</button>' +
                '</div>' +
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
        openDeleteKeyword(x.dataset.type, decodeURIComponent(x.dataset.value));
    }
});

document.getElementById('confirmKeywordModal').addEventListener('click', e => {
    if (e.target.id === 'confirmKeywordModal') closeConfirmKeyword();
});

document.addEventListener('click', function (e) {
    const voteBtn = e.target.closest('[data-decision]');
    if (!voteBtn) return;
    const key = decodeURIComponent(voteBtn.dataset.key || '');
    const job = ALL_JOBS.find(j => j.key === key);
    if (!job) return;
    if (voteBtn.dataset.decision === 'applied') {
        voteBtn.disabled = true;
        decide(job, 'applied', '', '');
    } else {
        openDecisionModal(job);
    }
});

document.getElementById('decisionModal').addEventListener('click', e => {
    if (e.target.id === 'decisionModal') closeDecisionModal();
});

document.getElementById('profileModal').addEventListener('click', e => {
    if (e.target.id === 'profileModal') closeProfileModal();
});

document.getElementById('profileSections').addEventListener('change', e => {
    const chip = e.target.closest('.profile-chip');
    if (chip) chip.classList.toggle('checked', e.target.checked);
    updateFocusPreview();
    schedulePreview();
});

document.getElementById('profileSections').addEventListener('input', e => {
    if (e.target.type === 'number') schedulePreview();
});

setupCvDrop();
loadKeywords();
</script>
</body>
</html>"""


def build_dashboard(remote_jobs=None, local_leads=None, config=None,
                    exclude_keys=None, applied_count=0, dismissed_count=0):
    remote_jobs = remote_jobs or []
    local_leads = local_leads or []
    if config is None:
        config = DEFAULT_SCORING_CONFIG
    exclude_keys = set(exclude_keys or ())

    all_jobs_data = []

    def add_job(job, source):
        if _is_blocked(job.get('url', '')):
            return
        key = job_key(job.get('url', ''), job.get('title', ''),
                      job.get('company', ''), job.get('location', ''))
        if key in exclude_keys:
            return
        score, goods, bads = score_job(job, config)
        all_jobs_data.append({
            "id": len(all_jobs_data),
            "key": key,
            "title": job.get('title', ''),
            "company": job.get('company', ''),
            "location": job.get('location', ''),
            "url": job.get('url', '#'),
            "desc": job.get('desc', ''),
            "score": score,
            "matches": goods,
            "redFlags": bads,
            "source": source,
        })

    for job in remote_jobs:
        add_job(job, "global")

    for job in local_leads:
        add_job(job, "local")

    jobs_json = json.dumps(all_jobs_data).replace('</', '<\\/')
    html_content = DASHBOARD_TEMPLATE.replace('__APPLIED_COUNT__', str(applied_count))
    html_content = html_content.replace('__DISMISSED_COUNT__', str(dismissed_count))
    html_content = html_content.replace('__JOBS_JSON__', jobs_json)

    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
        f.write(html_content)

    print("[OK] Dashboard compiled -> " + os.path.realpath(DASHBOARD_PATH))
