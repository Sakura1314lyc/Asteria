from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class Paper:
    paper_id: str = ""
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    abstract: str = ""
    url: str = ""
    doi: str = ""
    arxiv_id: str = ""
    venue: str = ""
    citation_count: int = 0
    source: str = ""
    open_access_url: str = ""
    score: float = 0.0
    categories: list[str] = field(default_factory=list)
    publication_type: str = ""
    code_urls: list[str] = field(default_factory=list)
    dataset_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Paper:
        allowed = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{key: value for key, value in data.items() if key in allowed})


@dataclass(slots=True)
class EvidenceCard:
    paper_id: str
    relevance: str
    objective: str
    methods: str
    data_or_sample: str
    findings: list[str]
    limitations: list[str]
    confidence: str
    cs_evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceCard:
        return cls(
            paper_id=str(data.get("paper_id", "")),
            relevance=str(data.get("relevance", "")),
            objective=str(data.get("objective", "")),
            methods=str(data.get("methods", "")),
            data_or_sample=str(data.get("data_or_sample", "")),
            findings=[str(item) for item in data.get("findings", [])],
            limitations=[str(item) for item in data.get("limitations", [])],
            confidence=str(data.get("confidence", "low")),
            cs_evidence=(
                dict(data.get("cs_evidence", {}))
                if isinstance(data.get("cs_evidence"), dict)
                else {}
            ),
        )


@dataclass(slots=True)
class ResearchState:
    run_id: str
    topic: str
    question: str
    language: str
    stage: str = "initialized"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    plan: dict[str, Any] = field(default_factory=dict)
    papers: list[Paper] = field(default_factory=list)
    screening: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[EvidenceCard] = field(default_factory=list)
    quality: list[dict[str, Any]] = field(default_factory=list)
    cs_analysis: dict[str, Any] = field(default_factory=dict)
    report: str = ""
    audit: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)

    def touch(self, stage: str | None = None) -> None:
        if stage:
            self.stage = stage
        self.updated_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "papers": [paper.to_dict() for paper in self.papers],
            "evidence": [card.to_dict() for card in self.evidence],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchState:
        payload = dict(data)
        payload["papers"] = [Paper.from_dict(item) for item in data.get("papers", [])]
        payload["evidence"] = [
            EvidenceCard.from_dict(item) for item in data.get("evidence", [])
        ]
        return cls(**payload)
