from __future__ import annotations

import unittest

from operational_guidance.diao.provider import DIAOKnowledgeProvider, GUIDANCE_NOT_SUPPORTED


SCENARIOS = {
    "B01.147": {
        "official": "B 01.147 AMEAÇA",
        "paraphrase": "intimidação por gesto ou palavra com promessa de mal injusto e grave",
        "colloquial": "ele disse que vai me pegar e fazer mal",
        "facts": "pessoa ameaçou a vítima verbalmente e causou medo",
        "ambiguous": "recebi palavras que me fizeram temer um mal grave",
    },
    "C01.155": {
        "official": "C 01.155 FURTO",
        "paraphrase": "subtração de coisa móvel alheia sem violência",
        "colloquial": "pegaram meu celular escondido sem eu ver",
        "facts": "objeto telefone foi subtraído sem grave ameaça ou agressão",
        "ambiguous": "meu objeto sumiu do local e ninguém viu",
    },
    "C01.157": {
        "official": "C 01.157 ROUBO",
        "paraphrase": "subtração de coisa móvel mediante grave ameaça ou violência",
        "colloquial": "apontou uma arma e levou meu telefone",
        "facts": "autor usou violência contra a vítima para levar pertences",
        "ambiguous": "levaram os pertences durante ameaça e resistência",
    },
}


class DIAORetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.provider = DIAOKnowledgeProvider()

    def test_three_real_natures_across_query_styles(self) -> None:
        for expected, queries in SCENARIOS.items():
            for style, query in queries.items():
                with self.subTest(section=expected, style=style, query=query):
                    hits = self.provider.search(query, top_k=5)
                    sections = [hit["section"]["id"] for hit in hits]
                    allowed_rank = 5 if style == "ambiguous" else 3
                    self.assertIn(expected, sections[:allowed_rank], sections)

    def test_required_provenance_is_present(self) -> None:
        required = {
            "source_document", "source_version", "source_sha256", "section", "page",
            "item", "chunk_id", "chunk_sha256", "relevance", "supporting_text",
        }
        for query in ("ameaça de mal grave", "furto de celular", "roubo com violência"):
            for hit in self.provider.search(query, top_k=3):
                self.assertEqual(required, required.intersection(hit))
                self.assertTrue(hit["source_document"])
                self.assertTrue(hit["chunk_id"])
                self.assertTrue(hit["page"]["pdf"])
                self.assertTrue(hit["supporting_text"])

    def test_guidance_requires_officer_confirmation(self) -> None:
        result = self.provider.retrieve_guidance(
            {"label": "ROUBO", "status": "PROPOSED"},
            [{"statement": "grave ameaça e subtração do telefone"}],
        )
        self.assertEqual(GUIDANCE_NOT_SUPPORTED, result["status"])
        self.assertEqual([], result["priority_actions"])
        self.assertEqual([], result["sources"])

    def test_supported_guidance_is_source_only(self) -> None:
        result = self.provider.retrieve_guidance(
            {"label": "ROUBO", "nature_code": "C01.157", "status": "OFFICER_CONFIRMED"},
            [{"statement": "autor usou grave ameaça para subtrair telefone"}],
        )
        self.assertEqual("SUPPORTED_BY_DIAO", result["status"])
        self.assertGreater(len(result["priority_actions"]), 0)
        for action in result["priority_actions"]:
            self.assertEqual("SOURCE_EXCERPT_REQUIRES_FAITHFUL_SUMMARY", action["kind"])
            self.assertTrue(action["chunk_id"])
            self.assertTrue(action["section"]["id"])
            self.assertTrue(action["page"]["pdf"])
            self.assertTrue(action["text"])

    def test_unknown_query_never_creates_guidance(self) -> None:
        result = self.provider.retrieve_guidance(
            {
                "label": "fenômeno quântico zxqv sem relação documental",
                "status": "OFFICER_CONFIRMED",
            },
            [],
        )
        self.assertEqual(GUIDANCE_NOT_SUPPORTED, result["status"])
        self.assertEqual([], result["priority_actions"])
        self.assertEqual([], result["sources"])

    def test_section_and_page_access_preserve_dual_pagination(self) -> None:
        section = self.provider.get_section("B 01.147")
        self.assertIsNotNone(section)
        assert section is not None
        self.assertEqual(102, section["first_pdf_page"])
        self.assertEqual(39, section["first_printed_page"])
        page = self.provider.get_page(102)
        self.assertTrue(any(hit["section"]["id"] == "B01.147" for hit in page))

    def test_unicode_source_text_is_not_mojibake(self) -> None:
        section = self.provider.get_section("B01.147")
        self.assertIsNotNone(section)
        assert section is not None
        self.assertEqual("AMEAÇA", section["title"])
        combined = " ".join(chunk["supporting_text"] for chunk in section["chunks"][:3])
        self.assertIn("Ameaçar", combined)
        self.assertNotIn("\ufffd", combined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
