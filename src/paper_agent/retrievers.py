from __future__ import annotations

import html
import json
import math
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import ClassVar, Protocol
from urllib.parse import urlencode
from xml.etree import ElementTree

from .config import Settings
from .models import Paper, SearchExecution
from .net import request_bytes, request_json


class Retriever(Protocol):
    name: str

    def search(self, query: str, limit: int) -> list[Paper]: ...


def _clean(text: str | None) -> str:
    without_tags = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _doi(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", value, flags=re.IGNORECASE).lower()


def _reconstruct_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, offsets in index.items():
        positions.extend((int(offset), word) for offset in offsets)
    return " ".join(word for _, word in sorted(positions))


class OpenAlexRetriever:
    name = "openalex"

    def __init__(self, settings: Settings):
        self.settings = settings

    def search(self, query: str, limit: int) -> list[Paper]:
        params = {
            "search": query,
            "per-page": min(limit, 100),
            "select": (
                "id,doi,title,publication_year,authorships,primary_location,"
                "abstract_inverted_index,cited_by_count,type,open_access,primary_topic"
            ),
        }
        email = os.getenv("OPENALEX_EMAIL")
        if email:
            params["mailto"] = email
        data = request_json(
            "https://api.openalex.org/works?" + urlencode(params),
            timeout=self.settings.request_timeout,
            retries=self.settings.max_retries,
        )
        papers: list[Paper] = []
        for item in data.get("results", []):
            if not isinstance(item, dict):
                continue
            authors = []
            for authorship in item.get("authorships") or []:
                author = authorship.get("author") or {}
                if author.get("display_name"):
                    authors.append(_clean(author["display_name"]))
            location = item.get("primary_location") or {}
            source = location.get("source") or {}
            landing = location.get("landing_page_url") or item.get("id") or ""
            oa = item.get("open_access") or {}
            primary_topic = item.get("primary_topic") or {}
            papers.append(
                Paper(
                    title=_clean(item.get("title")),
                    authors=authors,
                    year=item.get("publication_year"),
                    abstract=_reconstruct_abstract(item.get("abstract_inverted_index")),
                    url=landing,
                    doi=_doi(item.get("doi")),
                    venue=_clean(source.get("display_name")),
                    citation_count=int(item.get("cited_by_count") or 0),
                    source=self.name,
                    open_access_url=oa.get("oa_url") or "",
                    publication_type=str(item.get("type") or ""),
                    categories=[str(primary_topic.get("display_name"))]
                    if primary_topic.get("display_name")
                    else [],
                )
            )
        return [paper for paper in papers if paper.title]


class ArxivRetriever:
    name = "arxiv"
    namespace: ClassVar[dict[str, str]] = {"atom": "http://www.w3.org/2005/Atom"}

    def __init__(self, settings: Settings):
        self.settings = settings

    def search(self, query: str, limit: int) -> list[Paper]:
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": min(limit, 100),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        raw = request_bytes(
            "https://export.arxiv.org/api/query?" + urlencode(params),
            timeout=self.settings.request_timeout,
            retries=self.settings.max_retries,
        )
        root = ElementTree.fromstring(raw)
        papers: list[Paper] = []
        for entry in root.findall("atom:entry", self.namespace):
            identifier = _clean(entry.findtext("atom:id", "", self.namespace))
            arxiv_id = identifier.rstrip("/").split("/")[-1]
            published = _clean(entry.findtext("atom:published", "", self.namespace))
            year = int(published[:4]) if re.match(r"\d{4}", published) else None
            authors = [
                _clean(node.findtext("atom:name", "", self.namespace))
                for node in entry.findall("atom:author", self.namespace)
            ]
            doi_node = entry.find("{http://arxiv.org/schemas/atom}doi")
            doi_value = doi_node.text if doi_node is not None else ""
            categories = [
                str(node.attrib.get("term"))
                for node in entry.findall("atom:category", self.namespace)
                if node.attrib.get("term")
            ]
            papers.append(
                Paper(
                    title=_clean(entry.findtext("atom:title", "", self.namespace)),
                    authors=[author for author in authors if author],
                    year=year,
                    abstract=_clean(entry.findtext("atom:summary", "", self.namespace)),
                    url=identifier,
                    doi=_doi(doi_value),
                    arxiv_id=arxiv_id,
                    venue="arXiv",
                    source=self.name,
                    open_access_url=f"https://arxiv.org/pdf/{arxiv_id}"
                    if arxiv_id
                    else "",
                    categories=categories,
                    publication_type="preprint",
                )
            )
        return [paper for paper in papers if paper.title]


