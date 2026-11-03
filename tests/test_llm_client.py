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

LLAMA_ENV = dict(REMOTE_ENV, JSEARCH_LLM_MODEL="@cf/meta/llama-3.1-8b-instruct")


def response(status, text="", payload=None):
    fake = mock.Mock()
    fake.status_code = status
    fake.text = text
    fake.json.return_value = payload or {}
    return fake


def chat_response(content, finish_reason="stop", usage=None, reasoning=""):
    message = {"content": content}
    if reasoning:
        message["reasoning_content"] = reasoning
    return response(
        200,
        payload={
            "choices": [
                {
                    "message": message,
                    "finish_reason": finish_reason,
                }
            ],
            "usage": usage or {},
        },
    )


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

    def test_max_tokens_is_clamped(self):
        with mock.patch.dict(
            os.environ, {"JSEARCH_LLM_MAX_TOKENS": "999999"}, clear=True
        ):
            self.assertEqual(llm_client.get_config()["max_tokens"], 16384)
        with mock.patch.dict(
            os.environ, {"JSEARCH_LLM_MAX_TOKENS": "1"}, clear=True
        ):
            self.assertEqual(llm_client.get_config()["max_tokens"], 256)


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
        self.assertEqual(sent["max_completion_tokens"], 8)
        self.assertNotIn("max_tokens", sent)
        self.assertEqual(result["model"], "@cf/openai/gpt-oss-20b")
        self.assertEqual(result["host"], "api.cloudflare.com")
        self.assertGreaterEqual(result["latency_ms"], 0)
        self.assertTrue(result["ok"])

    def test_gpt_oss_omits_response_format(self):
        with mock.patch.dict(os.environ, REMOTE_ENV, clear=True):
            with mock.patch(
                "app.llm_client.requests.post",
                return_value=chat_response('{"skills": []}'),
            ) as post:
                result = llm_client.chat_json([{"role": "user", "content": "hi"}])
        sent = post.call_args.kwargs["json"]
        self.assertEqual(result, {"skills": []})
        self.assertNotIn("response_format", sent)
        self.assertEqual(sent["max_completion_tokens"], 8192)
        self.assertNotIn("max_tokens", sent)
        self.assertEqual(sent["reasoning_effort"], "low")

    def test_non_gpt_oss_uses_max_tokens(self):
        with mock.patch.dict(os.environ, LLAMA_ENV, clear=True):
            with mock.patch(
                "app.llm_client.requests.post",
                return_value=chat_response('{"skills": []}'),
            ) as post:
                llm_client.chat_json([{"role": "user", "content": "hi"}])
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["max_tokens"], 8192)
        self.assertNotIn("max_completion_tokens", sent)

    def test_budget_field_can_be_overridden(self):
        env = dict(REMOTE_ENV, JSEARCH_LLM_MAX_TOKENS_FIELD="max_tokens")
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch(
                "app.llm_client.requests.post",
                return_value=chat_response('{"skills": []}'),
            ) as post:
                llm_client.chat_json([{"role": "user", "content": "hi"}])
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["max_tokens"], 8192)
        self.assertNotIn("max_completion_tokens", sent)

    def test_reasoning_effort_can_be_overridden(self):
        env = dict(REMOTE_ENV, JSEARCH_LLM_REASONING_EFFORT="medium")
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch(
                "app.llm_client.requests.post",
                return_value=chat_response('{"skills": []}'),
            ) as post:
                llm_client.chat_json([{"role": "user", "content": "hi"}])
        self.assertEqual(post.call_args.kwargs["json"]["reasoning_effort"], "medium")

    def test_invalid_reasoning_effort_is_not_sent(self):
        env = dict(REMOTE_ENV, JSEARCH_LLM_REASONING_EFFORT="extreme")
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch(
                "app.llm_client.requests.post",
                return_value=chat_response('{"skills": []}'),
            ) as post:
                llm_client.chat_json([{"role": "user", "content": "hi"}])
        self.assertNotIn("reasoning_effort", post.call_args.kwargs["json"])

    def test_chat_json_retries_without_reasoning_effort_on_400(self):
        first = response(400, "reasoning_effort not supported")
        second = chat_response('{"skills": []}')
        with mock.patch.dict(os.environ, REMOTE_ENV, clear=True):
            with mock.patch(
                "app.llm_client.requests.post", side_effect=[first, second]
            ) as post:
                result = llm_client.chat_json([{"role": "user", "content": "hi"}])
        self.assertEqual(result, {"skills": []})
        self.assertIn("reasoning_effort", post.call_args_list[0].kwargs["json"])
        self.assertNotIn("reasoning_effort", post.call_args_list[1].kwargs["json"])

    def test_400_fallback_drops_all_optional_fields(self):
        first = response(400, "unsupported parameters")
        second = chat_response('{"skills": []}')
        env = dict(LLAMA_ENV, JSEARCH_LLM_REASONING_EFFORT="low")
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch(
                "app.llm_client.requests.post", side_effect=[first, second]
            ) as post:
                result = llm_client.chat_json([{"role": "user", "content": "hi"}])
        self.assertEqual(result, {"skills": []})
        first_payload = post.call_args_list[0].kwargs["json"]
        second_payload = post.call_args_list[1].kwargs["json"]
        self.assertIn("response_format", first_payload)
        self.assertIn("reasoning_effort", first_payload)
        self.assertNotIn("response_format", second_payload)
        self.assertNotIn("reasoning_effort", second_payload)

    def test_400_fallback_swaps_the_budget_field(self):
        first = response(400, "unsupported budget field")
        second = response(400, "still unsupported")
        third = chat_response('{"skills": []}')
        env = dict(
            LLAMA_ENV,
            JSEARCH_LLM_MAX_TOKENS_FIELD="max_completion_tokens",
        )
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch(
                "app.llm_client.requests.post",
                side_effect=[first, second, third],
            ) as post:
                result = llm_client.chat_json([{"role": "user", "content": "hi"}])
        self.assertEqual(result, {"skills": []})
        first_payload = post.call_args_list[0].kwargs["json"]
        second_payload = post.call_args_list[1].kwargs["json"]
        third_payload = post.call_args_list[2].kwargs["json"]
        self.assertIn("max_completion_tokens", first_payload)
        self.assertIn("max_completion_tokens", second_payload)
        self.assertNotIn("response_format", second_payload)
        self.assertIn("max_tokens", third_payload)
        self.assertNotIn("max_completion_tokens", third_payload)

    def test_chat_json_retries_without_response_format_on_400(self):
        first = response(400, "response_format not supported")
        second = chat_response('{"skills": []}')
        with mock.patch.dict(os.environ, LLAMA_ENV, clear=True):
            with mock.patch(
                "app.llm_client.requests.post", side_effect=[first, second]
            ) as post:
                result = llm_client.chat_json([{"role": "user", "content": "hi"}])
        self.assertEqual(result, {"skills": []})
        self.assertIn("response_format", post.call_args_list[0].kwargs["json"])
        self.assertNotIn("response_format", post.call_args_list[1].kwargs["json"])

    def test_empty_json_mode_response_retries_without_format(self):
        first = chat_response("")
        second = chat_response('{"skills": []}')
        with mock.patch.dict(os.environ, LLAMA_ENV, clear=True):
            with mock.patch(
                "app.llm_client.requests.post", side_effect=[first, second]
            ) as post:
                result = llm_client.chat_json([{"role": "user", "content": "hi"}])
        self.assertEqual(result, {"skills": []})
        self.assertIn("response_format", post.call_args_list[0].kwargs["json"])
        self.assertNotIn("response_format", post.call_args_list[1].kwargs["json"])

    def test_empty_response_after_retry_is_explained(self):
        empty = chat_response("")
        with mock.patch.dict(os.environ, LLAMA_ENV, clear=True):
            with mock.patch(
                "app.llm_client.requests.post", side_effect=[empty, empty]
            ):
                with self.assertRaises(llm_client.LLMError) as caught:
                    llm_client.chat_json([{"role": "user", "content": "hi"}])
        message = str(caught.exception)
        self.assertIn("empty final answer", message)
        self.assertIn("JSEARCH_LLM_MAX_TOKENS", message)

    def test_length_finish_reason_is_explained(self):
        truncated = chat_response(
            '{"skills": [',
            finish_reason="length",
            reasoning="x" * 42,
            usage={"completion_tokens": 8192},
        )
        with mock.patch.dict(os.environ, REMOTE_ENV, clear=True):
            with mock.patch(
                "app.llm_client.requests.post", return_value=truncated
            ):
                with self.assertRaises(llm_client.LLMError) as caught:
                    llm_client.chat_json([{"role": "user", "content": "hi"}])
        message = str(caught.exception)
        self.assertIn("ran out of output tokens", message)
        self.assertIn("JSEARCH_LLM_MAX_TOKENS", message)
        self.assertIn("8192", message)
        self.assertIn("reasoning 42 chars", message)
        self.assertIn("8192 output tokens", message)

    def test_max_tokens_env_override(self):
        env = dict(REMOTE_ENV, JSEARCH_LLM_MAX_TOKENS="4096")
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch(
                "app.llm_client.requests.post",
                return_value=chat_response('{"skills": []}'),
            ) as post:
                llm_client.chat_json([{"role": "user", "content": "hi"}])
        self.assertEqual(post.call_args.kwargs["json"]["max_completion_tokens"], 4096)

    def test_json_mode_can_be_disabled_for_other_models(self):
        env = dict(LLAMA_ENV, JSEARCH_LLM_JSON_MODE="0")
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch(
                "app.llm_client.requests.post",
                return_value=chat_response('{"skills": []}'),
            ) as post:
                llm_client.chat_json([{"role": "user", "content": "hi"}])
        self.assertNotIn("response_format", post.call_args.kwargs["json"])


if __name__ == "__main__":
    unittest.main()
