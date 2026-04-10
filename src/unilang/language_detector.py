from __future__ import annotations

import re

from .types import DetectionResult

_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ']+")


class LanguageDetector:
    """Phase 01 heuristic detector.

    It prioritizes being predictable and cheap over broad coverage. The initial target is to
    distinguish English from Portuguese reliably enough for runtime mediation tests.
    """

    _PT_HINTS = {
        "voce",
        "você",
        "nao",
        "não",
        "arquivo",
        "lingua",
        "língua",
        "resposta",
        "traducao",
        "tradução",
        "usuario",
        "usuário",
        "projeto",
        "obrigado",
        "ola",
        "olá",
        "para",
        "com",
        "está",
        "fazer",
    }
    _EN_HINTS = {
        "the",
        "and",
        "with",
        "this",
        "that",
        "read",
        "file",
        "project",
        "language",
        "response",
        "translate",
        "user",
        "agent",
        "runtime",
        "reasoning",
        "please",
        "build",
    }

    def detect(self, text: str, *, min_chars: int = 8) -> DetectionResult:
        stripped = text.strip()
        if len(stripped) < min_chars:
            return DetectionResult(language_code=None, confidence=0.0, reason="too_short")

        words = [word.lower() for word in _WORD_RE.findall(stripped)]
        if not words:
            return DetectionResult(language_code=None, confidence=0.0, reason="no_words")

        pt_score = self._score(words, self._PT_HINTS) + self._portuguese_orthography_bonus(stripped)
        en_score = self._score(words, self._EN_HINTS)

        if pt_score == 0 and en_score == 0:
            return DetectionResult(language_code=None, confidence=0.0, reason="unknown_language")
        if pt_score == en_score:
            return DetectionResult(language_code=None, confidence=0.0, reason="ambiguous")

        best_language = "pt-BR" if pt_score > en_score else "en"
        best_score = max(pt_score, en_score)
        total_score = pt_score + en_score
        confidence = min(0.99, best_score / max(total_score, 1))
        return DetectionResult(language_code=best_language, confidence=confidence, reason="heuristic_match")

    def _score(self, words: list[str], hints: set[str]) -> int:
        return sum(1 for word in words if word in hints)

    def _portuguese_orthography_bonus(self, text: str) -> int:
        bonus = 0
        if re.search(r"[ãõçáéíóúâêôà]", text.lower()):
            bonus += 3
        if re.search(r"\b(não|você|ação|tradução|memória|razão)\b", text.lower()):
            bonus += 2
        return bonus
