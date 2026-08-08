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
                self.assertEqual(health["version"], "0.14.1")
                self.assertTrue(health["web_available"])
                self.assertEqual(health["storage"], "sqlite")
                self.assertNotIn("database", health)
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
                edited_connection = client.put(
                    f"/connections/{connection_id}",
                    json={
                        "name": "Updated compatible API",
                        "base_url": "http://127.0.0.1:9998/v1",
                        "model": "updated-model",
                        "api_format": "chat_completions",
                        "api_key": "",
                    },
                )
                self.assertEqual(edited_connection.status_code, 200)
                self.assertEqual(edited_connection.json()["model"], "updated-model")
                self.assertEqual(
                    app.state.connections.resolve(connection_id).api_key,
                    "must-never-leak",
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
                self.assertTrue(job["result_available"])
                self.assertNotIn("result", job)
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
                deleted_chat = client.delete(
                    f"/conversations/{conversation_id}",
                    params={"confirmation": "Evidence Q&A"},
                )
                self.assertEqual(deleted_chat.status_code, 200)
                self.assertEqual(deleted_chat.json()["messages"], 2)
                self.assertEqual(
                    client.get(f"/conversations/{conversation_id}").status_code,
                    404,
                )
                completed_run = client.get(f"/runs/{run_id}").json()
                self.assertTrue(completed_run["artifacts_available"])
                self.assertNotIn("run_dir", completed_run)
                self.assertNotIn("data_root", client.get(f"/runs/{run_id}").text)
                self.assertNotIn(str(root), client.get("/projects").text)
                project_response = client.get(f"/projects/{project_id}")
                self.assertNotIn(str(root), project_response.text)
                self.assertNotIn('"path"', project_response.text)
                stored_run = app.state.workbench.database.get_run(run_id)
                self.assertIsNotNone(stored_run)
                completed_run_dir = Path(stored_run["run_dir"])
                self.assertTrue(completed_run_dir.is_dir())
                deleted_run = client.delete(
                    f"/runs/{run_id}",
                    params={"confirmation": run_id},
                )
                self.assertEqual(deleted_run.status_code, 200)
                self.assertFalse(completed_run_dir.exists())
                self.assertEqual(client.get(f"/runs/{run_id}").status_code, 404)
                paper_to_remove = client.get(f"/projects/{project_id}/papers").json()[0]
                removed_paper = client.delete(
                    f"/projects/{project_id}/papers/{paper_to_remove['id']}",
                    params={"confirmation": paper_to_remove["evidence_id"]},
                )
                self.assertEqual(removed_paper.status_code, 200)
                self.assertEqual(
                    len(client.get(f"/projects/{project_id}/papers").json()),
                    4,
                )
                self.assertEqual(
                    client.delete(f"/connections/{connection_id}").status_code,
                    200,
                )

    def test_project_update_and_confirmed_delete_clean_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = create_app(self.make_settings(root))
            with TestClient(app) as client:
                created = client.post(
                    "/projects",
                    json={
                        "name": "Lifecycle review",
                        "topic": "agent evaluation",
                        "research_question": "How are agents evaluated?",
                        "review_type": "narrative",
                        "language": "en",
                    },
                ).json()
                project_id = created["id"]

                empty_update = client.patch(f"/projects/{project_id}", json={})
                self.assertEqual(empty_update.status_code, 422)
                updated = client.patch(
                    f"/projects/{project_id}",
                    json={
                        "name": "Reproducible agent review",
                        "topic": "reproducible CS agents",
                        "research_question": "Which evaluations are reproducible?",
                        "review_type": "systematic",
                        "language": "zh-CN",
                    },
                )
                self.assertEqual(updated.status_code, 200)
                self.assertEqual(updated.json()["name"], "Reproducible agent review")
                self.assertEqual(updated.json()["protocol"]["review_type"], "systematic")
                project_detail = client.get(f"/projects/{project_id}").json()
                self.assertEqual(project_detail["events"][0]["event_type"], "metadata_updated")
                self.assertEqual(
                    project_detail["events"][0]["payload"]["changes"]["name"],
                    {
                        "before": "Lifecycle review",
                        "after": "Reproducible agent review",
                    },
                )

                missing_reason = client.put(
                    f"/projects/{project_id}/protocol",
                    json={**updated.json()["protocol"], "year_from": 2021},
                )
                self.assertEqual(missing_reason.status_code, 422)
                self.assertIn("reason", missing_reason.json()["detail"].lower())

                invalid_range = client.put(
                    f"/projects/{project_id}/protocol",
                    json={
                        **updated.json()["protocol"],
                        "year_from": 2025,
                        "year_to": 2020,
                        "amendment_reason": "Invalid range regression",
                    },
                )
                self.assertEqual(invalid_range.status_code, 422)

                invalid_year = client.put(
                    f"/projects/{project_id}/protocol",
                    json={
                        **updated.json()["protocol"],
                        "year_from": 1800,
                        "amendment_reason": "Invalid year regression",
                    },
                )
                self.assertEqual(invalid_year.status_code, 422)

                protocol_update = client.put(
                    f"/projects/{project_id}/protocol",
                    json={
                        **updated.json()["protocol"],
                        "year_from": 2021,
                        "include_keywords": ["agent", "evaluation"],
                        "amendment_reason": "Pilot search returned too many editorials",
                    },
                )
                self.assertEqual(protocol_update.status_code, 200)
                project_detail = client.get(f"/projects/{project_id}").json()
                protocol_event = project_detail["events"][0]
                self.assertEqual(protocol_event["event_type"], "protocol_updated")
                self.assertEqual(
                    protocol_event["payload"]["reason"],
                    "Pilot search returned too many editorials",
                )
                self.assertEqual(
                    protocol_event["payload"]["changes"]["year_from"],
                    {"before": None, "after": 2021},
                )

                upload = client.post(
                    f"/projects/{project_id}/documents",
                    files={
                        "file": (
                            "evidence.txt",
                            b"Reproducible evidence for lifecycle deletion.",
                            "text/plain",
                        )
                    },
                )
                self.assertEqual(upload.status_code, 201)
                project_root = root / "data" / project_id
                self.assertTrue(project_root.is_dir())
                wrong = client.delete(
                    f"/projects/{project_id}",
                    params={"confirmation": "Lifecycle review"},
                )
                self.assertEqual(wrong.status_code, 409)
                self.assertTrue(project_root.is_dir())

                deleted = client.delete(
                    f"/projects/{project_id}",
                    params={"confirmation": "Reproducible agent review"},
                )
                self.assertEqual(deleted.status_code, 200)
                self.assertTrue(deleted.json()["deleted"])
                self.assertEqual(deleted.json()["documents"], 1)
                self.assertFalse(project_root.exists())
                self.assertEqual(client.get(f"/projects/{project_id}").status_code, 404)
                with app.state.workbench.database.connection() as database:
                    fts_count = database.execute(
                        "SELECT COUNT(*) AS count FROM document_chunks_fts"
                    ).fetchone()["count"]
                self.assertEqual(fts_count, 0)

    def test_active_project_cannot_be_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app = create_app(self.make_settings(root))
            with TestClient(app) as client:
                project = app.state.workbench.create_project(
                    name="Active review",
                    topic="running agents",
                )
                run = app.state.workbench.create_run(project.id)
                blocked = client.delete(
                    f"/projects/{project.id}",
                    params={"confirmation": project.name},
                )
                self.assertEqual(blocked.status_code, 409)
                self.assertIn("active", blocked.json()["detail"])
                self.assertIsNotNone(app.state.workbench.database.get_run(run.id))

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
                stored_document = app.state.workbench.database.get_document(
                    project_id,
                    documents[0]["id"],
                )
                stored_root = Path(stored_document["source_path"]).parent
                self.assertTrue(stored_root.is_dir())

                search = client.get(
                    f"/projects/{project_id}/documents/search",
                    params={"q": "tail latency"},
                )
                self.assertEqual(search.status_code, 200)
                self.assertTrue(search.json())

                wrong_delete = client.delete(
                    f"/projects/{project_id}/documents/{documents[0]['id']}",
                    params={"confirmation": "wrong.txt"},
                )
                self.assertEqual(wrong_delete.status_code, 409)
                deleted_document = client.delete(
                    f"/projects/{project_id}/documents/{documents[0]['id']}",
                    params={"confirmation": "paper.txt"},
                )
                self.assertEqual(deleted_document.status_code, 200)
                self.assertFalse(stored_root.exists())
                self.assertEqual(
                    client.get(f"/projects/{project_id}/documents").json(),
                    [],
                )
                self.assertEqual(
                    client.get(
                        f"/projects/{project_id}/documents/search",
                        params={"q": "tail latency"},
                    ).json(),
                    [],
                )

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
