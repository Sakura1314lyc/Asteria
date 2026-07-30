from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from paper_agent.cli import main
from paper_agent.config import Settings
from paper_agent.llm import DemoLLM
from paper_agent.retrievers import FixtureRetriever
from paper_agent.workflow import ResearchAgent

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_dual_screening_can_be_completed_from_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            environment = {
                "PAPER_AGENT_DATA_ROOT": str(root / "data"),
                "PAPER_AGENT_DATABASE": str(root / "workbench.db"),
                "PAPER_AGENT_OUTPUT_ROOT": str(root / "runs"),
            }
            bibliography = root / "screening.ris"
            bibliography.write_text(
                """TY  - CONF
TI  - Independent Review Systems
AU  - Patel, Mira
PY  - 2025
ER  -
""",
                encoding="utf-8",
            )
            with patch.dict(os.environ, environment):
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(
                        main(
                            [
                                "project",
                                "create",
                                "Dual CLI",
                                "--topic",
                                "software engineering",
                            ]
                        ),
                        0,
                    )
                project_id = json.loads(output.getvalue())["id"]
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "bibliography",
                                "import",
                                project_id,
                                str(bibliography),
                            ]
                        ),
                        0,
                    )
                    self.assertEqual(
                        main(
                            [
                                "screen",
                                "configure",
                                project_id,
                                "--reviewer",
                                "alice",
                                "--reviewer",
                                "bob",
                            ]
                        ),
                        0,
                    )

                status_output = io.StringIO()
                with redirect_stdout(status_output):
                    self.assertEqual(
                        main(
                            [
                                "screen",
                                "status",
                                project_id,
                                "--reviewer",
                                "alice",
                                "--json",
                            ]
                        ),
                        0,
                    )
                paper_id = json.loads(status_output.getvalue())["papers"][0]["id"]
                for reviewer, status in (
                    ("alice", "included"),
                    ("bob", "excluded"),
                ):
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(
                            main(
                                [
                                    "screen",
                                    "decide",
                                    project_id,
                                    str(paper_id),
                                    status,
                                    "--reviewer",
                                    reviewer,
                                ]
                            ),
                            0,
                        )
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "screen",
                                "configure",
                                project_id,
                                "--open",
                            ]
                        ),
                        0,
                    )
                    self.assertEqual(
                        main(
                            [
                                "screen",
                                "resolve",
                                project_id,
                                str(paper_id),
                                "included",
                                "--reason",
                                "Resolved by discussion",
                                "--reviewer",
                                "carol",
                            ]
                        ),
                        0,
                    )

    def test_bibliography_import_has_human_and_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            environment = {
                "PAPER_AGENT_DATA_ROOT": str(root / "data"),
                "PAPER_AGENT_DATABASE": str(root / "workbench.db"),
                "PAPER_AGENT_OUTPUT_ROOT": str(root / "runs"),
            }
            bibliography = root / "library.ris"
            bibliography.write_text(
                """TY  - CONF
TI  - Auditable Research Agents
AU  - Chen, Lin
PY  - 2025
DO  - 10.5555/auditable
ER  -
""",
                encoding="utf-8",
            )
            with patch.dict(os.environ, environment):
                created_output = io.StringIO()
                with redirect_stdout(created_output):
                    self.assertEqual(
                        main(
                            [
                                "project",
                                "create",
                                "Import test",
                                "--topic",
                                "research agents",
                            ]
                        ),
                        0,
                    )
                project_id = json.loads(created_output.getvalue())["id"]

                human_output = io.StringIO()
                with redirect_stdout(human_output):
                    result = main(
                        [
                            "bibliography",
                            "import",
                            project_id,
                            str(bibliography),
                        ]
                    )
                self.assertEqual(result, 0)
                self.assertIn("新增 1", human_output.getvalue())
                self.assertIn("证据 ID：P001", human_output.getvalue())

                json_output = io.StringIO()
                with redirect_stdout(json_output):
                    result = main(
                        [
                            "bibliography",
                            "import",
                            project_id,
                            str(bibliography),
                            "--json",
                        ]
                    )
                self.assertEqual(result, 0)
                payload = json.loads(json_output.getvalue())
                self.assertEqual(payload["added"], 0)
                self.assertEqual(payload["already_present"], 1)

    def test_inspect_is_concise_by_default_and_json_on_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            agent = ResearchAgent(
                settings=Settings(output_root=Path(temp)),
                llm=DemoLLM("research agents"),
                retrievers=[FixtureRetriever(ROOT / "examples" / "demo_papers.json")],
            )
            run_dir = agent.run(
                "research agents",
                "How are citations audited?",
                stop_after="planned",
            )

            human_output = io.StringIO()
            with redirect_stdout(human_output):
                result = main(["inspect", str(run_dir)])
            self.assertEqual(result, 0)
            self.assertIn("运行：", human_output.getvalue())
            self.assertNotIn('"audit":', human_output.getvalue())

            json_output = io.StringIO()
            with redirect_stdout(json_output):
                result = main(["inspect", str(run_dir), "--json"])
            self.assertEqual(result, 0)
            self.assertIn('"run_id":', json_output.getvalue())
            self.assertIn('"audit":', json_output.getvalue())


if __name__ == "__main__":
    unittest.main()
