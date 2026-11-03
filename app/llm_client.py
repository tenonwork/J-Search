"""Minimal OpenAI-compatible chat client.

Works with Ollama, Cloudflare Workers AI, Groq, OpenRouter, vLLM, llama.cpp
and any other endpoint that implements ``POST /v1/chat/completions``. No SDK,
no new dependency: ``requests`` is already used by the fetchers.

Configuration is read from the environment on every call so the server does
not need a restart when you point it at a different model.
"""

import json
import os
import re
import time
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
        "max_tokens": _int_env("JSEARCH_LLM_MAX_TOKENS", 4096, 256, 16384),
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


def provider_host(base_url):
    """Return ``host[:port]`` for display, never including credentials."""
    try:
        parsed = urlparse(base_url)
        host = (parsed.hostname or "").strip()
        if not host:
            return str(base_url or "the configured endpoint")
        try:
            port = parsed.port
        except ValueError:
            port = None
        return host + (":" + str(port) if port else "")
    except Exception:
        return str(base_url or "the configured endpoint")


def _redact_detail(text, api_key=""):
    detail = " ".join(str(text or "").split())
    if api_key:
        detail = detail.replace(api_key, "[redacted]")
    detail = re.sub(
        r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[redacted]", detail
    )
    detail = re.sub(
        r"\b(?:sk|gsk)[-_][A-Za-z0-9_-]{12,}\b",
        "[redacted]",
        detail,
        flags=re.IGNORECASE,
    )
    return detail[:300]


def _connection_error(config):
    host = provider_host(config["base_url"])
    if is_local_url(config["base_url"]):
        return (
            "Could not reach the local model at "
            + host
            + ". Is Ollama running? Start it with `ollama serve`, or configure "
            "a hosted endpoint in .env."
        )
    return (
        "Could not reach "
        + host
        + ". Check your internet connection and JSEARCH_LLM_BASE_URL."
    )


def _timeout_error(config, timeout):
    return (
        "The model at "
        + provider_host(config["base_url"])
        + " did not respond within "
        + str(timeout)
        + " seconds."
    )


def _http_error(status, detail, config):
    host = provider_host(config["base_url"])
    detail = _redact_detail(detail, config.get("api_key", ""))

    if status in (401, 403):
        message = "The API key was rejected by " + host + ". Check JSEARCH_LLM_API_KEY."
    elif status == 404:
        message = (
            "The endpoint or model was not found. Check JSEARCH_LLM_BASE_URL "
            "(it usually ends in /v1) and JSEARCH_LLM_MODEL."
        )
    elif status == 429:
        message = "Rate limit reached at " + host + ". Wait a moment or switch models."
    elif status >= 500:
        message = host + " returned HTTP " + str(status) + ". Try again shortly."
    else:
        message = "The model returned HTTP " + str(status) + "."

    if detail:
        message += " " + detail
    return message


def _length_error(max_tokens):
    return (
        "The model ran out of output tokens before finishing. Increase "
        "JSEARCH_LLM_MAX_TOKENS (currently "
        + str(max_tokens)
        + ") or use a shorter CV."
    )


def _empty_content_error(config, finish_reason):
    message = (
        "The model at "
        + provider_host(config["base_url"])
        + " returned an empty final answer. Try again, increase "
        "JSEARCH_LLM_MAX_TOKENS, or switch models."
    )
    if finish_reason:
        message += " (finish reason: " + str(finish_reason) + ")"
    return message


def safe_base_url(base_url):
    """Return the endpoint with any embedded credentials removed."""
    try:
        parsed = urlparse(base_url)
    except Exception:
        return ""
    host = (parsed.hostname or "").strip()
    if not host:
        return ""
    if ":" in host and not host.startswith("["):
        host = "[" + host + "]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = host + (":" + str(port) if port else "")
    prefix = (parsed.scheme + "://") if parsed.scheme else ""
    return prefix + netloc + parsed.path


def public_config():
    """Safe-to-display configuration for the dashboard."""
    config = get_config()
    return {
        "configured": bool(config["base_url"] and config["model"]),
        "base_url": safe_base_url(config["base_url"]),
        "model": config["model"],
        "local": is_local_url(config["base_url"]),
        "host": provider_host(config["base_url"]),
        "has_api_key": bool(config["api_key"]),
        "default_config": (
            config["base_url"] == DEFAULT_BASE_URL
            and config["model"] == DEFAULT_MODEL
        ),
    }


def _headers(config):
    headers = {"Content-Type": "application/json"}
    if config["api_key"]:
        headers["Authorization"] = "Bearer " + config["api_key"]
    return headers


def _json_mode_enabled(config):
    """Return whether to ask the provider for a forced JSON object.

    gpt-oss models can return HTTP 200 with empty content when JSON mode is
    enabled, so they use prompt-only JSON plus the parser instead.
    """
    override = os.environ.get("JSEARCH_LLM_JSON_MODE", "").strip().lower()
    if override in ("0", "false", "no", "off"):
        return False
    if override in ("1", "true", "yes", "on"):
        return True
    return "gpt-oss" not in str(config.get("model", "")).lower()


