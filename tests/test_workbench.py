from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paper_agent.config import Settings
from paper_agent.database import Database
from paper_agent.domain import ReviewProtocol, RunStatus
from paper_agent.llm import DemoLLM
from paper_agent.models import EvidenceCard, Paper
from paper_agent.quality import assess_evidence_quality
from paper_agent.retrievers import FixtureRetriever
from paper_agent.screening import ScreeningEngine
from paper_agent.workbench import ResearchWorkbench, WorkbenchError

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "demo_papers.json"


class WorkbenchTests(unittest.TestCase):
    def make_settings(self, root: Path) -> Settings:
        return Settings(
            output_root=root / "runs",
            data_root=root / "data",
            database_path=root / "workbench.db",
            max_papers=5,
            max_queries=3,
            results_per_query=5,
        )

    def test_database_project_and_paper_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = Database(Path(temp) / "test.db")
            project = database.create_project(
                name="Test",
                topic="research agents",
                research_question="How are they evaluated?",
            )
            paper = Paper(
                paper_id="P001",
                title="Evidence Agents",
                authors=["A. Author"],
                year=2025,
                abstract="A sufficiently descriptive abstract.",
                doi="10.1/example",
                categories=["cs.AI", "cs.SE"],
                publication_type="Conference and Workshop Papers",
                code_urls=["https://example.org/code"],
                dataset_urls=["https://example.org/data"],
            )
            paper_id = database.upsert_paper(paper)
            database.attach_paper(project.id, paper_id, "P001")
            rows = database.list_project_papers(project.id)
            self.assertEqual(rows[0]["paper"].title, "Evidence Agents")
            self.assertEqual(rows[0]["paper"].categories, ["cs.AI", "cs.SE"])
            self.assertEqual(
                rows[0]["paper"].publication_type,
                "Conference and Workshop Papers",
            )
            self.assertEqual(rows[0]["paper"].code_urls, ["https://example.org/code"])
            self.assertEqual(
                rows[0]["paper"].dataset_urls,
                ["https://example.org/data"],
            )
            self.assertEqual(database.project_stats(project.id)["pending"], 1)

    def test_document_ingest_and_full_text_search(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workbench = ResearchWorkbench(self.make_settings(root))
            project = workbench.create_project(name="Docs", topic="evidence")
            document = root / "article.txt"
            document.write_text(
                "Retrieval augmented generation improves grounding.\n\n"
                "Citation audits detect unsupported paragraphs.",
                encoding="utf-8",
            )
            record = workbench.documents.ingest(
                project_id=project.id,
                source=document,
            )
            matches = workbench.documents.search(project.id, "citation audits")
            self.assertEqual(record.page_count, 1)
            self.assertTrue(matches)
            self.assertEqual(matches[0]["document_id"], record.id)

    def test_protocol_screening_is_explainable(self) -> None:
        protocol = ReviewProtocol(
            include_keywords=["agent"],
            exclude_keywords=["editorial"],
            year_from=2020,
        )
        suggestion = ScreeningEngine().suggest(
            Paper(
                paper_id="P001",
                title="Agent editorial",
                abstract="An editorial about agents.",
                year=2024,
            ),
            protocol,
        )
        self.assertEqual(suggestion.status, "excluded")
        self.assertIn("editorial", suggestion.matched_exclude)

    def test_quality_appraisal_has_bounded_score(self) -> None:
        quality = assess_evidence_quality(
            Paper(
                paper_id="P001",
                title="Study",
                abstract="A" * 400,
                doi="10.1/test",
            ),
            EvidenceCard(
                paper_id="P001",
                relevance="direct",
                objective="test",
                methods="Randomized comparison with a documented procedure." * 2,
                data_or_sample="120 participants",
                findings=["Finding one", "Finding two"],
                limitations=["Single-site sample."],
                confidence="medium",
            ),
        )
        self.assertGreaterEqual(quality.overall, 0)
        self.assertLessEqual(quality.overall, 1)

    def test_systematic_run_pauses_for_human_screening_then_continues(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings = self.make_settings(root)
            workbench = ResearchWorkbench(settings)
            project = workbench.create_project(
                name="Systematic review",
                topic="research agents",
                research_question="How are evidence-grounded agents designed?",
                review_type="systematic",
            )
            run = workbench.create_run(project.id)
            run_dir = workbench.execute_run(
                run.id,
                llm=DemoLLM(project.topic),
                retrievers=[FixtureRetriever(FIXTURE)],
            )
            paused = workbench.database.get_run(run.id)
            self.assertEqual(paused["status"], RunStatus.WAITING_FOR_SCREENING)
            self.assertEqual(paused["stage"], "searched")
            rows = workbench.database.list_project_papers(project.id)
            self.assertEqual(len(rows), 5)
            for index, row in enumerate(rows):
                workbench.record_screening(
                    project_id=project.id,
                    paper_id=row["id"],
                    status="excluded" if index == 0 else "included",
                    reason="test decision",
                    reviewer="unit-test",
                )
            workbench.continue_after_screening(
                run.id,
                llm=DemoLLM(project.topic),
                retrievers=[FixtureRetriever(FIXTURE)],
            )
            completed = workbench.database.get_run(run.id)
            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(completed["status"], RunStatus.COMPLETED)
            self.assertEqual(state["stage"], "completed")
            self.assertEqual(len(state["papers"]), 4)
            self.assertTrue((run_dir / "quality.json").exists())
            self.assertTrue((run_dir / "literature_graph.graphml").exists())
            self.assertTrue((run_dir / "cs_evidence_matrix.csv").exists())
            self.assertTrue((run_dir / "reproducibility.json").exists())
            self.assertEqual(len(workbench.database.list_reports(project.id)), 1)

    def test_systematic_run_uses_only_fulltext_inclusions_downstream(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workbench = ResearchWorkbench(self.make_settings(root))
            project = workbench.create_project(
                name="Two-stage systematic review",
                topic="research agents",
                research_question="How are evidence-grounded agents designed?",
                review_type="systematic",
            )
            run = workbench.create_run(project.id)
            run_dir = workbench.execute_run(
                run.id,
                llm=DemoLLM(project.topic),
                retrievers=[FixtureRetriever(FIXTURE)],
            )
            rows = workbench.database.list_project_papers(project.id)
            candidates = rows[:2]
            for index, row in enumerate(rows):
                workbench.record_screening(
                    project_id=project.id,
                    paper_id=row["id"],
                    status="included" if index < 2 else "excluded",
                    reason="Title and abstract eligibility decision",
                    reviewer="unit-test",
                )
            workbench.configure_fulltext_screening(
                project.id,
                enabled=True,
            )
            for index, row in enumerate(candidates):
                article = root / f"fulltext-{index}.txt"
                article.write_text(
                    f"Complete report {index}: methods, evaluation, and findings.",
                    encoding="utf-8",
                )
                workbench.documents.ingest(
                    project_id=project.id,
                    source=article,
                    paper_id=row["id"],
                )
            with self.assertRaises(WorkbenchError):
                workbench.continue_after_screening(
                    run.id,
                    llm=DemoLLM(project.topic),
                    retrievers=[FixtureRetriever(FIXTURE)],
                )
            workbench.record_fulltext_screening_batch(
                project_id=project.id,
                decisions=[
                    {
                        "paper_id": candidates[0]["id"],
                        "status": "included",
                        "reason": "Eligible complete empirical report",
                        "reviewer": "unit-test",
                    },
                    {
                        "paper_id": candidates[1]["id"],
                        "status": "excluded",
                        "reason": "No primary empirical contribution",
                        "exclusion_code": "not_primary_research",
                        "reviewer": "unit-test",
                    },
                ],
            )

            workbench.continue_after_screening(
                run.id,
                llm=DemoLLM(project.topic),
                retrievers=[FixtureRetriever(FIXTURE)],
            )

            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            review_flow = json.loads(
                (run_dir / "review_flow.json").read_text(encoding="utf-8")
            )
            self.assertEqual(state["stage"], "completed")
            self.assertEqual(
                [paper["paper_id"] for paper in state["papers"]],
                [candidates[0]["evidence_id"]],
            )
            self.assertEqual(
                review_flow["reports_excluded_after_fulltext"],
                1,
            )
            self.assertEqual(
                review_flow["fulltext_exclusion_reasons"],
                {"not_primary_research": 1},
            )


if __name__ == "__main__":
    unittest.main()
