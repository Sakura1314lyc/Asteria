from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paper_agent.config import Settings
from paper_agent.connections import ConnectionRegistry
from paper_agent.llm import OpenAIResponsesLLM


class ConnectionProtocolTests(unittest.TestCase):
    def settings(self) -> Settings:
        root = Path(tempfile.gettempdir()) / "paper-agent-connection-tests"
        return Settings(
            data_root=root / "data",
            database_path=root / "db.sqlite",
            output_root=root / "runs",
        )

    def test_deepseek_is_normalized_to_supported_protocol(self) -> None:
        connection = ConnectionRegistry(self.settings()).create(
            name="DeepSeek",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-pro",
            api_format="responses",
            api_key="secret",
        )
        self.assertEqual(connection["provider"], "deepseek")
        self.assertEqual(connection["api_format"], "chat_completions")
        self.assertEqual(connection["structured_output"], "json_object")
        self.assertIn("自动切换", connection["notice"])
        self.assertNotIn("api_key", connection)

    @patch("paper_agent.llm.request_json")
    def test_json_object_provider_receives_schema_in_prompt(self, request) -> None:
        request.return_value = {
            "choices": [{"message": {"content": '{"answer":"ok"}'}}]
        }
        llm = OpenAIResponsesLLM(
            self.settings(),
            api_key="secret",
            api_format="chat_completions",
            structured_output="json_object",
        )
        result = llm.json(
            name="answer",
            schema={
                "type": "object",
                "properties": {"answer": {"type": "string"}},
                "required": ["answer"],
                "additionalProperties": False,
            },
            instructions="Return the answer.",
            user_input="test",
        )
        self.assertEqual(result, {"answer": "ok"})
        payload = request.call_args.kwargs["payload"]
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertIn("JSON Schema", payload["messages"][0]["content"])


if __name__ == "__main__":
    unittest.main()
