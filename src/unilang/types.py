from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

VariantKind = Literal["raw", "provider", "render", "compressed", "retrieval"]
ContentKind = Literal["natural_text", "code", "terminal", "structured", "mixed"]
TranscriptSelector = Literal["legacy", "provider", "render"]
PromptArtifactKind = Literal["memory_snapshot", "profile_snapshot", "context_file"]
ToolResultAction = Literal["pass_through", "segment_then_normalize", "blocked"]
InternalPurpose = Literal["compression", "memory_builtin", "memory_external", "delegation"]
MemorySourceKind = Literal["transcript", "summary"]


@dataclass(slots=True)
class DetectionResult:
    language_code: str | None
    confidence: float
    reason: str


@dataclass(slots=True)
class MessageVariant:
    message_id: str
    variant_kind: VariantKind
    language_code: str | None
    content: str
    transform_name: str | None = None
    transform_version: str | None = None
    source_hash: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class TranscriptMessage:
    message_id: str
    content: str
    selector: TranscriptSelector
    role: str | None = None
    selected_variant_kind: VariantKind | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class TransformDecision:
    should_transform: bool
    reason: str
    source_language: str | None
    target_language: str | None
    content_kind: ContentKind


@dataclass(slots=True)
class NormalizedMessage:
    raw_text: str
    provider_text: str
    detection: DetectionResult
    content_kind: ContentKind
    decision: TransformDecision
    raw_variant: MessageVariant
    provider_variant: MessageVariant
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class LocalizedResponse:
    provider_content: str
    render_content: str
    render_language: str
    provider_variant: MessageVariant | None = None
    render_variant: MessageVariant | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class ToolResultDecision:
    action: ToolResultAction
    reason: str
    source_language: str | None
    target_language: str | None
    content_kind: ContentKind


@dataclass(slots=True)
class MediatedToolResult:
    tool_name: str | None
    raw_content: str
    provider_content: str
    detection: DetectionResult
    content_kind: ContentKind
    decision: ToolResultDecision
    raw_variant: MessageVariant
    provider_variant: MessageVariant
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class PromptArtifact:
    artifact_id: str
    kind: PromptArtifactKind
    content: str
    source_name: str | None = None
    language_code: str | None = None
    allow_external_translation: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class PromptArtifactScanResult:
    allowed: bool
    reason: str
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class PreparedPromptArtifact:
    artifact_id: str
    kind: PromptArtifactKind
    source_text: str
    prepared_text: str
    source_language: str | None
    prepared_language: str | None
    content_kind: ContentKind
    decision_reason: str
    used_cached_variant: bool
    used_provider_variant: bool
    scan_result: PromptArtifactScanResult
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class PreparedPromptArtifacts:
    session_id: str
    artifacts: tuple[PreparedPromptArtifact, ...]
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class InternalTranscriptView:
    purpose: InternalPurpose
    selector_requested: TranscriptSelector
    selector_used: TranscriptSelector
    messages: tuple[TranscriptMessage, ...]
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class CompressionInput:
    selector_requested: TranscriptSelector
    selector_used: TranscriptSelector
    messages: tuple[TranscriptMessage, ...]
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class PersistedCompressionSummary:
    provider_content: str
    render_content: str | None
    provider_variant: MessageVariant
    render_variant: MessageVariant | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class MemoryPayload:
    path_kind: Literal["built_in", "external"]
    source_kind: MemorySourceKind
    selector_requested: TranscriptSelector | None
    selector_used: TranscriptSelector | None
    messages: tuple[TranscriptMessage, ...]
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class DelegationPayload:
    selector_requested: TranscriptSelector
    selector_used: TranscriptSelector
    messages: tuple[TranscriptMessage, ...]
    content: str
    provider_language: str
    render_language: str | None
    mediation_enabled: bool
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class GatewayMessage:
    content: str
    selector_requested: TranscriptSelector
    selector_used: TranscriptSelector
    selected_variant_kind: VariantKind | None
    language_code: str | None
    message_id: str | None = None
    surface: str | None = None
    metadata: dict = field(default_factory=dict)
