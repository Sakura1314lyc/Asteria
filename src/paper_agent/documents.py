from __future__ import annotations

import hashlib
import mimetypes
import re
import shutil
from pathlib import Path
from typing import ClassVar

from .database import Database
from .domain import DocumentRecord, new_id


class DocumentError(RuntimeError):
    pass


class DocumentStore:
    """Immutable source-file storage plus page-aware FTS5 indexing."""

    SUPPORTED_SUFFIXES: ClassVar[set[str]] = {".pdf", ".txt", ".md"}

    def __init__(self, root: Path | str, database: Database):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = database

    def ingest(
        self,
        *,
        project_id: str,
        source: Path | str,
        paper_id: int | None = None,
        filename: str | None = None,
    ) -> DocumentRecord:
        self.database.require_project(project_id)
        source_path = Path(source).resolve()
        if not source_path.is_file():
            raise DocumentError(f"Document not found: {source_path}")
        suffix = source_path.suffix.lower()
        if suffix not in self.SUPPORTED_SUFFIXES:
            raise DocumentError(
                f"Unsupported document type {suffix!r}; expected PDF, TXT, or MD"
            )
        display_name = Path(filename).name if filename else source_path.name
        if not display_name:
            display_name = source_path.name
        digest = _sha256(source_path)
        existing = self.database.get_document_by_hash(project_id, digest)
        if existing:
            return DocumentRecord(
                id=existing["id"],
                project_id=existing["project_id"],
                paper_id=existing["paper_id"],
                filename=existing["filename"],
                sha256=existing["sha256"],
                media_type=existing["media_type"],
                source_path=existing["source_path"],
                text_path=existing["text_path"],
                page_count=existing["page_count"],
                created_at=existing["created_at"],
            )

        document_id = new_id("doc")
        document_dir = self.root / project_id / "documents" / document_id
        document_dir.mkdir(parents=True, exist_ok=False)
        stored_source = document_dir / f"source{suffix}"
        shutil.copy2(source_path, stored_source)
        pages = self._extract_pages(stored_source)
        extracted_path = document_dir / "extracted.txt"
        extracted_path.write_text(
            "\n\n".join(
                f"--- PAGE {page_number} ---\n{text}" for page_number, text in pages
            ),
            encoding="utf-8",
        )
        chunks = _chunk_pages(pages)
        record = DocumentRecord(
            id=document_id,
            project_id=project_id,
            paper_id=paper_id,
            filename=display_name,
            sha256=digest,
            media_type=mimetypes.guess_type(display_name)[0]
            or "application/octet-stream",
            source_path=str(stored_source),
            text_path=str(extracted_path),
            page_count=len(pages),
        )
        self.database.add_document(record, chunks)
        return record

    def _extract_pages(self, path: Path) -> list[tuple[int, str]]:
        if path.suffix.lower() != ".pdf":
            text = path.read_text(encoding="utf-8", errors="replace")
            return [(1, _normalize_text(text))]
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise DocumentError(
                "PDF support requires `pip install 'paper-research-agent[pdf]'`"
            ) from exc
        try:
            reader = PdfReader(str(path))
            pages = [
                (index, _normalize_text(page.extract_text() or ""))
                for index, page in enumerate(reader.pages, 1)
            ]
        except Exception as exc:
            raise DocumentError(f"Could not extract PDF text: {exc}") from exc
        if not any(text for _, text in pages):
            raise DocumentError(
                "The PDF contains no extractable text; OCR is required."
            )
        return pages

    def search(
        self,
        project_id: str,
        query: str,
        *,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        return self.database.search_documents(project_id, query, limit=limit)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalize_text(value: str) -> str:
    value = value.replace("\x00", "")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _chunk_pages(
    pages: list[tuple[int, str]],
    *,
    target_chars: int = 1800,
    overlap_chars: int = 250,
) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    chunk_index = 0
    for page, text in pages:
        paragraphs = [
            item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()
        ]
        buffer = ""
        for paragraph in paragraphs:
            candidate = f"{buffer}\n\n{paragraph}".strip()
            if buffer and len(candidate) > target_chars:
                chunks.append((page, chunk_index, buffer))
                chunk_index += 1
                overlap = buffer[-overlap_chars:]
                buffer = f"{overlap}\n\n{paragraph}".strip()
            else:
                buffer = candidate
        if buffer:
            chunks.append((page, chunk_index, buffer))
            chunk_index += 1
    return chunks
