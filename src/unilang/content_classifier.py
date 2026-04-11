from __future__ import annotations

import json
import re

from .types import ContentKind

_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```")
_XML_RE = re.compile(r"^\s*<[^>]+>.*</[^>]+>\s*$", re.DOTALL)
_JSONISH_RE = re.compile(r"^\s*[\[{].*[\]}]\s*$", re.DOTALL)
_SHELL_LINE_RE = re.compile(r"^(\$ |PS>|>>> |Traceback |INFO\b|WARN\b|WARNING\b|ERROR\b|DEBUG\b)", re.MULTILINE)
_CODE_KEYWORDS_RE = re.compile(r"\b(def|class|function|return|import|from|const|let|var|if|else|elif|for|while|public|private|package)\b")


class ContentClassifier:
    """Heuristic Phase 01 classifier.

    The goal is to protect obvious literal artifacts early. This version is intentionally
    conservative and classifies ambiguous content as natural text unless strong signals suggest
    code, structured data, terminal output, or mixed markdown.
    """

    def classify(self, text: str) -> ContentKind:
        stripped = text.strip()
        if not stripped:
            return "natural_text"

        if self._is_mixed(stripped):
            return "mixed"
        if self._is_terminal(stripped):
            return "terminal"
        if self._is_structured(stripped):
            return "structured"
        if self._is_code(stripped):
            return "code"
        return "natural_text"

    def _is_mixed(self, text: str) -> bool:
        matches = list(_FENCED_CODE_RE.finditer(text))
        if not matches:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if not lines:
                return False
            terminal_lines = [line for line in lines if _SHELL_LINE_RE.match(line) or "Traceback (most recent call last):" in line]
            prose_lines = [line for line in lines if line not in terminal_lines and self._looks_like_prose(line)]
            return bool(terminal_lines and prose_lines)

        prose_outside_fences = []
        cursor = 0
        for match in matches:
            prose_outside_fences.append(text[cursor:match.start()])
            cursor = match.end()
        prose_outside_fences.append(text[cursor:])
        return any(self._looks_like_prose(chunk) for chunk in prose_outside_fences)

    def _is_terminal(self, text: str) -> bool:
        if _SHELL_LINE_RE.search(text):
            return True
        return "Traceback (most recent call last):" in text

    def _is_structured(self, text: str) -> bool:
        if _XML_RE.match(text):
            return True
        if _JSONISH_RE.match(text):
            try:
                json.loads(text)
                return True
            except json.JSONDecodeError:
                pass

        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) >= 2 and all(":" in line and not line.lstrip().startswith(("def ", "class ", "if ")) for line in lines):
            key_value_lines = sum(1 for line in lines if re.match(r"^[A-Za-z0-9_.\-\s]+:\s+.+$", line))
            if key_value_lines / len(lines) >= 0.8:
                return True
        return False

    def _is_code(self, text: str) -> bool:
        lines = text.splitlines() or [text]
        keyword_hits = len(_CODE_KEYWORDS_RE.findall(text))
        indented_lines = sum(1 for line in lines if line.startswith(("    ", "\t")))
        symbol_density = sum(1 for char in text if char in "{}[]();=<>#") / max(len(text), 1)
        if keyword_hits >= 2:
            return True
        if indented_lines >= 2 and symbol_density > 0.02:
            return True
        if symbol_density > 0.08 and not self._looks_like_prose(text):
            return True
        return False

    def _looks_like_prose(self, text: str) -> bool:
        if not text.strip():
            return False
        words = re.findall(r"[A-Za-zÀ-ÿ]+", text)
        if len(words) < 3:
            return False
        punctuation = sum(1 for char in text if char in ",.;:!?")
        return punctuation >= 1 or len(words) >= 6
