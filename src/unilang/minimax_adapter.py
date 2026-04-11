from __future__ import annotations

import os
from typing import Literal

from .config import TransformFailureMode


class MiniMaxTranslationError(Exception):
    """Raised when MiniMax translation fails."""


class MiniMaxTranslationAdapter:
    """Translation adapter using MiniMax M2.7/M2.5 via Anthropic-compatible API.

    Parameters
    ----------
    api_key : str
        MiniMax API key (sk-cp-...).
    model : str, default "MiniMax-M2.7-highspeed"
        Model name. Use "MiniMax-M2.7" for slower but potentially more
        accurate translations, or "MiniMax-M2.7-highspeed" for faster.
    base_url : str, default "https://api.minimax.io/anthropic"
        API endpoint base URL.
    timeout_seconds : float, default 30.0
        Request timeout.
    failure_mode : TransformFailureMode, default "pass_through"
        Behaviour on translation failure.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "MiniMax-M2.7-highspeed",
        base_url: str = "https://api.minimax.io/anthropic",
        timeout_seconds: float = 30.0,
        failure_mode: TransformFailureMode = "pass_through",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._failure_mode = failure_mode

    def translate(
        self,
        *,
        text: str,
        source_language: str,
        target_language: str,
        preserve_literal_segments: bool = True,
    ) -> str:
        return self._call(
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
        return self._call(
            text=text,
            source_language=source_language,
            target_language=target_language,
            preserve_literal_segments=preserve_literal_segments,
        )

    def _call(
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
            import re

            _LITERAL_RE = re.compile(r"(```[\s\S]*?```|`[^`\n]+`)")

            parts: list[str] = []
            cursor = 0
            for match in _LITERAL_RE.finditer(text):
                prose = text[cursor : match.start()]
                if prose:
                    parts.append(
                        self._translate_chunk(prose, source_language, target_language)
                    )
                parts.append(match.group(0))
                cursor = match.end()
            tail = text[cursor:]
            if tail:
                parts.append(self._translate_chunk(tail, source_language, target_language))
            return "".join(parts)

        return self._translate_chunk(text, source_language, target_language)

    def _translate_chunk(
        self, text: str, source_language: str, target_language: str
    ) -> str:
        lang_display = _LANGUAGE_DISPLAY.get(
            (source_language, target_language),
            f"{source_language} to {target_language}",
        )

        system_prompt = (
            f"You are a professional translator. Translate the following text from "
            f"{lang_display}. Output ONLY the translated text, with no preamble, "
            f"explanation, or formatting. Preserve all punctuation and capitalization."
        )

        user_prompt = f"Translate this text from {source_language} to {target_language}:\n\n{text}"

        try:
            import anthropic

            client = anthropic.Anthropic(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
            )

            response = client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": user_prompt}],
                    }
                ],
                temperature=1.0,
            )

            if not response.content:
                raise MiniMaxTranslationError("Empty response from MiniMax API")

            first_block = response.content[0]
            if first_block.type == "text":
                return first_block.text
            elif first_block.type == "thinking":
                if len(response.content) > 1 and response.content[1].type == "text":
                    return response.content[1].text
                raise MiniMaxTranslationError(
                    f"Unexpected content block type: {first_block.type}"
                )
            else:
                raise MiniMaxTranslationError(
                    f"Unexpected content block type: {first_block.type}"
                )

        except Exception as exc:
            if self._failure_mode == "pass_through":
                import logging

                logging.getLogger("unilang.minimax").warning(
                    "MiniMax translation failed (%s). Falling back to pass-through.", exc
                )
                return text
            raise MiniMaxTranslationError(
                f"MiniMax translation failed: {exc}"
            ) from exc


_LANGUAGE_DISPLAY: dict[tuple[str, str], str] = {
    ("en", "es"): "English to Spanish",
    ("en", "pt-BR"): "English to Portuguese (Brazilian)",
    ("en", "pt"): "English to Portuguese",
    ("en", "zh"): "English to Chinese",
    ("en", "fr"): "English to French",
    ("en", "de"): "English to German",
    ("en", "ar"): "English to Arabic",
    ("en", "ja"): "English to Japanese",
    ("en", "ko"): "English to Korean",
    ("en", "it"): "English to Italian",
    ("en", "ru"): "English to Russian",
    ("en", "hi"): "English to Hindi",
    ("en", "nl"): "English to Dutch",
    ("en", "pl"): "English to Polish",
    ("en", "tr"): "English to Turkish",
    ("en", "vi"): "English to Vietnamese",
    ("en", "th"): "English to Thai",
    ("en", "he"): "English to Hebrew",
    ("es", "en"): "Spanish to English",
    ("es", "pt-BR"): "Spanish to Portuguese (Brazilian)",
    ("es", "pt"): "Spanish to Portuguese",
    ("es", "zh"): "Spanish to Chinese",
    ("es", "fr"): "Spanish to French",
    ("es", "de"): "Spanish to German",
    ("es", "ar"): "Spanish to Arabic",
    ("es", "ja"): "Spanish to Japanese",
    ("es", "ko"): "Spanish to Korean",
    ("es", "it"): "Spanish to Italian",
    ("es", "ru"): "Spanish to Russian",
    ("es", "hi"): "Spanish to Hindi",
    ("es", "nl"): "Spanish to Dutch",
    ("es", "pl"): "Spanish to Polish",
    ("es", "tr"): "Spanish to Turkish",
    ("es", "vi"): "Spanish to Vietnamese",
    ("es", "th"): "Spanish to Thai",
    ("es", "he"): "Spanish to Hebrew",
    ("pt-BR", "en"): "Portuguese (Brazilian) to English",
    ("pt-BR", "es"): "Portuguese (Brazilian) to Spanish",
    ("pt-BR", "zh"): "Portuguese (Brazilian) to Chinese",
    ("pt-BR", "fr"): "Portuguese (Brazilian) to French",
    ("pt-BR", "de"): "Portuguese (Brazilian) to German",
    ("pt-BR", "ar"): "Portuguese (Brazilian) to Arabic",
    ("pt-BR", "ja"): "Portuguese (Brazilian) to Japanese",
    ("pt-BR", "ko"): "Portuguese (Brazilian) to Korean",
    ("pt-BR", "it"): "Portuguese (Brazilian) to Italian",
    ("pt-BR", "ru"): "Portuguese (Brazilian) to Russian",
    ("pt-BR", "hi"): "Portuguese (Brazilian) to Hindi",
    ("pt-BR", "nl"): "Portuguese (Brazilian) to Dutch",
    ("pt-BR", "pl"): "Portuguese (Brazilian) to Polish",
    ("pt-BR", "tr"): "Portuguese (Brazilian) to Turkish",
    ("pt-BR", "vi"): "Portuguese (Brazilian) to Vietnamese",
    ("pt-BR", "th"): "Portuguese (Brazilian) to Thai",
    ("pt-BR", "he"): "Portuguese (Brazilian) to Hebrew",
    ("zh", "en"): "Chinese to English",
    ("fr", "en"): "French to English",
    ("de", "en"): "German to English",
    ("ar", "en"): "Arabic to English",
    ("ja", "en"): "Japanese to English",
    ("ko", "en"): "Korean to English",
    ("it", "en"): "Italian to English",
    ("ru", "en"): "Russian to English",
    ("hi", "en"): "Hindi to English",
    ("nl", "en"): "Dutch to English",
    ("pl", "en"): "Polish to English",
    ("tr", "en"): "Turkish to English",
    ("vi", "en"): "Vietnamese to English",
    ("th", "en"): "Thai to English",
    ("he", "en"): "Hebrew to English",
}
