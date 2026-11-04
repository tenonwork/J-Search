import sqlite3
import json
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from .paths import DB_PATH

DEFAULT_KEYWORDS = {
    "focus": ["react", "typescript", "python", "postgres", "supabase"],
    "exclude": ["senior", "lead", "manager", "architect"],
}

MAX_KEYWORD_GROUP = 40


def normalize_keyword_group(value):
    """Trim and bound a free-text keyword group name."""
    if not isinstance(value, str):
        return ''
    value = " ".join(value.split()).strip()
    return value[:MAX_KEYWORD_GROUP]

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


def _has_keyword_type_value_unique(c):
    """True when the keywords table has the current (type, value) unique key."""
    for index in c.execute('PRAGMA index_list(keywords)').fetchall():
        if not index['unique']:
            continue
        name = index['name'].replace('"', '""')
        columns = [
            row['name']
            for row in c.execute(f'PRAGMA index_info("{name}")').fetchall()
        ]
        if columns == ['type', 'value']:
            return True
    return False


def _migrate_keywords_table(c):
    """Rebuild the legacy keywords table without losing saved keywords.

    Older databases used ``value TEXT UNIQUE``, which prevents the same word
    from appearing in both the focus and exclude lists and makes
    ``ON CONFLICT(type, value)`` fail. The rebuild is idempotent.
    """
    if _has_keyword_type_value_unique(c):
        return
    legacy_columns = {
        row['name'] for row in c.execute('PRAGMA table_info(keywords)').fetchall()
    }
    group_expression = (
        "COALESCE(keyword_group, '')" if 'keyword_group' in legacy_columns else "''"
    )
    c.execute('ALTER TABLE keywords RENAME TO keywords_legacy')
    c.execute('''CREATE TABLE keywords(
        id INTEGER PRIMARY KEY,
        type TEXT NOT NULL,
        value TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        keyword_group TEXT NOT NULL DEFAULT '',
        UNIQUE(type, value)
    )''')
    c.execute('''INSERT OR IGNORE INTO keywords(type, value, enabled, keyword_group)
        SELECT type, value, enabled, ''' + group_expression + ''' FROM keywords_legacy
        WHERE type IN ('focus', 'exclude') AND value IS NOT NULL AND value != '' ''')
    c.execute('DROP TABLE keywords_legacy')


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS keywords(
        id INTEGER PRIMARY KEY,
        type TEXT NOT NULL,
        value TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        keyword_group TEXT NOT NULL DEFAULT '',
        UNIQUE(type, value)
    )''')
    keyword_cols = {row['name'] for row in c.execute('PRAGMA table_info(keywords)').fetchall()}
    if 'enabled' not in keyword_cols:
        c.execute('ALTER TABLE keywords ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1')
    _migrate_keywords_table(c)
    keyword_cols = {row['name'] for row in c.execute('PRAGMA table_info(keywords)').fetchall()}
    if 'keyword_group' not in keyword_cols:
        c.execute(
            "ALTER TABLE keywords ADD COLUMN keyword_group TEXT NOT NULL DEFAULT ''"
        )
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
    c.execute('''CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT ''
    )''')
    conn.commit()

    # Seed defaults on a brand new database
    c.execute('SELECT COUNT(*) AS n FROM keywords')
    if c.fetchone()['n'] == 0:
        for kw_type, values in DEFAULT_KEYWORDS.items():
            for value in values:
                c.execute('INSERT OR IGNORE INTO keywords(type, value) VALUES(?, ?)', (kw_type, value))
        conn.commit()

    conn.close()


def get_keywords():
    init_db()
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT type, value, enabled, keyword_group FROM keywords ORDER BY value')
    rows = c.fetchall()
    conn.close()
    result = {'focus': [], 'exclude': []}
    for r in rows:
        if r['type'] in result:
            result[r['type']].append({
                'value': r['value'],
                'enabled': bool(r['enabled']),
                'group': r['keyword_group'] or '',
            })
    return result


def add_keyword(kw_type, value, group=''):
    init_db()
    if kw_type not in ('focus', 'exclude'):
        return False
    value = (value or '').lower().strip()
    if not value:
        return False
    group = normalize_keyword_group(group)
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO keywords(type, value, enabled, keyword_group) VALUES(?, ?, 1, ?)
            ON CONFLICT(type, value) DO UPDATE SET
                enabled=1,
                keyword_group=CASE
                    WHEN excluded.keyword_group != '' THEN excluded.keyword_group
                    ELSE keywords.keyword_group
                END''', (kw_type, value, group))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def set_keyword_states(kw_type, states):
    """Persist which keywords are active.

    `states` maps keyword value -> bool. Disabled keywords stay in the table so
    they can be re-enabled later; they are not deleted.
    """
    if kw_type not in ('focus', 'exclude') or not isinstance(states, dict):
        return False
    init_db()
    conn = get_conn()
    c = conn.cursor()
    try:
        for value, enabled in states.items():
            c.execute('UPDATE keywords SET enabled=? WHERE type=? AND value=?',
                      (1 if enabled else 0, kw_type, (value or '').lower().strip()))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def set_keyword_groups(kw_type, groups):
    """Assign custom groups to saved keywords.

    `groups` maps keyword value -> group name. An empty name clears the group so
    the keyword falls back to its automatic scoring category.
    """
    if kw_type not in ('focus', 'exclude') or not isinstance(groups, dict):
        return False
    init_db()
    conn = get_conn()
    c = conn.cursor()
    try:
        for value, group in groups.items():
            c.execute(
                'UPDATE keywords SET keyword_group=? WHERE type=? AND value=?',
                (
                    normalize_keyword_group(group),
                    kw_type,
                    (value or '').lower().strip(),
                ),
            )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def delete_keywords(kw_type, values):
    init_db()
    if kw_type not in ('focus', 'exclude'):
        return
    conn = get_conn()
    c = conn.cursor()
    for v in values:
        try:
            c.execute('DELETE FROM keywords WHERE type=? AND value=?', (kw_type, (v or '').lower().strip()))
        except Exception:
            pass
    conn.commit()
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
    return set_setting('scoring_profile', profile)


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


