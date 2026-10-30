"""Minimal OpenAI-compatible chat client.

Works with Ollama, vLLM, llama.cpp, Groq, Together, Fireworks, OpenRouter and
any other endpoint that implements ``POST /v1/chat/completions``. No SDK, no
new dependency: ``requests`` is already used by the fetchers.

Configuration is read from the environment on every call so the server does
not need a restart when you point it at a different model.
"""

import json
import os
from urllib.parse import urlparse

import requests


class LLMError(RuntimeError):
    """Raised when the model is unreachable or returns unusable output."""


DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_MODEL = "qwen2.5:7b-instruct"


def get_config():
    return {
        "base_url": os.environ.get("JSEARCH_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        "model": os.environ.get("JSEARCH_LLM_MODEL", DEFAULT_MODEL).strip(),
        "api_key": os.environ.get("JSEARCH_LLM_API_KEY", "").strip(),
        "timeout": _int_env("JSEARCH_LLM_TIMEOUT", 90, 5, 600),
    }


def _int_env(name, default, low, high):
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def is_local_url(base_url):
    try:
        host = (urlparse(base_url).hostname or "").lower()
    except Exception:
        return False
    return host in ("localhost", "127.0.0.1", "::1", "0.0.0.0")


def public_config():
    """Safe-to-display configuration for the dashboard."""
    config = get_config()
    return {
        "configured": bool(config["base_url"] and config["model"]),
        "base_url": config["base_url"],
        "model": config["model"],
        "local": is_local_url(config["base_url"]),
    }


def chat_json(messages, max_tokens=2000):
    """Send chat messages and return the parsed JSON object.

    The model is asked for a JSON object. If it wraps the object in markdown
    or prose, the first balanced-looking object is extracted. One repair
    attempt is made when parsing fails.
    """
    config = get_config()
    if not config["base_url"] or not config["model"]:
        raise LLMError(
            "No model configured. Set JSEARCH_LLM_MODEL and, if needed, "
            "JSEARCH_LLM_BASE_URL."
        )

    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json"}
    if config["api_key"]:
        headers["Authorization"] = "Bearer " + config["api_key"]

    content = _post_for_content(config, payload, headers)

    try:
        return _parse_json(content)
    except ValueError:
        repair = list(messages) + [
            {"role": "assistant", "content": str(content)[:4000]},
            {
                "role": "user",
                "content": (
                    "That was not valid JSON. Return the same answer as one "
                    "valid JSON object with no markdown fences or commentary."
                ),
            },
        ]
        repaired = _post_for_content(config, dict(payload, messages=repair), headers)
        try:
            return _parse_json(repaired)
        except ValueError as exc:
            raise LLMError("The model did not return valid JSON.") from exc


def _post_for_content(config, payload, headers):
    url = config["base_url"] + "/chat/completions"
    try:
        response = requests.post(
            url, json=payload, headers=headers, timeout=config["timeout"]
        )
    except requests.RequestException as exc:
        raise LLMError(
            "Could not reach the model at "
            f"{config['base_url']}. Is Ollama running?"
        ) from exc

    # A few providers reject response_format. Retry once without it.
    if response.status_code == 400 and "response_format" in payload:
        fallback = dict(payload)
        fallback.pop("response_format", None)
        try:
            response = requests.post(
                url, json=fallback, headers=headers, timeout=config["timeout"]
            )
        except requests.RequestException as exc:
            raise LLMError(f"Could not reach the model at {config['base_url']}.") from exc

    if response.status_code >= 400:
        detail = (response.text or "").strip()[:300]
        raise LLMError(
            f"Model returned HTTP {response.status_code}"
            + (f": {detail}" if detail else ".")
        )

    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError("Unexpected response shape from the model.") from exc

    if isinstance(content, list):
        # Some OpenAI-compatible servers return structured content parts.
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return content


def _parse_json(content):
    text = str(content or "").strip()
    if not text:
        raise ValueError("empty response")

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except ValueError:
        pass

    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            value, _ = decoder.raw_decode(text[start:])
        except ValueError:
            value = None
        if isinstance(value, dict):
            return value
        start = text.find("{", start + 1)

    raise ValueError("no JSON object found")
