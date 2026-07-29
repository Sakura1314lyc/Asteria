from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paper_agent.config import Settings
from paper_agent.cs_evidence import (
    analyze_cs_evidence,
    assess_reproducibility,
    write_cs_artifacts,
)
from paper_agent.cs_taxonomy import CSTaxonomy
from paper_agent.models import EvidenceCard, Paper, ResearchState
from paper_agent.retrievers import DblpRetriever


def cs_card(paper_id: str = "P001") -> EvidenceCard:
    return EvidenceCard(
        paper_id=paper_id,
        relevance="direct",
        objective="Evaluate a retrieval model.",
        methods="Controlled benchmark experiments.",
        data_or_sample="Two public datasets.",
        findings=["The method improves retrieval accuracy."],
        limitations=["Evaluation is limited to English data."],
        confidence="medium",
        cs_evidence={
            "contribution_type": "algorithm",
            "problem": "Improve dense retrieval.",
            "core_contribution": "A new training objective.",
            "approach": "Contrastive learning with hard negatives.",
            "datasets": ["MS MARCO", "BEIR"],
            "tasks": ["passage retrieval"],
            "baselines": ["BM25", "DPR"],
            "metrics": ["MRR", "nDCG@10"],
            "headline_results": ["Higher nDCG@10 on BEIR."],
            "ablations": ["without hard negatives"],
            "compute": "4 A100 GPUs for 12 hours",
            "implementation_details": (
                "The model uses a fixed seed, documented optimizer, batch size, "
                "learning rate, and public configuration files."
            ),
            "code_availability": "yes",
            "code_urls": ["https://github.com/example/retrieval"],
            "dataset_urls": ["https://example.org/data"],
            "threats_to_validity": ["English-only evaluation"],
            "security_ethics": [],
            "evidence_level": "controlled_experiment",
        },
    )


class ComputerScienceTests(unittest.TestCase):
    def test_taxonomy_classifies_multiple_cs_directions(self) -> None:
        taxonomy = CSTaxonomy.load()
        ai = taxonomy.classify_text(
            "large language model reinforcement learning benchmark"
        )
        security = taxonomy.classify_text(
            "malware detection and side channel attack defense"
        )
        self.assertEqual(ai[0].domain_id, "artificial_intelligence")
        self.assertEqual(security[0].domain_id, "security_privacy")

    def test_query_expansion_adds_benchmark_and_validity_queries(self) -> None:
        taxonomy = CSTaxonomy.load()
        queries, domains = taxonomy.expand_queries(
            "distributed systems",
            [{"query": "distributed systems survey", "purpose": "overview"}],
            max_queries=5,
        )
        text = " ".join(item["query"] for item in queries)
        self.assertIn("benchmark evaluation reproducibility", text)
        self.assertIn("limitations threats to validity", text)
        self.assertEqual(domains[0].domain_id, "computer_systems")

    @patch("paper_agent.retrievers.request_json")
    def test_dblp_retriever_parses_cs_venue_metadata(self, request_json) -> None:
        request_json.return_value = {
            "result": {
                "hits": {
                    "hit": [
                        {
                            "info": {
                                "authors": {
                                    "author": [
                                        {"text": "Ada Example"},
                                        {"text": "Lin Tester"},
                                    ]
                                },
                                "title": "A &amp; B: Systems.",
                                "venue": "SOSP",
                                "year": "2025",
                                "type": "Conference and Workshop Papers",
                                "doi": "10.1000/example",
                                "url": "https://dblp.org/rec/conf/sosp/example",
                            }
                        }
                    ]
                }
            }
        }
        with patch.object(DblpRetriever, "minimum_interval_seconds", 0):
            papers = DblpRetriever(Settings()).search("systems", 5)
        self.assertEqual(papers[0].venue, "SOSP")
        self.assertEqual(papers[0].authors[0], "Ada Example")
        self.assertEqual(papers[0].doi, "10.1000/example")
        self.assertEqual(papers[0].title, "A & B: Systems.")

    def test_reproducibility_and_cs_artifacts(self) -> None:
        paper = Paper(
            paper_id="P001",
            title="Dense Retrieval with Hard Negatives",
            authors=["A. Author"],
            year=2025,
            abstract="A" * 500,
            doi="10.1/retrieval",
            venue="SIGIR",
            categories=["cs.IR", "cs.LG"],
        )
        card = cs_card()
        assessment = assess_reproducibility(paper, card)
        self.assertGreaterEqual(assessment.overall, 0.7)
        state = ResearchState(
            run_id="run_test",
            topic="dense retrieval",
            question="How is dense retrieval evaluated?",
            language="en",
            papers=[paper],
            evidence=[card],
        )
        analysis = analyze_cs_evidence(state)
        self.assertIn("data_management", analysis["landscape"]["domains"])
        self.assertEqual(
            analysis["benchmark_catalog"]["datasets"][0]["name"],
            "MS MARCO",
        )
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            write_cs_artifacts(run_dir, state)
            self.assertTrue((run_dir / "cs_evidence_matrix.csv").exists())
            self.assertTrue((run_dir / "research_agenda.json").exists())


if __name__ == "__main__":
    unittest.main()
