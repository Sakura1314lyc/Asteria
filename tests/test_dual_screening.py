from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from paper_agent.config import Settings
from paper_agent.database import Database, DatabaseError
from paper_agent.domain import ScreeningDecision
from paper_agent.models import Paper
from paper_agent.screening import evaluate_consensus
from paper_agent.workbench import ResearchWorkbench


class DualScreeningTests(unittest.TestCase):
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
                title=f"Computer science study {index + 1}",
                abstract="A reproducible systems experiment.",
            )
            paper_id = workbench.database.upsert_paper(paper)
            workbench.database.attach_paper(
                project_id,
                paper_id,
                paper.paper_id,
            )
            ids.append(paper_id)
        return ids

    def test_consensus_state_machine(self) -> None:
        reviewers = ["alice", "bob"]
        self.assertEqual(
            evaluate_consensus({}, reviewers).state,
            "pending",
        )
        self.assertEqual(
            evaluate_consensus({"alice": "included"}, reviewers).state,
            "pending",
        )
        self.assertEqual(
            evaluate_consensus(
                {"alice": "included", "bob": "included"},
                reviewers,
            ).state,
            "agreed",
        )
        conflict = evaluate_consensus(
            {"alice": "included", "bob": "excluded"},
            reviewers,
        )
        self.assertEqual(conflict.state, "conflict")
        self.assertEqual(conflict.status, "maybe")
        self.assertTrue(conflict.conflict)
        self.assertEqual(
            evaluate_consensus(
                {"alice": "maybe", "bob": "included"},
                reviewers,
            ).state,
            "awaiting_resolution",
        )

    def test_legacy_decisions_are_preserved_when_dual_mode_is_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workbench = self.make_workbench(Path(temp))
            project = workbench.create_project(name="Review", topic="CS agents")
            paper_id = self.attach_papers(workbench, project.id, 1)[0]
            workbench.record_screening(
                project_id=project.id,
                paper_id=paper_id,
                status="included",
                reason="legacy reason",
                reviewer="legacy-user",
            )

            workbench.configure_screening(
                project.id,
                mode="dual",
                reviewers=["alice", "bob"],
                blind=True,
            )
            alice = workbench.screening_workspace(project.id, reviewer="alice")
            bob = workbench.screening_workspace(project.id, reviewer="bob")

            self.assertEqual(alice["papers"][0]["my_decision"]["status"], "included")
            self.assertEqual(
                alice["papers"][0]["my_decision"]["reason"],
                "legacy reason",
            )
            self.assertIsNone(bob["papers"][0]["my_decision"])
            self.assertEqual(bob["papers"][0]["screening_status"], "pending")

    def test_blind_review_conflict_resolution_and_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workbench = self.make_workbench(Path(temp))
            project = workbench.create_project(name="Review", topic="CS agents")
            paper_ids = self.attach_papers(workbench, project.id)
            workbench.configure_screening(
                project.id,
                mode="dual",
                reviewers=["alice", "bob"],
                blind=True,
            )

            for paper_id in paper_ids:
                workbench.record_screening(
                    project_id=project.id,
                    paper_id=paper_id,
                    status="included",
                    reason="Alice evidence",
                    reviewer="alice",
                )
            hidden = workbench.screening_workspace(project.id, reviewer="bob")
            self.assertEqual(hidden["summary"], {"total": 2, "reviewer_completed": 0})
            self.assertTrue(all(not paper["decisions"] for paper in hidden["papers"]))
            with self.assertRaises(DatabaseError):
                workbench.configure_screening(
                    project.id,
                    mode="dual",
                    reviewers=["alice", "bob"],
                    blind=False,
                )

            workbench.record_screening(
                project_id=project.id,
                paper_id=paper_ids[0],
                status="excluded",
                reason="Bob conflict",
                reviewer="bob",
            )
            workbench.record_screening(
                project_id=project.id,
                paper_id=paper_ids[1],
                status="included",
                reason="Bob agrees",
                reviewer="bob",
            )
            hidden_final_rows = workbench.database.list_project_papers(project.id)
            self.assertTrue(
                all(
                    row["screening_status"] == "pending" and not row["screening_reason"]
                    for row in hidden_final_rows
                )
            )
            self.assertEqual(
                workbench.database.screening_gate(project.id),
                {
                    "ready": False,
                    "pending": 0,
                    "unresolved": 0,
                    "blind": True,
                },
            )
            workbench.configure_screening(
                project.id,
                mode="dual",
                reviewers=["alice", "bob"],
                blind=False,
            )
            open_workspace = workbench.screening_workspace(
                project.id,
                reviewer="alice",
            )
            self.assertEqual(open_workspace["summary"]["conflict"], 1)
            self.assertEqual(open_workspace["summary"]["agreed"], 1)
            self.assertEqual(
                open_workspace["papers"][0]["consensus_state"],
                "conflict",
            )
            self.assertFalse(workbench.database.screening_gate(project.id)["ready"])

            workbench.resolve_screening(
                project.id,
                paper_ids[0],
                status="included",
                reason="Consensus discussion accepted the study",
                resolved_by="carol",
            )
            self.assertTrue(workbench.database.screening_gate(project.id)["ready"])
            resolved = workbench.screening_workspace(project.id)
            self.assertEqual(resolved["summary"]["resolved"], 1)
            with self.assertRaises(DatabaseError):
                workbench.configure_screening(
                    project.id,
                    mode="dual",
                    reviewers=["alice", "bob"],
                    blind=True,
                )

            workbench.record_screening(
                project_id=project.id,
                paper_id=paper_ids[0],
                status="excluded",
                reason="Alice revised after full text",
                reviewer="alice",
            )
            revised = workbench.screening_workspace(project.id)
            self.assertEqual(revised["papers"][0]["consensus_state"], "agreed")
            self.assertIsNone(revised["papers"][0]["resolution"])
            self.assertEqual(
                revised["papers"][0]["screening_status"],
                "excluded",
            )

    def test_dual_reviewer_identity_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workbench = self.make_workbench(Path(temp))
            project = workbench.create_project(name="Review", topic="CS agents")
            paper_id = self.attach_papers(workbench, project.id, 1)[0]
            workbench.configure_screening(
                project.id,
                mode="dual",
                reviewers=["alice", "bob"],
            )
            with self.assertRaises(DatabaseError):
                workbench.record_screening(
                    project_id=project.id,
                    paper_id=paper_id,
                    status="included",
                    reviewer="mallory",
                )

    def test_screening_batch_rolls_back_as_one_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workbench = self.make_workbench(Path(temp))
            project = workbench.create_project(name="Review", topic="CS agents")
            paper_id = self.attach_papers(workbench, project.id, 1)[0]
            with self.assertRaises(DatabaseError):
                workbench.record_screening_batch(
                    project_id=project.id,
                    decisions=[
                        {
                            "paper_id": paper_id,
                            "status": "included",
                            "reason": "would otherwise persist",
                            "reviewer": "alice",
                        },
                        {
                            "paper_id": 999_999,
                            "status": "excluded",
                            "reason": "invalid paper",
                            "reviewer": "alice",
                        },
                    ],
                )
            row = workbench.database.list_project_papers(project.id)[0]
            self.assertEqual(row["screening_status"], "pending")
            self.assertEqual(
                workbench.database.screening_audit(project.id)["decisions"],
                [],
            )

    def test_schema_three_database_migrates_without_losing_legacy_decision(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database_path = Path(temp) / "legacy.db"
            database = Database(database_path)
            project = database.create_project(
                name="Legacy",
                topic="CS evidence",
                research_question="How is evidence assessed?",
            )
            paper = Paper(paper_id="P001", title="Legacy screened paper")
            paper_id = database.upsert_paper(paper)
            database.attach_paper(project.id, paper_id, "P001")
            database.record_screening(
                ScreeningDecision(
                    project_id=project.id,
                    paper_id=paper_id,
                    status="included",
                    reviewer="legacy-reviewer",
                )
            )
            with database.connection() as connection:
                connection.executescript(
                    """
                    DROP TABLE screening_resolution_events;
                    DROP TABLE screening_resolutions;
                    DROP TABLE screening_decision_events;
                    DROP TABLE screening_decisions;
                    DROP TABLE screening_configs;
                    UPDATE schema_meta SET version = 3;
                    """
                )

            migrated = Database(database_path)
            with migrated.connection() as connection:
                version = connection.execute(
                    "SELECT version FROM schema_meta"
                ).fetchone()["version"]
            self.assertEqual(version, 6)
            self.assertEqual(
                migrated.list_project_papers(project.id)[0]["screening_status"],
                "included",
            )
            self.assertEqual(
                migrated.get_screening_config(project.id)["mode"],
                "single",
            )

    def test_empty_dual_configuration_can_return_to_single_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workbench = self.make_workbench(Path(temp))
            project = workbench.create_project(name="Review", topic="CS agents")
            self.attach_papers(workbench, project.id, 1)
            workbench.configure_screening(
                project.id,
                mode="dual",
                reviewers=["alice", "bob"],
                blind=True,
            )
            config = workbench.configure_screening(
                project.id,
                mode="single",
            )
            self.assertEqual(config["mode"], "single")


if __name__ == "__main__":
    unittest.main()
