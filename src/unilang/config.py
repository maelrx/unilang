from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FallbackOnUnknown = Literal["pass_through", "assume_render_language", "assume_provider_language"]
ResponseLanguagePolicy = Literal["user_last_language", "fixed_render_language", "provider_language"]


@dataclass(slots=True)
class TranslatorConfig:
    provider: str = "main"
    model: str = ""
    base_url: str = ""


@dataclass(slots=True)
class TurnInputConfig:
    normalize_user_messages: bool = True
    detect_language: bool = True
    min_chars_for_detection: int = 8
    fallback_on_unknown: FallbackOnUnknown = "pass_through"


@dataclass(slots=True)
class OutputConfig:
    localize_assistant_messages: bool = True
    preserve_literals: bool = True
    response_language_policy: ResponseLanguagePolicy = "user_last_language"


@dataclass(slots=True)
class LanguageMediationConfig:
    enabled: bool = True
    provider_language: str = "en"
    render_language: str = "auto"
    translator: TranslatorConfig = field(default_factory=TranslatorConfig)
    turn_input: TurnInputConfig = field(default_factory=TurnInputConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
