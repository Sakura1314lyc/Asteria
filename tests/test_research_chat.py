from __future__ import annotations

import unittest

from paper_agent.agent_profiles import get_agent_profile
from paper_agent.research_chat import answer_project_question, build_chat_context


class FakeDatabase:
    def project_evidence_context(self, project_id: str, *, limit: int = 20):
        del project_id, limit
        return [
            {
                "paper_id": "P001",
                "screening_status": "included",
                "title": "Database transaction throughput",
                "abstract": "Evaluation of distributed transaction throughput.",
                "year": 2024,
                "doi": "",
                "url": "https://example.test/p1",
                "evidence": {"findings": ["Higher transaction throughput"]},
            },
            {
                "paper_id": "P002",
                "screening_status": "included",
                "title": "Vision benchmark robustness",
                "abstract": "Image corruption benchmark.",
                "year": 2023,
                "doi": "",
                "url": "https://example.test/p2",
                "evidence": {"findings": ["Robustness varies"]},
            },
        ]

    def search_documents(self, project_id: str, query: str, *, limit: int = 10):
        del project_id, query, limit
        return []


class FakeLLM:
    def text(self, *, instructions: str, user_input: str) -> str:
        self.instructions = instructions
        self.user_input = user_input
        return "事务吞吐证据见 [P001]，错误来源见 [P999]。"


class FakeDatabaseWithDocument(FakeDatabase):
    def search_documents(self, project_id: str, query: str, *, limit: int = 10):
        del project_id, query, limit
        return [
            {
                "document_id": "doc-1",
                "filename": "citation-audit.md",
                "page": 2,
                "content": "Citation precision and entailment require separate checks.",
            }
        ]


class ResearchChatTests(unittest.TestCase):
    def test_context_ranks_question_relevant_paper_first(self) -> None:
        context, sources = build_chat_context(
            FakeDatabase(),
            "project",
            "transaction throughput",
        )
        self.assertLess(context.index("P001"), context.index("P002"))
        self.assertEqual(sources[0]["id"], "P001")

    def test_unknown_model_citation_is_flagged(self) -> None:
        answer, sources = answer_project_question(
            database=FakeDatabase(),
            project_id="project",
            question="transaction throughput",
            history=[],
            agent=get_agent_profile("project_qa"),
            llm=FakeLLM(),
            demo=False,
        )
        self.assertIn("项目中不存在的来源", answer)
        self.assertEqual([source["id"] for source in sources], ["P001"])

    def test_demo_answer_keeps_a_matching_full_text_source(self) -> None:
        answer, sources = answer_project_question(
            database=FakeDatabaseWithDocument(),
            project_id="project",
            question="citation precision entailment",
            history=[],
            agent=get_agent_profile("project_qa"),
            llm=None,
            demo=True,
        )
        self.assertIn("[全文:citation-audit.md p.2]", answer)
        self.assertEqual(sources[-1]["kind"], "document")


if __name__ == "__main__":
    unittest.main()
