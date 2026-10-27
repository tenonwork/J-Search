import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path('jsearch.db')

DEFAULT_KEYWORDS = {
    "focus": ["react", "typescript", "python", "postgres", "supabase"],
    "exclude": ["senior", "lead", "manager", "architect"],
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS keywords(
        id INTEGER PRIMARY KEY,
        type TEXT NOT NULL,
        value TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        UNIQUE(type, value)
    )''')
    keyword_cols = {row['name'] for row in c.execute('PRAGMA table_info(keywords)').fetchall()}
    if 'enabled' not in keyword_cols:
        c.execute('ALTER TABLE keywords ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1')
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
    c.execute('SELECT type, value, enabled FROM keywords ORDER BY value')
    rows = c.fetchall()
    conn.close()
    result = {'focus': [], 'exclude': []}
    for r in rows:
        if r['type'] in result:
            result[r['type']].append({
                'value': r['value'],
                'enabled': bool(r['enabled']),
            })
    return result


def add_keyword(kw_type, value):
    init_db()
    if kw_type not in ('focus', 'exclude'):
        return False
    value = (value or '').lower().strip()
    if not value:
        return False
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO keywords(type, value, enabled) VALUES(?, ?, 1)
            ON CONFLICT(type, value) DO UPDATE SET enabled=1''', (kw_type, value))
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
