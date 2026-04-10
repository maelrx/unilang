from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import uuid

from .config import LanguageMediationConfig
from .content_classifier import ContentClassifier
from .language_detector import LanguageDetector
from .language_policy import LanguagePolicyEngine
from .translation_adapter import BaseTranslationAdapter
from .types import DetectionResult, LocalizedResponse, MessageVariant, NormalizedMessage


@dataclass(slots=True)
class SessionContext:
    session_id: str
    config: LanguageMediationConfig = field(default_factory=LanguageMediationConfig)
    last_user_language: str | None = None


class LanguageRuntime:
    def __init__(
        self,
        *,
        policy: LanguagePolicyEngine,
        detector: LanguageDetector,
        classifier: ContentClassifier,
        adapter: BaseTranslationAdapter,
    ) -> None:
        self.policy = policy
        self.detector = detector
        self.classifier = classifier
        self.adapter = adapter

    def normalize_user_message(self, session_ctx: SessionContext, raw_text: str) -> NormalizedMessage:
        config = session_ctx.config
        detection = self._detect(raw_text, config=config)
        content_kind = self.classifier.classify(raw_text)
        decision = self.policy.decide_user_input(
            text=raw_text,
            detected_language=detection.language_code,
            content_kind=content_kind,
            config=config,
        )

        provider_text = raw_text
        if decision.should_transform and decision.source_language and decision.target_language:
            provider_text = self.adapter.translate(
                text=raw_text,
                source_language=decision.source_language,
                target_language=decision.target_language,
                preserve_literal_segments=config.output.preserve_literals,
            )

        if detection.language_code:
            session_ctx.last_user_language = detection.language_code

        message_id = str(uuid.uuid4())
        raw_variant = MessageVariant(
            message_id=message_id,
            variant_kind="raw",
            language_code=detection.language_code,
            content=raw_text,
            transform_name=None,
            source_hash=self._hash(raw_text),
            metadata={"content_kind": content_kind},
        )
        provider_variant = MessageVariant(
            message_id=message_id,
            variant_kind="provider",
            language_code=decision.target_language or detection.language_code,
            content=provider_text,
            transform_name="translation" if decision.should_transform else "none",
            source_hash=self._hash(raw_text),
            metadata={"content_kind": content_kind, "reason": decision.reason},
        )
        return NormalizedMessage(
            raw_text=raw_text,
            provider_text=provider_text,
            detection=detection,
            content_kind=content_kind,
            decision=decision,
            raw_variant=raw_variant,
            provider_variant=provider_variant,
            metadata={"session_id": session_ctx.session_id},
        )

    def localize_assistant_output(self, session_ctx: SessionContext, provider_text: str) -> LocalizedResponse:
        config = session_ctx.config
        content_kind = self.classifier.classify(provider_text)
        decision = self.policy.decide_output_render(
            provider_text=provider_text,
            user_language=session_ctx.last_user_language,
            content_kind=content_kind,
            config=config,
        )

        render_text = provider_text
        if decision.should_transform and decision.source_language and decision.target_language:
            render_text = self.adapter.localize(
                text=provider_text,
                source_language=decision.source_language,
                target_language=decision.target_language,
                preserve_literal_segments=config.output.preserve_literals,
            )

        return LocalizedResponse(
            provider_content=provider_text,
            render_content=render_text,
            render_language=decision.target_language or config.provider_language,
            metadata={
                "content_kind": content_kind,
                "decision_reason": decision.reason,
                "user_language": session_ctx.last_user_language,
            },
        )

    def _detect(self, text: str, *, config: LanguageMediationConfig) -> DetectionResult:
        if not config.turn_input.detect_language:
            return DetectionResult(language_code=config.provider_language, confidence=1.0, reason="detection_disabled")
        return self.detector.detect(text, min_chars=config.turn_input.min_chars_for_detection)

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
