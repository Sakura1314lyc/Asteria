from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class ReviewType(StrEnum):
    NARRATIVE = "narrative"
    SCOPING = "scoping"
    SYSTEMATIC = "systematic"
    THESIS = "thesis"


class ScreeningStatus(StrEnum):
    PENDING = "pending"
    INCLUDED = "included"
    EXCLUDED = "excluded"
    MAYBE = "maybe"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_SCREENING = "waiting_for_screening"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class ReviewProtocol:
    review_type: str = ReviewType.NARRATIVE
    population: list[str] = field(default_factory=list)
    intervention: list[str] = field(default_factory=list)
    comparison: list[str] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    year_from: int | None = None
    year_to: int | None = None
    languages: list[str] = field(default_factory=list)
    study_types: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> ReviewProtocol:
        if not value:
            return cls()
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value[key] for key in allowed if key in value})


@dataclass(slots=True)
class Project:
    id: str
    name: str
    topic: str
    research_question: str
    review_type: str = ReviewType.NARRATIVE
    language: str = "zh-CN"
    protocol: ReviewProtocol = field(default_factory=ReviewProtocol)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["protocol"] = self.protocol.to_dict()
        return data


@dataclass(slots=True)
class ScreeningDecision:
    project_id: str
    paper_id: int
    status: str
    reason: str = ""
    reviewer: str = "human"
    decided_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class QualityAssessment:
    project_id: str
    paper_id: int
    rubric: str
    scores: dict[str, int]
    overall: float
    notes: list[str] = field(default_factory=list)
    assessed_by: str = "agent"
    assessed_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DocumentRecord:
    id: str
    project_id: str
    filename: str
    sha256: str
    media_type: str
    source_path: str
    text_path: str
    page_count: int
    paper_id: int | None = None
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class RunRecord:
    id: str
    project_id: str
    status: str
    stage: str
    run_dir: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
