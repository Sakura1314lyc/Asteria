from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paper_agent.bibliography import BibliographyError, parse_bibliography
from paper_agent.config import Settings
from paper_agent.domain import ScreeningStatus
from paper_agent.models import Paper
from paper_agent.workbench import ResearchWorkbench


class BibliographyParserTests(unittest.TestCase):
    def test_ris_maps_fields_and_deduplicates_doi(self) -> None:
        ris = """TY  - CONF
TI  - Evidence-Grounded Research Agents
AU  - Doe, Jane
PY  - 2025/03/01
DO  - https://doi.org/10.5555/Agent.1
KW  - research agents
ER  -
TY  - CONF
TI  - Evidence-Grounded Research Agents
AU  - Doe, Jane
AB  - A reproducible evaluation of citation-grounded agents.
DO  - 10.5555/agent.1
ER  -
"""
        result = parse_bibliography(ris.encode(), "library.ris")
        self.assertEqual(result.format, "ris")
        self.assertEqual(len(result.papers), 1)
        self.assertEqual(result.duplicates_in_file, 1)
        paper = result.papers[0]
        self.assertEqual(paper.doi, "10.5555/agent.1")
        self.assertEqual(paper.year, 2025)
        self.assertIn("reproducible evaluation", paper.abstract)

    def test_bibtex_handles_nested_braces_and_multiple_authors(self) -> None:
        bibtex = r"""
@inproceedings{agent2025,
  title = {{Evidence-Grounded} Agents: A {CS} Study},
  author = {Doe, Jane and {ACM Research Group}},
  booktitle = {Proceedings of the Agent Systems Conference},
  year = {2025},
  doi = {https://doi.org/10.5555/agent.2},
  keywords = {agents; reproducibility}
}
"""
        result = parse_bibliography(bibtex.encode(), "library.bib")
        paper = result.papers[0]
        self.assertEqual(paper.title, "Evidence-Grounded Agents: A CS Study")
        self.assertEqual(paper.authors, ["Doe, Jane", "ACM Research Group"])
        self.assertEqual(paper.publication_type, "inproceedings")
        self.assertEqual(paper.doi, "10.5555/agent.2")

    def test_parenthesized_bibtex_keeps_parentheses_inside_braces(self) -> None:
        bibtex = r"""
@article(agent2025,
  title = {Agent Evaluation (A Reproducibility Study)},
  author = {Doe, Jane},
  year = {2025}
)
"""
        result = parse_bibliography(bibtex.encode(), "library.bib")
        self.assertEqual(
            result.papers[0].title,
            "Agent Evaluation (A Reproducibility Study)",
        )
        self.assertEqual(result.papers[0].year, 2025)

    def test_csl_json_maps_date_container_and_arxiv(self) -> None:
        payload = [
            {
                "id": "paper-1",
                "type": "article-journal",
                "title": "Auditing Citation Support",
                "author": [
                    {"given": "Lin", "family": "Chen"},
                    {"literal": "Asteria Research"},
                ],
                "issued": {"date-parts": [[2024, 8, 1]]},
                "container-title": "Journal of Research Agents",
                "DOI": "10.5555/audit.1",
                "URL": "https://example.test/audit",
            },
            {"id": "missing-title", "type": "article"},
        ]
        result = parse_bibliography(
            json.dumps(payload).encode(),
            "library.json",
        )
        self.assertEqual(len(result.papers), 1)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.papers[0].authors[1], "Asteria Research")
        self.assertEqual(result.papers[0].venue, "Journal of Research Agents")
        self.assertEqual(result.papers[0].year, 2024)

    def test_rejects_invalid_or_empty_bibliographies(self) -> None:
        with self.assertRaises(BibliographyError):
            parse_bibliography(b"not-json", "library.json")
        with self.assertRaises(BibliographyError):
            parse_bibliography(b"", "library.ris")
        with self.assertRaises(BibliographyError):
            parse_bibliography(b"data", "library.txt")

    def test_record_limit_is_applied_before_deduplication(self) -> None:
        repeated = b"""TY  - JOUR
TI  - Same paper
DO  - 10.5555/same
ER  -
TY  - JOUR
TI  - Same paper
DO  - 10.5555/same
ER  -
TY  - JOUR
TI  - Same paper
DO  - 10.5555/same
ER  -
"""
        with (
            patch("paper_agent.bibliography.MAX_BIBLIOGRAPHY_RECORDS", 2),
            self.assertRaises(BibliographyError),
        ):
            parse_bibliography(repeated, "library.ris")


class BibliographyImportTests(unittest.TestCase):
    def test_global_upsert_enriches_without_erasing_and_upgrades_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workbench = ResearchWorkbench(
                Settings(
                    data_root=root / "data",
                    database_path=root / "workbench.db",
                )
            )
            first_id = workbench.database.upsert_paper(
                Paper(
                    title="Stable Metadata Study",
                    authors=["Jane Doe"],
                    abstract="Keep this complete abstract.",
                    citation_count=12,
                    source="import:ris",
                )
            )
            second_id = workbench.database.upsert_paper(
                Paper(
                    title="Stable Metadata Study",
                    doi="10.5555/stable",
                    citation_count=3,
                    source="openalex",
                )
            )
            self.assertEqual(second_id, first_id)

            project = workbench.create_project(name="Upsert", topic="metadata")
            workbench.database.attach_paper(project.id, first_id, "P001")
            stored = workbench.database.list_project_papers(project.id)[0]["paper"]
            self.assertEqual(stored.authors, ["Jane Doe"])
            self.assertEqual(stored.abstract, "Keep this complete abstract.")
            self.assertEqual(stored.doi, "10.5555/stable")
            self.assertEqual(stored.citation_count, 12)

    def test_import_is_idempotent_and_preserves_existing_metadata_and_status(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workbench = ResearchWorkbench(
                Settings(
                    data_root=root / "data",
                    database_path=root / "workbench.db",
                )
            )
            project = workbench.create_project(name="Import", topic="agents")
            existing_id = workbench.database.upsert_paper(
                Paper(
                    title="Existing Agent Study",
                    abstract="Detailed existing abstract that must not be erased.",
                    doi="10.5555/existing",
                    source="openalex",
                )
            )
            workbench.database.attach_paper(
                project.id,
                existing_id,
                "P001",
                status=ScreeningStatus.INCLUDED,
            )
            ris = """TY  - JOUR
TI  - Existing Agent Study
AU  - Doe, Jane
PY  - 2024
DO  - 10.5555/existing
ER  -
TY  - CONF
TI  - Newly Imported Agent Study
AU  - Chen, Lin
PY  - 2025
DO  - 10.5555/new
ER  -
"""
            first = workbench.import_bibliography(
                project.id,
                data=ris.encode(),
                filename="library.ris",
            )
            self.assertEqual(first.added, 1)
            self.assertEqual(first.already_present, 1)
            self.assertEqual(first.evidence_ids, ["P002"])
            self.assertGreaterEqual(first.enriched, 1)

            rows = workbench.database.list_project_papers(project.id)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["screening_status"], ScreeningStatus.INCLUDED)
            self.assertIn("must not be erased", rows[0]["paper"].abstract)
            self.assertEqual(rows[0]["paper"].authors, ["Doe, Jane"])

            second = workbench.import_bibliography(
                project.id,
                data=ris.encode(),
                filename="library.ris",
            )
            self.assertEqual(second.added, 0)
            self.assertEqual(second.already_present, 2)
            self.assertEqual(
                len(workbench.database.list_project_papers(project.id)),
                2,
            )


if __name__ == "__main__":
    unittest.main()
