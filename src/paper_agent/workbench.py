from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .agent_profiles import get_agent_profile
from .artifacts import checkpoint, load_state
from .bibliography import (
    BibliographyImportResult,
    parse_bibliography,
)
from .config import Settings
from .database import Database
from .documents import DocumentStore
from .domain import (
    QualityAssessment,
    ReviewProtocol,
    RunRecord,
    RunStatus,
    ScreeningDecision,
    ScreeningStatus,
    new_id,
)
from .fulltext_screening import FullTextDecision
from .llm import LanguageModel
from .models import ResearchState
from .profiles import get_profile
from .retrievers import Retriever
from .workflow import ResearchAgent


class WorkbenchError(RuntimeError):
    pass


class ResearchWorkbench:
    """Application service coordinating projects, runs, artifacts, and review gates."""

    def __init__(
        self,
        settings: Settings,
        *,
        database: Database | None = None,
    ):
        self.settings = settings
        self.data_root = settings.data_root.resolve()
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.database = database or Database(settings.database_path)
        self.documents = DocumentStore(self.data_root, self.database)

    def create_project(
        self,
        *,
        name: str,
        topic: str,
        research_question: str = "",
        review_type: str = "narrative",
        language: str | None = None,
        protocol: ReviewProtocol | None = None,
    ):
        get_profile(review_type)
        return self.database.create_project(
            name=name,
            topic=topic,
            research_question=research_question or topic,
            review_type=review_type,
            language=language or self.settings.language,
            protocol=protocol,
        )

    def import_bibliography(
        self,
        project_id: str,
        *,
        data: bytes,
        filename: str,
    ) -> BibliographyImportResult:
        self.database.require_project(project_id)
        parsed = parse_bibliography(data, filename)
        imported = self.database.import_project_papers(project_id, parsed.papers)
        return BibliographyImportResult(
            filename=Path(filename).name,
            format=parsed.format,
            parsed=len(parsed.papers),
            added=int(imported["added"]),
            already_present=int(imported["already_present"]),
            enriched=int(imported["enriched"]),
            skipped=parsed.skipped,
            duplicates_in_file=parsed.duplicates_in_file,
            evidence_ids=[str(value) for value in imported.get("evidence_ids", [])],
            warnings=parsed.warnings,
        )

    def create_run(
        self,
        project_id: str,
        *,
        agent_id: str = "deep_review",
        connection: dict[str, str] | None = None,
    ) -> RunRecord:
        project = self.database.require_project(project_id)
        agent = get_agent_profile(agent_id)
        config = self.settings.to_dict()
        config["agent"] = {
            "id": agent.id,
            "name": agent.name,
        }
        if connection:
            config["connection"] = connection
        run = RunRecord(
            id=new_id("run"),
            project_id=project.id,
            status=RunStatus.QUEUED,
            stage="initialized",
            config=config,
        )
        self.database.create_run(run)
        return run

    def execute_run(
        self,
        run_id: str,
        *,
        llm: LanguageModel,
        retrievers: list[Retriever] | None = None,
        stop_for_screening: bool | None = None,
        agent_id: str | None = None,
    ) -> Path:
        run = self.database.get_run(run_id)
        if not run:
            raise WorkbenchError(f"Run not found: {run_id}")
        project = self.database.require_project(run["project_id"])
        profile = get_profile(project.review_type)
        selected_agent = get_agent_profile(
            agent_id or str(run["config"].get("agent", {}).get("id", "deep_review"))
        )
        should_pause = (
            profile.requires_manual_screening
            or selected_agent.default_stop_for_screening
            if stop_for_screening is None
            else stop_for_screening
        )
        project_settings = replace(
            self.settings,
            language=project.language,
            output_root=self.data_root / project.id / "runs",
        )
        protocol_settings = project_settings.to_dict()
        protocol_settings["protocol"] = project.protocol.to_dict()
        self.database.update_run(
            run_id,
            status=RunStatus.RUNNING,
            stage="initialized",
            error="",
        )

        def progress(stage: str, message: str) -> None:
            self.database.update_run(run_id, stage=stage)
            self.database.add_event(run_id, stage, message)

        agent = ResearchAgent(
            settings=project_settings,
            llm=llm,
            retrievers=retrievers,
            progress=progress,
            protocol=project.protocol,
            agent_profile=selected_agent,
        )
        try:
            stop_after = "searched" if should_pause else "completed"
            run_dir = agent.run(
                project.topic,
                project.research_question,
                stop_after=stop_after,
            )
            state = load_state(run_dir)
            state.settings.update(protocol_settings)
            checkpoint(run_dir, state)
            self._import_state(project.id, run_id, run_dir, state)
            status = (
                RunStatus.WAITING_FOR_SCREENING if should_pause else RunStatus.COMPLETED
            )
            self.database.update_run(
                run_id,
                status=status,
                stage=state.stage,
                run_dir=str(run_dir),
            )
            return run_dir
        except Exception as exc:
            self.database.update_run(
                run_id,
                status=RunStatus.FAILED,
                error=str(exc),
            )
            self.database.add_event(run_id, "failed", str(exc))
            raise

    def continue_after_screening(
        self,
        run_id: str,
        *,
        llm: LanguageModel,
        retrievers: list[Retriever] | None = None,
        agent_id: str | None = None,
    ) -> Path:
        run = self.database.get_run(run_id)
        if not run:
            raise WorkbenchError(f"Run not found: {run_id}")
        if run["status"] != RunStatus.WAITING_FOR_SCREENING:
            raise WorkbenchError(
                f"Run must be waiting_for_screening, got {run['status']!r}"
            )
        run_dir = Path(run["run_dir"])
        state = load_state(run_dir)
        gate = self.database.screening_gate(run["project_id"])
        if gate.get("blind"):
            raise WorkbenchError(
                "Blind screening must be opened before research can continue"
            )
        if gate["pending"]:
            raise WorkbenchError(
                f"{gate['pending']} papers still need a screening decision"
            )
        if gate["unresolved"]:
            raise WorkbenchError(
                f"{gate['unresolved']} papers still need conflict resolution"
            )
        rows = self.database.list_project_papers(run["project_id"])
        fulltext_gate = self.database.fulltext_screening_gate(run["project_id"])
        if fulltext_gate["blind"]:
            raise WorkbenchError(
                "Full-text blind screening must be opened before research can continue"
            )
        if fulltext_gate["awaiting_retrieval"]:
            raise WorkbenchError(
                f"{fulltext_gate['awaiting_retrieval']} reports still need "
                "full-text retrieval"
            )
        if fulltext_gate["pending"]:
            raise WorkbenchError(
                f"{fulltext_gate['pending']} retrieved reports still need "
                "a full-text decision"
            )
        if fulltext_gate["unresolved"]:
            raise WorkbenchError(
                f"{fulltext_gate['unresolved']} full-text decisions still "
                "need resolution"
            )
        if fulltext_gate["enabled"]:
            included_ids = {
                row["evidence_id"]
                for row in rows
                if row["fulltext_status"] == ScreeningStatus.INCLUDED
            }
        else:
            included_ids = {
                row["evidence_id"]
                for row in rows
                if row["screening_status"]
                in {
                    ScreeningStatus.INCLUDED,
                    ScreeningStatus.MAYBE,
                }
            }
        state.papers = [
            paper for paper in state.papers if paper.paper_id in included_ids
        ]
        if not state.papers:
            raise WorkbenchError("No included papers remain after screening")
        title_screening = [
            {
                "paper_id": row["evidence_id"],
                "stage": "title_abstract",
                "status": row["screening_status"],
                "reasons": [row["screening_reason"]],
                "reviewer": row["reviewer"],
            }
            for row in rows
        ]
        fulltext_screening = (
            [
                {
                    "paper_id": row["evidence_id"],
                    "stage": "full_text",
                    "retrieval_status": row["retrieval_status"],
                    "status": row["fulltext_status"],
                    "reasons": [row["fulltext_reason"]],
                    "exclusion_code": row["fulltext_exclusion_code"],
                    "reviewer": row["fulltext_reviewer"],
                }
                for row in rows
                if row["screening_status"]
                in {
                    ScreeningStatus.INCLUDED,
                    ScreeningStatus.MAYBE,
                }
            ]
            if fulltext_gate["enabled"]
            else []
        )
        state.screening = title_screening + fulltext_screening
        state.touch("screened")
        checkpoint(run_dir, state)
        project = self.database.require_project(run["project_id"])
        selected_agent = get_agent_profile(
            agent_id or str(run["config"].get("agent", {}).get("id", "deep_review"))
        )
        project_settings = replace(
            self.settings,
            language=project.language,
            output_root=run_dir.parent,
        )
        self.database.update_run(
            run_id,
            status=RunStatus.RUNNING,
            stage="screened",
            error="",
        )

        def progress(stage: str, message: str) -> None:
            self.database.update_run(run_id, stage=stage)
            self.database.add_event(run_id, stage, message)

        agent = ResearchAgent(
            settings=project_settings,
            llm=llm,
            retrievers=retrievers,
            progress=progress,
            protocol=project.protocol,
            agent_profile=selected_agent,
        )
        try:
            agent.resume(run_dir)
            final_state = load_state(run_dir)
            self._import_state(project.id, run_id, run_dir, final_state)
            self.database.update_run(
                run_id,
                status=RunStatus.COMPLETED,
                stage=final_state.stage,
            )
            return run_dir
        except Exception as exc:
            self.database.update_run(
                run_id,
                status=RunStatus.FAILED,
                error=str(exc),
            )
            self.database.add_event(run_id, "failed", str(exc))
            raise

    def record_screening(
        self,
        *,
        project_id: str,
        paper_id: int,
        status: str,
        reason: str = "",
        reviewer: str = "human",
    ) -> None:
        if status not in {
            ScreeningStatus.INCLUDED,
            ScreeningStatus.EXCLUDED,
            ScreeningStatus.MAYBE,
        }:
            raise ValueError("status must be included, excluded, or maybe")
        self.database.record_screening(
            ScreeningDecision(
                project_id=project_id,
                paper_id=paper_id,
                status=status,
                reason=reason,
                reviewer=reviewer,
            )
        )

    def record_screening_batch(
        self,
        *,
        project_id: str,
        decisions: list[dict],
    ) -> None:
        records: list[ScreeningDecision] = []
        for decision in decisions:
            status = str(decision["status"])
            if status not in {
                ScreeningStatus.INCLUDED,
                ScreeningStatus.EXCLUDED,
                ScreeningStatus.MAYBE,
            }:
                raise ValueError("status must be included, excluded, or maybe")
            records.append(
                ScreeningDecision(
                    project_id=project_id,
                    paper_id=int(decision["paper_id"]),
                    status=status,
                    reason=str(decision.get("reason", "")),
                    reviewer=str(decision.get("reviewer", "human")),
                )
            )
        self.database.record_screening_batch(records)

    def configure_screening(
        self,
        project_id: str,
        *,
        mode: str,
        reviewers: list[str] | None = None,
        blind: bool = False,
    ) -> dict:
        return self.database.configure_screening(
            project_id,
            mode=mode,
            reviewers=reviewers,
            blind=blind,
        )

    def screening_workspace(
        self,
        project_id: str,
        *,
        reviewer: str = "",
    ) -> dict:
        return self.database.screening_workspace(
            project_id,
            reviewer_id=reviewer,
        )

    def resolve_screening(
        self,
        project_id: str,
        paper_id: int,
        *,
        status: str,
        reason: str,
        resolved_by: str,
    ) -> dict:
        return self.database.resolve_screening(
            project_id,
            paper_id,
            status=status,
            reason=reason,
            resolved_by=resolved_by,
        )

    def configure_fulltext_screening(
        self,
        project_id: str,
        *,
        enabled: bool,
        blind: bool = True,
    ) -> dict:
        return self.database.configure_fulltext_screening(
            project_id,
            enabled=enabled,
            blind=blind,
        )

    def record_fulltext_retrieval(
        self,
        project_id: str,
        paper_id: int,
        *,
        status: str,
        reason: str = "",
        updated_by: str = "human",
    ) -> dict:
        return self.database.record_fulltext_retrieval(
            project_id,
            paper_id,
            status=status,
            reason=reason,
            updated_by=updated_by,
        )

    def record_fulltext_screening_batch(
        self,
        *,
        project_id: str,
        decisions: list[dict],
    ) -> None:
        records = [
            FullTextDecision(
                project_id=project_id,
                paper_id=int(decision["paper_id"]),
                status=str(decision["status"]),
                reason=str(decision.get("reason", "")),
                exclusion_code=str(decision.get("exclusion_code", "")),
                reviewer=str(decision.get("reviewer", "human")),
            )
            for decision in decisions
        ]
        self.database.record_fulltext_screening_batch(records)

    def fulltext_screening_workspace(
        self,
        project_id: str,
        *,
        reviewer: str = "",
    ) -> dict:
        return self.database.fulltext_screening_workspace(
            project_id,
            reviewer_id=reviewer,
        )

    def resolve_fulltext_screening(
        self,
        project_id: str,
        paper_id: int,
        *,
        status: str,
        reason: str,
        exclusion_code: str,
        resolved_by: str,
    ) -> dict:
        return self.database.resolve_fulltext_screening(
            project_id,
            paper_id,
            status=status,
            reason=reason,
            exclusion_code=exclusion_code,
            resolved_by=resolved_by,
        )

    def _import_state(
        self,
        project_id: str,
        run_id: str,
        run_dir: Path,
        state: ResearchState,
    ) -> None:
        db_ids: dict[str, int] = {}
        screening_map = {
            str(item.get("paper_id")): str(item.get("status", "pending"))
            for item in state.screening
        }
        for paper in state.papers:
            db_id = self.database.upsert_paper(paper)
            db_ids[paper.paper_id] = db_id
            status = screening_map.get(
                paper.paper_id,
                ScreeningStatus.PENDING,
            )
            self.database.attach_paper(
                project_id,
                db_id,
                paper.paper_id,
                status=status,
            )
        for card in state.evidence:
            db_id = db_ids.get(card.paper_id)
            if db_id is not None:
                self.database.save_evidence(project_id, db_id, card)
        for item in state.quality:
            evidence_id = str(item.get("paper_id", ""))
            db_id = db_ids.get(evidence_id)
            if db_id is None:
                continue
            self.database.save_quality(
                QualityAssessment(
                    project_id=project_id,
                    paper_id=db_id,
                    rubric=str(item.get("rubric", "unknown")),
                    scores={
                        str(key): int(value)
                        for key, value in dict(item.get("scores", {})).items()
                    },
                    overall=float(item.get("overall", 0)),
                    notes=[str(note) for note in item.get("notes", [])],
                )
            )
        for item in state.cs_analysis.get("reproducibility", []):
            evidence_id = str(item.get("paper_id", ""))
            db_id = db_ids.get(evidence_id)
            if db_id is None:
                continue
            self.database.save_quality(
                QualityAssessment(
                    project_id=project_id,
                    paper_id=db_id,
                    rubric=str(item.get("rubric", "cs_reproducibility_v1")),
                    scores={
                        str(key): int(value)
                        for key, value in dict(item.get("scores", {})).items()
                    },
                    overall=float(item.get("overall", 0)),
                    notes=[
                        str(item.get("note", "")),
                        "Missing fields: "
                        + ", ".join(str(value) for value in item.get("missing", [])),
                    ],
                )
            )
        if state.report and (run_dir / "report.md").exists():
            existing = [
                report
                for report in self.database.list_reports(project_id)
                if report["run_id"] == run_id
            ]
            if not existing:
                self.database.add_report(
                    project_id=project_id,
                    run_id=run_id,
                    title=f"{state.topic} 研究报告",
                    format="markdown",
                    path=str(run_dir / "report.md"),
                )
