import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/dev"))
from local_llm import ollama_schema


class LocalLLMSchemaTests(unittest.TestCase):
    def test_optional_scalar_conversion_preserves_server_schema(self):
        original = {"type": "object", "properties": {
            "parameter1": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": None, "title": "Parameter1"},
            "token": {"type": "string"}}, "required": ["token"]}
        before = copy.deepcopy(original)
        converted = ollama_schema(original)
        self.assertEqual(converted["properties"]["parameter1"], {"type": "integer"})
        self.assertEqual(converted["required"], ["token"])
        self.assertEqual(original, before)

    def test_general_unions_and_non_null_defaults_are_preserved(self):
        original = {"anyOf": [{"type": "integer"}, {"type": "string"}], "default": 0}
        self.assertEqual(ollama_schema(original), original)
        self.assertEqual(ollama_schema({"type": "boolean", "default": False}), {"type": "boolean", "default": False})


if __name__ == "__main__":
    unittest.main()
