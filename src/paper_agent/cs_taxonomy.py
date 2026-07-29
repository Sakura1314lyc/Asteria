from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

from .models import Paper


@dataclass(frozen=True, slots=True)
class CSDomain:
    id: str
    name_en: str
    name_zh: str
    arxiv_categories: tuple[str, ...]
    keywords: tuple[str, ...]
    venue_hints: tuple[str, ...]
    evidence_profile: str


@dataclass(frozen=True, slots=True)
class DomainScore:
    domain_id: str
    name_en: str
    name_zh: str
    score: float
    matched_keywords: tuple[str, ...]
    arxiv_categories: tuple[str, ...]
    evidence_profile: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "name_en": self.name_en,
            "name_zh": self.name_zh,
            "score": self.score,
            "matched_keywords": list(self.matched_keywords),
            "arxiv_categories": list(self.arxiv_categories),
            "evidence_profile": self.evidence_profile,
        }


class CSTaxonomy:
    def __init__(self, domains: list[CSDomain], version: str, sources: dict[str, str]):
        self.domains = domains
        self.version = version
        self.sources = sources
        self.by_id = {domain.id: domain for domain in domains}
        self.by_category: dict[str, list[CSDomain]] = {}
        for domain in domains:
            for category in domain.arxiv_categories:
                self.by_category.setdefault(category, []).append(domain)

    @classmethod
    def load(cls) -> CSTaxonomy:
        path = files("paper_agent").joinpath("data/cs_taxonomy.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        domains = [
            CSDomain(
                id=item["id"],
                name_en=item["name_en"],
                name_zh=item["name_zh"],
                arxiv_categories=tuple(item["arxiv_categories"]),
                keywords=tuple(item["keywords"]),
                venue_hints=tuple(item["venue_hints"]),
                evidence_profile=item["evidence_profile"],
            )
            for item in payload["domains"]
        ]
        return cls(domains, payload["version"], payload["sources"])

    def classify_text(self, text: str, *, limit: int = 3) -> list[DomainScore]:
        normalized = _normalize(text)
        scores: list[DomainScore] = []
        for domain in self.domains:
            matched = tuple(
                keyword
                for keyword in domain.keywords
                if _normalize(keyword) in normalized
            )
            category_hits = tuple(
                category
                for category in domain.arxiv_categories
                if category.casefold() in text.casefold()
            )
            score = sum(2.0 + min(len(keyword) / 20, 1.5) for keyword in matched)
            score += 4.0 * len(category_hits)
            if score:
                scores.append(
                    DomainScore(
                        domain_id=domain.id,
                        name_en=domain.name_en,
                        name_zh=domain.name_zh,
                        score=round(score, 3),
                        matched_keywords=matched,
                        arxiv_categories=domain.arxiv_categories,
                        evidence_profile=domain.evidence_profile,
                    )
                )
        if not scores:
            general = self.by_id["general_cs"]
            scores.append(
                DomainScore(
                    domain_id=general.id,
                    name_en=general.name_en,
                    name_zh=general.name_zh,
                    score=0.1,
                    matched_keywords=(),
                    arxiv_categories=general.arxiv_categories,
                    evidence_profile=general.evidence_profile,
                )
            )
        scores.sort(key=lambda item: (item.score, item.domain_id), reverse=True)
        return scores[:limit]

    def classify_paper(self, paper: Paper, *, limit: int = 3) -> list[DomainScore]:
        category_domains: dict[str, float] = {}
        for category in paper.categories:
            for domain in self.by_category.get(category, []):
                category_domains[domain.id] = category_domains.get(domain.id, 0) + 8.0
        text_scores = self.classify_text(
            f"{paper.title}\n{paper.abstract}\n{paper.venue}",
            limit=len(self.domains),
        )
        merged: dict[str, DomainScore] = {item.domain_id: item for item in text_scores}
        for domain_id, bonus in category_domains.items():
            domain = self.by_id[domain_id]
            current = merged.get(domain_id)
            merged[domain_id] = DomainScore(
                domain_id=domain_id,
                name_en=domain.name_en,
                name_zh=domain.name_zh,
                score=round((current.score if current else 0) + bonus, 3),
                matched_keywords=current.matched_keywords if current else (),
                arxiv_categories=domain.arxiv_categories,
                evidence_profile=domain.evidence_profile,
            )
        values = sorted(
            merged.values(),
            key=lambda item: (item.score, item.domain_id),
            reverse=True,
        )
        return values[:limit]

    def expand_queries(
        self,
        topic: str,
        queries: list[dict[str, str]],
        *,
        max_queries: int = 8,
    ) -> tuple[list[dict[str, str]], list[DomainScore]]:
        classifications = self.classify_text(
            " ".join([topic, *[item.get("query", "") for item in queries]]),
            limit=3,
        )
        expanded = list(queries)
        existing = {_normalize(item.get("query", "")) for item in expanded}
        for classification in classifications:
            domain = self.by_id[classification.domain_id]
            additions = [
                (
                    f"{topic} benchmark evaluation reproducibility",
                    f"{domain.name_en}: benchmarks and reproducibility",
                ),
                (
                    f"{topic} limitations threats to validity",
                    f"{domain.name_en}: limitations and validity",
                ),
            ]
            for query, purpose in additions:
                normalized = _normalize(query)
                if normalized not in existing and len(expanded) < max_queries:
                    expanded.append({"query": query, "purpose": purpose})
                    existing.add(normalized)
        return expanded[:max_queries], classifications


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()
