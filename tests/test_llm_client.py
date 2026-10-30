import json
import os
import unittest
from unittest import mock

import requests

from app import llm_client

REMOTE_ENV = {
    "JSEARCH_LLM_BASE_URL": "https://api.cloudflare.com/client/v4/accounts/abc/ai/v1",
    "JSEARCH_LLM_MODEL": "@cf/openai/gpt-oss-20b",
    "JSEARCH_LLM_API_KEY": "secret-key-123",
    "JSEARCH_LLM_TIMEOUT": "30",
}


def response(status, text="", payload=None):
    fake = mock.Mock()
    fake.status_code = status
    fake.text = text
    fake.json.return_value = payload or {}
    return fake


class ConfigTests(unittest.TestCase):
    def test_public_config_never_contains_the_key(self):
        with mock.patch.dict(os.environ, REMOTE_ENV, clear=True):
            config = llm_client.public_config()
        self.assertNotIn("api_key", config)
        self.assertNotIn("secret-key-123", json.dumps(config))
        self.assertTrue(config["has_api_key"])
        self.assertFalse(config["local"])
        self.assertEqual(config["host"], "api.cloudflare.com")
        self.assertFalse(config["default_config"])

    def test_local_default_is_flagged(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            config = llm_client.public_config()
        self.assertTrue(config["local"])
        self.assertTrue(config["default_config"])
        self.assertFalse(config["has_api_key"])

    def test_provider_host_includes_port(self):
        self.assertEqual(
            llm_client.provider_host("http://127.0.0.1:11434/v1"),
            "127.0.0.1:11434",
        )

    def test_public_config_strips_embedded_credentials(self):
        env = dict(
            REMOTE_ENV,
            JSEARCH_LLM_BASE_URL="https://user:pass@example.com/v1",
        )
        with mock.patch.dict(os.environ, env, clear=True):
            config = llm_client.public_config()
        self.assertEqual(config["base_url"], "https://example.com/v1")
        self.assertNotIn("pass", json.dumps(config))


class ErrorTests(unittest.TestCase):
    def test_local_connection_error_mentions_ollama(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch(
                "app.llm_client.requests.post",
                side_effect=requests.ConnectionError("refused"),
            ):
                with self.assertRaises(llm_client.LLMError) as caught:
                    llm_client.chat_json([{"role": "user", "content": "hi"}])
        message = str(caught.exception)
        self.assertIn("Ollama", message)
        self.assertIn("127.0.0.1", message)

    def test_remote_connection_error_does_not_mention_ollama(self):
        with mock.patch.dict(os.environ, REMOTE_ENV, clear=True):
            with mock.patch(
                "app.llm_client.requests.post",
                side_effect=requests.ConnectionError("refused"),
            ):
                with self.assertRaises(llm_client.LLMError) as caught:
                    llm_client.chat_json([{"role": "user", "content": "hi"}])
        message = str(caught.exception)
        self.assertNotIn("Ollama", message)
        self.assertIn("api.cloudflare.com", message)
        self.assertIn("JSEARCH_LLM_BASE_URL", message)

    def test_rejected_key_has_actionable_message(self):
        with mock.patch.dict(os.environ, REMOTE_ENV, clear=True):
            with mock.patch(
                "app.llm_client.requests.post",
                return_value=response(401, '{"error": "invalid api key"}'),
            ):
                with self.assertRaises(llm_client.LLMError) as caught:
                    llm_client.chat_json([{"role": "user", "content": "hi"}])
        message = str(caught.exception)
        self.assertIn("API key was rejected", message)
        self.assertIn("api.cloudflare.com", message)

    def test_missing_endpoint_and_model_are_named(self):
        with mock.patch.dict(os.environ, REMOTE_ENV, clear=True):
            with mock.patch(
                "app.llm_client.requests.post",
                return_value=response(404, "not found"),
            ):
                with self.assertRaises(llm_client.LLMError) as caught:
                    llm_client.chat_json([{"role": "user", "content": "hi"}])
        message = str(caught.exception)
        self.assertIn("JSEARCH_LLM_BASE_URL", message)
        self.assertIn("JSEARCH_LLM_MODEL", message)

    def test_rate_limit_is_explained(self):
        with mock.patch.dict(os.environ, REMOTE_ENV, clear=True):
            with mock.patch(
                "app.llm_client.requests.post",
                return_value=response(429, "slow down"),
            ):
                with self.assertRaises(llm_client.LLMError) as caught:
                    llm_client.chat_json([{"role": "user", "content": "hi"}])
        self.assertIn("Rate limit reached", str(caught.exception))

    def test_timeout_names_the_timeout(self):
        with mock.patch.dict(os.environ, REMOTE_ENV, clear=True):
            with mock.patch(
                "app.llm_client.requests.post",
                side_effect=requests.Timeout("too slow"),
            ):
                with self.assertRaises(llm_client.LLMError) as caught:
                    llm_client.chat_json([{"role": "user", "content": "hi"}])
        self.assertIn("did not respond within 30 seconds", str(caught.exception))

    def test_provider_detail_redacts_the_api_key(self):
        with mock.patch.dict(os.environ, REMOTE_ENV, clear=True):
            with mock.patch(
                "app.llm_client.requests.post",
                return_value=response(500, "failure for secret-key-123"),
            ):
                with self.assertRaises(llm_client.LLMError) as caught:
                    llm_client.chat_json([{"role": "user", "content": "hi"}])
        message = str(caught.exception)
        self.assertNotIn("secret-key-123", message)
        self.assertIn("[redacted]", message)


class RequestTests(unittest.TestCase):
    def test_ping_sends_no_cv_content(self):
        payload = {"choices": [{"message": {"content": "OK"}}]}
        with mock.patch.dict(os.environ, REMOTE_ENV, clear=True):
            with mock.patch(
                "app.llm_client.requests.post",
                return_value=response(200, payload=payload),
            ) as post:
                result = llm_client.ping()
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["messages"][0]["content"], "Reply with the single word OK.")
        self.assertEqual(result["model"], "@cf/openai/gpt-oss-20b")
        self.assertEqual(result["host"], "api.cloudflare.com")
        self.assertGreaterEqual(result["latency_ms"], 0)
        self.assertTrue(result["ok"])

    def test_chat_json_retries_without_response_format(self):
        first = response(400, "response_format not supported")
        second = response(
            200,
            payload={"choices": [{"message": {"content": '{"skills": []}'}}]},
        )
        with mock.patch.dict(os.environ, REMOTE_ENV, clear=True):
            with mock.patch(
                "app.llm_client.requests.post", side_effect=[first, second]
            ) as post:
                result = llm_client.chat_json([{"role": "user", "content": "hi"}])
        self.assertEqual(result, {"skills": []})
        self.assertIn("response_format", post.call_args_list[0].kwargs["json"])
        self.assertNotIn("response_format", post.call_args_list[1].kwargs["json"])


if __name__ == "__main__":
    unittest.main()
