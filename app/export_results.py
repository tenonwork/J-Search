"""Package the dashboard's current results as JSON or a Word document.

The browser sends the roles already visible in the active tab. This module
only checks that payload and writes it; it does not rescore or refilter.
"""

import json
import re
from datetime import datetime, timezone
from io import BytesIO

MAX_EXPORT_JOBS = 2000
MAX_DESCRIPTION_LENGTH = 20000
MAX_FIELD_LENGTH = 500
MAX_KEYWORD_LENGTH = 80
MAX_KEYWORDS = 80

_SCOPES = ('global', 'local')
_STRICTNESS = ('strict', 'balanced', 'lenient')
_SORTS = {
    'recommended': 'Most recommended first',
    'newest': 'Newest first',
    'lowest': 'Lowest match first',
}
_DOCX_TYPE = (
    'application/vnd.openxmlformats-officedocument'
    '.wordprocessingml.document'
)


class ExportError(ValueError):
    """The export payload cannot be turned into a file."""


def _text(value, limit=MAX_FIELD_LENGTH):
    if not isinstance(value, str):
        value = '' if value is None else str(value)
    value = value.replace('\x00', '').strip()
    return value[:limit]


def _keyword_list(values):
    if not isinstance(values, (list, tuple)):
        return []
    out = []
    seen = set()
    for value in values:
        text = _text(value, MAX_KEYWORD_LENGTH).lower()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= MAX_KEYWORDS:
            break
    return out


def _job(item):
    if not isinstance(item, dict):
        raise ExportError('Each exported role must be an object.')
    try:
        score = int(item.get('score') or 0)
    except (TypeError, ValueError):
        score = 0
    source = item.get('source')
    if source not in _SCOPES:
        source = 'global'
    return {
        'title': _text(item.get('title')) or 'Untitled role',
        'company': _text(item.get('company')) or 'Unknown company',
        'location': _text(item.get('location')) or 'Location not listed',
        'url': _text(item.get('url'), 2000),
        'source': source,
        'score': score,
        'description': _text(item.get('description'), MAX_DESCRIPTION_LENGTH),
        'matches': _keyword_list(item.get('matches')),
        'red_flags': _keyword_list(item.get('red_flags')),
        'highlights': _keyword_list(item.get('highlights')),
    }


def normalize_snapshot(payload):
    """Return the document contents, or raise ExportError."""
    if not isinstance(payload, dict):
        raise ExportError('Send the current results to export.')
    fmt = payload.get('format')
    if fmt not in ('json', 'docx'):
        raise ExportError('Choose JSON or Word.')
    scope = payload.get('scope')
    if scope not in _SCOPES:
        raise ExportError('Export the Global or Local tab.')
    strictness = payload.get('strictness')
    if strictness not in _STRICTNESS:
        strictness = 'balanced'
    sort = payload.get('sort')
    if sort not in _SORTS:
        sort = 'recommended'
    jobs_in = payload.get('jobs')
    if not isinstance(jobs_in, list) or not jobs_in:
        raise ExportError('Nothing in this view to export.')
    if len(jobs_in) > MAX_EXPORT_JOBS:
        raise ExportError(f'Export is limited to {MAX_EXPORT_JOBS} roles.')

    exported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        'format': fmt,
        'exported_at': exported_at,
        'view': {
            'scope': scope,
            'strictness': strictness,
            'sort': sort,
            'count': len(jobs_in),
        },
        'highlight_keywords': _keyword_list(payload.get('highlight_keywords')),
        'jobs': [_job(item) for item in jobs_in],
    }


def _filename(snapshot):
    scope = snapshot['view']['scope']
    day = snapshot['exported_at'][:10]
    ext = 'docx' if snapshot['format'] == 'docx' else 'json'
    return f'jsearch-{scope}-{day}.{ext}'


def _json_document(snapshot):
    body = {
        'exported_at': snapshot['exported_at'],
        'view': snapshot['view'],
        'highlight_keywords': snapshot['highlight_keywords'],
        'jobs': snapshot['jobs'],
    }
    return json.dumps(body, indent=2, ensure_ascii=False).encode('utf-8')


def _joined(values, empty):
    return ', '.join(values) if values else empty


def _docx_document(snapshot):
    from docx import Document

    view = snapshot['view']
    document = Document()
    document.add_heading('J-Search results', level=1)
    document.add_paragraph(
        f"{view['scope'].title()} · {view['strictness'].title()} · "
        f"{_SORTS[view['sort']]} · {view['count']} "
        f"role{'s' if view['count'] != 1 else ''}"
    )
    document.add_paragraph(f"Exported {snapshot['exported_at']}")
    document.add_paragraph(
        'Highlight keywords: ' + _joined(
            snapshot['highlight_keywords'], 'none enabled'
        )
    )

    for job in snapshot['jobs']:
        document.add_heading(job['title'], level=2)
        document.add_paragraph(
            f"{job['company']} · {job['location']} · "
            f"{job['source'].title()} · score {job['score']}"
        )
        if job['url']:
            document.add_paragraph(job['url'])
        document.add_heading('Matched signals', level=3)
        document.add_paragraph(_joined(job['matches'], 'No positive signals matched.'))
        document.add_heading('Red flags', level=3)
        document.add_paragraph(_joined(job['red_flags'], 'None'))
        document.add_heading('Highlight keywords that fit', level=3)
        document.add_paragraph(_joined(job['highlights'], 'None'))
        document.add_heading('Description', level=3)
        description = job['description'] or (
            'No description was captured for this role.'
        )
        for line in re.split(r'\r?\n', description):
            document.add_paragraph(line)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def build_export(payload):
    """Return ``(filename, content_type, body)`` for a download."""
    snapshot = normalize_snapshot(payload)
    filename = _filename(snapshot)
    if snapshot['format'] == 'docx':
        return filename, _DOCX_TYPE, _docx_document(snapshot)
    return filename, 'application/json; charset=utf-8', _json_document(snapshot)
