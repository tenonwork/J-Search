import os
import re
import json
from urllib.parse import urlparse

from .paths import DASHBOARD_PATH


DASHBOARD_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0b0f19">
<meta name="description" content="J-Search — local-first job triage, scoring and application tracking.">
<title>J-Search — Your Digital Navigator</title>
<link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32.png">
<link rel="icon" type="image/png" sizes="64x64" href="/static/icon-64.png">
<link rel="icon" type="image/png" sizes="512x512" href="/static/icon-512.png">
<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
<script>window.__JSEARCH_BOOTSTRAP__ = __BOOTSTRAP_JSON__;</script>
<link rel="stylesheet" href="/static/app.css">
<script type="module" src="/static/app.js"></script>
</head>
<body>
<div id="root"></div>
</body>
</html>
"""


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
    "pos_skills": ["pos"],
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
    "pos_skills", "pos_weight",
    "dealbreakers", "dealbreaker_weight",
)

# The editable score weights, in the order the dashboard shows them. `list_field`
# points at the keyword list each weight applies to. POS is a normal, editable
# group like the rest.
WEIGHT_GROUPS = (
    {
        "key": "core_weight",
        "list_field": "core_skills",
        "label": "Core skills",
        "description": "Your strongest stack keywords. Every match adds the full core weight.",
        "tone": "cyan",
        "min": 0,
        "max": 100,
    },
    {
        "key": "ai_weight",
        "list_field": "ai_skills",
        "label": "AI & infrastructure",
        "description": "AI, data and tooling keywords. Each match adds the AI weight.",
        "tone": "blue",
        "min": 0,
        "max": 100,
    },
    {
        "key": "good_weight",
        "list_field": "good_matches",
        "label": "Good matches",
        "description": "Location, work style and general fit terms such as remote, hybrid or Nairobi.",
        "tone": "emerald",
        "min": 0,
        "max": 100,
    },
    {
        "key": "pos_weight",
        "list_field": "pos_skills",
        "label": "POS systems",
        "description": "Point-of-sale terms such as pos, till or checkout. Each match adds the POS weight.",
        "tone": "amber",
        "min": 0,
        "max": 100,
    },
    {
        "key": "dealbreaker_weight",
        "list_field": "dealbreakers",
        "label": "Dealbreakers",
        "description": "Red flags such as senior, lead or 10+ years. Each match subtracts this penalty.",
        "tone": "rose",
        "min": -100,
        "max": 0,
    },
)

WEIGHT_FIELDS = tuple(group["key"] for group in WEIGHT_GROUPS)

_PROFILE_LIST_FIELDS = {
    "core_skills": 60,
    "ai_skills": 40,
    "good_matches": 40,
    "pos_skills": 40,
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


def profile_from_config(config):
    """Flat profile (weights + lists) for a resolved per-scope config."""
    result = {"version": PROFILE_VERSION}
    for field in PROFILE_FIELDS:
        value = config.get(field, DEFAULT_SCORING_CONFIG.get(field))
        result[field] = list(value) if isinstance(value, list) else value
    return result


def weights_view(config=None, profile=None):
    """Everything the weights form needs to show and explain the scoring scale."""
    config = config or DEFAULT_SCORING_CONFIG

    groups = []
    for definition in WEIGHT_GROUPS:
        item = dict(definition)
        item["weight"] = int(config.get(definition["key"], DEFAULT_SCORING_CONFIG[definition["key"]]))
        item["keywords"] = list(config.get(definition["list_field"], []))
        item["system"] = False
        groups.append(item)

    return {
        "weights": {group["key"]: group["weight"] for group in groups},
        "defaults": {key: int(DEFAULT_SCORING_CONFIG[key]) for key in WEIGHT_FIELDS},
        "groups": groups,
        "profile": effective_profile(profile),
    }


def merge_weight_overrides(profile, weights):
    """Merge validated weight changes into the stored profile.

    Returns an empty dict when no valid weight was supplied, so callers can tell
    a bad request from a successful merge.
    """
    if not isinstance(weights, dict):
        return {}
    clean = normalize_scoring_profile({
        key: value for key, value in weights.items() if key in WEIGHT_FIELDS
    })
    if not clean:
        return {}
    merged = dict(normalize_scoring_profile(profile or {}))
    merged.update(clean)
    return normalize_scoring_profile(merged)


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
    pos_skills = config.get('pos_skills', DEFAULT_SCORING_CONFIG['pos_skills'])
    pos_weight = config.get('pos_weight', 5)
    dealbreakers = config.get('dealbreakers', DEFAULT_SCORING_CONFIG['dealbreakers'])
    dealbreaker_weight = config.get('dealbreaker_weight', -30)

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

    for word in pos_skills:
        if _matches_skill(text, word):
            score += pos_weight
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


def build_dashboard(remote_jobs=None, local_leads=None, config=None, configs=None,
                    exclude_keys=None, applied_count=0, dismissed_count=0):
    remote_jobs = remote_jobs or []
    local_leads = local_leads or []
    if config is None:
        config = DEFAULT_SCORING_CONFIG
    configs = configs if isinstance(configs, dict) else {}
    exclude_keys = set(exclude_keys or ())

    all_jobs_data = []

    def add_job(job, source):
        if _is_blocked(job.get('url', '')):
            return
        key = job_key(job.get('url', ''), job.get('title', ''),
                      job.get('company', ''), job.get('location', ''))
        if key in exclude_keys:
            return
        job_config = configs.get(source) or config
        score, goods, bads = score_job(job, job_config)
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

    bootstrap = {
        "jobs": all_jobs_data,
        "appliedCount": applied_count,
        "dismissedCount": dismissed_count,
    }
    bootstrap_json = json.dumps(bootstrap).replace('</', '<\\/')
    html_content = DASHBOARD_SHELL.replace('__BOOTSTRAP_JSON__', bootstrap_json)

    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
        f.write(html_content)

    print("[OK] Dashboard compiled -> " + os.path.realpath(DASHBOARD_PATH))
