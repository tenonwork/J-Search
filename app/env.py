"""Load local configuration from a ``.env`` file.

The project deliberately avoids a dotenv dependency. Only simple
``KEY=value`` lines are supported, which is all the model configuration
needs. Real environment variables always win, so a shell export or a
service manager still overrides the file.
"""

import os
import re
from pathlib import Path

from .paths import ROOT_DIR

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_env(text):
    """Parse dotenv-style text into a dict.

    Supports comments, blank lines, an optional ``export`` prefix, single or
    double quotes and ``#`` comments after unquoted values.
    """
    values = {}
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not _KEY_RE.match(key):
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            quote = value[0]
            value = value[1:-1]
            if quote == '"':
                value = (
                    value.replace("\\n", "\n")
                    .replace("\\t", "\t")
                    .replace('\\"', '"')
                    .replace("\\\\", "\\")
                )
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()

        values[key] = value
    return values


def load_dotenv(path=None):
    """Load a ``.env`` file into ``os.environ`` without overwriting values.

    Returns the parsed mapping (empty when the file is missing or unreadable).
    """
    env_path = Path(path) if path else ROOT_DIR / ".env"
    try:
        text = env_path.read_text(encoding="utf-8-sig")
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return {}

    values = parse_env(text)
    for key, value in values.items():
        if not os.environ.get(key):
            os.environ[key] = value
    return values
