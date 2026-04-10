from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

VariantKind = Literal["raw", "provider", "render", "compressed", "retrieval"]
ContentKind = Literal["natural_text", "code", "terminal", "structured", "mixed"]


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
