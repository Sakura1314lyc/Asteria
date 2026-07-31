from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paper_agent.artifacts import citation_audit
from paper_agent.config import Settings
from paper_agent.domain import ReviewProtocol
from paper_agent.llm import DemoLLM, _extract_output_text
from paper_agent.models import Paper, ResearchState
from paper_agent.retrievers import FixtureRetriever, rank_papers, search_all
from paper_agent.workflow import ResearchAgent

ROOT = Path(__file__).resolve().parents[1]


class CoreTests(unittest.TestCase):
    def test_research_state_ignores_future_fields_and_defaults_search_log(self) -> None:
        state = ResearchState.from_dict(
            {
                "run_id": "old-run",
                "topic": "legacy",
                "question": "Does it resume?",
                "language": "en",
                "future_field": {"not": "known"},
            }
        )
        self.assertEqual(state.search_log, {})
        self.assertEqual(state.run_id, "old-run")

    def test_extracts_responses_api_output_text(self) -> None:
        response = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": '{"ok": true}'}],
                }
            ]
        }
        self.assertEqual(_extract_output_text(response), '{"ok": true}')

    def test_rank_assigns_stable_evidence_ids(self) -> None:
        papers = [
            Paper(title="Unrelated note", year=2020),
            Paper(
                title="Research agent citation audit",
                abstract="research agent evidence citation",
                year=2025,
                citation_count=10,
            ),
        ]
        ranked = rank_papers(papers, "research agent citation", 2)
        self.assertEqual(ranked[0].paper_id, "P001")
        self.assertIn("Research agent", ranked[0].title)

    def test_citation_audit_rejects_unknown_ids(self) -> None:
        papers = [Paper(paper_id="P001", title="A")]
        report = (
            "# Report\n\n"
            "This is a sufficiently long factual paragraph for structural audit "
            "and it cites both a known and an invalid record. [P001] [P999]"
        )
        audit = citation_audit(report, papers)
        self.assertEqual(audit["unknown_citations"], ["P999"])
        self.assertFalse(audit["passed"])

    def test_citation_grounding_proxy_flags_lexically_aligned_claim(self) -> None:
        papers = [
            Paper(
                paper_id="P001",
                title="Tail Latency Evaluation",
                abstract=(
                    "The systems evaluation reports throughput and tail latency "
                    "under realistic workloads."
                ),
            )
        ]
        report = (
            "The systems evaluation reports throughput and tail latency under "
            "realistic workloads, allowing direct comparison. [P001]"
        )
        audit = citation_audit(report, papers)
        grounding = audit["grounding_proxy"]
        self.assertEqual(grounding["assessable_count"], 1)
        self.assertEqual(grounding["aligned_proxy_count"], 1)
        self.assertEqual(grounding["alignment_rate"], 1.0)
        self.assertEqual(grounding["assessment_coverage"], 1.0)
        self.assertEqual(grounding["effective_alignment_rate"], 1.0)

    def test_search_continues_when_one_retriever_fails(self) -> None:
        class GoodRetriever:
            name = "good"

            def search(self, query: str, limit: int) -> list[Paper]:
                return [Paper(title=f"Evidence for {query}", source=self.name)]

        class FailingRetriever:
            name = "failing"

            def search(self, query: str, limit: int) -> list[Paper]:
                raise RuntimeError("temporary outage")

        papers, warnings, executions = search_all(
            [GoodRetriever(), FailingRetriever()],
            ["topic"],
            Settings(results_per_query=1),
        )
        self.assertEqual(len(papers), 1)
        self.assertEqual(len(warnings), 1)
        self.assertIn("temporary outage", warnings[0])
        self.assertEqual([item.status for item in executions], ["succeeded", "failed"])
        self.assertEqual(executions[0].result_count, 1)
        self.assertEqual(executions[1].result_count, 0)
        self.assertEqual(executions[1].error, "temporary outage")

    def test_demo_workflow_writes_all_artifacts(self) -> None:
        fixture = ROOT / "examples" / "demo_papers.json"
        with tempfile.TemporaryDirectory() as temp:
            settings = Settings(
                output_root=Path(temp),
                max_papers=5,
                max_queries=3,
                results_per_query=5,
            )
            agent = ResearchAgent(
                settings=settings,
                llm=DemoLLM("科研智能体"),
                retrievers=[FixtureRetriever(fixture)],
                protocol=ReviewProtocol(
                    year_from=2020,
                    languages=["en"],
                ),
            )
            run_dir = agent.run("科研智能体", "如何构建可审计的科研智能体？")
            expected = {
                "state.json",
                "events.jsonl",
                "plan.json",
                "search_log.json",
                "search_results.json",
                "evidence.json",
                "report.md",
                "references.bib",
                "audit.json",
            }
            self.assertTrue(
                expected.issubset({path.name for path in run_dir.iterdir()})
            )
            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["stage"], "completed")
            self.assertEqual(len(state["papers"]), 5)
            self.assertTrue(state["audit"]["passed"])
            search_log = json.loads(
                (run_dir / "search_log.json").read_text(encoding="utf-8")
            )
            self.assertEqual(search_log["schema_version"], 1)
            self.assertEqual(search_log["summary"]["failed"], 0)
            self.assertEqual(
                search_log["configured_restrictions"]["year_from"],
                2020,
            )
            self.assertEqual(
                search_log["configured_restrictions"]["languages"],
                ["en"],
            )
            self.assertGreater(
                search_log["summary"]["records_returned_before_deduplication"],
                search_log["summary"]["unique_records_after_deduplication"],
            )

    def test_workflow_preserves_an_explicit_research_question(self) -> None:
        fixture = ROOT / "examples" / "demo_papers.json"
        with tempfile.TemporaryDirectory() as temp:
            settings = Settings(
                output_root=Path(temp),
                max_papers=2,
                max_queries=2,
                results_per_query=2,
            )
            agent = ResearchAgent(
                settings=settings,
                llm=DemoLLM("research agents"),
                retrievers=[FixtureRetriever(fixture)],
            )
            question = "How should citation reliability be evaluated?"
            run_dir = agent.run(
                "research agents",
                question,
                stop_after="planned",
            )
            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["question"], question)
            self.assertEqual(state["plan"]["input_question"], question)
            self.assertEqual(
                state["plan"]["question_policy"],
                "explicit_preserved",
            )


if __name__ == "__main__":
    unittest.main()
