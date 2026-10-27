import sqlite3
import json
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
        UNIQUE(type, value)
    )''')
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
    c.execute('SELECT type, value FROM keywords ORDER BY value')
    rows = c.fetchall()
    conn.close()
    result = {'focus': [], 'exclude': []}
    for r in rows:
        if r['type'] in result:
            result[r['type']].append(r['value'])
    return result


def add_keyword(kw_type, value):
    init_db()
    value = (value or '').lower().strip()
    if not value:
        return False
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute('INSERT OR IGNORE INTO keywords(type, value) VALUES(?, ?)', (kw_type, value))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def delete_keywords(kw_type, values):
    init_db()
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
