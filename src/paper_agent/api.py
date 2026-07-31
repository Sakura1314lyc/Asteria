import json
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from .agent_profiles import get_agent_profile, list_agent_profiles
from .artifacts import load_state
from .bibliography import (
    SUPPORTED_BIBLIOGRAPHY_SUFFIXES,
    BibliographyError,
)
from .config import Settings
from .connections import ConnectionError, ConnectionRegistry
from .cs_taxonomy import CSTaxonomy
from .database import DatabaseError
from .domain import ReviewProtocol
from .exporter import export_project
from .jobs import JobManager
from .llm import DemoLLM, LLMError, OpenAIResponsesLLM
from .research_chat import answer_project_question
from .retrievers import bundled_demo_retriever
from .workbench import ResearchWorkbench, WorkbenchError

ARTIFACT_SUFFIXES = {
    ".bib",
    ".csv",
    ".graphml",
    ".json",
    ".jsonl",
    ".md",
}


def create_app(settings: Settings | None = None):
    try:
        from fastapi import FastAPI, File, HTTPException, Query, UploadFile
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import FileResponse, RedirectResponse
        from fastapi.staticfiles import StaticFiles
        from pydantic import BaseModel, Field
        from starlette.background import BackgroundTask
    except ImportError as exc:
        raise RuntimeError(
            "API dependencies are missing. Install with "
            "`pip install 'paper-research-agent[api]'`."
        ) from exc

    active_settings = settings or Settings.from_env()
    workbench = ResearchWorkbench(active_settings)
    jobs = JobManager(max_workers=2)
    connections = ConnectionRegistry(active_settings)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        jobs.shutdown(wait=False)

    app = FastAPI(
        title="Paper Research Agent API",
        version="0.8.0",
        description=(
            "Local-first API for literature discovery, screening, evidence "
            "extraction, quality appraisal, full-text search, and report generation."
        ),
        lifespan=lifespan,
    )
    app.state.workbench = workbench
    app.state.jobs = jobs
    app.state.connections = connections
    if active_settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(active_settings.cors_origins),
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    class ProjectCreate(BaseModel):
        name: str = Field(min_length=1, max_length=200)
        topic: str = Field(min_length=1, max_length=500)
        research_question: str = Field(default="", max_length=2000)
        review_type: str = "narrative"
        language: str = "zh-CN"

    class ProtocolUpdate(BaseModel):
        review_type: str = "systematic"
        population: list[str] = []
        intervention: list[str] = []
        comparison: list[str] = []
        outcomes: list[str] = []
        include_keywords: list[str] = []
        exclude_keywords: list[str] = []
        year_from: int | None = None
        year_to: int | None = None
        languages: list[str] = []
        study_types: list[str] = []
        notes: str = ""

    class RunCreate(BaseModel):
        demo: bool = False
        stop_for_screening: bool | None = None
        agent_id: str = "deep_review"
        connection_id: str | None = None

    class ConnectionCreate(BaseModel):
        name: str = Field(min_length=1, max_length=100)
        base_url: str = Field(min_length=8, max_length=500)
        model: str = Field(min_length=1, max_length=200)
        api_format: str = "responses"
        api_key: str = Field(min_length=1, max_length=1000)

    class ConversationCreate(BaseModel):
        title: str = Field(default="新对话", max_length=200)
        agent_id: str = "project_qa"
        connection_id: str | None = None
        demo: bool = False

    class MessageCreate(BaseModel):
        content: str = Field(min_length=1, max_length=20_000)
        agent_id: str | None = None
        connection_id: str | None = None
        demo: bool = False

    class ScreeningItem(BaseModel):
        paper_id: int
        status: str = Field(max_length=20)
        reason: str = Field(default="", max_length=4000)
        reviewer: str = Field(default="human", min_length=1, max_length=100)

    class ScreeningBatch(BaseModel):
        decisions: list[ScreeningItem] = Field(min_length=1, max_length=1000)

    class ScreeningConfigUpdate(BaseModel):
        mode: str = Field(default="single", max_length=20)
        reviewers: list[str] = Field(default_factory=list, max_length=2)
        blind: bool = False

    class ScreeningResolutionRequest(BaseModel):
        status: str = Field(max_length=20)
        reason: str = Field(min_length=1, max_length=4000)
        resolved_by: str = Field(min_length=1, max_length=100)

    class FullTextConfigUpdate(BaseModel):
        enabled: bool = True
        blind: bool = True

    class FullTextRetrievalRequest(BaseModel):
        status: str = Field(max_length=30)
        reason: str = Field(default="", max_length=4000)
        updated_by: str = Field(default="human", min_length=1, max_length=100)

    class FullTextScreeningItem(BaseModel):
        paper_id: int
        status: str = Field(max_length=20)
        reason: str = Field(default="", max_length=4000)
        exclusion_code: str = Field(default="", max_length=100)
        reviewer: str = Field(default="human", min_length=1, max_length=100)

    class FullTextScreeningBatch(BaseModel):
        decisions: list[FullTextScreeningItem] = Field(
            min_length=1,
            max_length=1000,
        )

    class FullTextResolutionRequest(BaseModel):
        status: str = Field(max_length=20)
        reason: str = Field(min_length=1, max_length=4000)
        exclusion_code: str = Field(default="", max_length=100)
        resolved_by: str = Field(min_length=1, max_length=100)

    class ClassificationRequest(BaseModel):
        text: str = Field(min_length=2, max_length=5000)
        limit: int = Field(default=3, ge=1, le=10)

    upload_file_parameter = File(...)
    bibliography_file_parameter = File(...)

    def project_or_404(project_id: str):
        project = workbench.database.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    def run_or_404(run_id: str):
        run = workbench.database.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return run

    def run_directory(run_id: str) -> tuple[dict[str, Any], Path]:
        run = run_or_404(run_id)
        if not run["run_dir"]:
            raise HTTPException(status_code=409, detail="Run has no artifacts yet")
        run_dir = Path(run["run_dir"]).resolve()
        if not run_dir.is_dir():
            raise HTTPException(status_code=410, detail="Run artifacts are missing")
        data_root = active_settings.data_root.resolve()
        if not run_dir.is_relative_to(data_root):
            raise HTTPException(
                status_code=403, detail="Run directory is outside data root"
            )
        return run, run_dir

    def public_document(document: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in document.items()
            if key not in {"source_path", "text_path"}
        }

    def document_or_404(project_id: str, document_id: str) -> dict[str, Any]:
        project_or_404(project_id)
        document = workbench.database.get_document(project_id, document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return document

    def make_llm(
        demo: bool,
        topic: str,
        connection_id: str | None = None,
    ):
        try:
            if demo:
                return DemoLLM(topic)
            connection = connections.resolve(connection_id)
            return OpenAIResponsesLLM(
                connections.llm_settings(connection),
                api_key=connection.api_key,
                api_format=connection.api_format,
                structured_output=connection.structured_output,
            )
        except (ConnectionError, LLMError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def conversation_or_404(conversation_id: str) -> dict[str, Any]:
        conversation = workbench.database.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation

    @app.get("/health")
    def health() -> dict[str, Any]:
        configured_web = (
            active_settings.web_dist.resolve()
            if active_settings.web_dist
            else Path(__file__).parent / "web_dist"
        )
        return {
            "status": "ok",
            "version": "0.8.0",
            "database": str(active_settings.database_path),
            "specialization": "computer_science",
            "web_available": (configured_web / "index.html").is_file(),
        }

    @app.get("/capabilities")
    def capabilities() -> dict[str, Any]:
        return {
            "mode": "local-first",
            "model": active_settings.model,
            "language": active_settings.language,
            "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
            "semantic_scholar_configured": bool(os.getenv("S2_API_KEY")),
            "retrievers": {
                "openalex": True,
                "arxiv": True,
                "dblp": active_settings.dblp_enabled,
                "semantic_scholar": bool(os.getenv("S2_API_KEY")),
                "local_documents": True,
            },
            "review_types": ["narrative", "scoping", "systematic", "thesis"],
            "max_upload_mb": active_settings.max_upload_mb,
            "authentication": False,
            "session_credentials": True,
        }

    @app.get("/agents")
    def list_agents() -> list[dict[str, object]]:
        return list_agent_profiles()

    @app.get("/connections")
    def list_connections() -> list[dict[str, object]]:
        return connections.list()

    @app.post("/connections", status_code=201)
    def create_connection(payload: ConnectionCreate) -> dict[str, object]:
        try:
            return connections.create(**payload.model_dump())
        except ConnectionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete("/connections/{connection_id}")
    def delete_connection(connection_id: str) -> dict[str, bool]:
        try:
            connections.delete(connection_id)
        except ConnectionError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"deleted": True}

    @app.post("/connections/{connection_id}/test")
    def test_connection(connection_id: str) -> dict[str, Any]:
        llm = make_llm(False, "", connection_id)
        try:
            output = llm.text(
                instructions="Return exactly the word OK.",
                user_input="Connection test",
            )
        except LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        connection = connections.resolve(connection_id)
        return {
            "ok": bool(output),
            "model": connection.model,
            "api_format": connection.api_format,
        }

    @app.get("/taxonomy")
    def get_taxonomy() -> dict[str, Any]:
        taxonomy = CSTaxonomy.load()
        return {
            "version": taxonomy.version,
            "sources": taxonomy.sources,
            "domains": [
                {
                    "id": domain.id,
                    "name_en": domain.name_en,
                    "name_zh": domain.name_zh,
                    "arxiv_categories": list(domain.arxiv_categories),
                    "evidence_profile": domain.evidence_profile,
                }
                for domain in taxonomy.domains
            ],
        }

    @app.post("/taxonomy/classify")
    def classify_topic(payload: ClassificationRequest) -> list[dict[str, Any]]:
        return [
            item.to_dict()
            for item in CSTaxonomy.load().classify_text(
                payload.text,
                limit=payload.limit,
            )
        ]

    @app.post("/projects", status_code=201)
    def create_project(payload: ProjectCreate) -> dict[str, Any]:
        try:
            project = workbench.create_project(**payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return project.to_dict()

    @app.get("/projects")
    def list_projects() -> list[dict[str, Any]]:
        return [
            {
                **project.to_dict(),
                "stats": workbench.database.project_stats(project.id),
                "runs": workbench.database.list_runs(project.id)[:1],
            }
            for project in workbench.database.list_projects()
        ]

    @app.get("/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        project = project_or_404(project_id)
        return {
            **project.to_dict(),
            "stats": workbench.database.project_stats(project.id),
            "runs": workbench.database.list_runs(project.id),
            "reports": workbench.database.list_reports(project.id),
            "documents": [
                public_document(document)
                for document in workbench.database.list_documents(project.id)
            ],
        }

    @app.put("/projects/{project_id}/protocol")
    def update_protocol(
        project_id: str,
        payload: ProtocolUpdate,
    ) -> dict[str, Any]:
        project_or_404(project_id)
        try:
            protocol = ReviewProtocol.from_dict(payload.model_dump())
            return workbench.database.update_protocol(
                project_id,
                protocol,
            ).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/projects/{project_id}/runs", status_code=202)
    def start_run(project_id: str, payload: RunCreate) -> dict[str, Any]:
        project = project_or_404(project_id)
        try:
            agent = get_agent_profile(payload.agent_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        llm = make_llm(payload.demo, project.topic, payload.connection_id)
        connection_meta = {
            "id": "demo" if payload.demo else (payload.connection_id or "env-openai"),
            "name": "离线演示"
            if payload.demo
            else connections.resolve(payload.connection_id).name,
            "model": "demo"
            if payload.demo
            else connections.resolve(payload.connection_id).model,
        }
        run = workbench.create_run(
            project_id,
            agent_id=agent.id,
            connection=connection_meta,
        )
        retrievers = [bundled_demo_retriever()] if payload.demo else None
        job = jobs.submit(
            f"research:{run.id}",
            lambda: workbench.execute_run(
                run.id,
                llm=llm,
                retrievers=retrievers,
                stop_for_screening=payload.stop_for_screening,
                agent_id=agent.id,
            ),
        )
        return {"run_id": run.id, "job_id": job.id, "status": "queued"}

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        return run_or_404(run_id)

    @app.get("/runs/{run_id}/cs-analysis")
    def get_cs_analysis(run_id: str) -> dict[str, Any]:
        _, run_dir = run_directory(run_id)
        return load_state(run_dir).cs_analysis

    @app.get("/runs/{run_id}/research")
    def get_research(run_id: str) -> dict[str, Any]:
        run, run_dir = run_directory(run_id)
        state = load_state(run_dir)
        return {
            "run": run,
            "topic": state.topic,
            "question": state.question,
            "stage": state.stage,
            "plan": state.plan,
            "papers": [paper.to_dict() for paper in state.papers],
            "screening": state.screening,
            "evidence": [card.to_dict() for card in state.evidence],
            "quality": state.quality,
            "cs_analysis": state.cs_analysis,
            "audit": state.audit,
            "warnings": state.warnings,
        }

    @app.get("/runs/{run_id}/report")
    def get_report(run_id: str) -> dict[str, Any]:
        _, run_dir = run_directory(run_id)
        state = load_state(run_dir)
        if not state.report:
            raise HTTPException(status_code=409, detail="Report is not available yet")
        return {
            "run_id": run_id,
            "topic": state.topic,
            "question": state.question,
            "markdown": state.report,
            "audit": state.audit,
            "updated_at": state.updated_at,
        }

    @app.get("/runs/{run_id}/graph")
    def get_graph(run_id: str) -> dict[str, Any]:
        _, run_dir = run_directory(run_id)
        graph_path = run_dir / "literature_graph.json"
        if not graph_path.is_file():
            raise HTTPException(status_code=409, detail="Graph is not available yet")
        return json.loads(graph_path.read_text(encoding="utf-8"))

    @app.get("/runs/{run_id}/artifacts")
    def list_artifacts(run_id: str) -> list[dict[str, Any]]:
        _, run_dir = run_directory(run_id)
        return [
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "modified_at": path.stat().st_mtime,
                "url": f"/runs/{run_id}/artifacts/{path.name}",
            }
            for path in sorted(run_dir.iterdir(), key=lambda item: item.name)
            if path.is_file() and path.suffix.lower() in ARTIFACT_SUFFIXES
        ]

    @app.get("/runs/{run_id}/artifacts/{artifact_name}")
    def download_artifact(run_id: str, artifact_name: str):
        _, run_dir = run_directory(run_id)
        if Path(artifact_name).name != artifact_name:
            raise HTTPException(status_code=400, detail="Invalid artifact name")
        artifact = run_dir / artifact_name
        if artifact.suffix.lower() not in ARTIFACT_SUFFIXES or not artifact.is_file():
            raise HTTPException(status_code=404, detail="Artifact not found")
        return FileResponse(artifact, filename=artifact.name)

    @app.get("/runs/{run_id}/events")
    def get_events(
        run_id: str,
        after: int = Query(default=0, ge=0),
    ) -> list[dict[str, Any]]:
        run_or_404(run_id)
        return workbench.database.list_events(run_id, after_id=after)

    @app.get("/jobs")
    def list_jobs() -> list[dict[str, Any]]:
        return [job.to_dict() for job in jobs.list()]

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job.to_dict()

    @app.delete("/jobs/{job_id}")
    def cancel_job(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if not jobs.cancel(job_id):
            raise HTTPException(
                status_code=409,
                detail="Only queued jobs can be cancelled safely",
            )
        return job.to_dict()

    @app.get("/projects/{project_id}/papers")
    def list_papers(
        project_id: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        project_or_404(project_id)
        rows = workbench.database.list_project_papers(project_id, status=status)
        return [
            {
                **{key: value for key, value in row.items() if key != "paper"},
                "paper": row["paper"].to_dict(),
            }
            for row in rows
        ]

    @app.post("/projects/{project_id}/bibliography", status_code=201)
    async def import_bibliography(
        project_id: str,
        file: UploadFile = bibliography_file_parameter,
    ) -> dict[str, Any]:
        project_or_404(project_id)
        filename = Path(file.filename or "").name
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_BIBLIOGRAPHY_SUFFIXES:
            raise HTTPException(
                status_code=415,
                detail="Expected a RIS, BibTeX, or CSL JSON file",
            )
        received = 0
        limit_bytes = active_settings.max_upload_mb * 1024 * 1024
        content = bytearray()
        while chunk := await file.read(1024 * 1024):
            received += len(chunk)
            if received > limit_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        "Bibliography exceeds the configured "
                        f"{active_settings.max_upload_mb} MB limit"
                    ),
                )
            content.extend(chunk)
        try:
            result = workbench.import_bibliography(
                project_id,
                data=bytes(content),
                filename=filename,
            )
        except BibliographyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return result.to_dict()

    @app.post("/projects/{project_id}/screening")
    def save_screening(
        project_id: str,
        payload: ScreeningBatch,
    ) -> dict[str, int]:
        project_or_404(project_id)
        try:
            workbench.record_screening_batch(
                project_id=project_id,
                decisions=[decision.model_dump() for decision in payload.decisions],
            )
        except DatabaseError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (ValueError, WorkbenchError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"updated": len(payload.decisions)}

    @app.get("/projects/{project_id}/screening/config")
    def get_screening_config(project_id: str) -> dict[str, Any]:
        project_or_404(project_id)
        return workbench.database.get_screening_config(project_id)

    @app.put("/projects/{project_id}/screening/config")
    def update_screening_config(
        project_id: str,
        payload: ScreeningConfigUpdate,
    ) -> dict[str, Any]:
        project_or_404(project_id)
        try:
            return workbench.configure_screening(
                project_id,
                mode=payload.mode,
                reviewers=payload.reviewers,
                blind=payload.blind,
            )
        except DatabaseError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/projects/{project_id}/screening/workspace")
    def get_screening_workspace(
        project_id: str,
        reviewer: str = Query(default="", max_length=100),
    ) -> dict[str, Any]:
        project_or_404(project_id)
        try:
            workspace = workbench.screening_workspace(
                project_id,
                reviewer=reviewer,
            )
        except DatabaseError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        workspace["papers"] = [
            {
                **{key: value for key, value in paper.items() if key != "paper"},
                "paper": paper["paper"].to_dict(),
            }
            for paper in workspace["papers"]
        ]
        return workspace

    @app.post("/projects/{project_id}/screening/{paper_id}/resolve")
    def resolve_screening(
        project_id: str,
        paper_id: int,
        payload: ScreeningResolutionRequest,
    ) -> dict[str, Any]:
        project_or_404(project_id)
        try:
            return workbench.resolve_screening(
                project_id,
                paper_id,
                status=payload.status,
                reason=payload.reason,
                resolved_by=payload.resolved_by,
            )
        except DatabaseError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/projects/{project_id}/screening/fulltext/config")
    def get_fulltext_screening_config(project_id: str) -> dict[str, Any]:
        project_or_404(project_id)
        return workbench.database.get_screening_config(project_id)

    @app.put("/projects/{project_id}/screening/fulltext/config")
    def update_fulltext_screening_config(
        project_id: str,
        payload: FullTextConfigUpdate,
    ) -> dict[str, Any]:
        project_or_404(project_id)
        try:
            return workbench.configure_fulltext_screening(
                project_id,
                enabled=payload.enabled,
                blind=payload.blind,
            )
        except DatabaseError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/projects/{project_id}/screening/fulltext/workspace")
    def get_fulltext_screening_workspace(
        project_id: str,
        reviewer: str = Query(default="", max_length=100),
    ) -> dict[str, Any]:
        project_or_404(project_id)
        try:
            workspace = workbench.fulltext_screening_workspace(
                project_id,
                reviewer=reviewer,
            )
        except DatabaseError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        workspace["papers"] = [
            {
                **{key: value for key, value in paper.items() if key != "paper"},
                "paper": paper["paper"].to_dict(),
            }
            for paper in workspace["papers"]
        ]
        return workspace

    @app.post("/projects/{project_id}/screening/fulltext")
    def save_fulltext_screening(
        project_id: str,
        payload: FullTextScreeningBatch,
    ) -> dict[str, int]:
        project_or_404(project_id)
        try:
            workbench.record_fulltext_screening_batch(
                project_id=project_id,
                decisions=[decision.model_dump() for decision in payload.decisions],
            )
        except DatabaseError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"updated": len(payload.decisions)}

    @app.post("/projects/{project_id}/screening/fulltext/{paper_id}/retrieval")
    def save_fulltext_retrieval(
        project_id: str,
        paper_id: int,
        payload: FullTextRetrievalRequest,
    ) -> dict[str, Any]:
        project_or_404(project_id)
        try:
            return workbench.record_fulltext_retrieval(
                project_id,
                paper_id,
                status=payload.status,
                reason=payload.reason,
                updated_by=payload.updated_by,
            )
        except DatabaseError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/projects/{project_id}/screening/fulltext/{paper_id}/resolve")
    def resolve_fulltext_screening(
        project_id: str,
        paper_id: int,
        payload: FullTextResolutionRequest,
    ) -> dict[str, Any]:
        project_or_404(project_id)
        try:
            return workbench.resolve_fulltext_screening(
                project_id,
                paper_id,
                status=payload.status,
                reason=payload.reason,
                exclusion_code=payload.exclusion_code,
                resolved_by=payload.resolved_by,
            )
        except DatabaseError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/projects/{project_id}/prisma")
    def get_prisma_flow(project_id: str) -> dict[str, Any]:
        project_or_404(project_id)
        return workbench.database.prisma_flow(project_id)

    @app.post("/runs/{run_id}/continue", status_code=202)
    def continue_run(
        run_id: str,
        demo: bool = False,
        connection_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        run = run_or_404(run_id)
        project = project_or_404(run["project_id"])
        stored_connection = str(run["config"].get("connection", {}).get("id", ""))
        selected_connection = connection_id or (
            None
            if stored_connection in {"", "demo", "env-openai"}
            else stored_connection
        )
        selected_agent = agent_id or str(
            run["config"].get("agent", {}).get("id", "deep_review")
        )
        llm = make_llm(demo, project.topic, selected_connection)
        retrievers = [bundled_demo_retriever()] if demo else None
        job = jobs.submit(
            f"continue:{run_id}",
            lambda: workbench.continue_after_screening(
                run_id,
                llm=llm,
                retrievers=retrievers,
                agent_id=selected_agent,
            ),
        )
        return {"run_id": run_id, "job_id": job.id, "status": "queued"}

    @app.get("/projects/{project_id}/conversations")
    def list_conversations(project_id: str) -> list[dict[str, Any]]:
        project_or_404(project_id)
        return workbench.database.list_conversations(project_id)

    @app.post("/projects/{project_id}/conversations", status_code=201)
    def create_conversation(
        project_id: str,
        payload: ConversationCreate,
    ) -> dict[str, Any]:
        project_or_404(project_id)
        try:
            agent = get_agent_profile(payload.agent_id)
            if payload.demo:
                connection_id = "demo"
                connection_label = "离线演示"
            else:
                connection = connections.resolve(payload.connection_id)
                connection_id = connection.id
                connection_label = f"{connection.name} · {connection.model}"
        except (ConnectionError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return workbench.database.create_conversation(
            project_id=project_id,
            title=payload.title,
            agent_id=agent.id,
            connection_id=connection_id,
            connection_label=connection_label,
        )

    @app.get("/conversations/{conversation_id}")
    def get_conversation(conversation_id: str) -> dict[str, Any]:
        conversation = conversation_or_404(conversation_id)
        return {
            **conversation,
            "messages": workbench.database.list_messages(conversation_id),
        }

    @app.post("/conversations/{conversation_id}/messages", status_code=201)
    def create_message(
        conversation_id: str,
        payload: MessageCreate,
    ) -> dict[str, Any]:
        conversation = conversation_or_404(conversation_id)
        project = project_or_404(conversation["project_id"])
        selected_agent_id = payload.agent_id or conversation["agent_id"]
        selected_connection_id = payload.connection_id or conversation["connection_id"]
        is_demo = payload.demo or selected_connection_id == "demo"
        try:
            agent = get_agent_profile(selected_agent_id)
            llm = (
                None
                if is_demo
                else make_llm(False, project.topic, selected_connection_id)
            )
        except (ConnectionError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        user_message = workbench.database.add_message(
            conversation_id=conversation_id,
            role="user",
            content=payload.content.strip(),
        )
        history = workbench.database.list_messages(conversation_id)
        try:
            answer, sources = answer_project_question(
                database=workbench.database,
                project_id=project.id,
                question=payload.content.strip(),
                history=history,
                agent=agent,
                llm=llm,
                demo=is_demo,
            )
        except (LLMError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        assistant_message = workbench.database.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
            sources=sources,
        )
        return {
            "user_message": user_message,
            "assistant_message": assistant_message,
        }

    @app.get("/projects/{project_id}/documents")
    def list_documents(project_id: str) -> list[dict[str, Any]]:
        project_or_404(project_id)
        return [
            public_document(document)
            for document in workbench.database.list_documents(project_id)
        ]

    @app.post("/projects/{project_id}/documents", status_code=201)
    async def upload_document(
        project_id: str,
        file: UploadFile = upload_file_parameter,
        paper_id: int | None = None,
    ) -> dict[str, Any]:
        project_or_404(project_id)
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in workbench.documents.SUPPORTED_SUFFIXES:
            raise HTTPException(status_code=415, detail="Expected PDF, TXT, or MD")
        incoming = active_settings.data_root / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        temp_path = incoming / f"{uuid4().hex}{suffix}"
        try:
            received = 0
            limit_bytes = active_settings.max_upload_mb * 1024 * 1024
            with temp_path.open("wb") as handle:
                while chunk := await file.read(1024 * 1024):
                    received += len(chunk)
                    if received > limit_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=(
                                "Document exceeds the configured "
                                f"{active_settings.max_upload_mb} MB limit"
                            ),
                        )
                    handle.write(chunk)
            record = workbench.documents.ingest(
                project_id=project_id,
                source=temp_path,
                paper_id=paper_id,
                filename=file.filename,
            )
            return public_document(asdict(record))
        finally:
            temp_path.unlink(missing_ok=True)

    @app.get("/projects/{project_id}/documents/search")
    def search_documents(
        project_id: str,
        q: str = Query(min_length=2),
        limit: int = Query(default=10, ge=1, le=100),
    ) -> list[dict[str, Any]]:
        project_or_404(project_id)
        return workbench.documents.search(project_id, q, limit=limit)

    @app.get("/projects/{project_id}/documents/{document_id}")
    def get_document(project_id: str, document_id: str) -> dict[str, Any]:
        return public_document(document_or_404(project_id, document_id))

    @app.get("/projects/{project_id}/documents/{document_id}/file")
    def download_document(project_id: str, document_id: str):
        document = document_or_404(project_id, document_id)
        source = Path(document["source_path"]).resolve()
        data_root = active_settings.data_root.resolve()
        if not source.is_file():
            raise HTTPException(status_code=410, detail="Document file is missing")
        if not source.is_relative_to(data_root):
            raise HTTPException(
                status_code=403,
                detail="Document file is outside data root",
            )
        return FileResponse(
            source,
            media_type=document["media_type"],
            filename=document["filename"],
        )

    @app.get("/projects/{project_id}/documents/{document_id}/text")
    def get_document_text(project_id: str, document_id: str) -> dict[str, Any]:
        document = document_or_404(project_id, document_id)
        text_path = Path(document["text_path"]).resolve()
        data_root = active_settings.data_root.resolve()
        if not text_path.is_file():
            raise HTTPException(status_code=410, detail="Extracted text is missing")
        if not text_path.is_relative_to(data_root):
            raise HTTPException(
                status_code=403,
                detail="Extracted text is outside data root",
            )
        return {
            "document": public_document(document),
            "text": text_path.read_text(encoding="utf-8"),
        }

    @app.get("/projects/{project_id}/export")
    def download_project_export(project_id: str):
        project = project_or_404(project_id)
        export_root = active_settings.data_root / "exports"
        target = export_root / f"{project.id}-{uuid4().hex}.zip"
        archive = export_project(workbench.database, project.id, target)
        return FileResponse(
            archive,
            media_type="application/zip",
            filename=f"{project.id}.zip",
            background=BackgroundTask(archive.unlink, missing_ok=True),
        )

    web_dist = (
        active_settings.web_dist.resolve()
        if active_settings.web_dist
        else Path(__file__).parent / "web_dist"
    )
    if (web_dist / "index.html").is_file():
        assets = web_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="web-assets")
        brand_mark = web_dist / "asteria-mark.svg"
        if brand_mark.is_file():

            @app.get("/asteria-mark.svg", include_in_schema=False)
            def web_brand_mark():
                return FileResponse(brand_mark, media_type="image/svg+xml")

        @app.get("/", include_in_schema=False)
        def web_root():
            return RedirectResponse("/app")

        @app.get("/app", include_in_schema=False)
        @app.get("/app/{spa_path:path}", include_in_schema=False)
        def web_app(spa_path: str = ""):
            return FileResponse(web_dist / "index.html")

    return app
