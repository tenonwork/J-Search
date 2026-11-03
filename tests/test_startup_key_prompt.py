import os
import unittest
from unittest import mock

import run


REMOTE_CONFIG = {
    'base_url': 'https://api.cloudflare.com/client/v4/accounts/example/ai/v1',
    'model': '@cf/openai/gpt-oss-20b',
    'api_key': '',
}
LOCAL_CONFIG = {
    'base_url': 'http://127.0.0.1:11434/v1',
    'model': 'qwen2.5:7b-instruct',
    'api_key': '',
}


class StartupKeyPromptTests(unittest.TestCase):
    def test_existing_key_skips_prompt(self):
        config = dict(REMOTE_CONFIG, api_key='configured')
        with mock.patch.object(run.llm_client, 'get_config', return_value=config), \
                mock.patch.object(run.getpass, 'getpass') as prompt:
            run._prompt_for_missing_api_key()
        prompt.assert_not_called()

    def test_local_endpoint_skips_prompt(self):
        with mock.patch.object(run.llm_client, 'get_config', return_value=LOCAL_CONFIG), \
                mock.patch.object(run.getpass, 'getpass') as prompt:
            run._prompt_for_missing_api_key()
        prompt.assert_not_called()

    def test_missing_remote_key_is_kept_in_memory(self):
        with mock.patch.dict(os.environ, {'JSEARCH_LLM_API_KEY': ''}, clear=False), \
                mock.patch.object(run.llm_client, 'get_config', return_value=dict(REMOTE_CONFIG)), \
                mock.patch.object(run.sys.stdin, 'isatty', return_value=True), \
                mock.patch('builtins.print'), \
                mock.patch.object(run.getpass, 'getpass', return_value=' test-key ') as prompt:
            run._prompt_for_missing_api_key()
            self.assertEqual(os.environ['JSEARCH_LLM_API_KEY'], 'test-key')
        prompt.assert_called_once()

    def test_non_interactive_startup_skips_prompt(self):
        with mock.patch.dict(os.environ, {'JSEARCH_LLM_API_KEY': ''}, clear=False), \
                mock.patch.object(run.llm_client, 'get_config', return_value=dict(REMOTE_CONFIG)), \
                mock.patch.object(run.sys.stdin, 'isatty', return_value=False), \
                mock.patch('builtins.print'), \
                mock.patch.object(run.getpass, 'getpass') as prompt:
            run._prompt_for_missing_api_key()
            self.assertEqual(os.environ.get('JSEARCH_LLM_API_KEY'), '')
        prompt.assert_not_called()

    def test_blank_input_does_not_set_a_key(self):
        with mock.patch.dict(os.environ, {'JSEARCH_LLM_API_KEY': ''}, clear=False), \
                mock.patch.object(run.llm_client, 'get_config', return_value=dict(REMOTE_CONFIG)), \
                mock.patch.object(run.sys.stdin, 'isatty', return_value=True), \
                mock.patch('builtins.print'), \
                mock.patch.object(run.getpass, 'getpass', return_value='   '):
            run._prompt_for_missing_api_key()
            self.assertEqual(os.environ.get('JSEARCH_LLM_API_KEY'), '')


if __name__ == '__main__':
    unittest.main()
