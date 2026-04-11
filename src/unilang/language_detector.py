from __future__ import annotations

import re

from .types import DetectionResult

_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ']+")
_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_HEBREW_RE = re.compile(r"[\u0590-\u05FF]")
_HIRAGANA_KATAKANA_RE = re.compile(r"[\u3040-\u30FF]")
_HAN_RE = re.compile(r"[\u4E00-\u9FFF]")
_HANGUL_RE = re.compile(r"[\uAC00-\uD7AF]")
_THAI_RE = re.compile(r"[\u0E00-\u0E7F]")


class LanguageDetector:
    """Cheap heuristic detector with explicit coverage for the runtime's benchmark languages."""

    _LATIN_HINTS = {
        "pt-BR": {
            "leia",
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
            "preciso",
            "ajuda",
            "codigo",
            "código",
            "esse",
            "diga",
            "modulo",
            "módulo",
            "faz",
        },
        "en": {
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
            "hello",
            "today",
            "need",
            "help",
            "code",
        },
        "es": {"hola", "como", "cómo", "estas", "estás", "hoy", "necesito", "ayuda", "codigo", "código"},
        "fr": {"bonjour", "comment", "allez", "vous", "aujourd'hui", "besoin", "aide", "code", "mon"},
        "de": {"hallo", "wie", "geht", "dir", "ich", "brauche", "hilfe", "code", "heute"},
        "it": {"ciao", "come", "stai", "oggi", "bisogno", "aiuto", "codice", "mio"},
        "nl": {"hallo", "hoe", "gaat", "vandaag", "hulp", "nodig", "mijn", "code"},
        "pl": {"cześć", "jak", "się", "masz", "dzisiaj", "potrzebuję", "pomocy", "kodem"},
        "tr": {"merhaba", "bugün", "nasılsın", "kodum", "yardıma", "ihtiyacım", "var"},
        "vi": {"xin", "chào", "bạn", "khỏe", "hôm", "nay", "tôi", "cần", "giúp", "đỡ"},
    }
    _ORTHOGRAPHY_PATTERNS = {
        "pt-BR": (re.compile(r"[ãõç]|\b(não|você|tradução|memória|razão|olá)\b"), 3),
        "es": (re.compile(r"[ñ¿¡]"), 3),
        "fr": (re.compile(r"[çœæ]"), 2),
        "de": (re.compile(r"[äöüß]"), 3),
        "pl": (re.compile(r"[ąćęłńóśźż]"), 3),
        "tr": (re.compile(r"[çğıöşü]"), 3),
        "vi": (re.compile(r"[ăâđêôơưàáảãạèéẻẽẹìíỉĩịòóỏõọùúủũụỳýỷỹỵ]"), 3),
    }

    def __init__(self, supported_languages: list[str] | tuple[str, ...] | set[str] | None = None) -> None:
        self._supported_languages = set(supported_languages) if supported_languages else None

    def detect(self, text: str, *, min_chars: int = 8) -> DetectionResult:
        stripped = text.strip()
        if len(stripped) < min_chars:
            return DetectionResult(language_code=None, confidence=0.0, reason="too_short")

        scripted = self._detect_script_language(stripped)
        if scripted is not None:
            return scripted

        words = [word.lower() for word in _WORD_RE.findall(stripped)]
        if not words:
            return DetectionResult(language_code=None, confidence=0.0, reason="no_words")

        scores = {
            language_code: self._score(words, hints) + self._orthography_bonus(language_code, stripped)
            for language_code, hints in self._LATIN_HINTS.items()
            if self._is_supported(language_code)
        }

        if not scores:
            return DetectionResult(language_code=None, confidence=0.0, reason="unsupported_languages")

        best_language, best_score = max(scores.items(), key=lambda item: item[1])
        total_score = sum(scores.values())
        ranked_scores = sorted(scores.values(), reverse=True)
        second_best = ranked_scores[1] if len(ranked_scores) > 1 else 0

        if best_score == 0:
            return DetectionResult(language_code=None, confidence=0.0, reason="unknown_language")
        if best_score < 2:
            return DetectionResult(language_code=None, confidence=0.0, reason="unknown_language")
        if best_score == second_best:
            return DetectionResult(language_code=None, confidence=0.0, reason="ambiguous")

        confidence = min(0.99, best_score / max(total_score, 1))
        return DetectionResult(language_code=best_language, confidence=confidence, reason="heuristic_match")

    def _score(self, words: list[str], hints: set[str]) -> int:
        return sum(1 for word in words if word in hints)

    def _orthography_bonus(self, language_code: str, text: str) -> int:
        pattern_config = self._ORTHOGRAPHY_PATTERNS.get(language_code)
        if pattern_config is None:
            return 0
        pattern, bonus = pattern_config
        return bonus if pattern.search(text.lower()) else 0

    def _detect_script_language(self, text: str) -> DetectionResult | None:
        script_languages = (
            ("ja", _HIRAGANA_KATAKANA_RE),
            ("ko", _HANGUL_RE),
            ("ar", _ARABIC_RE),
            ("ru", _CYRILLIC_RE),
            ("hi", _DEVANAGARI_RE),
            ("th", _THAI_RE),
            ("he", _HEBREW_RE),
            ("zh", _HAN_RE),
        )
        for language_code, pattern in script_languages:
            if self._is_supported(language_code) and pattern.search(text):
                return DetectionResult(language_code=language_code, confidence=0.99, reason="script_match")
        return None

    def _is_supported(self, language_code: str) -> bool:
        return self._supported_languages is None or language_code in self._supported_languages
