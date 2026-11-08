"""Sourced pregnancy companion with optional Gemini generation."""

import json
import os
import re
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:  # pragma: no cover - Vercel dependency installation handles this
    TfidfVectorizer = None
    cosine_similarity = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KB_FILE = os.path.join(BASE_DIR, "knowledge_base.json")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_BASE_URL = os.environ.get(
    "GEMINI_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai/",
).rstrip("/")
MEMORY_SIZE = 8
SIMILARITY_THRESHOLD = 0.12
DISCLAIMER = (
    "This is general information, not medical advice or a personal assessment. "
    "Your maternity care team can guide you about your situation."
)
EMERGENCY_MESSAGE = (
    "I'm glad you told me. This could need urgent medical attention. Please contact "
    "your local emergency number or go to the nearest emergency department now. "
    "Tell them you are pregnant or recently gave birth. I can't assess or treat this."
)
EMERGENCY_PHRASES = (
    "trouble breathing", "difficulty breathing", "can't breathe", "cannot breathe",
    "shortness of breath", "chest pain", "severe bleeding", "heavy bleeding",
    "soaking a pad", "seizure", "fainted", "passed out", "severe headache",
    "vision changes", "blurry vision", "baby stopped moving", "baby not moving",
    "reduced fetal movement", "fluid leaking", "harm myself", "hurt myself",
    "suicidal", "harm my baby", "hurt my baby",
)
HEALTH_TERMS = (
    "pregnan", "prenatal", "antenatal", "postnatal", "postpartum", "birth",
    "labor", "labour", "delivery", "bleeding", "baby", "fetus", "fetal",
    "midwife", "maternity", "clinic", "checkup", "check-up", "contraction",
    "feeding", "breast", "pain", "fever", "headache", "discharge",
)


class KnowledgeBase:
    def __init__(self, filepath=KB_FILE):
        with open(filepath, "r", encoding="utf-8") as source_file:
            self.entries = json.load(source_file)
        self.vectorizer = None
        self.matrix = None
        self._build_index()

    def _build_index(self):
        if TfidfVectorizer is None or not self.entries:
            return
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self.matrix = self.vectorizer.fit_transform(
            [entry["content"] for entry in self.entries]
        )

    def retrieve(self, query, top_k=3):
        if self.vectorizer is None or self.matrix is None:
            return []
        normalized_query = query
        for pattern, replacement in (
            (r"\bprenatal\b", "antenatal"),
            (r"\bcheck[- ]?ups?\b", "contacts"),
            (r"\bpostpartum\b", "postnatal"),
            (r"\blying[ -]?in\b", "maternity clinic"),
            (r"\bdelivery\b", "birth"),
        ):
            normalized_query = re.sub(
                pattern, replacement, normalized_query, flags=re.IGNORECASE
            )
        terms = self.vectorizer.build_analyzer()(normalized_query)
        if not terms:
            return []
        known_terms = sum(term in self.vectorizer.vocabulary_ for term in terms)
        if known_terms / len(terms) < 0.25:
            return []
        scores = cosine_similarity(
            self.vectorizer.transform([normalized_query]), self.matrix
        ).flatten()
        matches = []
        for index in scores.argsort()[::-1][:top_k]:
            if scores[index] >= SIMILARITY_THRESHOLD:
                entry = self.entries[index]
                matches.append({
                    "topic": entry["topic"],
                    "text": entry["content"],
                    "source": entry["source"],
                    "url": entry.get("url", ""),
                    "similarity": float(scores[index]),
                })
        return matches


