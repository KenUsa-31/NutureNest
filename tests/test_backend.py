import os
import unittest
from unittest.mock import patch

from backend import CompanionBackend, EMERGENCY_MESSAGE, KnowledgeBase


class CompanionBackendTests(unittest.TestCase):
    def setUp(self):
        self.bot = CompanionBackend(knowledge_base=KnowledgeBase())

    def test_prenatal_question_returns_cited_fallback_without_key(self):
        with patch("backend.GEMINI_API_KEY", ""):
            answer = "".join(self.bot.stream_response("What are prenatal checkups for?"))
        self.assertIn("antenatal contacts", answer)
        self.assertIn("World Health Organization", answer)
        self.assertIn("Source:", answer)
        self.assertIn("not medical advice", answer)

    def test_unknown_question_gets_companion_fallback(self):
        with patch("backend.GEMINI_API_KEY", ""):
            answer = "".join(self.bot.stream_response("Explain quantum entanglement"))
        self.assertIn("I'm here with you", answer)
        self.assertIn("reliable source", answer)

    def test_emergency_uses_fixed_message_before_model(self):
        with patch("backend.GEMINI_API_KEY", ""), patch.object(
            self.bot, "_gemini_stream", side_effect=AssertionError("model must not run")
        ):
            answer = "".join(self.bot.stream_response("I have chest pain and trouble breathing"))
        self.assertEqual(answer, EMERGENCY_MESSAGE)
        self.assertTrue(self.bot.last_metadata["emergency"])


if __name__ == "__main__":
    unittest.main()
