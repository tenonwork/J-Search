import sqlite3
import json
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from .paths import DB_PATH

DEFAULT_KEYWORDS = {
    "focus": ["react", "typescript", "python", "postgres", "supabase"],
    "exclude": ["senior", "lead", "manager", "architect"],
}

KEYWORD_SCOPES = ('global', 'local')
KEYWORD_TYPES = ('focus', 'exclude', 'score')
KEYWORD_WEIGHT_GROUPS = (
    'core_skills',
    'ai_skills',
    'good_matches',
    'pos_skills',
    'dealbreakers',
)
MAX_KEYWORD_LENGTH = 60
MAX_KEYWORDS_PER_SCOPE = 400
KEYWORD_WORKSPACE_VERSION = 2
KEYWORD_WORKSPACE_VERSION_SETTING = 'keyword_workspace_version'

LOCAL_SITES_SETTING = "local_sites"
MAX_LOCAL_SITES = 50

DISCOVERY_QUERIES_SETTING = "discovery_queries"
MAX_DISCOVERY_QUERIES = 10
MAX_DISCOVERY_QUERY_LENGTH = 120

DEFAULT_LOCAL_SITES = (
    {
        "url": "https://www.co-opbank.co.ke/career_tax/co-op-bank/",
        "label": "Co-operative Bank of Kenya",
        "enabled": True,
    },
)


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_keyword_value(value):
    """Normalise one keyword for storage and matching."""
    if not isinstance(value, str):
        return ''
    value = " ".join(value.lower().split()).strip(" ,;:")
    return value[:MAX_KEYWORD_LENGTH]


def _default_scoring_lists():
    from .job_dashboard import DEFAULT_SCORING_CONFIG
    return {
        field: [
            normalize_keyword_value(value)
            for value in DEFAULT_SCORING_CONFIG.get(field, [])
            if normalize_keyword_value(value)
        ]
        for field in KEYWORD_WEIGHT_GROUPS
    }


def _weight_by_field(profile):
    from .job_dashboard import DEFAULT_SCORING_CONFIG, WEIGHT_GROUPS
    profile = profile if isinstance(profile, dict) else {}
    result = {}
    for group in WEIGHT_GROUPS:
        field = group.get('list_field')
        if not field:
            continue
        try:
            result[field] = int(
                profile.get(group['key'], DEFAULT_SCORING_CONFIG.get(group['key'], 0))
            )
        except (TypeError, ValueError):
            result[field] = int(DEFAULT_SCORING_CONFIG.get(group['key'], 0))
    return result


def _weights_from_profile(profile):
    from .job_dashboard import DEFAULT_SCORING_CONFIG, WEIGHT_GROUPS
    profile = profile if isinstance(profile, dict) else {}
    weights = {}
    for group in WEIGHT_GROUPS:
        key = group['key']
        try:
            weights[key] = int(
                profile.get(key, DEFAULT_SCORING_CONFIG.get(key, 0))
            )
        except (TypeError, ValueError):
            weights[key] = int(DEFAULT_SCORING_CONFIG.get(key, 0))
    return weights


def _pick_weight_group(value, lists, weights):
    """Pick one weight for a keyword when legacy data has duplicates.

    Keeps the group with the largest absolute weight; ties follow the
    canonical group order so the result is deterministic.
    """
    candidates = [
        field for field in KEYWORD_WEIGHT_GROUPS
        if value in lists.get(field, ())
    ]
    if not candidates:
        return ''
    return max(
        candidates,
        key=lambda field: (
            abs(weights.get(field, 0)),
            -KEYWORD_WEIGHT_GROUPS.index(field),
        ),
    )


def _keyword_columns(c):
    return {row['name'] for row in c.execute('PRAGMA table_info(keywords)').fetchall()}


def _keyword_unique_keys(c):
    keys = []
    for index in c.execute('PRAGMA index_list(keywords)').fetchall():
        if not index['unique']:
            continue
        name = index['name'].replace('"', '""')
        columns = [
            row['name']
            for row in c.execute(f'PRAGMA index_info("{name}")').fetchall()
        ]
        keys.append(columns)
    return keys


def _is_workspace_schema(c):
    columns = _keyword_columns(c)
    if 'scope' not in columns or 'weight_group' not in columns:
        return False
    return ['scope', 'value'] in _keyword_unique_keys(c)


