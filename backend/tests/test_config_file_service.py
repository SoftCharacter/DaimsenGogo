import os
import tempfile
import unittest
from pathlib import Path

from backend.models.config_models import AppConfig
from backend.models.theme_models import Theme
from backend.services import file_service as service


_ENV_KEYS = (
    "LLM_PROVIDER_NAME",
    "MODEL_PROVIDER_NAME",
    "OPENAI_PROVIDER_NAME",
    "LLM_BASE_URL",
    "MODEL_BASE_URL",
    "OPENAI_BASE_URL",
    "BASE_URL",
    "LLM_API_KEY",
    "MODEL_API_KEY",
    "OPENAI_API_KEY",
    "API_KEY",
    "LLM_MODEL",
    "MODEL_NAME",
    "OPENAI_MODEL",
    "WEB_SEARCH_ENABLED",
    "TAVILY_API_KEY",
)


class ConfigFileServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_data_dir = service.DATA_DIR
        self.original_root_dir = service.ROOT_DIR
        self.original_config_path = service.CONFIG_PATH
        self.original_themes_dir = service.THEMES_DIR
        self.original_task_cache_dir = service.TASK_CACHE_DIR
        self.original_env_path = service.ENV_PATH
        self.original_env = {key: os.environ.get(key) for key in _ENV_KEYS}
        for key in _ENV_KEYS:
            os.environ.pop(key, None)

        root = Path(self.temp_dir.name)
        service.DATA_DIR = root / "data"
        service.ROOT_DIR = root
        service.CONFIG_PATH = service.DATA_DIR / "config.json"
        service.THEMES_DIR = service.DATA_DIR / "themes"
        service.TASK_CACHE_DIR = service.DATA_DIR / "task_cache"
        service.ENV_PATH = root / ".env"

    def tearDown(self):
        service.DATA_DIR = self.original_data_dir
        service.ROOT_DIR = self.original_root_dir
        service.CONFIG_PATH = self.original_config_path
        service.THEMES_DIR = self.original_themes_dir
        service.TASK_CACHE_DIR = self.original_task_cache_dir
        service.ENV_PATH = self.original_env_path
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
            original = self.original_env[key]
            if original is not None:
                os.environ[key] = original
        self.temp_dir.cleanup()

    def test_load_config_applies_env_overrides_to_missing_config_file(self):
        service.ENV_PATH.write_text(
            "\n".join([
                'LLM_PROVIDER_NAME="DeepSeek"',
                'LLM_BASE_URL="https://api.deepseek.com/v1/"',
                'LLM_API_KEY="secret-key"',
                'LLM_MODEL="deepseek-chat"',
                'WEB_SEARCH_ENABLED="false"',
                'TAVILY_API_KEY="tavily-secret"',
            ]),
            encoding="utf-8",
        )

        config = service.load_config()

        self.assertEqual(config.provider.name, "DeepSeek")
        self.assertEqual(config.provider.base_url, "https://api.deepseek.com/v1")
        self.assertEqual(config.provider.api_key, "secret-key")
        self.assertEqual(config.selected_model, "deepseek-chat")
        self.assertIn("deepseek-chat", config.available_models)
        self.assertTrue(config.web_search.enabled)
        self.assertEqual(config.web_search.tavily_api_key, "tavily-secret")

    def test_load_config_prefers_env_values_over_persisted_json(self):
        persisted = AppConfig()
        persisted.provider.name = "JSONProvider"
        persisted.provider.base_url = "https://json.example.com/v1"
        persisted.provider.api_key = "json-key"
        persisted.selected_model = "json-model"
        persisted.available_models = ["json-model"]
        persisted.web_search.enabled = False
        persisted.web_search.tavily_api_key = "json-tavily"
        service.ensure_dirs()
        service.CONFIG_PATH.write_text(persisted.model_dump_json(indent=2), encoding="utf-8")
        service.ENV_PATH.write_text(
            "\n".join([
                'LLM_PROVIDER_NAME="EnvProvider"',
                'LLM_BASE_URL="https://env.example.com/v1"',
                'LLM_API_KEY="env-key"',
                'LLM_MODEL="env-model"',
                'TAVILY_API_KEY="env-tavily"',
            ]),
            encoding="utf-8",
        )

        config = service.load_config()

        self.assertEqual(config.provider.name, "EnvProvider")
        self.assertEqual(config.provider.base_url, "https://env.example.com/v1")
        self.assertEqual(config.provider.api_key, "env-key")
        self.assertEqual(config.selected_model, "env-model")
        self.assertEqual(config.web_search.tavily_api_key, "env-tavily")
        self.assertIn("json-model", config.available_models)
        self.assertIn("env-model", config.available_models)
        self.assertTrue(config.web_search.enabled)

    def test_load_config_ignores_placeholder_env_base_url(self):
        service.ENV_PATH.write_text(
            "\n".join([
                'LLM_BASE_URL="https://your-provider.example.com/v1"',
                'LLM_MODEL="placeholder-model"',
            ]),
            encoding="utf-8",
        )

        config = service.load_config()

        self.assertEqual(config.provider.base_url, "")
        self.assertEqual(config.selected_model, "placeholder-model")

    def test_save_config_writes_secrets_to_env_and_clears_persisted_json(self):
        config = AppConfig()
        config.provider.name = "Provider"
        config.provider.base_url = "https://provider.example.com/v1/"
        config.provider.api_key = "api-secret"
        config.selected_model = "model-a"
        config.available_models = ["model-a", "model-b"]
        config.web_search.enabled = False
        config.web_search.tavily_api_key = "tavily-secret"

        service.save_config(config)
        persisted = AppConfig.model_validate_json(service.CONFIG_PATH.read_text(encoding="utf-8"))
        env_text = service.ENV_PATH.read_text(encoding="utf-8")

        self.assertEqual(persisted.provider.name, "")
        self.assertEqual(persisted.provider.base_url, "")
        self.assertEqual(persisted.provider.api_key, "")
        self.assertEqual(persisted.selected_model, "")
        self.assertEqual(persisted.web_search.tavily_api_key, "")
        self.assertEqual(persisted.available_models, ["model-a", "model-b"])
        self.assertIn("LLM_PROVIDER_NAME='Provider'", env_text)
        self.assertIn("LLM_BASE_URL='https://provider.example.com/v1'", env_text)
        self.assertIn("LLM_API_KEY='api-secret'", env_text)
        self.assertIn("LLM_MODEL='model-a'", env_text)
        self.assertIn("WEB_SEARCH_ENABLED='true'", env_text)
        self.assertIn("TAVILY_API_KEY='tavily-secret'", env_text)

    def test_delete_theme_reports_source_task_cache_cleanup(self):
        theme = Theme(id="theme_1", name="测试主题", source_task_id="task_1")
        service.save_theme(theme)
        cache_dir = service.TASK_CACHE_DIR / "task_1"
        cache_dir.mkdir(parents=True)
        (cache_dir / "kline.json").write_text("{}", encoding="utf-8")

        result = service.delete_theme_with_cache_result("theme_1")

        self.assertTrue(result.deleted)
        self.assertEqual(result.source_task_id, "task_1")
        self.assertTrue(result.task_cache_removed)
        self.assertIsNone(service.load_theme("theme_1"))
        self.assertFalse(cache_dir.exists())


if __name__ == "__main__":
    unittest.main()