def ping(timeout=20):
    """Send a tiny completion to verify the endpoint, key and model.

    No CV content is sent. Returns dashboard-safe details on success and
    raises :class:`LLMError` with an actionable message on failure.
    """
    config = get_config()
    if not config["base_url"] or not config["model"]:
        raise LLMError(
            "No model configured. Set JSEARCH_LLM_MODEL and, if needed, "
            "JSEARCH_LLM_BASE_URL."
        )

    payload = {
        "model": config["model"],
        "messages": [{"role": "user", "content": "Reply with the single word OK."}],
        "temperature": 0,
        "max_tokens": 8,
    }
    started = time.perf_counter()
    result, _ = _post_chat(config, payload, _headers(config), timeout=timeout)
    latency_ms = int((time.perf_counter() - started) * 1000)
    return {
        "ok": True,
        "model": config["model"],
        "host": provider_host(config["base_url"]),
        "latency_ms": latency_ms,
        "reply": result["content"].strip()[:80],
    }


def chat_json(messages, max_tokens=None):
    """Send chat messages and return the parsed JSON object.

    The model is asked for a JSON object. If it wraps the object in markdown
    or prose, the first balanced-looking object is extracted. JSON mode is
    skipped for models that return empty content with it, and one repair
    attempt is made when parsing fails.
    """
    config = get_config()
    if not config["base_url"] or not config["model"]:
        raise LLMError(
            "No model configured. Set JSEARCH_LLM_MODEL and, if needed, "
            "JSEARCH_LLM_BASE_URL."
        )

    budget = config["max_tokens"] if max_tokens is None else max_tokens
    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": 0,
        "max_tokens": budget,
    }
    if _json_mode_enabled(config):
        payload["response_format"] = {"type": "json_object"}
    headers = _headers(config)

    result, used_payload = _request_with_format_fallback(config, payload, headers)
    if not result["content"].strip():
        if result["finish_reason"] == "length":
            raise LLMError(_length_error(budget))
        raise LLMError(_empty_content_error(config, result["finish_reason"]))

    try:
        return _parse_json(result["content"])
    except ValueError:
        if result["finish_reason"] == "length":
            raise LLMError(_length_error(budget))
        repair = list(messages) + [
            {"role": "assistant", "content": str(result["content"])[:4000]},
            {
                "role": "user",
                "content": (
                    "That was not valid JSON. Return the same answer as one "
                    "valid JSON object with no markdown fences or commentary."
                ),
            },
        ]
        repaired, _ = _request_with_format_fallback(
            config, dict(used_payload, messages=repair), headers
        )
        if not repaired["content"].strip():
            if repaired["finish_reason"] == "length":
                raise LLMError(_length_error(budget))
            raise LLMError(_empty_content_error(config, repaired["finish_reason"]))
        try:
            return _parse_json(repaired["content"])
        except ValueError as exc:
            if repaired["finish_reason"] == "length":
                raise LLMError(_length_error(budget)) from exc
            raise LLMError("The model did not return valid JSON.") from exc


def _request(config, url, payload, headers, timeout):
    try:
        return requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.Timeout as exc:
        raise LLMError(_timeout_error(config, timeout)) from exc
    except requests.RequestException as exc:
        raise LLMError(_connection_error(config)) from exc


def _post_chat(config, payload, headers, timeout=None):
    """POST one chat request and return its content, metadata and payload."""
    url = config["base_url"] + "/chat/completions"
    timeout = timeout or config["timeout"]
    used_payload = payload

    response = _request(config, url, payload, headers, timeout)

    # A few providers reject response_format. Retry once without it.
    if response.status_code == 400 and "response_format" in payload:
        used_payload = dict(payload)
        used_payload.pop("response_format", None)
        response = _request(config, url, used_payload, headers, timeout)

    if response.status_code >= 400:
        raise LLMError(_http_error(response.status_code, response.text, config))

    try:
        data = response.json()
        choice = data["choices"][0]
        message = choice["message"]
        content = message.get("content") or ""
        finish_reason = choice.get("finish_reason")
        usage = data.get("usage") or {}
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError("Unexpected response shape from the model.") from exc

    if isinstance(content, list):
        # Some OpenAI-compatible servers return structured content parts.
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return {
        "content": str(content or ""),
        "finish_reason": finish_reason,
        "usage": usage,
    }, used_payload


def _request_with_format_fallback(config, payload, headers):
    """Retry without JSON mode when a model returns an empty answer."""
    result, used_payload = _post_chat(config, payload, headers)
    if not result["content"].strip() and "response_format" in used_payload:
        fallback = dict(used_payload)
        fallback.pop("response_format", None)
        result, used_payload = _post_chat(config, fallback, headers)
    return result, used_payload


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
