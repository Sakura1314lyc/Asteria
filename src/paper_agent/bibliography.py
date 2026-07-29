from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .models import Paper

SUPPORTED_BIBLIOGRAPHY_SUFFIXES = {".ris", ".bib", ".json"}
MAX_BIBLIOGRAPHY_RECORDS = 10_000
MAX_IMPORT_WARNINGS = 100


class BibliographyError(ValueError):
    pass


@dataclass(slots=True)
class BibliographyParseResult:
    format: str
    papers: list[Paper]
    skipped: int = 0
    duplicates_in_file: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BibliographyImportResult:
    filename: str
    format: str
    parsed: int
    added: int
    already_present: int
    enriched: int
    skipped: int
    duplicates_in_file: int
    evidence_ids: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_bibliography(data: bytes, filename: str) -> BibliographyParseResult:
    safe_name = Path(filename).name
    suffix = Path(safe_name).suffix.lower()
    if suffix not in SUPPORTED_BIBLIOGRAPHY_SUFFIXES:
        raise BibliographyError("Expected a .ris, .bib, or .json bibliography file")
    text, decoding_warning = _decode(data)
    if not text.strip():
        raise BibliographyError("Bibliography file is empty")
    warnings = [decoding_warning] if decoding_warning else []
    if suffix == ".ris":
        values, skipped, parser_warnings = _parse_ris(text)
        format_name = "ris"
    elif suffix == ".bib":
        values, skipped, parser_warnings = _parse_bibtex(text)
        format_name = "bibtex"
    else:
        values, skipped, parser_warnings = _parse_csl_json(text)
        format_name = "csl-json"
    warnings.extend(parser_warnings)
    if len(values) > MAX_BIBLIOGRAPHY_RECORDS:
        raise BibliographyError(
            f"Bibliography contains more than {MAX_BIBLIOGRAPHY_RECORDS} records"
        )
    papers, duplicate_count = _deduplicate(values)
    if not papers:
        raise BibliographyError("No valid bibliography records with titles were found")
    return BibliographyParseResult(
        format=format_name,
        papers=papers,
        skipped=skipped,
        duplicates_in_file=duplicate_count,
        warnings=warnings[:MAX_IMPORT_WARNINGS],
    )


def merge_papers(current: Paper, incoming: Paper) -> tuple[Paper, bool]:
    """Enrich an existing record without erasing stronger stored metadata."""

    enriched = any(
        not old and bool(new)
        for old, new in (
            (current.authors, incoming.authors),
            (current.year, incoming.year),
            (current.abstract, incoming.abstract),
            (current.url, incoming.url),
            (current.doi, incoming.doi),
            (current.arxiv_id, incoming.arxiv_id),
            (current.venue, incoming.venue),
            (current.open_access_url, incoming.open_access_url),
            (current.publication_type, incoming.publication_type),
        )
    )
    return (
        Paper(
            title=current.title or incoming.title,
            authors=current.authors or incoming.authors,
            year=current.year or incoming.year,
            abstract=current.abstract or incoming.abstract,
            url=current.url or incoming.url,
            doi=current.doi or incoming.doi,
            arxiv_id=current.arxiv_id or incoming.arxiv_id,
            venue=current.venue or incoming.venue,
            citation_count=max(current.citation_count, incoming.citation_count),
            source=current.source or incoming.source,
            open_access_url=current.open_access_url or incoming.open_access_url,
            score=max(current.score, incoming.score),
            categories=list(dict.fromkeys(current.categories + incoming.categories)),
            publication_type=(
                current.publication_type or incoming.publication_type
            ),
            code_urls=list(dict.fromkeys(current.code_urls + incoming.code_urls)),
            dataset_urls=list(
                dict.fromkeys(current.dataset_urls + incoming.dataset_urls)
            ),
        ),
        enriched,
    )


