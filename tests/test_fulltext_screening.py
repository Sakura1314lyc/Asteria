from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from paper_agent.config import Settings
from paper_agent.database import Database, DatabaseError
from paper_agent.fulltext_screening import (
    FullTextDecision,
    evaluate_fulltext_consensus,
)
from paper_agent.models import Paper
from paper_agent.workbench import ResearchWorkbench


class FullTextScreeningTests(unittest.TestCase):
    def make_workbench(self, root: Path) -> ResearchWorkbench:
        return ResearchWorkbench(
            Settings(
                output_root=root / "runs",
                data_root=root / "data",
                database_path=root / "asteria.db",
            )
        )

    def attach_papers(
        self,
        workbench: ResearchWorkbench,
        project_id: str,
        amount: int = 2,
    ) -> list[int]:
        ids: list[int] = []
        for index in range(amount):
            paper = Paper(
                paper_id=f"P{index + 1:03d}",
                title=f"Systems evaluation {index + 1}",
                abstract="We evaluate a computer system with public workloads.",
            )
            paper_id = workbench.database.upsert_paper(paper)
            workbench.database.attach_paper(
                project_id,
                paper_id,
                paper.paper_id,
            )
            ids.append(paper_id)
        return ids

    def include_title_candidates(
        self,
        workbench: ResearchWorkbench,
        project_id: str,
        paper_ids: list[int],
        reviewer: str = "human",
    ) -> None:
        for paper_id in paper_ids:
            workbench.record_screening(
                project_id=project_id,
                paper_id=paper_id,
                status="included",
                reason="Potentially eligible from title and abstract",
                reviewer=reviewer,
            )

    def test_fulltext_consensus_requires_same_exclusion_code(self) -> None:
        reviewers = ["alice", "bob"]
        same = evaluate_fulltext_consensus(
            {
                "alice": ("excluded", "wrong_study_design"),
                "bob": ("excluded", "wrong_study_design"),
            },
            reviewers,
        )
        self.assertEqual(same.state, "agreed")
        self.assertEqual(same.exclusion_code, "wrong_study_design")
        different = evaluate_fulltext_consensus(
            {
                "alice": ("excluded", "wrong_study_design"),
                "bob": ("excluded", "wrong_topic"),
            },
            reviewers,
        )
        self.assertEqual(different.state, "awaiting_resolution")
        self.assertEqual(different.status, "maybe")

    def test_single_fulltext_retrieval_decision_and_prisma_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workbench = self.make_workbench(root)
            project = workbench.create_project(
                name="Full text",
                topic="systems reproducibility",
            )
            paper_ids = self.attach_papers(workbench, project.id)
            self.include_title_candidates(workbench, project.id, paper_ids)
            config = workbench.database.configure_fulltext_screening(
                project.id,
                enabled=True,
            )
            self.assertTrue(config["fulltext_enabled"])
            self.assertFalse(config["fulltext_blind"])

            article = root / "paper.txt"
            article.write_text(
                "Methods\nWorkloads, baselines, and repeated trials.",
                encoding="utf-8",
            )
            workbench.documents.ingest(
                project_id=project.id,
                source=article,
                paper_id=paper_ids[0],
            )
            self.assertEqual(
                workbench.database.prisma_flow(project.id)[
                    "reports_assessed_for_eligibility"
                ],
                0,
            )
            retrieved = workbench.database.list_project_papers(project.id)[0]
            self.assertEqual(retrieved["retrieval_status"], "retrieved")
            workbench.database.record_fulltext_retrieval(
                project.id,
                paper_ids[1],
                status="not_retrieved",
                reason="Publisher copy and author manuscript unavailable",
                updated_by="librarian",
            )
            with self.assertRaises(ValueError):
                workbench.database.record_fulltext_screening(
                    FullTextDecision(
                        project_id=project.id,
                        paper_id=paper_ids[0],
                        status="excluded",
                        reason="Wrong design",
                        reviewer="reviewer",
                    )
                )
            workbench.database.record_fulltext_screening(
                FullTextDecision(
                    project_id=project.id,
                    paper_id=paper_ids[0],
                    status="excluded",
                    reason="The paper is a position paper without evaluation",
                    exclusion_code="not_primary_research",
                    reviewer="reviewer",
                )
            )

            self.assertTrue(
                workbench.database.fulltext_screening_gate(project.id)["ready"]
            )
            flow = workbench.database.prisma_flow(project.id)
            self.assertEqual(flow["reports_sought_for_retrieval"], 2)
            self.assertEqual(flow["reports_not_retrieved"], 1)
            self.assertEqual(flow["reports_assessed_for_eligibility"], 1)
            self.assertEqual(flow["reports_excluded_after_fulltext"], 1)
            self.assertEqual(
                flow["fulltext_exclusion_reasons"],
                {"not_primary_research": 1},
            )
            self.assertEqual(flow["studies_included_in_synthesis"], 0)

    def test_dual_fulltext_blinding_and_reason_conflict_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workbench = self.make_workbench(root)
            project = workbench.create_project(
                name="Dual full text",
                topic="distributed systems",
            )
            paper_id = self.attach_papers(workbench, project.id, 1)[0]
            workbench.configure_screening(
                project.id,
                mode="dual",
                reviewers=["alice", "bob"],
                blind=True,
            )
            for reviewer in ("alice", "bob"):
                workbench.record_screening(
                    project_id=project.id,
                    paper_id=paper_id,
                    status="included",
                    reason="Potentially eligible",
                    reviewer=reviewer,
                )
            workbench.configure_screening(
                project.id,
                mode="dual",
                reviewers=["alice", "bob"],
                blind=False,
            )
            workbench.database.configure_fulltext_screening(
                project.id,
                enabled=True,
                blind=True,
            )
            article = root / "paper.txt"
            article.write_text(
                "Full experimental report with system evaluation.",
                encoding="utf-8",
            )
            workbench.documents.ingest(
                project_id=project.id,
                source=article,
                paper_id=paper_id,
            )
            workbench.database.record_fulltext_screening(
                FullTextDecision(
                    project_id=project.id,
                    paper_id=paper_id,
                    status="excluded",
                    reason="No primary experiment",
                    exclusion_code="not_primary_research",
                    reviewer="alice",
                )
            )
            bob = workbench.database.fulltext_screening_workspace(
                project.id,
                reviewer_id="bob",
            )
            self.assertIsNone(bob["papers"][0]["my_decision"])
            self.assertNotIn("No primary experiment", str(bob))
            workbench.database.record_fulltext_screening(
                FullTextDecision(
                    project_id=project.id,
                    paper_id=paper_id,
                    status="excluded",
                    reason="The system is outside the review topic",
                    exclusion_code="wrong_topic",
                    reviewer="bob",
                )
            )
            self.assertEqual(
                workbench.database.list_project_papers(project.id)[0][
                    "fulltext_status"
                ],
                "pending",
            )
            workbench.database.configure_fulltext_screening(
                project.id,
                enabled=True,
                blind=False,
            )
            opened = workbench.database.fulltext_screening_workspace(project.id)
            self.assertEqual(
                opened["papers"][0]["consensus_state"],
                "awaiting_resolution",
            )
            self.assertFalse(
                workbench.database.fulltext_screening_gate(project.id)["ready"]
            )
            workbench.database.resolve_fulltext_screening(
                project.id,
                paper_id,
                status="excluded",
                reason="Discussion confirmed that this is not primary research",
                exclusion_code="not_primary_research",
                resolved_by="carol",
            )
            self.assertTrue(
                workbench.database.fulltext_screening_gate(project.id)["ready"]
            )
            audit = workbench.database.screening_audit(project.id)
            self.assertEqual(len(audit["fulltext"]["decision_events"]), 2)
            self.assertEqual(len(audit["fulltext"]["resolution_events"]), 1)

    def test_fulltext_cannot_start_before_title_screening_finishes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workbench = self.make_workbench(Path(temp))
            project = workbench.create_project(name="Gate", topic="CS")
            self.attach_papers(workbench, project.id, 1)
            with self.assertRaises(DatabaseError):
                workbench.database.configure_fulltext_screening(
                    project.id,
                    enabled=True,
                )

    def test_title_revision_invalidates_current_fulltext_but_keeps_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workbench = self.make_workbench(root)
            project = workbench.create_project(name="Revision", topic="CS")
            paper_id = self.attach_papers(workbench, project.id, 1)[0]
            self.include_title_candidates(workbench, project.id, [paper_id])
            workbench.database.configure_fulltext_screening(
                project.id,
                enabled=True,
            )
            article = root / "paper.txt"
            article.write_text("A complete experimental report.", encoding="utf-8")
            workbench.documents.ingest(
                project_id=project.id,
                source=article,
                paper_id=paper_id,
            )
            workbench.database.record_fulltext_screening(
                FullTextDecision(
                    project_id=project.id,
                    paper_id=paper_id,
                    status="included",
                    reason="Eligible complete report",
                    reviewer="human",
                )
            )

            workbench.record_screening(
                project_id=project.id,
                paper_id=paper_id,
                status="excluded",
                reason="Correction: duplicate record",
                reviewer="human",
            )

            paper = workbench.database.list_project_papers(project.id)[0]
            self.assertEqual(paper["fulltext_status"], "pending")
            self.assertEqual(paper["retrieval_status"], "retrieved")
            audit = workbench.database.screening_audit(project.id)
            self.assertEqual(audit["fulltext"]["decisions"], [])
            self.assertEqual(len(audit["fulltext"]["decision_events"]), 1)
            with self.assertRaises(DatabaseError):
                workbench.configure_screening(
                    project.id,
                    mode="dual",
                    reviewers=["alice", "bob"],
                    blind=True,
                )

    def test_schema_four_tables_receive_fulltext_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database_path = Path(temp) / "schema-four.db"
            legacy_connection = sqlite3.connect(database_path)
            try:
                connection = legacy_connection
                connection.executescript(
                    """
                    CREATE TABLE schema_meta (version INTEGER NOT NULL);
                    INSERT INTO schema_meta(version) VALUES (4);
                    CREATE TABLE project_papers (
                        project_id TEXT NOT NULL,
                        paper_id INTEGER NOT NULL,
                        evidence_id TEXT NOT NULL,
                        screening_status TEXT NOT NULL DEFAULT 'pending',
                        screening_reason TEXT NOT NULL DEFAULT '',
                        reviewer TEXT NOT NULL DEFAULT '',
                        tags_json TEXT NOT NULL DEFAULT '[]',
                        added_at TEXT NOT NULL,
                        decided_at TEXT NOT NULL DEFAULT '',
                        PRIMARY KEY (project_id, paper_id),
                        UNIQUE (project_id, evidence_id)
                    );
                    CREATE TABLE screening_configs (
                        project_id TEXT PRIMARY KEY,
                        mode TEXT NOT NULL DEFAULT 'single',
                        blind INTEGER NOT NULL DEFAULT 0,
                        reviewers_json TEXT NOT NULL DEFAULT '[]',
                        updated_at TEXT NOT NULL
                    );
                    """
                )
                connection.commit()
            finally:
                legacy_connection.close()

            database = Database(database_path)
            with database.connection() as connection:
                project_columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(project_papers)"
                    ).fetchall()
                }
                config_columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(screening_configs)"
                    ).fetchall()
                }
                version = connection.execute(
                    "SELECT version FROM schema_meta"
                ).fetchone()["version"]
            self.assertEqual(version, 6)
            self.assertIn("retrieval_status", project_columns)
            self.assertIn("fulltext_exclusion_code", project_columns)
            self.assertIn("fulltext_enabled", config_columns)
            self.assertIn("fulltext_blind", config_columns)


if __name__ == "__main__":
    unittest.main()
