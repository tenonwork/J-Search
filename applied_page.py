"""Applied and hidden job tracker pages.

Both pages are rendered from the `decisions` table, so they keep working even
after the jobs table is refreshed or the source posting disappears.
"""

import html
from datetime import datetime
from urllib.parse import quote


DECISIONS_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__PAGE_TITLE__ - J-Search</title>
<style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f4f6f8; margin: 0; padding: 20px; color: #0f172a; }
    .container { max-width: 1100px; margin: 0 auto; }
    header { background: #fff; padding: 24px 32px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
    h1 { margin: 0 0 4px 0; font-size: 28px; }
    .subtitle { color: #64748b; font-size: 14px; margin: 0; }
    .header-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .btn { padding: 10px 18px; border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s; text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }
    .btn-primary { background: #2563eb; color: #fff; }
    .btn-primary:hover { background: #1d4ed8; }
    .btn-outline { background: #fff; color: #0f172a; border: 1px solid #cbd5e1; }
    .btn-outline:hover { background: #f8fafc; }
    .btn-sm { padding: 6px 12px; font-size: 12px; }
    .summary { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
    .count { color: #64748b; font-size: 14px; }
    .row { background: #fff; padding: 20px 24px; margin-bottom: 12px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; }
    .row-main { flex: 1; min-width: 0; }
    .row-title { font-size: 17px; font-weight: 700; margin: 0 0 5px 0; }
    .row-meta { color: #64748b; font-size: 13px; margin-bottom: 8px; }
    .badges { display: flex; flex-wrap: wrap; gap: 6px; }
    .badge { display: inline-block; padding: 3px 9px; border-radius: 6px; font-size: 11px; font-weight: 600; }
    .badge-score { background: #dbeafe; color: #1e40af; }
    .badge-reason { background: #fee2e2; color: #991b1b; }
    .badge-note { background: #f1f5f9; color: #475569; }
    .row-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .empty { text-align: center; padding: 60px 20px; color: #94a3b8; background: #fff; border-radius: 12px; font-size: 14px; }
</style>
</head>
<body>
<div class="container">
    <header>
        <div>
            <h1>__PAGE_TITLE__</h1>
            <p class="subtitle">__PAGE_SUBTITLE__</p>
        </div>
        <div class="header-actions">
            <a class="btn btn-outline" href="/">Dashboard</a>
            __NAV_LINKS__
        </div>
    </header>
    <div class="summary">
        <span class="count">__COUNT_LABEL__</span>
    </div>
    __BODY__
</div>
<script>
document.addEventListener('click', async function (e) {
    const btn = e.target.closest('[data-restore]');
    if (!btn) return;
    const key = decodeURIComponent(btn.dataset.restore || '');
    btn.disabled = true;
    btn.textContent = 'Restoring...';
    try {
        const res = await fetch('/api/decisions/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: key })
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        btn.textContent = 'Restored';
        window.location.reload();
    } catch (err) {
        btn.disabled = false;
        btn.textContent = 'Restore';
        alert('Could not restore this job.');
    }
});
</script>
</body>
</html>"""


def _fmt_date(value):
    if not value:
        return ''
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.strftime('%d %b %Y')
    except Exception:
        return str(value)[:10]


def _safe_url(url):
    url = (url or '').strip()
    if url.startswith('http://') or url.startswith('https://'):
        return html.escape(url, quote=True)
    return ''


def _row_html(decision, status):
    title = html.escape(decision.get('title') or 'Untitled role')
    company = html.escape(decision.get('company') or 'Unknown company')
    location = html.escape(decision.get('location') or '')
    source = html.escape((decision.get('source') or '').capitalize())
    score = decision.get('score') or 0
    url = _safe_url(decision.get('url') or '')
    date = _fmt_date(decision.get('applied_at') or decision.get('updated_at'))

    meta_parts = [company]
    if location:
        meta_parts.append(location)
    if source:
        meta_parts.append(source)
    if date:
        meta_parts.append(('Applied ' if status == 'applied' else 'Hidden ') + date)

    badges = ['<span class="badge badge-score">Score ' + html.escape(str(score)) + '</span>']
    if status == 'dismissed':
        badges.append('<span class="badge badge-reason">' + html.escape(decision.get('reason') or 'No reason given') + '</span>')
        note = (decision.get('note') or '').strip()
        if note:
            badges.append('<span class="badge badge-note">' + html.escape(note) + '</span>')

    key_attr = html.escape(quote(decision.get('job_key') or '', safe=''), quote=True)
    open_btn = ('<a class="btn btn-primary btn-sm" href="' + url +
                '" target="_blank" rel="noopener noreferrer">Open</a>') if url else ''
    restore_btn = ('<button class="btn btn-outline btn-sm" data-restore="' +
                   key_attr + '">Restore</button>')

    return ('<div class="row">'
            '<div class="row-main">'
            '<h3 class="row-title">' + title + '</h3>'
            '<div class="row-meta">' + ' &bull; '.join(meta_parts) + '</div>'
            '<div class="badges">' + ''.join(badges) + '</div>'
            '</div>'
            '<div class="row-actions">' + open_btn + restore_btn + '</div>'
            '</div>')


def build_decisions_page(decisions, status, applied_count=0, dismissed_count=0):
    decisions = decisions or []
    if status == 'applied':
        page_title = 'Applied Jobs'
        subtitle = 'Roles you have marked as applied for'
        count_label = str(applied_count) + ' applied'
        nav_links = ('<a class="btn btn-outline" href="/hidden">Hidden (' +
                     str(dismissed_count) + ')</a>')
        empty = ('No applications logged yet. Mark a job as applied from the '
                 'dashboard and it will appear here.')
    else:
        page_title = 'Hidden Jobs'
        subtitle = 'Roles you dismissed, with the reason you gave'
        count_label = str(dismissed_count) + ' hidden'
        nav_links = ('<a class="btn btn-outline" href="/applied">Applied (' +
                     str(applied_count) + ')</a>')
        empty = ('No hidden jobs. Jobs you dismiss from the dashboard will '
                 'appear here with their reason.')

    body = ''.join(_row_html(d, status) for d in decisions) if decisions else (
        '<div class="empty">' + empty + '</div>')

    return (DECISIONS_TEMPLATE
            .replace('__PAGE_TITLE__', page_title)
            .replace('__PAGE_SUBTITLE__', subtitle)
            .replace('__COUNT_LABEL__', count_label)
            .replace('__NAV_LINKS__', nav_links)
            .replace('__BODY__', body))