class CompanionBackend:
    def __init__(self, knowledge_base=None, history=None):
        self.kb = knowledge_base or KnowledgeBase()
        self.history = list(history or [])[-MEMORY_SIZE:]
        self.lock = threading.Lock()
        self.last_metadata = {}

    @staticmethod
    def _is_emergency(text):
        lowered = text.lower()
        return any(phrase in lowered for phrase in EMERGENCY_PHRASES)

    @staticmethod
    def _is_health_related(text):
        lowered = text.lower()
        return any(term in lowered for term in HEALTH_TERMS)

    def _fallback(self, retrieved):
        if not retrieved:
            return (
                "I'm here with you. I don't have a reliable source for that specific "
                "question, but we can talk through what's on your mind. What would feel "
                "helpful right now?"
            )
        passages = []
        for entry in retrieved[:2]:
            citation = f"Source: {entry['source']}"
            if entry.get("url"):
                citation += f" ({entry['url']})"
            passages.append(f"{entry['topic']}\n{entry['text']}\n{citation}")
        return (
            "I'm glad you asked. Here's what the reviewed sources say:\n\n"
            + "\n\n".join(passages)
            + "\n\nWhat feels most useful to talk about next?"
        )

    def _system_prompt(self):
        return (
            "You are NurtureNest, a warm AI companion for people navigating pregnancy "
            "and the period after birth. Companionship is your main purpose; information "
            "is secondary. Listen, acknowledge feelings the person actually expresses, "
            "and ask at most one gentle, open question. Never pretend to be human.\n\n"
            "When giving medical information, use only the retrieved source passages and "
            "cite their source. If they do not answer, say you don't have a reliable "
            "source rather than guessing. You do not know any real clinic's hours, prices, "
            "staff, policies, or services. Do not diagnose, assess an individual pregnancy, "
            "recommend medicines, or make a personal care plan. Encourage the person to "
            "contact their qualified maternity-care provider for personal guidance. "
            "For urgent symptoms, direct them to local emergency care. Be supportive, "
            "brief, and clear; do not pressure the person or promise outcomes.\n\n"
            f"Retrieved source passages:\n{self._context}"
        )

    @property
    def _context(self):
        return "No relevant passages were found."

    def _messages(self, query, retrieved):
        context = "\n\n".join(
            f"[{item['topic']}] {item['text']} Source: {item['source']}"
            for item in retrieved
        ) or "No relevant passages were found."
        system = self._system_prompt().replace(self._context, context)
        messages = [{"role": "system", "content": system}]
        messages.extend(self.history[-MEMORY_SIZE:])
        messages.append({"role": "user", "content": query})
        return messages

    @staticmethod
    def _gemini_stream(messages):
        request = Request(
            f"{GEMINI_BASE_URL}/chat/completions",
            data=json.dumps({
                "model": GEMINI_MODEL,
                "messages": messages,
                "max_tokens": 420,
                "stream": True,
            }).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {GEMINI_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            response = urlopen(request, timeout=45)
        except HTTPError as exc:
            raise RuntimeError(f"Gemini request returned HTTP {exc.code}.") from exc
        with response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                choices = chunk.get("choices", [])
                if choices:
                    content = choices[0].get("delta", {}).get("content", "")
                    if isinstance(content, str) and content:
                        yield content

    def stream_response(self, query):
        started = time.time()
        if self._is_emergency(query):
            self.last_metadata = {
                "topics": [], "sources": [], "emergency": True,
                "response_time": time.time() - started,
            }
            yield EMERGENCY_MESSAGE
            return

        retrieved = self.kb.retrieve(query)
        self.last_metadata = {
            "topics": [item["topic"] for item in retrieved],
            "sources": [
                {"topic": item["topic"], "label": item["source"], "url": item.get("url", "")}
                for item in retrieved
            ],
            "emergency": False,
            "response_time": 0.0,
        }

        full_response = []
        if GEMINI_API_KEY:
            try:
                for part in self._gemini_stream(self._messages(query, retrieved)):
                    full_response.append(part)
                    yield part
            except Exception:
                if full_response:
                    yield "\n\nI lost connection while replying. Please try again or contact your care team."
                else:
                    response = self._fallback(retrieved)
                    full_response.append(response)
                    yield response
        else:
            response = self._fallback(retrieved)
            full_response.append(response)
            yield response

        text = "".join(full_response)
        if self._is_health_related(query) and DISCLAIMER.lower() not in text.lower():
            yield f"\n\n{DISCLAIMER}"
        self.last_metadata["response_time"] = time.time() - started
