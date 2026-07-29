from __future__ import annotations

from dataclasses import asdict, dataclass

from .domain import ReviewProtocol, ScreeningStatus
from .models import Paper


@dataclass(slots=True)
class ScreeningSuggestion:
    paper_id: str
    status: str
    reasons: list[str]
    matched_include: list[str]
    matched_exclude: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ScreeningEngine:
    """Transparent rule-based suggestions; final decisions remain human-owned."""

    def suggest(
        self,
        paper: Paper,
        protocol: ReviewProtocol,
    ) -> ScreeningSuggestion:
        text = f"{paper.title}\n{paper.abstract}".casefold()
        matched_include = [
            term for term in protocol.include_keywords if term.casefold() in text
        ]
        matched_exclude = [
            term for term in protocol.exclude_keywords if term.casefold() in text
        ]
        reasons: list[str] = []

        if protocol.year_from and paper.year and paper.year < protocol.year_from:
            reasons.append(f"year {paper.year} is before {protocol.year_from}")
        if protocol.year_to and paper.year and paper.year > protocol.year_to:
            reasons.append(f"year {paper.year} is after {protocol.year_to}")
        if matched_exclude:
            reasons.append("matched exclusion keywords: " + ", ".join(matched_exclude))
        hard_exclusion = bool(reasons)

        if hard_exclusion:
            status = ScreeningStatus.EXCLUDED
        elif protocol.include_keywords and not matched_include:
            status = ScreeningStatus.MAYBE
            reasons.append("no inclusion keyword matched")
        elif not paper.abstract:
            status = ScreeningStatus.MAYBE
            reasons.append("abstract is missing")
        else:
            status = ScreeningStatus.INCLUDED
            reasons.append("passed configured metadata and keyword rules")
        return ScreeningSuggestion(
            paper_id=paper.paper_id,
            status=str(status),
            reasons=reasons,
            matched_include=matched_include,
            matched_exclude=matched_exclude,
        )

    def suggest_many(
        self,
        papers: list[Paper],
        protocol: ReviewProtocol,
    ) -> list[ScreeningSuggestion]:
        return [self.suggest(paper, protocol) for paper in papers]