def _create_keywords_table(c):
    c.execute('''CREATE TABLE IF NOT EXISTS keywords(
        id INTEGER PRIMARY KEY,
        scope TEXT NOT NULL DEFAULT 'global',
        value TEXT NOT NULL,
        weight_group TEXT NOT NULL DEFAULT '',
        type TEXT NOT NULL DEFAULT 'focus',
        enabled INTEGER NOT NULL DEFAULT 1,
        UNIQUE(scope, value)
    )''')


def _get_setting_raw(c, key, default=None):
    row = c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row['value'])
    except Exception:
        return default


def _set_setting_raw(c, key, value):
    c.execute('''INSERT INTO settings(key, value, updated_at) VALUES(?,?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at''',
        (key, json.dumps(value), _now_iso()))


def _read_legacy_keyword_rows(c):
    columns = _keyword_columns(c)
    if not columns or 'value' not in columns:
        return []
    rows = []
    for row in c.execute('SELECT * FROM keywords').fetchall():
        data = dict(row)
        kw_type = str(data.get('type') or 'focus').strip().lower()
        if kw_type not in ('focus', 'exclude'):
            continue
        value = normalize_keyword_value(data.get('value'))
        if not value:
            continue
        rows.append({
            'type': kw_type,
            'value': value,
            'enabled': bool(data.get('enabled', 1)),
        })
    return rows


def _normalise_list(values, fallback=()):
    if not isinstance(values, (list, tuple)):
        values = fallback
    out = []
    seen = set()
    for value in values:
        value = normalize_keyword_value(value)
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
        if len(out) >= 60:
            break
    return out


def _scoring_lists_from_profile(profile):
    defaults = _default_scoring_lists()
    lists = {}
    for field in KEYWORD_WEIGHT_GROUPS:
        raw = profile.get(field) if isinstance(profile, dict) else None
        lists[field] = _normalise_list(raw, defaults.get(field, []))
    return lists


def _workspace_seed_rows(legacy_rows, scoring_lists, weights_by_field):
    row_map = {}
    for item in legacy_rows:
        value = item['value']
        current = row_map.get(value)
        if current is None:
            row_map[value] = {
                'type': item['type'],
                'enabled': bool(item.get('enabled', True)),
            }
            continue
        if item['type'] == 'exclude':
            current['type'] = 'exclude'
            current['enabled'] = bool(item.get('enabled', True))
        elif current['type'] != 'exclude':
            current['enabled'] = current['enabled'] or bool(item.get('enabled', True))

    list_sets = {
        field: set(_normalise_list(values))
        for field, values in scoring_lists.items()
    }
    for field in KEYWORD_WEIGHT_GROUPS:
        for value in list_sets[field]:
            row_map.setdefault(value, {'type': 'score', 'enabled': True})

    rows = []
    for value in sorted(row_map):
        item = row_map[value]
        rows.append({
            'value': value,
            'weight_group': _pick_weight_group(value, list_sets, weights_by_field),
            'type': item['type'],
            'enabled': bool(item.get('enabled', True)),
        })
    return rows


def _default_legacy_rows():
    rows = []
    for kw_type, values in DEFAULT_KEYWORDS.items():
        for value in values:
            value = normalize_keyword_value(value)
            if value:
                rows.append({
                    'type': kw_type,
                    'value': value,
                    'enabled': True,
                })
    return rows


def _seed_workspace(c):
    profile = _get_setting_raw(c, 'scoring_profile', {})
    profile = profile if isinstance(profile, dict) else {}
    legacy_rows = _read_legacy_keyword_rows(c)
    if not legacy_rows:
        legacy_rows = _default_legacy_rows()
    lists = _scoring_lists_from_profile(profile)
    rows = _workspace_seed_rows(legacy_rows, lists, _weight_by_field(profile))
    c.executemany('''INSERT OR IGNORE INTO keywords(
            scope, value, weight_group, type, enabled)
        VALUES(?,?,?,?,?)''', [
        (scope, row['value'], row['weight_group'], row['type'],
         1 if row['enabled'] else 0)
        for scope in KEYWORD_SCOPES
        for row in rows
    ])
    _set_setting_raw(c, 'scoring_profile', _weights_from_profile(profile))
    return rows


