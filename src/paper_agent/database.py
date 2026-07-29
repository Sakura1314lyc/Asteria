from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .bibliography import merge_papers
from .domain import (
    DocumentRecord,
    Project,
    QualityAssessment,
    ReviewProtocol,
    RunRecord,
    ScreeningDecision,
    ScreeningStatus,
    new_id,
    utc_now,
)
from .models import EvidenceCard, Paper

SCHEMA_VERSION = 3


class DatabaseError(RuntimeError):
    pass


class Database:
    """SQLite repository for long-lived research workspaces."""

    def __init__(self, path: Path | str):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> None:
        with self.connection() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    version INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    research_question TEXT NOT NULL,
                    review_type TEXT NOT NULL,
                    language TEXT NOT NULL,
                    protocol_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS papers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_key TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    authors_json TEXT NOT NULL,
                    year INTEGER,
                    abstract TEXT NOT NULL,
                    url TEXT NOT NULL,
                    doi TEXT NOT NULL,
                    arxiv_id TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    citation_count INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL,
                    open_access_url TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS project_papers (
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
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

                CREATE TABLE IF NOT EXISTS evidence_cards (
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
                    card_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, paper_id)
                );

                CREATE TABLE IF NOT EXISTS quality_assessments (
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    paper_id INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
                    rubric TEXT NOT NULL,
                    scores_json TEXT NOT NULL,
                    overall REAL NOT NULL,
                    notes_json TEXT NOT NULL,
                    assessed_by TEXT NOT NULL,
                    assessed_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, paper_id, rubric)
                );

                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    run_dir TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    error TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS run_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    timestamp TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_events_run_id
                    ON run_events(run_id, id);
                CREATE INDEX IF NOT EXISTS idx_project_papers_status
                    ON project_papers(project_id, screening_status);

                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    paper_id INTEGER REFERENCES papers(id) ON DELETE SET NULL,
                    filename TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    text_path TEXT NOT NULL,
                    page_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(project_id, sha256)
                );

                CREATE TABLE IF NOT EXISTS document_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    page INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    UNIQUE(document_id, chunk_index)
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
                    content,
                    document_id UNINDEXED,
                    page UNINDEXED,
                    chunk_id UNINDEXED
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    run_id TEXT REFERENCES runs(id) ON DELETE SET NULL,
                    title TEXT NOT NULL,
                    format TEXT NOT NULL,
                    path TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id)
                        ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    connection_id TEXT NOT NULL,
                    connection_label TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id)
                        ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_conversations_project
                    ON conversations(project_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id, created_at);
                """
            )
            row = db.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO schema_meta(version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            elif row["version"] > SCHEMA_VERSION:
                raise DatabaseError(
                    f"Database schema {row['version']} is newer than supported "
                    f"version {SCHEMA_VERSION}"
                )
            elif row["version"] < SCHEMA_VERSION:
                db.execute(
                    "UPDATE schema_meta SET version = ?",
                    (SCHEMA_VERSION,),
                )

    def create_project(
        self,
        *,
        name: str,
        topic: str,
        research_question: str,
        review_type: str = "narrative",
        language: str = "zh-CN",
        protocol: ReviewProtocol | None = None,
    ) -> Project:
        now = utc_now()
        project = Project(
            id=new_id("prj"),
            name=name.strip(),
            topic=topic.strip(),
            research_question=research_question.strip() or topic.strip(),
            review_type=review_type,
            language=language,
            protocol=protocol or ReviewProtocol(review_type=review_type),
            created_at=now,
            updated_at=now,
        )
        if not project.name or not project.topic:
            raise ValueError("Project name and topic are required")
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO projects(
                    id, name, topic, research_question, review_type, language,
                    protocol_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.name,
                    project.topic,
                    project.research_question,
                    project.review_type,
                    project.language,
                    _json(project.protocol.to_dict()),
                    project.created_at,
                    project.updated_at,
                ),
            )
        return project

    def get_project(self, project_id: str) -> Project | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        return _project(row) if row else None

    def require_project(self, project_id: str) -> Project:
        project = self.get_project(project_id)
        if project is None:
            raise DatabaseError(f"Project not found: {project_id}")
        return project

    def list_projects(self) -> list[Project]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM projects ORDER BY updated_at DESC"
            ).fetchall()
        return [_project(row) for row in rows]

    def update_protocol(
        self,
        project_id: str,
        protocol: ReviewProtocol,
    ) -> Project:
        now = utc_now()
        with self.connection() as db:
            result = db.execute(
                """
                UPDATE projects
                SET protocol_json = ?, review_type = ?, updated_at = ?
                WHERE id = ?
                """,
                (_json(protocol.to_dict()), protocol.review_type, now, project_id),
            )
            if result.rowcount != 1:
                raise DatabaseError(f"Project not found: {project_id}")
        return self.require_project(project_id)

    def upsert_paper(self, paper: Paper) -> int:
        canonical = canonical_key(paper)
        now = utc_now()
        with self.connection() as db:
            existing = db.execute(
                "SELECT * FROM papers WHERE canonical_key = ?",
                (canonical,),
            ).fetchone()
            if existing is None and paper.title:
                existing = db.execute(
                    """
                    SELECT * FROM papers
                    WHERE lower(trim(title)) = lower(trim(?))
                    ORDER BY id
                    LIMIT 1
                    """,
                    (paper.title,),
                ).fetchone()
            if existing:
                merged, _ = merge_papers(_stored_paper(existing), paper)
                updated_canonical = canonical_key(merged)
                conflict = db.execute(
                    "SELECT id FROM papers WHERE canonical_key = ? AND id != ?",
                    (updated_canonical, existing["id"]),
                ).fetchone()
                if conflict is not None:
                    updated_canonical = str(existing["canonical_key"])
                db.execute(
                    """
                    UPDATE papers SET
                        canonical_key = ?, title = ?, authors_json = ?, year = ?,
                        abstract = ?, url = ?, doi = ?, arxiv_id = ?, venue = ?,
                        citation_count = ?, source = ?,
                        open_access_url = ?, metadata_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        updated_canonical,
                        merged.title,
                        _json(merged.authors),
                        merged.year,
                        merged.abstract,
                        merged.url,
                        merged.doi,
                        merged.arxiv_id,
                        merged.venue,
                        merged.citation_count,
                        merged.source,
                        merged.open_access_url,
                        _json(_paper_metadata(merged)),
                        now,
                        existing["id"],
                    ),
                )
                return int(existing["id"])
            cursor = db.execute(
                """
                INSERT INTO papers(
                    canonical_key, title, authors_json, year, abstract, url, doi,
                    arxiv_id, venue, citation_count, source, open_access_url,
                    metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    canonical,
                    paper.title,
                    _json(paper.authors),
                    paper.year,
                    paper.abstract,
                    paper.url,
                    paper.doi,
                    paper.arxiv_id,
                    paper.venue,
                    paper.citation_count,
                    paper.source,
                    paper.open_access_url,
                    _json(_paper_metadata(paper)),
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def attach_paper(
        self,
        project_id: str,
        paper_id: int,
        evidence_id: str,
        *,
        status: str = ScreeningStatus.PENDING,
    ) -> None:
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO project_papers(
                    project_id, paper_id, evidence_id, screening_status, added_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id, paper_id) DO UPDATE SET
                    evidence_id = excluded.evidence_id
                """,
                (project_id, paper_id, evidence_id, status, utc_now()),
            )

    def import_project_papers(
        self,
        project_id: str,
        papers: list[Paper],
    ) -> dict[str, Any]:
        """Atomically enrich the global library and attach records to a project."""

        now = utc_now()
        added = 0
        already_present = 0
        enriched = 0
        evidence_ids: list[str] = []
        with self.connection() as db:
            project = db.execute(
                "SELECT id FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            if project is None:
                raise DatabaseError(f"Project not found: {project_id}")
            used_ids = {
                str(row["evidence_id"])
                for row in db.execute(
                    "SELECT evidence_id FROM project_papers WHERE project_id = ?",
                    (project_id,),
                ).fetchall()
            }
            next_number = max(
                (
                    int(value[1:])
                    for value in used_ids
                    if re.fullmatch(r"P\d{3,}", value)
                ),
                default=0,
            ) + 1
            for paper in papers:
                canonical = canonical_key(paper)
                existing = db.execute(
                    "SELECT * FROM papers WHERE canonical_key = ?",
                    (canonical,),
                ).fetchone()
                if existing is None and paper.title:
                    existing = db.execute(
                        """
                        SELECT * FROM papers
                        WHERE lower(trim(title)) = lower(trim(?))
                        ORDER BY id
                        LIMIT 1
                        """,
                        (paper.title,),
                    ).fetchone()
                if existing is not None:
                    merged, was_enriched = merge_papers(
                        _stored_paper(existing),
                        paper,
                    )
                    paper_id = int(existing["id"])
                    updated_canonical = canonical_key(merged)
                    conflict = db.execute(
                        "SELECT id FROM papers WHERE canonical_key = ? AND id != ?",
                        (updated_canonical, paper_id),
                    ).fetchone()
                    if conflict is not None:
                        updated_canonical = str(existing["canonical_key"])
                    db.execute(
                        """
                        UPDATE papers SET
                            canonical_key = ?, title = ?, authors_json = ?, year = ?,
                            abstract = ?, url = ?, doi = ?, arxiv_id = ?, venue = ?,
                            citation_count = ?, source = ?, open_access_url = ?,
                            metadata_json = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            updated_canonical,
                            merged.title,
                            _json(merged.authors),
                            merged.year,
                            merged.abstract,
                            merged.url,
                            merged.doi,
                            merged.arxiv_id,
                            merged.venue,
                            merged.citation_count,
                            merged.source,
                            merged.open_access_url,
                            _json(_paper_metadata(merged)),
                            now,
                            paper_id,
                        ),
                    )
                    enriched += int(was_enriched)
                else:
                    cursor = db.execute(
                        """
                        INSERT INTO papers(
                            canonical_key, title, authors_json, year, abstract,
                            url, doi, arxiv_id, venue, citation_count, source,
                            open_access_url, metadata_json, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            canonical,
                            paper.title,
                            _json(paper.authors),
                            paper.year,
                            paper.abstract,
                            paper.url,
                            paper.doi,
                            paper.arxiv_id,
                            paper.venue,
                            paper.citation_count,
                            paper.source,
                            paper.open_access_url,
                            _json(_paper_metadata(paper)),
                            now,
                            now,
                        ),
                    )
                    paper_id = int(cursor.lastrowid)

                attached = db.execute(
                    """
                    SELECT evidence_id FROM project_papers
                    WHERE project_id = ? AND paper_id = ?
                    """,
                    (project_id, paper_id),
                ).fetchone()
                if attached is not None:
                    already_present += 1
                    continue
                while f"P{next_number:03d}" in used_ids:
                    next_number += 1
                evidence_id = f"P{next_number:03d}"
                used_ids.add(evidence_id)
                next_number += 1
                db.execute(
                    """
                    INSERT INTO project_papers(
                        project_id, paper_id, evidence_id,
                        screening_status, added_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        paper_id,
                        evidence_id,
                        ScreeningStatus.PENDING,
                        now,
                    ),
                )
                evidence_ids.append(evidence_id)
                added += 1
            db.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, project_id),
            )
        return {
            "added": added,
            "already_present": already_present,
            "enriched": enriched,
            "evidence_ids": evidence_ids,
        }

    def list_project_papers(
        self,
        project_id: str,
        *,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT p.*, pp.evidence_id, pp.screening_status,
                   pp.screening_reason, pp.reviewer, pp.tags_json, pp.decided_at
            FROM project_papers pp
            JOIN papers p ON p.id = pp.paper_id
            WHERE pp.project_id = ?
        """
        values: list[Any] = [project_id]
        if status:
            query += " AND pp.screening_status = ?"
            values.append(status)
        query += " ORDER BY pp.evidence_id"
        with self.connection() as db:
            rows = db.execute(query, values).fetchall()
        return [_paper_row(row) for row in rows]

    def record_screening(self, decision: ScreeningDecision) -> None:
        with self.connection() as db:
            result = db.execute(
                """
                UPDATE project_papers
                SET screening_status = ?, screening_reason = ?, reviewer = ?,
                    decided_at = ?
                WHERE project_id = ? AND paper_id = ?
                """,
                (
                    decision.status,
                    decision.reason,
                    decision.reviewer,
                    decision.decided_at,
                    decision.project_id,
                    decision.paper_id,
                ),
            )
            if result.rowcount != 1:
                raise DatabaseError("Paper is not attached to this project")

    def save_evidence(
        self,
        project_id: str,
        paper_id: int,
        card: EvidenceCard,
    ) -> None:
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO evidence_cards(project_id, paper_id, card_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id, paper_id) DO UPDATE SET
                    card_json = excluded.card_json,
                    updated_at = excluded.updated_at
                """,
                (project_id, paper_id, _json(card.to_dict()), utc_now()),
            )

    def save_quality(self, assessment: QualityAssessment) -> None:
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO quality_assessments(
                    project_id, paper_id, rubric, scores_json, overall,
                    notes_json, assessed_by, assessed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, paper_id, rubric) DO UPDATE SET
                    scores_json = excluded.scores_json,
                    overall = excluded.overall,
                    notes_json = excluded.notes_json,
                    assessed_by = excluded.assessed_by,
                    assessed_at = excluded.assessed_at
                """,
                (
                    assessment.project_id,
                    assessment.paper_id,
                    assessment.rubric,
                    _json(assessment.scores),
                    assessment.overall,
                    _json(assessment.notes),
                    assessment.assessed_by,
                    assessment.assessed_at,
                ),
            )

    def create_run(self, run: RunRecord) -> None:
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO runs(
                    id, project_id, status, stage, run_dir, config_json,
                    error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.project_id,
                    run.status,
                    run.stage,
                    run.run_dir,
                    _json(run.config),
                    run.error,
                    run.created_at,
                    run.updated_at,
                ),
            )

    def update_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        stage: str | None = None,
        run_dir: str | None = None,
        error: str | None = None,
    ) -> None:
        fields = ["updated_at = ?"]
        values: list[Any] = [utc_now()]
        for name, value in (
            ("status", status),
            ("stage", stage),
            ("run_dir", run_dir),
            ("error", error),
        ):
            if value is not None:
                fields.append(f"{name} = ?")
                values.append(value)
        values.append(run_id)
        with self.connection() as db:
            db.execute(
                f"UPDATE runs SET {', '.join(fields)} WHERE id = ?",
                values,
            )

    def add_event(
        self,
        run_id: str,
        stage: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO run_events(
                    run_id, timestamp, stage, message, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, utc_now(), stage, message, _json(payload or {})),
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _run_row(row) if row else None

    def list_runs(self, project_id: str) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM runs WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        return [_run_row(row) for row in rows]

    def list_events(self, run_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT * FROM run_events
                WHERE run_id = ? AND id > ?
                ORDER BY id
                """,
                (run_id, after_id),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "stage": row["stage"],
                "message": row["message"],
                "payload": _loads(row["payload_json"], {}),
            }
            for row in rows
        ]

    def project_stats(self, project_id: str) -> dict[str, int]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT screening_status, COUNT(*) AS count
                FROM project_papers
                WHERE project_id = ?
                GROUP BY screening_status
                """,
                (project_id,),
            ).fetchall()
            documents = db.execute(
                "SELECT COUNT(*) AS count FROM documents WHERE project_id = ?",
                (project_id,),
            ).fetchone()["count"]
        stats = {"total": 0, "documents": int(documents)}
        for row in rows:
            stats[row["screening_status"]] = int(row["count"])
            stats["total"] += int(row["count"])
        return stats

    def add_document(
        self,
        document: DocumentRecord,
        chunks: list[tuple[int, int, str]],
    ) -> None:
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO documents(
                    id, project_id, paper_id, filename, sha256, media_type,
                    source_path, text_path, page_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.id,
                    document.project_id,
                    document.paper_id,
                    document.filename,
                    document.sha256,
                    document.media_type,
                    document.source_path,
                    document.text_path,
                    document.page_count,
                    document.created_at,
                ),
            )
            for page, chunk_index, content in chunks:
                cursor = db.execute(
                    """
                    INSERT INTO document_chunks(
                        document_id, page, chunk_index, content
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (document.id, page, chunk_index, content),
                )
                db.execute(
                    """
                    INSERT INTO document_chunks_fts(
                        content, document_id, page, chunk_id
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (content, document.id, page, cursor.lastrowid),
                )

    def get_document_by_hash(
        self,
        project_id: str,
        sha256: str,
    ) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                """
                SELECT * FROM documents
                WHERE project_id = ? AND sha256 = ?
                """,
                (project_id, sha256),
            ).fetchone()
        return dict(row) if row else None

    def list_documents(self, project_id: str) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT * FROM documents
                WHERE project_id = ?
                ORDER BY created_at DESC
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_document(
        self,
        project_id: str,
        document_id: str,
    ) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                """
                SELECT * FROM documents
                WHERE project_id = ? AND id = ?
                """,
                (project_id, document_id),
            ).fetchone()
        return dict(row) if row else None

    def search_documents(
        self,
        project_id: str,
        query: str,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        terms = [term.replace('"', "") for term in query.split() if term.strip()]
        if not terms:
            return []
        fts_query = " OR ".join(f'"{term}"' for term in terms[:12])
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT f.document_id, f.page, f.chunk_id, f.content,
                       bm25(document_chunks_fts) AS rank, d.filename, d.paper_id
                FROM document_chunks_fts f
                JOIN documents d ON d.id = f.document_id
                WHERE document_chunks_fts MATCH ? AND d.project_id = ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, project_id, max(1, min(limit, 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_report(
        self,
        *,
        project_id: str,
        run_id: str | None,
        title: str,
        format: str,
        path: str,
    ) -> dict[str, Any]:
        with self.connection() as db:
            version = (
                int(
                    db.execute(
                        "SELECT COUNT(*) AS count FROM reports WHERE project_id = ?",
                        (project_id,),
                    ).fetchone()["count"]
                )
                + 1
            )
            report_id = new_id("rpt")
            created_at = utc_now()
            db.execute(
                """
                INSERT INTO reports(
                    id, project_id, run_id, title, format, path, version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    project_id,
                    run_id,
                    title,
                    format,
                    path,
                    version,
                    created_at,
                ),
            )
        return {
            "id": report_id,
            "project_id": project_id,
            "run_id": run_id,
            "title": title,
            "format": format,
            "path": path,
            "version": version,
            "created_at": created_at,
        }

    def list_reports(self, project_id: str) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT * FROM reports
                WHERE project_id = ?
                ORDER BY version DESC
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_conversation(
        self,
        *,
        project_id: str,
        title: str,
        agent_id: str,
        connection_id: str,
        connection_label: str,
    ) -> dict[str, Any]:
        conversation_id = new_id("chat")
        now = utc_now()
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO conversations(
                    id, project_id, title, agent_id, connection_id,
                    connection_label, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    project_id,
                    title.strip() or "新对话",
                    agent_id,
                    connection_id,
                    connection_label,
                    now,
                    now,
                ),
            )
        return {
            "id": conversation_id,
            "project_id": project_id,
            "title": title.strip() or "新对话",
            "agent_id": agent_id,
            "connection_id": connection_id,
            "connection_label": connection_label,
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
        }

    def list_conversations(self, project_id: str) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT c.*, COUNT(m.id) AS message_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE c.project_id = ?
                GROUP BY c.id
                ORDER BY c.updated_at DESC
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                """
                SELECT c.*, COUNT(m.id) AS message_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE c.id = ?
                GROUP BY c.id
                """,
                (conversation_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at, id
                """,
                (conversation_id,),
            ).fetchall()
        return [
            {
                **{
                    key: value
                    for key, value in dict(row).items()
                    if key != "sources_json"
                },
                "sources": _loads(row["sources_json"], []),
            }
            for row in rows
        ]

    def add_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        sources: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        message_id = new_id("msg")
        now = utc_now()
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO messages(
                    id, conversation_id, role, content, sources_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    conversation_id,
                    role,
                    content,
                    _json(sources or []),
                    now,
                ),
            )
            db.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
        return {
            "id": message_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "sources": sources or [],
            "created_at": now,
        }

    def project_evidence_context(
        self,
        project_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT pp.evidence_id, pp.screening_status, p.title, p.authors_json,
                       p.year, p.abstract, p.venue, p.doi, p.url, ec.card_json
                FROM project_papers pp
                JOIN papers p ON p.id = pp.paper_id
                LEFT JOIN evidence_cards ec
                    ON ec.project_id = pp.project_id AND ec.paper_id = pp.paper_id
                WHERE pp.project_id = ? AND pp.screening_status != 'excluded'
                ORDER BY
                    CASE pp.screening_status
                        WHEN 'included' THEN 0
                        WHEN 'maybe' THEN 1
                        ELSE 2
                    END,
                    pp.evidence_id
                LIMIT ?
                """,
                (project_id, max(1, min(limit, 50))),
            ).fetchall()
        return [
            {
                "paper_id": row["evidence_id"],
                "screening_status": row["screening_status"],
                "title": row["title"],
                "authors": _loads(row["authors_json"], []),
                "year": row["year"],
                "abstract": row["abstract"],
                "venue": row["venue"],
                "doi": row["doi"],
                "url": row["url"],
                "evidence": _loads(row["card_json"], {}),
            }
            for row in rows
        ]


def canonical_key(paper: Paper) -> str:
    import re

    if paper.doi:
        return f"doi:{paper.doi.lower().strip()}"
    if paper.arxiv_id:
        return f"arxiv:{paper.arxiv_id.lower().strip()}"
    normalized = re.sub(r"\W+", "", paper.title.lower())
    return f"title:{normalized[:200]}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        topic=row["topic"],
        research_question=row["research_question"],
        review_type=row["review_type"],
        language=row["language"],
        protocol=ReviewProtocol.from_dict(_loads(row["protocol_json"], {})),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _paper_row(row: sqlite3.Row) -> dict[str, Any]:
    paper = _stored_paper(row)
    paper.paper_id = row["evidence_id"]
    return {
        "id": row["id"],
        "paper": paper,
        "evidence_id": row["evidence_id"],
        "screening_status": row["screening_status"],
        "screening_reason": row["screening_reason"],
        "reviewer": row["reviewer"],
        "tags": _loads(row["tags_json"], []),
        "decided_at": row["decided_at"],
    }


def _stored_paper(row: sqlite3.Row) -> Paper:
    metadata = _loads(row["metadata_json"], {})
    return Paper(
        title=row["title"],
        authors=_loads(row["authors_json"], []),
        year=row["year"],
        abstract=row["abstract"],
        url=row["url"],
        doi=row["doi"],
        arxiv_id=row["arxiv_id"],
        venue=row["venue"],
        citation_count=row["citation_count"],
        source=row["source"],
        open_access_url=row["open_access_url"],
        categories=[str(value) for value in metadata.get("categories", [])],
        publication_type=str(metadata.get("publication_type", "")),
        code_urls=[str(value) for value in metadata.get("code_urls", [])],
        dataset_urls=[str(value) for value in metadata.get("dataset_urls", [])],
    )


def _paper_metadata(paper: Paper) -> dict[str, Any]:
    return {
        "categories": paper.categories,
        "publication_type": paper.publication_type,
        "code_urls": paper.code_urls,
        "dataset_urls": paper.dataset_urls,
    }


def _run_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "status": row["status"],
        "stage": row["stage"],
        "run_dir": row["run_dir"],
        "config": _loads(row["config_json"], {}),
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
