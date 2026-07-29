from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from .database import Database


def export_project(
    database: Database,
    project_id: str,
    destination: Path | str,
) -> Path:
    project = database.require_project(project_id)
    target = Path(destination).resolve()
    if target.suffix.lower() != ".zip":
        target = target.with_suffix(".zip")
    target.parent.mkdir(parents=True, exist_ok=True)
    papers = database.list_project_papers(project_id)
    runs = database.list_runs(project_id)
    reports = database.list_reports(project_id)
    documents = database.list_documents(project_id)
    manifest: list[dict[str, str | int]] = []

    def add_file(archive: ZipFile, source: Path, arcname: str) -> None:
        if not source.is_file():
            return
        archive.write(source, arcname)
        manifest.append(
            {
                "path": arcname,
                "bytes": source.stat().st_size,
                "sha256": _sha256(source),
            }
        )

    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "project.json",
            json.dumps(project.to_dict(), ensure_ascii=False, indent=2),
        )
        archive.writestr(
            "papers.json",
            json.dumps(
                [
                    {
                        **{key: value for key, value in row.items() if key != "paper"},
                        "paper": row["paper"].to_dict(),
                    }
                    for row in papers
                ],
                ensure_ascii=False,
                indent=2,
            ),
        )
        archive.writestr("runs.json", json.dumps(runs, ensure_ascii=False, indent=2))
        archive.writestr(
            "reports.json",
            json.dumps(reports, ensure_ascii=False, indent=2),
        )
        for run in runs:
            run_dir = Path(run["run_dir"]) if run["run_dir"] else None
            if not run_dir or not run_dir.is_dir():
                continue
            for source in run_dir.iterdir():
                if source.is_file() and source.suffix.lower() in {
                    ".json",
                    ".jsonl",
                    ".md",
                    ".bib",
                    ".csv",
                    ".graphml",
                }:
                    add_file(
                        archive,
                        source,
                        f"runs/{run['id']}/{source.name}",
                    )
        for document in documents:
            for field, label in (
                ("source_path", "source"),
                ("text_path", "extracted.txt"),
            ):
                source = Path(document[field])
                filename = source.name if label == "source" else label
                add_file(
                    archive,
                    source,
                    f"documents/{document['id']}/{filename}",
                )
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "project_id": project_id,
                    "files": manifest,
                    "note": (
                        "Checksums cover stored artifact files. JSON metadata "
                        "written directly into the archive is not included."
                    ),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
