from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from zipfile import ZipFile

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover - API extra is optional
    TestClient = None

from paper_agent.api import create_app
from paper_agent.config import Settings


@unittest.skipIf(TestClient is None, "API test dependencies are not installed")
class ApiWebTests(unittest.TestCase):
    def make_settings(self, root: Path) -> Settings:
        return Settings(
            output_root=root / "runs",
            data_root=root / "data",
            database_path=root / "workbench.db",
            max_papers=5,
            max_queries=3,
            results_per_query=5,
            max_upload_mb=1,
        )

    def wait_for_job(self, client: TestClient, job_id: str) -> dict:
        for _ in range(100):
            payload = client.get(f"/jobs/{job_id}").json()
            if payload["status"] in {"completed", "failed", "cancelled"}:
                return payload
            time.sleep(0.03)
        self.fail(f"Job did not finish: {job_id}")

    def test_web_demo_research_and_artifact_api(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = create_app(self.make_settings(root))
            with TestClient(app) as client:
                health = client.get("/health").json()
                self.assertEqual(health["version"], "0.10.0")
                self.assertTrue(health["web_available"])
                self.assertEqual(client.get("/").status_code, 200)
                self.assertIn("Asteria", client.get("/app").text)
                self.assertEqual(client.get("/asteria-mark.svg").status_code, 200)
                self.assertIn(
                    "three connected evidence nodes",
                    client.get("/asteria-mark.svg").text,
                )

                capabilities = client.get("/capabilities").json()
                self.assertNotIn("database", capabilities)
                self.assertEqual(capabilities["max_upload_mb"], 1)
                agents = client.get("/agents").json()
                self.assertIn("project_qa", {agent["id"] for agent in agents})

                connection = client.post(
                    "/connections",
                    json={
                        "name": "Test compatible API",
                        "base_url": "http://127.0.0.1:9999/v1",
                        "model": "test-model",
                        "api_format": "chat_completions",
                        "api_key": "must-never-leak",
                    },
                )
                self.assertEqual(connection.status_code, 201)
                connection_id = connection.json()["id"]
                self.assertNotIn("api_key", connection.json())
                self.assertNotIn(
                    "must-never-leak",
                    client.get("/connections").text,
                )

                project_response = client.post(
                    "/projects",
                    json={
                        "name": "Web smoke",
                        "topic": "research agent systems",
                        "research_question": "How are research agents evaluated?",
                        "review_type": "systematic",
                        "language": "zh-CN",
                    },
                )
                self.assertEqual(project_response.status_code, 201)
                project_id = project_response.json()["id"]

                start = client.post(
                    f"/projects/{project_id}/runs",
                    json={"demo": True},
                ).json()
                job = self.wait_for_job(client, start["job_id"])
                self.assertEqual(job["status"], "completed")
                run_id = start["run_id"]
                run = client.get(f"/runs/{run_id}").json()
                self.assertEqual(run["status"], "waiting_for_screening")

                papers = client.get(f"/projects/{project_id}/papers").json()
                self.assertEqual(len(papers), 5)
                decisions = [
                    {
                        "paper_id": item["id"],
                        "status": "excluded" if index == 0 else "included",
                        "reason": "Web API test decision",
                        "reviewer": "api-test",
                    }
                    for index, item in enumerate(papers)
                ]
                screening = client.post(
                    f"/projects/{project_id}/screening",
                    json={"decisions": decisions},
                )
                self.assertEqual(screening.json()["updated"], 5)

                continuation = client.post(f"/runs/{run_id}/continue?demo=true").json()
                continued_job = self.wait_for_job(client, continuation["job_id"])
                self.assertEqual(continued_job["status"], "completed")
                self.assertEqual(
                    client.get(f"/runs/{run_id}").json()["status"],
                    "completed",
                )

                research = client.get(f"/runs/{run_id}/research")
                self.assertEqual(research.status_code, 200)
                self.assertEqual(len(research.json()["evidence"]), 4)
                self.assertEqual(research.json()["search_log"]["schema_version"], 1)
                self.assertGreater(
                    research.json()["search_log"]["summary"][
                        "planned_executions"
                    ],
                    0,
                )
                self.assertTrue(client.get(f"/runs/{run_id}/report").json()["markdown"])
                self.assertIn("nodes", client.get(f"/runs/{run_id}/graph").json())
                artifact_names = {
                    item["name"]
                    for item in client.get(f"/runs/{run_id}/artifacts").json()
                }
                self.assertIn("cs_evidence_matrix.csv", artifact_names)
                self.assertIn("citation_grounding.json", artifact_names)
                self.assertIn("search_log.json", artifact_names)
                self.assertIn("report.md", artifact_names)

                conversation = client.post(
                    f"/projects/{project_id}/conversations",
                    json={
                        "title": "Evidence Q&A",
                        "agent_id": "project_qa",
                        "demo": True,
                    },
                )
                self.assertEqual(conversation.status_code, 201)
                conversation_id = conversation.json()["id"]
                answer = client.post(
                    f"/conversations/{conversation_id}/messages",
                    json={
                        "content": "这些论文主要研究什么？",
                        "demo": True,
                    },
                )
                self.assertEqual(answer.status_code, 201)
                self.assertTrue(answer.json()["assistant_message"]["sources"])
                saved_chat = client.get(f"/conversations/{conversation_id}").json()
                self.assertEqual(len(saved_chat["messages"]), 2)
                self.assertNotIn("sources_json", saved_chat["messages"][1])

                archive_response = client.get(f"/projects/{project_id}/export")
                self.assertEqual(archive_response.status_code, 200)
                archive_path = root / "export.zip"
                archive_path.write_bytes(archive_response.content)
                with ZipFile(archive_path) as archive:
                    self.assertIn("screening_audit.json", archive.namelist())
                    self.assertTrue(
                        any(
                            name.endswith("cs_evidence_matrix.csv")
                            for name in archive.namelist()
                        )
                    )
                self.assertEqual(
                    client.delete(f"/connections/{connection_id}").status_code,
                    200,
                )

    def test_document_routes_are_safe_and_search_is_not_shadowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = create_app(self.make_settings(root))
            with TestClient(app) as client:
                project_id = client.post(
                    "/projects",
                    json={
                        "name": "Documents",
                        "topic": "systems",
                        "research_question": "How is tail latency measured?",
                    },
                ).json()["id"]
                upload = client.post(
                    f"/projects/{project_id}/documents",
                    files={
                        "file": (
                            "paper.txt",
                            b"Tail latency evaluation uses p99 measurements.",
                            "text/plain",
                        )
                    },
                )
                self.assertEqual(upload.status_code, 201)
                self.assertEqual(upload.json()["filename"], "paper.txt")
                self.assertNotIn("source_path", upload.json())
                self.assertNotIn("text_path", upload.json())

                documents = client.get(f"/projects/{project_id}/documents").json()
                self.assertEqual(len(documents), 1)
                self.assertNotIn("source_path", documents[0])

                search = client.get(
                    f"/projects/{project_id}/documents/search",
                    params={"q": "tail latency"},
                )
                self.assertEqual(search.status_code, 200)
                self.assertTrue(search.json())

                oversized = client.post(
                    f"/projects/{project_id}/documents",
                    files={
                        "file": (
                            "large.txt",
                            b"x" * (1024 * 1024 + 1),
                            "text/plain",
                        )
                    },
                )
                self.assertEqual(oversized.status_code, 413)

    def test_bibliography_import_is_safe_idempotent_and_visible(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = create_app(self.make_settings(root))
            with TestClient(app) as client:
                project_id = client.post(
                    "/projects",
                    json={
                        "name": "Bibliography",
                        "topic": "research agents",
                        "research_question": "How are agents evaluated?",
                    },
                ).json()["id"]
                ris = b"""TY  - JOUR
TI  - Agent Evaluation Protocols
AU  - Doe, Jane
PY  - 2025
DO  - 10.5555/eval
ER  -
TY  - CONF
TI  - Citation Auditing Systems
AU  - Chen, Lin
PY  - 2024
DO  - 10.5555/audit
ER  -
"""
                imported = client.post(
                    f"/projects/{project_id}/bibliography",
                    files={
                        "file": (
                            "zotero-export.ris",
                            ris,
                            "application/x-research-info-systems",
                        )
                    },
                )
                self.assertEqual(imported.status_code, 201)
                self.assertEqual(imported.json()["filename"], "zotero-export.ris")
                self.assertEqual(imported.json()["added"], 2)
                self.assertEqual(imported.json()["evidence_ids"], ["P001", "P002"])
                self.assertEqual(
                    len(client.get(f"/projects/{project_id}/papers").json()),
                    2,
                )

                repeated = client.post(
                    f"/projects/{project_id}/bibliography",
                    files={
                        "file": (
                            "zotero-export.ris",
                            ris,
                            "application/x-research-info-systems",
                        )
                    },
                )
                self.assertEqual(repeated.json()["added"], 0)
                self.assertEqual(repeated.json()["already_present"], 2)

                unsupported = client.post(
                    f"/projects/{project_id}/bibliography",
                    files={"file": ("references.txt", b"data", "text/plain")},
                )
                self.assertEqual(unsupported.status_code, 415)
                malformed = client.post(
                    f"/projects/{project_id}/bibliography",
                    files={"file": ("references.json", b"{", "application/json")},
                )
                self.assertEqual(malformed.status_code, 422)

                oversized = client.post(
                    f"/projects/{project_id}/bibliography",
                    files={
                        "file": (
                            "oversized.ris",
                            b"x" * (1024 * 1024 + 1),
                            "application/x-research-info-systems",
                        )
                    },
                )
                self.assertEqual(oversized.status_code, 413)

    def test_dual_screening_api_keeps_blind_decisions_private(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = create_app(self.make_settings(root))
            with TestClient(app) as client:
                project_id = client.post(
                    "/projects",
                    json={
                        "name": "Independent screening",
                        "topic": "software engineering evidence",
                    },
                ).json()["id"]
                bibliography = b"""TY  - CONF
TI  - Reproducible Software Experiments
AU  - Doe, Jane
PY  - 2025
ER  -
"""
                imported = client.post(
                    f"/projects/{project_id}/bibliography",
                    files={
                        "file": (
                            "screening.ris",
                            bibliography,
                            "application/x-research-info-systems",
                        )
                    },
                )
                self.assertEqual(imported.status_code, 201)
                paper_id = client.get(f"/projects/{project_id}/papers").json()[0]["id"]
                config_url = f"/projects/{project_id}/screening/config"
                screening_url = f"/projects/{project_id}/screening"

                configured = client.put(
                    config_url,
                    json={
                        "mode": "dual",
                        "reviewers": ["alice", "bob"],
                        "blind": True,
                    },
                )
                self.assertEqual(configured.status_code, 200)
                decided = client.post(
                    screening_url,
                    json={
                        "decisions": [
                            {
                                "paper_id": paper_id,
                                "status": "included",
                                "reason": "Alice private rationale",
                                "reviewer": "alice",
                            }
                        ]
                    },
                )
                self.assertEqual(decided.status_code, 200)

                bob_workspace = client.get(
                    f"/projects/{project_id}/screening/workspace",
                    params={"reviewer": "bob"},
                )
                self.assertEqual(bob_workspace.status_code, 200)
                self.assertNotIn("Alice private rationale", bob_workspace.text)
                self.assertEqual(
                    bob_workspace.json()["papers"][0]["consensus_state"],
                    "blinded",
                )
                early_open = client.put(
                    config_url,
                    json={
                        "mode": "dual",
                        "reviewers": ["alice", "bob"],
                        "blind": False,
                    },
                )
                self.assertEqual(early_open.status_code, 409)

                bob_decision = client.post(
                    screening_url,
                    json={
                        "decisions": [
                            {
                                "paper_id": paper_id,
                                "status": "excluded",
                                "reason": "Bob private rationale",
                                "reviewer": "bob",
                            }
                        ]
                    },
                )
                self.assertEqual(bob_decision.status_code, 200)
                generic_papers = client.get(f"/projects/{project_id}/papers")
                self.assertNotIn("Alice private rationale", generic_papers.text)
                self.assertNotIn("Bob private rationale", generic_papers.text)
                self.assertEqual(
                    generic_papers.json()[0]["screening_status"],
                    "pending",
                )
                opened = client.put(
                    config_url,
                    json={
                        "mode": "dual",
                        "reviewers": ["alice", "bob"],
                        "blind": False,
                    },
                )
                self.assertEqual(opened.status_code, 200)
                workspace = client.get(
                    f"/projects/{project_id}/screening/workspace"
                ).json()
                self.assertEqual(workspace["summary"]["conflict"], 1)
                resolution = client.post(
                    f"/projects/{project_id}/screening/{paper_id}/resolve",
                    json={
                        "status": "included",
                        "reason": "Resolved after discussion",
                        "resolved_by": "carol",
                    },
                )
                self.assertEqual(resolution.status_code, 200)

    def test_fulltext_screening_api_and_prisma_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = create_app(self.make_settings(root))
            with TestClient(app) as client:
                project_id = client.post(
                    "/projects",
                    json={
                        "name": "Full-text API",
                        "topic": "systems evaluation",
                    },
                ).json()["id"]
                bibliography = b"""TY  - CONF
TI  - A Systems Position Paper
AU  - Doe, Jane
PY  - 2025
ER  -
"""
                self.assertEqual(
                    client.post(
                        f"/projects/{project_id}/bibliography",
                        files={
                            "file": (
                                "fulltext.ris",
                                bibliography,
                                "application/x-research-info-systems",
                            )
                        },
                    ).status_code,
                    201,
                )
                paper_id = client.get(f"/projects/{project_id}/papers").json()[0]["id"]
                self.assertEqual(
                    client.post(
                        f"/projects/{project_id}/screening",
                        json={
                            "decisions": [
                                {
                                    "paper_id": paper_id,
                                    "status": "included",
                                    "reason": "Potentially eligible",
                                    "reviewer": "alice",
                                }
                            ]
                        },
                    ).status_code,
                    200,
                )
                config = client.put(
                    f"/projects/{project_id}/screening/fulltext/config",
                    json={"enabled": True, "blind": False},
                )
                self.assertEqual(config.status_code, 200)
                upload = client.post(
                    f"/projects/{project_id}/documents",
                    params={"paper_id": paper_id},
                    files={
                        "file": (
                            "paper.txt",
                            b"Position paper without an empirical evaluation.",
                            "text/plain",
                        )
                    },
                )
                self.assertEqual(upload.status_code, 201)
                workspace = client.get(
                    f"/projects/{project_id}/screening/fulltext/workspace"
                )
                self.assertEqual(workspace.status_code, 200)
                self.assertEqual(
                    workspace.json()["papers"][0]["retrieval_status"],
                    "retrieved",
                )
                invalid = client.post(
                    f"/projects/{project_id}/screening/fulltext",
                    json={
                        "decisions": [
                            {
                                "paper_id": paper_id,
                                "status": "excluded",
                                "reason": "No evaluation",
                                "reviewer": "alice",
                            }
                        ]
                    },
                )
                self.assertEqual(invalid.status_code, 422)
                decided = client.post(
                    f"/projects/{project_id}/screening/fulltext",
                    json={
                        "decisions": [
                            {
                                "paper_id": paper_id,
                                "status": "excluded",
                                "reason": "No empirical evaluation",
                                "exclusion_code": "not_primary_research",
                                "reviewer": "alice",
                            }
                        ]
                    },
                )
                self.assertEqual(decided.status_code, 200)
                flow = client.get(f"/projects/{project_id}/prisma").json()
                self.assertEqual(flow["reports_assessed_for_eligibility"], 1)
                self.assertEqual(flow["reports_excluded_after_fulltext"], 1)
                archive = client.get(f"/projects/{project_id}/export")
                archive_path = root / "fulltext-export.zip"
                archive_path.write_bytes(archive.content)
                with ZipFile(archive_path) as exported:
                    self.assertIn("prisma_flow.json", exported.namelist())


if __name__ == "__main__":
    unittest.main()