def add_keywords_bulk(kw_type, values, groups=None):
    """Insert several keywords in one transaction. Returns the count attempted."""
    if kw_type not in ('focus', 'exclude') or not isinstance(values, (list, tuple)):
        return 0
    groups = groups if isinstance(groups, dict) else {}
    init_db()
    conn = get_conn()
    c = conn.cursor()
    count = 0
    try:
        for value in values:
            value = (value or '').lower().strip()
            if not value:
                continue
            group = normalize_keyword_group(groups.get(value, ''))
            c.execute('''INSERT INTO keywords(type, value, enabled, keyword_group) VALUES(?, ?, 1, ?)
                ON CONFLICT(type, value) DO UPDATE SET
                    enabled=1,
                    keyword_group=CASE
                        WHEN excluded.keyword_group != '' THEN excluded.keyword_group
                        ELSE keywords.keyword_group
                    END''', (kw_type, value, group))
            count += 1
        conn.commit()
        return count
    except Exception:
        return 0
    finally:
        conn.close()


def replace_keywords(kw_type, values):
    """Replace every keyword of one type. Used by the profile import."""
    if kw_type not in ('focus', 'exclude'):
        return 0
    init_db()
    conn = get_conn()
    c = conn.cursor()
    try:
        existing_groups = {
            row['value']: row['keyword_group'] or ''
            for row in c.execute(
                'SELECT value, keyword_group FROM keywords WHERE type=?', (kw_type,)
            ).fetchall()
        }
        c.execute('DELETE FROM keywords WHERE type=?', (kw_type,))
        conn.commit()
    finally:
        conn.close()
    return add_keywords_bulk(kw_type, values, existing_groups)


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