def _decode(data: bytes) -> tuple[str, str]:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), ""
    try:
        return data.decode("utf-8-sig"), ""
    except UnicodeDecodeError:
        return (
            data.decode("cp1252", errors="replace"),
            "Input was not UTF-8; decoded as Windows-1252 and may need review.",
        )


def _parse_ris(text: str) -> tuple[list[Paper], int, list[str]]:
    records: list[dict[str, list[str]]] = []
    current: dict[str, list[str]] = {}
    last_tag = ""
    warnings: list[str] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip("\r\n")
        match = re.match(r"^([A-Z0-9]{2})  - ?(.*)$", line)
        if match:
            tag, value = match.groups()
            if tag == "TY" and current:
                records.append(current)
                current = {}
            current.setdefault(tag, []).append(value.strip())
            last_tag = tag
            if tag == "ER":
                records.append(current)
                current = {}
                last_tag = ""
        elif line.strip() and last_tag and current.get(last_tag):
            current[last_tag][-1] = f"{current[last_tag][-1]} {line.strip()}".strip()
        elif line.strip():
            _warn(warnings, f"RIS line {line_number} was not recognized")
    if current:
        records.append(current)

    papers: list[Paper] = []
    skipped = 0
    for index, record in enumerate(records, start=1):
        title = _first(record, "TI", "T1", "CT")
        if not title:
            skipped += 1
            _warn(warnings, f"RIS record {index} has no title and was skipped")
            continue
        url = _first(record, "UR", "L1", "L2")
        doi = _normalize_doi(_first(record, "DO", "DI"))
        publication_type = _first(record, "TY").lower()
        arxiv_id = _arxiv_id(
            _first(record, "AN", "M3"),
            doi,
            url,
        )
        papers.append(
            Paper(
                title=_clean_text(title),
                authors=[
                    _clean_text(value)
                    for tag in ("AU", "A1")
                    for value in record.get(tag, [])
                    if value.strip()
                ],
                year=_year(_first(record, "PY", "Y1", "DA")),
                abstract=_clean_text(_first(record, "AB", "N2")),
                url=url,
                doi=doi,
                arxiv_id=arxiv_id,
                venue=_clean_text(_first(record, "JO", "JF", "T2", "JA")),
                source="import:ris",
                open_access_url=url,
                categories=[
                    _clean_text(value)
                    for value in record.get("KW", [])
                    if value.strip()
                ],
                publication_type=publication_type,
            )
        )
    return papers, skipped, warnings


def _parse_bibtex(text: str) -> tuple[list[Paper], int, list[str]]:
    papers: list[Paper] = []
    skipped = 0
    warnings: list[str] = []
    entries = list(_bibtex_entries(text, warnings))
    for index, (entry_type, body) in enumerate(entries, start=1):
        if entry_type in {"comment", "preamble", "string"}:
            continue
        parts = _split_top_level(body, ",")
        fields: dict[str, str] = {}
        for raw_field in parts[1:]:
            pair = _split_once_top_level(raw_field, "=")
            if not pair:
                continue
            key, value = pair
            fields[key.strip().lower()] = _bibtex_value(value)
        title = _clean_latex(fields.get("title", ""))
        if not title:
            skipped += 1
            _warn(warnings, f"BibTeX entry {index} has no title and was skipped")
            continue
        url = fields.get("url", "").strip()
        doi = _normalize_doi(fields.get("doi", ""))
        arxiv_id = _arxiv_id(
            fields.get("eprint", ""),
            fields.get("archiveprefix", ""),
            doi,
            url,
        )
        authors = [
            _clean_latex(author)
            for author in _split_bibtex_authors(fields.get("author", ""))
            if _clean_latex(author)
        ]
        keywords = re.split(r"\s*[,;]\s*", fields.get("keywords", ""))
        papers.append(
            Paper(
                title=title,
                authors=authors,
                year=_year(fields.get("year", "") or fields.get("date", "")),
                abstract=_clean_latex(fields.get("abstract", "")),
                url=url,
                doi=doi,
                arxiv_id=arxiv_id,
                venue=_clean_latex(
                    fields.get("journal", "")
                    or fields.get("booktitle", "")
                    or fields.get("journaltitle", "")
                    or fields.get("publisher", "")
                ),
                source="import:bibtex",
                open_access_url=url,
                categories=[
                    _clean_latex(value) for value in keywords if value.strip()
                ],
                publication_type=entry_type,
            )
        )
    return papers, skipped, warnings


