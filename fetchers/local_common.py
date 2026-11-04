"""Shared constants and helpers for the local job sources."""

import re


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

LOCAL_LOCATION = "Local (Kenya / East Africa)"

TECH_PATTERN = re.compile(
    r'\b(software|developer|engineer|programmer|frontend|front-end|backend|back-end|'
    r'full[\s-]?stack|web|mobile|android|ios|devops|cloud|data|database|analyst|'
    r'analytics|it\b|ict|tech|technical|qa|quality assurance|tester|test|'
    r'systems?|network|security|cyber|architect|python|java|javascript|react|'
    r'node|php|dotnet|\.net|sql|api|support)\b',
    re.I,
)


def clean_text(text):
    return re.sub(r'\s+', ' ', (text or '')).strip()


def is_tech_title(title):
    return bool(TECH_PATTERN.search(title or ''))