def _ensure_keyword_workspace(c):
    version = _get_setting_raw(c, KEYWORD_WORKSPACE_VERSION_SETTING)
    if _is_workspace_schema(c):
        if version == KEYWORD_WORKSPACE_VERSION:
            return
        count = c.execute('SELECT COUNT(*) AS n FROM keywords').fetchone()['n']
        if count == 0:
            _seed_workspace(c)
        else:
            profile = _get_setting_raw(c, 'scoring_profile', {})
            _set_setting_raw(c, 'scoring_profile', _weights_from_profile(profile))
        _set_setting_raw(c, KEYWORD_WORKSPACE_VERSION_SETTING, KEYWORD_WORKSPACE_VERSION)
        return

    legacy_rows = _read_legacy_keyword_rows(c)
    if not legacy_rows:
        legacy_rows = _default_legacy_rows()
    profile = _get_setting_raw(c, 'scoring_profile', {})
    profile = profile if isinstance(profile, dict) else {}
    lists = _scoring_lists_from_profile(profile)
    rows = _workspace_seed_rows(legacy_rows, lists, _weight_by_field(profile))

    c.execute('ALTER TABLE keywords RENAME TO keywords_legacy')
    _create_keywords_table(c)
    c.executemany('''INSERT OR IGNORE INTO keywords(
            scope, value, weight_group, type, enabled)
        VALUES(?,?,?,?,?)''', [
        (scope, row['value'], row['weight_group'], row['type'],
         1 if row['enabled'] else 0)
        for scope in KEYWORD_SCOPES
        for row in rows
    ])
    c.execute('DROP TABLE keywords_legacy')
    _set_setting_raw(c, 'scoring_profile', _weights_from_profile(profile))
    _set_setting_raw(c, KEYWORD_WORKSPACE_VERSION_SETTING, KEYWORD_WORKSPACE_VERSION)


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT ''
    )''')
    _create_keywords_table(c)
    _ensure_keyword_workspace(c)
    c.execute('CREATE INDEX IF NOT EXISTS idx_keywords_scope_type ON keywords(scope, type)')
    c.execute('''CREATE TABLE IF NOT EXISTS jobs(
        id INTEGER PRIMARY KEY,
        title TEXT,
        company TEXT,
        location TEXT,
        url TEXT UNIQUE,
        description TEXT,
        source TEXT,
        score INTEGER,
        matches TEXT,
        redflags TEXT,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS decisions(
        job_key TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '',
        company TEXT NOT NULL DEFAULT '',
        location TEXT NOT NULL DEFAULT '',
        url TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT '',
        score INTEGER NOT NULL DEFAULT 0,
        applied_at TEXT,
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_decisions_status ON decisions(status)')
    conn.commit()
    conn.close()


def get_keyword_rows(scope=None):
    """All managed keyword rows, optionally limited to one scope."""
    init_db()
    conn = get_conn()
    c = conn.cursor()
    if scope in KEYWORD_SCOPES:
        c.execute('''SELECT scope, value, weight_group, type, enabled
            FROM keywords WHERE scope=? ORDER BY value''', (scope,))
    else:
        c.execute('''SELECT scope, value, weight_group, type, enabled
            FROM keywords ORDER BY scope, value''')
    rows = c.fetchall()
    conn.close()
    return [{
        'scope': r['scope'],
        'value': r['value'],
        'weight_group': r['weight_group'] or '',
        'type': r['type'] if r['type'] in KEYWORD_TYPES else 'focus',
        'enabled': bool(r['enabled']),
    } for r in rows]


def get_keywords(scope='global'):
    scope = scope if scope in KEYWORD_SCOPES else 'global'
    result = {'focus': [], 'exclude': []}
    for row in get_keyword_rows(scope):
        if row['type'] in result:
            result[row['type']].append({
                'value': row['value'],
                'enabled': row['enabled'],
                'weight_group': row['weight_group'],
            })
    return result


def get_scoring_lists(scope='global'):
    """Enabled keywords grouped by the weight they feed."""
    scope = scope if scope in KEYWORD_SCOPES else 'global'
    lists = {field: [] for field in KEYWORD_WEIGHT_GROUPS}
    for row in get_keyword_rows(scope):
        if row['enabled'] and row['weight_group'] in lists:
            lists[row['weight_group']].append(row['value'])
    return lists


def get_workspace():
    return {
        'weights': get_scoring_profile() or {},
        'scopes': {scope: get_keyword_rows(scope) for scope in KEYWORD_SCOPES},
    }


def normalize_workspace_rows(rows, scope):
    """Validate and normalise one scope's keyword rows for a full save."""
    if scope not in KEYWORD_SCOPES or not isinstance(rows, (list, tuple)):
        return []
    clean = []
    seen = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        value = normalize_keyword_value(item.get('value'))
        if not value or value in seen:
            continue
        seen.add(value)
        weight_group = str(item.get('weight_group') or '').strip().lower()
        if weight_group not in KEYWORD_WEIGHT_GROUPS:
            weight_group = ''
        kw_type = str(item.get('type') or 'focus').strip().lower()
        if kw_type not in KEYWORD_TYPES:
            kw_type = 'focus'
        if not weight_group and kw_type == 'score':
            kw_type = 'focus'
        clean.append({
            'scope': scope,
            'value': value,
            'weight_group': weight_group,
            'type': kw_type,
            'enabled': bool(item.get('enabled', True)),
        })
        if len(clean) >= MAX_KEYWORDS_PER_SCOPE:
            break
    return clean


def save_workspace(weights, scopes):
    """Replace both keyword sets and merge the shared weights atomically."""
    from .job_dashboard import WEIGHT_FIELDS, normalize_scoring_profile

    if not isinstance(scopes, dict):
        return False
    incoming = {
        key: value for key, value in (weights or {}).items()
        if key in WEIGHT_FIELDS
    }
    clean_weights = normalize_scoring_profile(incoming)
    if not clean_weights:
        return False

    rows = []
    for scope in KEYWORD_SCOPES:
        rows.extend(normalize_workspace_rows(scopes.get(scope, []), scope))

    init_db()
    conn = get_conn()
    c = conn.cursor()
    try:
        existing = _get_setting_raw(c, 'scoring_profile', {})
        merged_weights = _weights_from_profile(existing)
        merged_weights.update(clean_weights)
        c.execute('DELETE FROM keywords')
        c.executemany('''INSERT INTO keywords(
                scope, value, weight_group, type, enabled)
            VALUES(?,?,?,?,?)''', [
            (row['scope'], row['value'], row['weight_group'], row['type'],
             1 if row['enabled'] else 0)
            for row in rows
        ])
        _set_setting_raw(c, 'scoring_profile', merged_weights)
        _set_setting_raw(c, KEYWORD_WORKSPACE_VERSION_SETTING, KEYWORD_WORKSPACE_VERSION)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def add_keyword(kw_type, value, weight_group='', scope='global'):
    if kw_type not in KEYWORD_TYPES:
        return False
    scope = scope if scope in KEYWORD_SCOPES else 'global'
    value = normalize_keyword_value(value)
    if not value:
        return False
    weight_group = weight_group if weight_group in KEYWORD_WEIGHT_GROUPS else ''
    if kw_type == 'score' and not weight_group:
        return False
    init_db()
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO keywords(scope, value, weight_group, type, enabled)
            VALUES(?,?,?,?,1)
            ON CONFLICT(scope, value) DO UPDATE SET
                enabled=1,
                type=excluded.type,
                weight_group=CASE
                    WHEN excluded.weight_group != '' THEN excluded.weight_group
                    ELSE keywords.weight_group
                END''', (scope, value, weight_group, kw_type))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def set_keyword_states(kw_type, states, scope='global'):
    """Persist which keywords are active.

    `states` maps keyword value -> bool. Disabled keywords stay in the table so
    they can be re-enabled later; they are not deleted.
    """
    if kw_type not in KEYWORD_TYPES or not isinstance(states, dict):
        return False
    scope = scope if scope in KEYWORD_SCOPES else 'global'
    init_db()
    conn = get_conn()
    c = conn.cursor()
    try:
        for value, enabled in states.items():
            value = normalize_keyword_value(value)
            if not value:
                continue
            c.execute(
                'UPDATE keywords SET enabled=? WHERE scope=? AND type=? AND value=?',
                (1 if enabled else 0, scope, kw_type, value),
            )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def delete_keywords(kw_type, values, scope='global'):
    if kw_type not in KEYWORD_TYPES and kw_type != 'all':
        return False
    scope = scope if scope in KEYWORD_SCOPES else 'global'
    init_db()
    conn = get_conn()
    c = conn.cursor()
    try:
        for value in values:
            value = normalize_keyword_value(value)
            if not value:
                continue
            if kw_type == 'all':
                c.execute(
                    'DELETE FROM keywords WHERE scope=? AND value=?',
                    (scope, value),
                )
            else:
                c.execute(
                    'DELETE FROM keywords WHERE scope=? AND type=? AND value=?',
                    (scope, kw_type, value),
                )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Settings: small JSON documents (scoring profile, candidate profile).
# ---------------------------------------------------------------------------

def get_setting(key, default=None):
    init_db()
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key=?', (key,))
    row = c.fetchone()
    conn.close()
    if not row:
        return default
    try:
        return json.loads(row['value'])
    except Exception:
        return default


def set_setting(key, value):
    init_db()
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO settings(key, value, updated_at) VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at''',
            (key, json.dumps(value), _now_iso()))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def delete_setting(key):
    init_db()
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute('DELETE FROM settings WHERE key=?', (key,))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_scoring_profile():
    profile = get_setting('scoring_profile')
    return profile if isinstance(profile, dict) else None


def save_scoring_profile(profile):
    """Persist the shared score weights only; keyword lists live in keywords."""
    from .job_dashboard import WEIGHT_FIELDS

    if not isinstance(profile, dict):
        return False
    weights = {key: profile[key] for key in WEIGHT_FIELDS if key in profile}
    if not weights:
        return False
    return set_setting('scoring_profile', weights)


def get_candidate_profile():
    candidate = get_setting('candidate_profile')
    return candidate if isinstance(candidate, dict) else None


def save_candidate_profile(candidate):
    return set_setting('candidate_profile', candidate)


def _clean_site_url(value):
    """Normalise a watched-source URL, or return an empty string."""
    if not isinstance(value, str):
        return ''
    url = value.strip()
    if not url or len(url) > 1000:
        return ''
    if '://' not in url:
        url = 'https://' + url
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return ''
    if parsed.scheme.lower() not in ('http', 'https'):
        return ''
    if not parsed.netloc or parsed.username or parsed.password:
        return ''
    if port not in (None, 80, 443):
        return ''
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path or '/',
        '',
        parsed.query,
        '',
    ))