class SemanticScholarRetriever:
    name = "semantic_scholar"

    def __init__(self, settings: Settings):
        self.settings = settings

    def search(self, query: str, limit: int) -> list[Paper]:
        fields = (
            "paperId,title,authors,year,abstract,url,externalIds,venue,"
            "citationCount,openAccessPdf,fieldsOfStudy,publicationTypes"
        )
        headers = {}
        api_key = os.getenv("S2_API_KEY")
        if api_key:
            headers["x-api-key"] = api_key
        data = request_json(
            "https://api.semanticscholar.org/graph/v1/paper/search?"
            + urlencode({"query": query, "limit": min(limit, 100), "fields": fields}),
            headers=headers,
            timeout=self.settings.request_timeout,
            retries=self.settings.max_retries,
        )
        papers: list[Paper] = []
        for item in data.get("data", []):
            external = item.get("externalIds") or {}
            oa = item.get("openAccessPdf") or {}
            publication_types = item.get("publicationTypes") or []
            papers.append(
                Paper(
                    title=_clean(item.get("title")),
                    authors=[
                        _clean(author.get("name"))
                        for author in item.get("authors") or []
                        if author.get("name")
                    ],
                    year=item.get("year"),
                    abstract=_clean(item.get("abstract")),
                    url=item.get("url") or "",
                    doi=_doi(external.get("DOI")),
                    arxiv_id=external.get("ArXiv") or "",
                    venue=_clean(item.get("venue")),
                    citation_count=int(item.get("citationCount") or 0),
                    source=self.name,
                    open_access_url=oa.get("url") or "",
                    categories=[
                        str(value) for value in item.get("fieldsOfStudy") or []
                    ],
                    publication_type=", ".join(
                        str(value) for value in publication_types
                    ),
                )
            )
        return [paper for paper in papers if paper.title]


class DblpRetriever:
    """CS-specific venue metadata from DBLP's publication search API."""

    name = "dblp"
    _rate_lock: ClassVar[threading.Lock] = threading.Lock()
    _last_request: ClassVar[float] = 0.0
    minimum_interval_seconds = 1.0

    def __init__(self, settings: Settings):
        self.settings = settings

    def search(self, query: str, limit: int) -> list[Paper]:
        self._respect_rate_limit()
        data = request_json(
            "https://dblp.org/search/publ/api?"
            + urlencode(
                {
                    "q": query,
                    "h": min(limit, 1000),
                    "f": 0,
                    "c": 0,
                    "format": "json",
                }
            ),
            timeout=self.settings.request_timeout,
            retries=self.settings.max_retries,
        )
        result = data.get("result") or {}
        hits = (result.get("hits") or {}).get("hit") or []
        if isinstance(hits, dict):
            hits = [hits]
        papers: list[Paper] = []
        for hit in hits:
            info = hit.get("info") or {}
            authors = _dblp_authors(info.get("authors"))
            ee_values = _as_strings(info.get("ee"))
            doi_value = str(info.get("doi") or "")
            if not doi_value:
                doi_url = next(
                    (value for value in ee_values if "doi.org/" in value.casefold()),
                    "",
                )
                doi_value = _doi(doi_url)
            year_text = str(info.get("year") or "")
            year = int(year_text) if year_text.isdigit() else None
            papers.append(
                Paper(
                    title=_clean(str(info.get("title") or "")),
                    authors=authors,
                    year=year,
                    abstract="",
                    url=str(info.get("url") or (ee_values[0] if ee_values else "")),
                    doi=_doi(doi_value),
                    venue=_clean(str(info.get("venue") or info.get("journal") or "")),
                    source=self.name,
                    open_access_url=next(
                        (
                            value
                            for value in ee_values
                            if "doi.org/" not in value.casefold()
                        ),
                        "",
                    ),
                    publication_type=str(info.get("type") or ""),
                )
            )
        return [paper for paper in papers if paper.title]

    @classmethod
    def _respect_rate_limit(cls) -> None:
        with cls._rate_lock:
            elapsed = time.monotonic() - cls._last_request
            if elapsed < cls.minimum_interval_seconds:
                time.sleep(cls.minimum_interval_seconds - elapsed)
            cls._last_request = time.monotonic()


def _dblp_authors(value: object) -> list[str]:
    if isinstance(value, dict):
        value = value.get("author", [])
    if not isinstance(value, list):
        value = [value] if value else []
    authors: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = item.get("text") or item.get("@pid") or ""
        else:
            name = item
        cleaned = _clean(str(name or ""))
        if cleaned:
            authors.append(cleaned)
    return authors


def _as_strings(value: object) -> list[str]:
    if isinstance(value, list):
        values = value
    else:
        values = [value] if value else []
    result: list[str] = []
    for item in values:
        if isinstance(item, dict):
            item = item.get("text") or item.get("url") or ""
        if item:
            result.append(str(item))
    return result


class FixtureRetriever:
    name = "fixture"

    def __init__(self, path: Path | str):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        records = payload["papers"] if isinstance(payload, dict) else payload
        self.papers = [Paper.from_dict(item) for item in records]

    def search(self, query: str, limit: int) -> list[Paper]:
        terms = _terms(query)
        scored = []
        for paper in self.papers:
            haystack = f"{paper.title} {paper.abstract}".lower()
            match = sum(term in haystack for term in terms)
            scored.append((match, paper))
        scored.sort(key=lambda item: (item[0], item[1].year or 0), reverse=True)
        return [paper for _, paper in scored[:limit]]


