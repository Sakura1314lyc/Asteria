from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from paper_agent.config import Settings
from paper_agent.evaluation import evaluate_run
from paper_agent.exporter import export_project
from paper_agent.jobs import JobManager
from paper_agent.llm import DemoLLM
from paper_agent.plugins import RetrieverRegistry
from paper_agent.retrievers import FixtureRetriever
from paper_agent.workbench import ResearchWorkbench

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "demo_papers.json"


class EngineeringTests(unittest.TestCase):
    def make_workbench(self, root: Path) -> ResearchWorkbench:
        return ResearchWorkbench(
            Settings(
                data_root=root / "data",
                database_path=root / "data" / "workbench.db",
                output_root=root / "runs",
                max_papers=5,
                max_queries=3,
                results_per_query=5,
            )
        )

    def test_job_manager_tracks_result(self) -> None:
        manager = JobManager(max_workers=1)
        try:
            job = manager.submit("answer", lambda: 42)
            manager.futures[job.id].result(timeout=2)
            self.assertEqual(manager.get(job.id).status, "completed")
            self.assertEqual(manager.get(job.id).result, 42)
        finally:
            manager.shutdown()

    def test_builtin_plugins_are_discoverable(self) -> None:
        names = {item.name for item in RetrieverRegistry().discover().list()}
        self.assertTrue({"openalex", "arxiv", "semantic_scholar"} <= names)

    def test_evaluate_and_export_completed_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workbench = self.make_workbench(root)
            project = workbench.create_project(
                name="Exportable",
                topic="research agents",
            )
            run = workbench.create_run(project.id)
            run_dir = workbench.execute_run(
                run.id,
                llm=DemoLLM(project.topic),
                retrievers=[FixtureRetriever(FIXTURE)],
                stop_for_screening=False,
            )
            evaluation = evaluate_run(run_dir)
            self.assertGreaterEqual(evaluation.overall, 0.7)
            self.assertTrue((run_dir / "review_flow.json").exists())
            self.assertTrue((run_dir / "study_matrix.csv").exists())
            archive = export_project(
                workbench.database,
                project.id,
                root / "export.zip",
            )
            with ZipFile(archive) as package:
                names = set(package.namelist())
            self.assertIn("project.json", names)
            self.assertIn("manifest.json", names)
            self.assertTrue(any(name.endswith("/report.md") for name in names))


if __name__ == "__main__":
    unittest.main()