def _site_key(url):
    """Deduplicate sources while ignoring scheme, a leading www and fragments."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix('www.')
    path = (parsed.path or '/').rstrip('/')
    return host + path + ('?' + parsed.query if parsed.query else '')


def _site_label_from_url(url):
    host = urlparse(url).netloc.lower().removeprefix('www.')
    return host or 'Local source'


def normalize_local_sites(sites):
    """Return a safe, deduplicated list of watched local career pages."""
    if not isinstance(sites, (list, tuple)):
        return []
    clean = []
    seen = set()
    for item in sites:
        if isinstance(item, str):
            item = {'url': item}
        if not isinstance(item, dict):
            continue
        url = _clean_site_url(item.get('url'))
        if not url:
            continue
        key = _site_key(url)
        if key in seen:
            continue
        seen.add(key)
        label = ' '.join(str(item.get('label') or '').split())[:120]
        clean.append({
            'url': url,
            'label': label or _site_label_from_url(url),
            'enabled': bool(item.get('enabled', True)),
        })
        if len(clean) >= MAX_LOCAL_SITES:
            break
    return clean


def get_local_sites():
    """Watched career pages. The default is returned only before the first save."""
    value = get_setting(LOCAL_SITES_SETTING)
    if value is None:
        return normalize_local_sites(DEFAULT_LOCAL_SITES)
    return normalize_local_sites(value)


def save_local_sites(sites):
    return set_setting(LOCAL_SITES_SETTING, normalize_local_sites(sites))


def normalize_discovery_queries(values):
    """Clean user-defined searches for the local web-search source."""
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)):
        return []
    clean = []
    seen = set()
    for value in values:
        if not isinstance(value, str):
            continue
        value = " ".join(value.split()).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        clean.append(value[:MAX_DISCOVERY_QUERY_LENGTH])
        if len(clean) >= MAX_DISCOVERY_QUERIES:
            break
    return clean


def get_discovery_queries():
    return normalize_discovery_queries(
        get_setting(DISCOVERY_QUERIES_SETTING, [])
    )


def save_discovery_queries(queries):
    return set_setting(
        DISCOVERY_QUERIES_SETTING,
        normalize_discovery_queries(queries),
    )


def get_decision_reason_counts():
    """Dismissal reasons, most common first."""
    init_db()
    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT reason, COUNT(*) AS n FROM decisions
        WHERE status='dismissed' AND reason != ''
        GROUP BY reason ORDER BY n DESC''')
    rows = c.fetchall()
    conn.close()
    return {r['reason']: r['n'] for r in rows}


def add_keywords_bulk(kw_type, values, weight_group='', scope='global'):
    """Insert several keywords at once. Returns the number accepted."""
    if kw_type not in ('focus', 'exclude') or not isinstance(values, (list, tuple)):
        return 0
    if isinstance(weight_group, dict):
        group_map = weight_group
        default_group = ''
    else:
        group_map = {}
        default_group = weight_group
    count = 0
    for value in values:
        clean = normalize_keyword_value(value)
        if not clean:
            continue
        group = group_map.get(clean, default_group)
        if add_keyword(kw_type, clean, group, scope):
            count += 1
    return count


def replace_keywords(kw_type, values, weight_group='', scope='global'):
    """Replace one visibility list in one scope. Used by the profile import."""
    if kw_type not in ('focus', 'exclude'):
        return 0
    scope = scope if scope in KEYWORD_SCOPES else 'global'
    init_db()
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute('DELETE FROM keywords WHERE scope=? AND type=?', (scope, kw_type))
        conn.commit()
    finally:
        conn.close()
    return add_keywords_bulk(kw_type, values, weight_group, scope)


def _rows_from_profile(profile, focus, exclude):
    """Turn a flat CV proposal into managed keyword rows."""
    from .job_dashboard import WEIGHT_GROUPS

    profile = profile if isinstance(profile, dict) else {}
    weights = _weight_by_field(profile)
    list_sets = {}
    for group in WEIGHT_GROUPS:
        field = group.get('list_field')
        if field:
            list_sets[field] = set(_normalise_list(profile.get(field, [])))
    focus_set = set(_normalise_list(focus))
    exclude_set = set(_normalise_list(exclude))
    values = set(focus_set) | set(exclude_set)
    for field_values in list_sets.values():
        values.update(field_values)

    rows = {}
    for value in values:
        if value in exclude_set:
            kw_type = 'exclude'
        elif value in focus_set:
            kw_type = 'focus'
        else:
            kw_type = 'score'
        rows[value] = {
            'value': value,
            'weight_group': _pick_weight_group(value, list_sets, weights),
            'type': kw_type,
            'enabled': True,
        }
    return rows


def apply_profile_keywords(profile, focus, exclude, mode='add', scopes=('global',)):
    """Merge a CV proposal into one or both keyword sets."""
    scopes = [scope for scope in scopes if scope in KEYWORD_SCOPES]
    if not scopes:
        scopes = ['global']
    rows = _rows_from_profile(profile, focus, exclude)
    init_db()
    conn = get_conn()
    c = conn.cursor()
    try:
        for scope in scopes:
            if mode == 'replace':
                c.execute('DELETE FROM keywords WHERE scope=?', (scope,))
            for row in rows.values():
                c.execute('''INSERT INTO keywords(scope, value, weight_group, type, enabled)
                    VALUES(?,?,?,?,1)
                    ON CONFLICT(scope, value) DO UPDATE SET
                        type=CASE
                            WHEN excluded.type = 'score'
                                 AND keywords.type IN ('focus', 'exclude')
                            THEN keywords.type
                            ELSE excluded.type
                        END,
                        weight_group=CASE
                            WHEN excluded.weight_group != '' THEN excluded.weight_group
                            ELSE keywords.weight_group
                        END,
                        enabled=1''', (
                    scope, row['value'], row['weight_group'], row['type'],
                ))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def save_jobs(jobs, source):
    init_db()
    conn = get_conn()
    c = conn.cursor()
    for job in jobs:
        try:
            c.execute('''INSERT OR REPLACE INTO jobs(title, company, location, url, description, source, score, matches, redflags)
                VALUES(?,?,?,?,?,?,?,?,?)''',
                (job.get('title'), job.get('company'), job.get('location'), job.get('url'),
                 job.get('desc'), source, job.get('score', 0),
                 json.dumps(job.get('matches', [])), json.dumps(job.get('redFlags', []))))
        except Exception:
            pass
    conn.commit()
    conn.close()


def get_jobs(source=None):
    init_db()
    conn = get_conn()
    c = conn.cursor()
    if source:
        c.execute('SELECT * FROM jobs WHERE source=? ORDER BY score DESC', (source,))
    else:
        c.execute('SELECT * FROM jobs ORDER BY score DESC')
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({
            'id': r['id'],
            'title': r['title'],
            'company': r['company'],
            'location': r['location'],
            'url': r['url'],
            'desc': r['description'],
            'source': r['source'],
            'score': r['score'],
            'matches': json.loads(r['matches'] or '[]'),
            'redFlags': json.loads(r['redflags'] or '[]')
        })
    return result


# ---------------------------------------------------------------------------
# Decisions: jobs marked as applied for or dismissed.
# ---------------------------------------------------------------------------

DECISION_STATUSES = ('applied', 'dismissed')


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _decision_row(r):
    return {
        'job_key': r['job_key'],
        'status': r['status'],
        'reason': r['reason'] or '',
        'note': r['note'] or '',
        'title': r['title'] or '',
        'company': r['company'] or '',
        'location': r['location'] or '',
        'url': r['url'] or '',
        'source': r['source'] or '',
        'score': r['score'] if r['score'] is not None else 0,
        'applied_at': r['applied_at'] or '',
        'created_at': r['created_at'] or '',
        'updated_at': r['updated_at'] or '',
    }


def set_decision(job_key, status, reason='', note='', snapshot=None):
    """Create or update the decision for a job.

    `snapshot` is the job dict shown in the UI. Copying its display fields here
    keeps the applied/hidden pages working even if the jobs table is refreshed.
    """
    if not job_key or status not in DECISION_STATUSES:
        return False

    init_db()
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute('SELECT status, applied_at, created_at FROM decisions WHERE job_key=?', (job_key,))
        existing = c.fetchone()
        now = _now_iso()

        if existing:
            prev_status = existing['status']
            prev_applied_at = existing['applied_at']
            created_at = existing['created_at'] or now
            if status == 'applied':
                applied_at = prev_applied_at if prev_status == 'applied' and prev_applied_at else now
            else:
                applied_at = None
        else:
            created_at = now
            applied_at = now if status == 'applied' else None

        def text(value, limit):
            return str(value or '')[:limit]

        try:
            score = int(snapshot.get('score') or 0)
        except (TypeError, ValueError):
            score = 0

        c.execute('''INSERT INTO decisions(
                job_key, status, reason, note, title, company, location, url, source,
                score, applied_at, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(job_key) DO UPDATE SET
                status=excluded.status,
                reason=excluded.reason,
                note=excluded.note,
                title=excluded.title,
                company=excluded.company,
                location=excluded.location,
                url=excluded.url,
                source=excluded.source,
                score=excluded.score,
                applied_at=excluded.applied_at,
                updated_at=excluded.updated_at''',
            (job_key, status, text(reason, 200), text(note, 1000),
             text(snapshot.get('title'), 300), text(snapshot.get('company'), 300),
             text(snapshot.get('location'), 300), text(snapshot.get('url'), 1000),
             text(snapshot.get('source'), 50), score, applied_at, created_at, now))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def delete_decision(job_key):
    init_db()
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute('DELETE FROM decisions WHERE job_key=?', (job_key,))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def get_decisions(status=None):
    init_db()
    conn = get_conn()
    c = conn.cursor()
    if status == 'applied':
        c.execute('SELECT * FROM decisions WHERE status=? ORDER BY applied_at DESC, updated_at DESC', (status,))
    elif status == 'dismissed':
        c.execute('SELECT * FROM decisions WHERE status=? ORDER BY updated_at DESC', (status,))
    else:
        c.execute('SELECT * FROM decisions ORDER BY updated_at DESC')
    rows = c.fetchall()
    conn.close()
    return [_decision_row(r) for r in rows]


def get_decision(job_key):
    init_db()
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM decisions WHERE job_key=?', (job_key,))
    row = c.fetchone()
    conn.close()
    return _decision_row(row) if row else None


def get_decision_keys():
    init_db()
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT job_key FROM decisions')
    rows = c.fetchall()
    conn.close()
    return {r['job_key'] for r in rows}


def get_decision_counts():
    init_db()
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT status, COUNT(*) AS n FROM decisions GROUP BY status')
    rows = c.fetchall()
    conn.close()
    counts = {'applied': 0, 'dismissed': 0}
    for r in rows:
        if r['status'] in counts:
            counts[r['status']] = r['n']
    return counts
