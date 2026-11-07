import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class AIEnvironmentTests(unittest.TestCase):
    def load_ai_module(self):
        # Simulate python-dotenv's documented behavior when an old .env exists.
        dotenv = types.ModuleType("dotenv")
        def load_dotenv():
            os.environ.setdefault("SAKURAFRP_USERNAME", "old-account")
            os.environ.setdefault("ZHIPU_API_KEY", "old-key")
        dotenv.load_dotenv = load_dotenv
        zhipuai = types.ModuleType("zhipuai")
        zhipuai.ZhipuAI = lambda **kwargs: kwargs
        spec = importlib.util.spec_from_file_location(
            "test_ai_module", Path(__file__).with_name("ai_service.py")
        )
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"dotenv": dotenv, "zhipuai": zhipuai}):
            spec.loader.exec_module(module)
        return module

    def test_import_does_not_fill_missing_credentials_from_dotenv(self):
        with patch.dict(os.environ, {}, clear=True):
            self.load_ai_module()
            self.assertNotIn("SAKURAFRP_USERNAME", os.environ)
            self.assertNotIn("ZHIPU_API_KEY", os.environ)

    def test_explicit_ai_environment_is_used(self):
        with patch.dict(os.environ, {"ZHIPU_API_KEY": "configured-key", "ZHIPU_MODEL_VISION": "vision-model"}, clear=True):
            service = self.load_ai_module().AIService()
            self.assertEqual(service.api_key, "configured-key")
            self.assertEqual(service.model_vision, "vision-model")


if __name__ == "__main__":
    unittest.main()