def bundled_demo_retriever() -> FixtureRetriever:
    """Load the packaged synthetic corpus used by the Web onboarding flow."""
    payload = json.loads(
        resources.files("paper_agent")
        .joinpath("data/demo_papers.json")
        .read_text(encoding="utf-8")
    )
    retriever = object.__new__(FixtureRetriever)
    records = payload["papers"] if isinstance(payload, dict) else payload
    retriever.papers = [Paper.from_dict(item) for item in records]
    return retriever


def _terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower())
        if token not in {"the", "and", "for", "with", "from", "review", "研究"}
    }


def _dedupe_key(paper: Paper) -> str:
    if paper.doi:
        return f"doi:{paper.doi}"
    if paper.arxiv_id:
        return f"arxiv:{paper.arxiv_id.lower()}"
    normalized = re.sub(r"\W+", "", paper.title.lower())
    return f"title:{normalized[:180]}"


def _merge(preferred: Paper, other: Paper) -> Paper:
    if not preferred.abstract and other.abstract:
        preferred.abstract = other.abstract
    if not preferred.doi:
        preferred.doi = other.doi
    if not preferred.arxiv_id:
        preferred.arxiv_id = other.arxiv_id
    if not preferred.open_access_url:
        preferred.open_access_url = other.open_access_url
    if not preferred.venue:
        preferred.venue = other.venue
    if not preferred.authors:
        preferred.authors = other.authors
    preferred.citation_count = max(preferred.citation_count, other.citation_count)
    if other.source and other.source not in preferred.source.split("+"):
        preferred.source = "+".join(filter(None, [preferred.source, other.source]))
    return preferred


def rank_papers(papers: list[Paper], question: str, limit: int) -> list[Paper]:
    terms = _terms(question)
    current_year = datetime.now(UTC).year
    for paper in papers:
        title = paper.title.lower()
        abstract = paper.abstract.lower()
        title_hits = sum(term in title for term in terms)
        abstract_hits = sum(term in abstract for term in terms)
        relevance = (3.0 * title_hits + abstract_hits) / max(len(terms), 1)
        citations = math.log1p(max(paper.citation_count, 0)) / 4
        recency = 0.0
        if paper.year:
            recency = max(0.0, 1.0 - (current_year - paper.year) / 20)
        completeness = (
            0.4 * bool(paper.abstract)
            + 0.2 * bool(paper.doi or paper.arxiv_id)
            + 0.2 * bool(paper.authors)
            + 0.2 * bool(paper.venue)
        )
        paper.score = round(relevance + citations + recency + completeness, 4)
    papers.sort(
        key=lambda paper: (paper.score, paper.citation_count, paper.year or 0),
        reverse=True,
    )
    selected = papers[:limit]
    for index, paper in enumerate(selected, 1):
        paper.paper_id = f"P{index:03d}"
    return selected


def search_all(
    retrievers: list[Retriever],
    queries: list[str],
    settings: Settings,
) -> tuple[list[Paper], list[str], list[SearchExecution]]:
    results: list[Paper] = []
    warnings: list[str] = []
    executions: list[SearchExecution] = []
    jobs = []

    def execute(retriever: Retriever, query: str) -> tuple[list[Paper], SearchExecution]:
        started = datetime.now(UTC)
        started_counter = time.perf_counter()
        status = "succeeded"
        error = ""
        papers: list[Paper] = []
        try:
            papers = retriever.search(query, settings.results_per_query)
        except Exception as exc:  # noqa: BLE001 - record isolated source failures
            status = "failed"
            error = str(exc)
        completed = datetime.now(UTC)
        endpoints = {
            "openalex": "https://api.openalex.org/works",
            "arxiv": "https://export.arxiv.org/api/query",
            "semantic_scholar": (
                "https://api.semanticscholar.org/graph/v1/paper/search"
            ),
            "dblp": "https://dblp.org/search/publ/api",
            "fixture": "local fixture",
        }
        execution = SearchExecution(
            source=retriever.name,
            query=query,
            limit=settings.results_per_query,
            started_at=started.isoformat(),
            completed_at=completed.isoformat(),
            duration_ms=max(0, round((time.perf_counter() - started_counter) * 1000)),
            status=status,
            result_count=len(papers),
            endpoint=endpoints.get(retriever.name, ""),
            error=error,
        )
        return papers, execution

    with ThreadPoolExecutor(
        max_workers=min(8, max(1, len(retrievers) * len(queries)))
    ) as pool:
        for retriever in retrievers:
            for query in queries:
                jobs.append(
                    (
                        retriever.name,
                        query,
                        pool.submit(execute, retriever, query),
                    )
                )
        for source, query, future in jobs:
            papers, execution = future.result()
            executions.append(execution)
            results.extend(papers)
            if execution.status == "failed":
                warnings.append(
                    f"{source} query {query!r} failed: {execution.error}"
                )

    deduped: dict[str, Paper] = {}
    for paper in results:
        key = _dedupe_key(paper)
        if key in deduped:
            deduped[key] = _merge(deduped[key], paper)
        else:
            deduped[key] = paper
    return list(deduped.values()), warnings, executions
