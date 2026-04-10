from __future__ import annotations

from abc import ABC, abstractmethod
import re

_LITERAL_SEGMENT_RE = re.compile(r"(```[\s\S]*?```|`[^`\n]+`)")


def preserve_literals(text: str, transform) -> str:
    parts: list[str] = []
    cursor = 0
    for match in _LITERAL_SEGMENT_RE.finditer(text):
        prose = text[cursor:match.start()]
        if prose:
            parts.append(transform(prose))
        parts.append(match.group(0))
        cursor = match.end()
    tail = text[cursor:]
    if tail:
        parts.append(transform(tail))
    return "".join(parts)


class BaseTranslationAdapter(ABC):
    """Adapter contract for runtime normalization/localization.

    Concrete integrations can later route through Hermes auxiliary models. Phase 01 keeps the
    contract host-agnostic so it can be tested outside Hermes.
    """

    def translate(
        self,
        *,
        text: str,
        source_language: str,
        target_language: str,
        preserve_literal_segments: bool = True,
    ) -> str:
        return self._transform(
            text=text,
            source_language=source_language,
            target_language=target_language,
            preserve_literal_segments=preserve_literal_segments,
        )

    def localize(
        self,
        *,
        text: str,
        source_language: str,
        target_language: str,
        preserve_literal_segments: bool = True,
    ) -> str:
        return self._transform(
            text=text,
            source_language=source_language,
            target_language=target_language,
            preserve_literal_segments=preserve_literal_segments,
        )

    def _transform(
        self,
        *,
        text: str,
        source_language: str,
        target_language: str,
        preserve_literal_segments: bool,
    ) -> str:
        if source_language == target_language:
            return text
        if preserve_literal_segments:
            return preserve_literals(text, lambda chunk: self._transform_prose(chunk, source_language, target_language))
        return self._transform_prose(text, source_language, target_language)

    @abstractmethod
    def _transform_prose(self, text: str, source_language: str, target_language: str) -> str:
        raise NotImplementedError


class PassthroughTranslationAdapter(BaseTranslationAdapter):
    def _transform_prose(self, text: str, source_language: str, target_language: str) -> str:
        return text
