from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FallbackOnUnknown = Literal["pass_through", "assume_render_language", "assume_provider_language"]
ResponseLanguagePolicy = Literal["user_last_language", "fixed_render_language", "provider_language"]
TransformFailureMode = Literal["pass_through"]
PromptArtifactPrivacyMode = Literal["permissive", "strict", "local_only"]
InternalTranscriptSelector = Literal["legacy", "provider", "render"]
CompressionPersistMode = Literal["provider_only", "provider_plus_render"]


@dataclass(slots=True)
class TranslatorConfig:
    provider: str = "main"
    model: str = ""
    base_url: str = ""
    timeout_seconds: float = 8.0
    failure_mode: TransformFailureMode = "pass_through"


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
class PromptArtifactConfig:
    enabled: bool = False
    privacy_mode: PromptArtifactPrivacyMode = "strict"
    transform_version: str = "v1"
    policy_version: str = "v1"


@dataclass(slots=True)
class ToolResultConfig:
    enabled: bool = False
    min_chars_for_normalization: int = 160
    max_chars_for_normalization: int = 12000
    min_detection_confidence: float = 0.7
    transform_version: str = "v1"
    policy_version: str = "v1"
    allowlisted_tools: tuple[str, ...] = ()
    denylisted_tools: tuple[str, ...] = ()


@dataclass(slots=True)
class CompressionConfig:
    enabled: bool = False
    transcript_selector: InternalTranscriptSelector = "provider"
    persist_mode: CompressionPersistMode = "provider_only"


@dataclass(slots=True)
class MemoryConfig:
    enabled: bool = False
    built_in_selector: InternalTranscriptSelector = "provider"
    external_selector: InternalTranscriptSelector = "provider"


@dataclass(slots=True)
class DelegationConfig:
    transcript_selector: InternalTranscriptSelector = "provider"
    inherit_enabled: bool = True
    inherit_render_context: bool = False


@dataclass(slots=True)
class GatewayConfig:
    outbound_selector: InternalTranscriptSelector = "render"
    surface_overrides: dict[str, InternalTranscriptSelector] = field(default_factory=dict)


@dataclass(slots=True)
class LanguageMediationConfig:
    enabled: bool = False
    provider_language: str = "en"
    render_language: str = "auto"
    translator: TranslatorConfig = field(default_factory=TranslatorConfig)
    turn_input: TurnInputConfig = field(default_factory=TurnInputConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    prompt_artifacts: PromptArtifactConfig = field(default_factory=PromptArtifactConfig)
    tool_results: ToolResultConfig = field(default_factory=ToolResultConfig)
    compression: CompressionConfig = field(default_factory=CompressionConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    delegation: DelegationConfig = field(default_factory=DelegationConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
