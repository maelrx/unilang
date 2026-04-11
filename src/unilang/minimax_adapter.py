from __future__ import annotations

import logging

from .config import TransformFailureMode
from .translation_adapter import BaseTranslationAdapter


class MiniMaxTranslationError(Exception):
    """Raised when MiniMax translation fails."""


class MiniMaxTranslationAdapter(BaseTranslationAdapter):
    """Translation adapter using MiniMax's Anthropic-compatible API."""

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
        self._client = None
        self._logger = logging.getLogger("unilang.minimax")

    def _transform_prose(self, text: str, source_language: str, target_language: str) -> str:
        lang_display = _LANGUAGE_DISPLAY.get(
            (source_language, target_language),
            f"{source_language} to {target_language}",
        )
        system_prompt = (
            "You are a professional translator. Translate the user's text exactly once. "
            f"Translate from {lang_display}. Output only the translated text. Preserve meaning, "
            "tone, punctuation, and capitalization. Do not add explanations or markdown fences."
        )
        user_prompt = (
            f"Source language: {source_language}\n"
            f"Target language: {target_language}\n\n"
            f"Text:\n{text}"
        )

        try:
            response = self._get_client().messages.create(
                model=self._model,
                max_tokens=4096,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": user_prompt}],
                    }
                ],
                temperature=0.1,
            )
            translated_text = self._extract_text(response)
            if not translated_text:
                raise MiniMaxTranslationError("Empty response from MiniMax API")
            return translated_text.strip()
        except Exception as exc:
            if self._failure_mode == "pass_through":
                self._logger.warning(
                    "MiniMax translation failed (%s). Falling back to pass-through.", exc
                )
                return text
            raise MiniMaxTranslationError(f"MiniMax translation failed: {exc}") from exc

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
            )
        return self._client

    def _extract_text(self, response) -> str:
        text_blocks: list[str] = []
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text" and getattr(block, "text", None):
                text_blocks.append(block.text)
        return "".join(text_blocks)


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