def _parse_csl_json(text: str) -> tuple[list[Paper], int, list[str]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BibliographyError(
            f"Invalid CSL JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        records = payload["items"]
    elif isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = [payload]
    else:
        raise BibliographyError("CSL JSON must be an object or an array of objects")

    papers: list[Paper] = []
    skipped = 0
    warnings: list[str] = []
    for index, raw in enumerate(records, start=1):
        if not isinstance(raw, dict):
            skipped += 1
            _warn(warnings, f"CSL JSON item {index} is not an object and was skipped")
            continue
        title = _string(raw.get("title"))
        if not title:
            skipped += 1
            _warn(warnings, f"CSL JSON item {index} has no title and was skipped")
            continue
        authors = []
        for author in raw.get("author", []):
            if not isinstance(author, dict):
                continue
            literal = _string(author.get("literal"))
            name = literal or " ".join(
                value
                for value in (
                    _string(author.get("given")),
                    _string(author.get("family")),
                )
                if value
            )
            if name:
                authors.append(name)
        url = _string(raw.get("URL") or raw.get("url"))
        doi = _normalize_doi(_string(raw.get("DOI") or raw.get("doi")))
        archive = _string(raw.get("archive"))
        archive_location = _string(
            raw.get("archive_location") or raw.get("archive-location")
        )
        keyword_value = raw.get("keyword")
        keywords = (
            [_string(value) for value in keyword_value]
            if isinstance(keyword_value, list)
            else re.split(r"\s*[,;]\s*", _string(keyword_value))
        )
        papers.append(
            Paper(
                title=_clean_text(title),
                authors=authors,
                year=_csl_year(raw),
                abstract=_clean_text(_string(raw.get("abstract"))),
                url=url,
                doi=doi,
                arxiv_id=_arxiv_id(archive, archive_location, doi, url),
                venue=_clean_text(_string(raw.get("container-title"))),
                source="import:csl-json",
                open_access_url=url,
                categories=[value for value in keywords if value],
                publication_type=_string(raw.get("type")),
            )
        )
    return papers, skipped, warnings


def _bibtex_entries(
    text: str,
    warnings: list[str],
):
    cursor = 0
    while True:
        start = text.find("@", cursor)
        if start < 0:
            return
        type_match = re.match(r"@([A-Za-z]+)\s*([\{\(])", text[start:])
        if not type_match:
            cursor = start + 1
            continue
        entry_type = type_match.group(1).lower()
        opener = type_match.group(2)
        closer = "}" if opener == "{" else ")"
        body_start = start + type_match.end()
        depth = 1
        brace_depth = 0
        quoted = False
        escaped = False
        index = body_start
        while index < len(text):
            char = text[index]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = not quoted
            elif not quoted:
                if opener == "(" and char == "{":
                    brace_depth += 1
                elif opener == "(" and char == "}":
                    brace_depth = max(0, brace_depth - 1)
                elif char == opener and brace_depth == 0:
                    depth += 1
                elif char == closer and brace_depth == 0:
                    depth -= 1
                    if depth == 0:
                        yield entry_type, text[body_start:index]
                        cursor = index + 1
                        break
            index += 1
        else:
            _warn(warnings, f"Unclosed BibTeX @{entry_type} entry was ignored")
            return


def _split_top_level(value: str, separator: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quoted = False
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            quoted = not quoted
            continue
        if quoted:
            continue
        if char in "{(":
            depth += 1
        elif char in "})":
            depth = max(0, depth - 1)
        elif char == separator and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    parts.append(value[start:].strip())
    return parts


def _split_once_top_level(value: str, separator: str) -> tuple[str, str] | None:
    parts = _split_top_level(value, separator)
    if len(parts) < 2:
        return None
    return parts[0], separator.join(parts[1:])


def _bibtex_value(value: str) -> str:
    parts = _split_top_level(value.strip(), "#")
    return "".join(_strip_wrapping(part.strip()) for part in parts)


def _strip_wrapping(value: str) -> str:
    while len(value) >= 2 and (
        (value[0] == "{" and value[-1] == "}")
        or (value[0] == '"' and value[-1] == '"')
    ):
        value = value[1:-1].strip()
    return value


def _split_bibtex_authors(value: str) -> list[str]:
    authors: list[str] = []
    start = 0
    depth = 0
    lowered = value.casefold()
    index = 0
    while index < len(value):
        char = value[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif depth == 0 and lowered[index : index + 5] == " and ":
            authors.append(value[start:index].strip())
            start = index + 5
            index += 4
        index += 1
    authors.append(value[start:].strip())
    return [author for author in authors if author]


def _clean_latex(value: str) -> str:
    value = value.replace(r"\&", "&").replace(r"\_", "_").replace(r"\%", "%")
    value = re.sub(r"\\(?:textit|textbf|emph|url|href)\s*\{([^{}]*)\}", r"\1", value)
    value = re.sub(r"\\[A-Za-z]+\*?", "", value)
    value = value.replace("{", "").replace("}", "")
    return _clean_text(value)


def _deduplicate(papers: list[Paper]) -> tuple[list[Paper], int]:
    unique: dict[str, Paper] = {}
    duplicates = 0
    for paper in papers:
        key = _paper_key(paper)
        if key in unique:
            unique[key], _ = merge_papers(unique[key], paper)
            duplicates += 1
        else:
            unique[key] = paper
    return list(unique.values()), duplicates


def _paper_key(paper: Paper) -> str:
    if paper.doi:
        return f"doi:{paper.doi.casefold().strip()}"
    if paper.arxiv_id:
        return f"arxiv:{paper.arxiv_id.casefold().strip()}"
    normalized = re.sub(r"\W+", "", paper.title.casefold())
    return f"title:{normalized[:200]}"


def _first(record: dict[str, list[str]], *tags: str) -> str:
    for tag in tags:
        values = record.get(tag)
        if values:
            return values[0].strip()
    return ""


def _normalize_doi(value: str) -> str:
    result = value.strip()
    result = re.sub(r"^(?:doi:\s*)", "", result, flags=re.IGNORECASE)
    result = re.sub(
        r"^https?://(?:dx\.)?doi\.org/",
        "",
        result,
        flags=re.IGNORECASE,
    )
    return result.rstrip(" .").casefold()


def _arxiv_id(*values: str) -> str:
    for value in values:
        match = re.search(
            r"(?:arxiv[:./\s])(?:abs/|pdf/)?([a-z-]+/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?",
            value,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1).casefold()
    return ""


def _year(value: str) -> int | None:
    match = re.search(r"\b(18|19|20|21)\d{2}\b", value)
    return int(match.group(0)) if match else None


def _csl_year(record: dict[str, Any]) -> int | None:
    for key in ("issued", "published", "published-print", "published-online"):
        value = record.get(key)
        if not isinstance(value, dict):
            continue
        parts = value.get("date-parts")
        if (
            isinstance(parts, list)
            and parts
            and isinstance(parts[0], list)
            and parts[0]
        ):
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                pass
        raw = _string(value.get("raw"))
        if raw_year := _year(raw):
            return raw_year
    return _year(_string(record.get("issued")))


def _string(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return next((_string(item) for item in value if _string(item)), "")
    if value is None:
        return ""
    return str(value).strip()


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _warn(warnings: list[str], message: str) -> None:
    if len(warnings) < MAX_IMPORT_WARNINGS:
        warnings.append(message)
