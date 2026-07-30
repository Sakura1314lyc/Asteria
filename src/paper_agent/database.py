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
from .screening import evaluate_consensus

SCHEMA_VERSION = 4


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

                CREATE TABLE IF NOT EXISTS screening_configs (
                    project_id TEXT PRIMARY KEY REFERENCES projects(id)
                        ON DELETE CASCADE,
                    mode TEXT NOT NULL DEFAULT 'single',
                    blind INTEGER NOT NULL DEFAULT 0,
                    reviewers_json TEXT NOT NULL DEFAULT '[]',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS screening_decisions (
                    project_id TEXT NOT NULL REFERENCES projects(id)
                        ON DELETE CASCADE,
                    paper_id INTEGER NOT NULL REFERENCES papers(id)
                        ON DELETE CASCADE,
                    reviewer_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    decided_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, paper_id, reviewer_id)
                );

                CREATE TABLE IF NOT EXISTS screening_decision_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES projects(id)
                        ON DELETE CASCADE,
                    paper_id INTEGER NOT NULL REFERENCES papers(id)
                        ON DELETE CASCADE,
                    reviewer_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    decided_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS screening_resolutions (
                    project_id TEXT NOT NULL REFERENCES projects(id)
                        ON DELETE CASCADE,
                    paper_id INTEGER NOT NULL REFERENCES papers(id)
                        ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    resolved_by TEXT NOT NULL,
                    resolved_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, paper_id)
                );

                CREATE TABLE IF NOT EXISTS screening_resolution_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES projects(id)
                        ON DELETE CASCADE,
                    paper_id INTEGER NOT NULL REFERENCES papers(id)
                        ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    resolved_by TEXT NOT NULL,
                    resolved_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_screening_decisions_project
                    ON screening_decisions(project_id, reviewer_id, paper_id);
                CREATE INDEX IF NOT EXISTS idx_screening_decision_events_project
                    ON screening_decision_events(project_id, paper_id, id);
                CREATE INDEX IF NOT EXISTS idx_screening_resolution_events_project
                    ON screening_resolution_events(project_id, paper_id, id);

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
            next_number = (
                max(
                    (
                        int(value[1:])
                        for value in used_ids
                        if re.fullmatch(r"P\d{3,}", value)
                    ),
                    default=0,
                )
                + 1
            )
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
            db.execute("BEGIN IMMEDIATE")
            _record_screening_transaction(db, decision)

    def record_screening_batch(
        self,
        decisions: list[ScreeningDecision],
    ) -> None:
        if not decisions:
            raise ValueError("At least one screening decision is required")
        project_ids = {decision.project_id for decision in decisions}
        if len(project_ids) != 1:
            raise ValueError("A screening batch must belong to one project")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            for decision in decisions:
                _record_screening_transaction(db, decision)

    def get_screening_config(self, project_id: str) -> dict[str, Any]:
        with self.connection() as db:
            if not _project_exists(db, project_id):
                raise DatabaseError("Project not found")
            return _screening_config(db, project_id)

    def configure_screening(
        self,
        project_id: str,
        *,
        mode: str,
        reviewers: list[str] | None = None,
        blind: bool = False,
    ) -> dict[str, Any]:
        normalized_mode = mode.strip().lower()
        normalized_reviewers = list(
            dict.fromkeys(
                reviewer.strip() for reviewer in (reviewers or []) if reviewer.strip()
            )
        )
        if normalized_mode not in {"single", "dual"}:
            raise ValueError("Screening mode must be 'single' or 'dual'")
        if normalized_mode == "dual" and len(normalized_reviewers) != 2:
            raise ValueError("Dual screening requires exactly two unique reviewers")
        if normalized_mode == "single":
            normalized_reviewers = []
            blind = False

        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if not _project_exists(db, project_id):
                raise DatabaseError("Project not found")
            current = _screening_config(db, project_id)
            has_config = db.execute(
                "SELECT 1 FROM screening_configs WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            decision_count = int(
                db.execute(
                    """
                    SELECT COUNT(*) AS amount FROM screening_decisions
                    WHERE project_id = ?
                    """,
                    (project_id,),
                ).fetchone()["amount"]
            )

            if (
                current["mode"] == "dual"
                and normalized_mode == "single"
                and decision_count
            ):
                raise DatabaseError(
                    "Dual screening cannot be disabled after decisions exist"
                )
            if (
                current["mode"] == "dual"
                and normalized_mode == "dual"
                and current["reviewers"] != normalized_reviewers
                and decision_count
            ):
                raise DatabaseError(
                    "Reviewers cannot be changed after dual screening has started"
                )
            if (
                current["mode"] == "dual"
                and current["blind"]
                and normalized_mode == "dual"
                and not blind
                and not _all_dual_decisions_complete(
                    db,
                    project_id,
                    current["reviewers"],
                )
            ):
                raise DatabaseError(
                    "Blind review can only be opened after both reviewers finish"
                )
            if (
                current["mode"] == "dual"
                and not current["blind"]
                and normalized_mode == "dual"
                and blind
                and decision_count
            ):
                raise DatabaseError(
                    "Blind review cannot be restored after decisions were opened"
                )

            enabling_dual = current["mode"] == "single" and normalized_mode == "dual"
            if enabling_dual:
                db.execute(
                    "DELETE FROM screening_decisions WHERE project_id = ?",
                    (project_id,),
                )
                legacy = db.execute(
                    """
                    SELECT paper_id, screening_status, screening_reason, decided_at
                    FROM project_papers
                    WHERE project_id = ? AND screening_status != ?
                    """,
                    (project_id, ScreeningStatus.PENDING),
                ).fetchall()
                for row in legacy:
                    migrated = ScreeningDecision(
                        project_id=project_id,
                        paper_id=row["paper_id"],
                        status=row["screening_status"],
                        reason=row["screening_reason"],
                        reviewer=normalized_reviewers[0],
                        decided_at=row["decided_at"] or utc_now(),
                    )
                    _save_screening_decision(db, migrated)
                db.execute(
                    """
                    UPDATE project_papers
                    SET screening_status = ?, screening_reason = '',
                        reviewer = '', decided_at = ''
                    WHERE project_id = ?
                    """,
                    (ScreeningStatus.PENDING, project_id),
                )

            now = utc_now()
            db.execute(
                """
                INSERT INTO screening_configs(
                    project_id, mode, blind, reviewers_json, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    mode = excluded.mode,
                    blind = excluded.blind,
                    reviewers_json = excluded.reviewers_json,
                    updated_at = excluded.updated_at
                """,
                (
                    project_id,
                    normalized_mode,
                    int(blind),
                    _json(normalized_reviewers),
                    now,
                ),
            )
            if (
                current["mode"] == "dual"
                and current["blind"]
                and normalized_mode == "dual"
                and not blind
            ):
                paper_rows = db.execute(
                    """
                    SELECT paper_id FROM project_papers
                    WHERE project_id = ?
                    """,
                    (project_id,),
                ).fetchall()
                for paper_row in paper_rows:
                    _recompute_screening(
                        db,
                        project_id,
                        paper_row["paper_id"],
                        normalized_reviewers,
                    )
            if has_config is None or enabling_dual:
                db.execute(
                    "UPDATE projects SET updated_at = ? WHERE id = ?",
                    (now, project_id),
                )
            return _screening_config(db, project_id)

    def screening_workspace(
        self,
        project_id: str,
        *,
        reviewer_id: str = "",
    ) -> dict[str, Any]:
        with self.connection() as db:
            if not _project_exists(db, project_id):
                raise DatabaseError("Project not found")
            config = _screening_config(db, project_id)
            if (
                config["mode"] == "dual"
                and reviewer_id
                and reviewer_id not in config["reviewers"]
            ):
                raise DatabaseError(
                    f"Reviewer must be one of: {', '.join(config['reviewers'])}"
                )
            rows = db.execute(
                """
                SELECT p.*, pp.evidence_id, pp.screening_status,
                       pp.screening_reason, pp.reviewer, pp.tags_json,
                       pp.decided_at
                FROM project_papers pp
                JOIN papers p ON p.id = pp.paper_id
                WHERE pp.project_id = ?
                ORDER BY pp.evidence_id
                """,
                (project_id,),
            ).fetchall()
            papers = [_paper_row(row) for row in rows]
            decisions = db.execute(
                """
                SELECT paper_id, reviewer_id, status, reason, decided_at
                FROM screening_decisions
                WHERE project_id = ?
                ORDER BY paper_id, reviewer_id
                """,
                (project_id,),
            ).fetchall()
            resolutions = db.execute(
                """
                SELECT paper_id, status, reason, resolved_by, resolved_at
                FROM screening_resolutions
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchall()

        decision_map: dict[int, dict[str, dict[str, str]]] = {}
        for row in decisions:
            decision_map.setdefault(row["paper_id"], {})[row["reviewer_id"]] = {
                "reviewer_id": row["reviewer_id"],
                "status": row["status"],
                "reason": row["reason"],
                "decided_at": row["decided_at"],
            }
        resolution_map = {
            row["paper_id"]: {
                "status": row["status"],
                "reason": row["reason"],
                "resolved_by": row["resolved_by"],
                "resolved_at": row["resolved_at"],
            }
            for row in resolutions
        }

        state_counts = {
            "pending": 0,
            "agreed": 0,
            "conflict": 0,
            "awaiting_resolution": 0,
            "resolved": 0,
        }
        for paper in papers:
            paper_decisions = decision_map.get(paper["id"], {})
            resolution = resolution_map.get(paper["id"])
            if config["mode"] == "dual":
                consensus = evaluate_consensus(
                    {
                        reviewer: item["status"]
                        for reviewer, item in paper_decisions.items()
                    },
                    config["reviewers"],
                )
                state = "resolved" if resolution else consensus.state
                state_counts[state] += 1
                if config["blind"]:
                    own = paper_decisions.get(reviewer_id) if reviewer_id else None
                    paper["screening_status"] = (
                        own["status"] if own else ScreeningStatus.PENDING
                    )
                    paper["screening_reason"] = own["reason"] if own else ""
                    paper["reviewer"] = reviewer_id
                    paper["decided_at"] = own["decided_at"] if own else ""
                    paper["my_decision"] = own
                    paper["decisions"] = []
                    paper["resolution"] = None
                    paper["consensus_state"] = "blinded"
                else:
                    paper["my_decision"] = paper_decisions.get(reviewer_id)
                    paper["decisions"] = list(paper_decisions.values())
                    paper["resolution"] = resolution
                    paper["consensus_state"] = state
            else:
                state = (
                    "pending"
                    if paper["screening_status"] == ScreeningStatus.PENDING
                    else "agreed"
                )
                state_counts[state] += 1
                paper["my_decision"] = None
                paper["decisions"] = []
                paper["resolution"] = None
                paper["consensus_state"] = state

        summary = {
            "total": len(papers),
            **state_counts,
            "reviewer_completed": sum(
                1
                for decisions_for_paper in decision_map.values()
                if reviewer_id in decisions_for_paper
            ),
        }
        if config["blind"]:
            summary = {
                "total": len(papers),
                "reviewer_completed": summary["reviewer_completed"],
            }
        return {"config": config, "summary": summary, "papers": papers}

    def resolve_screening(
        self,
        project_id: str,
        paper_id: int,
        *,
        status: str,
        reason: str,
        resolved_by: str,
    ) -> dict[str, Any]:
        if status not in {ScreeningStatus.INCLUDED, ScreeningStatus.EXCLUDED}:
            raise ValueError("Resolution status must be included or excluded")
        if not resolved_by.strip():
            raise ValueError("Resolver is required")
        if not reason.strip():
            raise ValueError("Resolution reason is required")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if not _paper_is_attached(db, project_id, paper_id):
                raise DatabaseError("Paper is not attached to this project")
            config = _screening_config(db, project_id)
            if config["mode"] != "dual":
                raise DatabaseError("Resolution is only available in dual mode")
            if config["blind"]:
                raise DatabaseError("Open blind review before resolving decisions")
            rows = db.execute(
                """
                SELECT reviewer_id FROM screening_decisions
                WHERE project_id = ? AND paper_id = ?
                """,
                (project_id, paper_id),
            ).fetchall()
            completed = {row["reviewer_id"] for row in rows}
            if not set(config["reviewers"]).issubset(completed):
                raise DatabaseError("Both reviewers must decide before resolution")
            now = utc_now()
            values = (
                project_id,
                paper_id,
                status,
                reason.strip(),
                resolved_by.strip(),
                now,
            )
            db.execute(
                """
                INSERT INTO screening_resolutions(
                    project_id, paper_id, status, reason, resolved_by, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, paper_id) DO UPDATE SET
                    status = excluded.status,
                    reason = excluded.reason,
                    resolved_by = excluded.resolved_by,
                    resolved_at = excluded.resolved_at
                """,
                values,
            )
            db.execute(
                """
                INSERT INTO screening_resolution_events(
                    project_id, paper_id, status, reason, resolved_by, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            db.execute(
                """
                UPDATE project_papers
                SET screening_status = ?, screening_reason = ?, reviewer = ?,
                    decided_at = ?
                WHERE project_id = ? AND paper_id = ?
                """,
                (
                    status,
                    reason.strip(),
                    resolved_by.strip(),
                    now,
                    project_id,
                    paper_id,
                ),
            )
            return {
                "paper_id": paper_id,
                "status": status,
                "reason": reason.strip(),
                "resolved_by": resolved_by.strip(),
                "resolved_at": now,
            }

    def screening_gate(self, project_id: str) -> dict[str, Any]:
        workspace = self.screening_workspace(project_id)
        if workspace["config"]["mode"] == "single":
            pending = workspace["summary"]["pending"]
            return {
                "ready": pending == 0,
                "pending": pending,
                "unresolved": 0,
                "blind": False,
            }
        if workspace["config"]["blind"]:
            return {
                "ready": False,
                "pending": 0,
                "unresolved": 0,
                "blind": True,
            }
        summary = workspace["summary"]
        unresolved = summary["conflict"] + summary["awaiting_resolution"]
        return {
            "ready": summary["pending"] == 0 and unresolved == 0,
            "pending": summary["pending"],
            "unresolved": unresolved,
            "blind": False,
        }

    def screening_audit(self, project_id: str) -> dict[str, Any]:
        """Return the complete review trail for controlled project export."""

        with self.connection() as db:
            if not _project_exists(db, project_id):
                raise DatabaseError("Project not found")
            config = _screening_config(db, project_id)
            decisions = [
                dict(row)
                for row in db.execute(
                    """
                    SELECT paper_id, reviewer_id, status, reason, decided_at
                    FROM screening_decisions
                    WHERE project_id = ?
                    ORDER BY paper_id, reviewer_id
                    """,
                    (project_id,),
                ).fetchall()
            ]
            decision_events = [
                dict(row)
                for row in db.execute(
                    """
                    SELECT id, paper_id, reviewer_id, status, reason, decided_at
                    FROM screening_decision_events
                    WHERE project_id = ?
                    ORDER BY id
                    """,
                    (project_id,),
                ).fetchall()
            ]
            resolutions = [
                dict(row)
                for row in db.execute(
                    """
                    SELECT paper_id, status, reason, resolved_by, resolved_at
                    FROM screening_resolutions
                    WHERE project_id = ?
                    ORDER BY paper_id
                    """,
                    (project_id,),
                ).fetchall()
            ]
            resolution_events = [
                dict(row)
                for row in db.execute(
                    """
                    SELECT id, paper_id, status, reason, resolved_by, resolved_at
                    FROM screening_resolution_events
                    WHERE project_id = ?
                    ORDER BY id
                    """,
                    (project_id,),
                ).fetchall()
            ]
        return {
            "config": config,
            "decisions": decisions,
            "decision_events": decision_events,
            "resolutions": resolutions,
            "resolution_events": resolution_events,
            "gate": self.screening_gate(project_id),
        }

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


def _project_exists(db: sqlite3.Connection, project_id: str) -> bool:
    return (
        db.execute(
            "SELECT 1 FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        is not None
    )


def _paper_is_attached(
    db: sqlite3.Connection,
    project_id: str,
    paper_id: int,
) -> bool:
    return (
        db.execute(
            """
            SELECT 1 FROM project_papers
            WHERE project_id = ? AND paper_id = ?
            """,
            (project_id, paper_id),
        ).fetchone()
        is not None
    )


def _screening_config(
    db: sqlite3.Connection,
    project_id: str,
) -> dict[str, Any]:
    row = db.execute(
        """
        SELECT mode, blind, reviewers_json, updated_at
        FROM screening_configs
        WHERE project_id = ?
        """,
        (project_id,),
    ).fetchone()
    if row is None:
        return {
            "mode": "single",
            "blind": False,
            "reviewers": [],
            "updated_at": "",
        }
    return {
        "mode": row["mode"],
        "blind": bool(row["blind"]),
        "reviewers": _loads(row["reviewers_json"], []),
        "updated_at": row["updated_at"],
    }


def _save_screening_decision(
    db: sqlite3.Connection,
    decision: ScreeningDecision,
) -> None:
    values = (
        decision.project_id,
        decision.paper_id,
        decision.reviewer,
        decision.status,
        decision.reason,
        decision.decided_at,
    )
    db.execute(
        """
        INSERT INTO screening_decisions(
            project_id, paper_id, reviewer_id, status, reason, decided_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, paper_id, reviewer_id) DO UPDATE SET
            status = excluded.status,
            reason = excluded.reason,
            decided_at = excluded.decided_at
        """,
        values,
    )
    db.execute(
        """
        INSERT INTO screening_decision_events(
            project_id, paper_id, reviewer_id, status, reason, decided_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        values,
    )


def _record_screening_transaction(
    db: sqlite3.Connection,
    decision: ScreeningDecision,
) -> None:
    if not _paper_is_attached(db, decision.project_id, decision.paper_id):
        raise DatabaseError("Paper is not attached to this project")
    config = _screening_config(db, decision.project_id)
    reviewers = config["reviewers"]
    if config["mode"] == "dual" and decision.reviewer not in reviewers:
        raise DatabaseError(f"Reviewer must be one of: {', '.join(reviewers)}")

    if config["mode"] == "single":
        db.execute(
            """
            DELETE FROM screening_decisions
            WHERE project_id = ? AND paper_id = ?
            """,
            (decision.project_id, decision.paper_id),
        )
    _save_screening_decision(db, decision)

    if config["mode"] == "dual":
        db.execute(
            """
            DELETE FROM screening_resolutions
            WHERE project_id = ? AND paper_id = ?
            """,
            (decision.project_id, decision.paper_id),
        )
        if config["blind"]:
            db.execute(
                """
                UPDATE project_papers
                SET screening_status = ?, screening_reason = '',
                    reviewer = '', decided_at = ''
                WHERE project_id = ? AND paper_id = ?
                """,
                (
                    ScreeningStatus.PENDING,
                    decision.project_id,
                    decision.paper_id,
                ),
            )
        else:
            _recompute_screening(
                db,
                decision.project_id,
                decision.paper_id,
                reviewers,
            )
    else:
        db.execute(
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


def _recompute_screening(
    db: sqlite3.Connection,
    project_id: str,
    paper_id: int,
    reviewers: list[str],
) -> None:
    rows = db.execute(
        """
        SELECT reviewer_id, status, reason, decided_at
        FROM screening_decisions
        WHERE project_id = ? AND paper_id = ?
        """,
        (project_id, paper_id),
    ).fetchall()
    decisions = {row["reviewer_id"]: row for row in rows}
    consensus = evaluate_consensus(
        {
            reviewer: decisions[reviewer]["status"]
            for reviewer in reviewers
            if reviewer in decisions
        },
        reviewers,
    )
    reasons = list(
        dict.fromkeys(
            decisions[reviewer]["reason"].strip()
            for reviewer in reviewers
            if reviewer in decisions and decisions[reviewer]["reason"].strip()
        )
    )
    decided_at = ""
    if consensus.complete:
        decided_at = max(
            decisions[reviewer]["decided_at"]
            for reviewer in reviewers
            if reviewer in decisions
        )
    db.execute(
        """
        UPDATE project_papers
        SET screening_status = ?, screening_reason = ?, reviewer = ?,
            decided_at = ?
        WHERE project_id = ? AND paper_id = ?
        """,
        (
            consensus.status,
            " | ".join(reasons) if consensus.complete else "",
            "dual-consensus" if consensus.complete else "",
            decided_at,
            project_id,
            paper_id,
        ),
    )


def _all_dual_decisions_complete(
    db: sqlite3.Connection,
    project_id: str,
    reviewers: list[str],
) -> bool:
    paper_count = int(
        db.execute(
            """
            SELECT COUNT(*) AS amount FROM project_papers
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()["amount"]
    )
    decision_count = int(
        db.execute(
            """
            SELECT COUNT(*) AS amount
            FROM screening_decisions
            WHERE project_id = ?
              AND reviewer_id IN (?, ?)
            """,
            (project_id, reviewers[0], reviewers[1]),
        ).fetchone()["amount"]
    )
    return decision_count == paper_count * len(reviewers)


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
