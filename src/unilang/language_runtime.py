from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import re
import time
import uuid

from .language_cache import LanguageCache, TransformCacheKey
from .config import LanguageMediationConfig
from .content_classifier import ContentClassifier
from .language_detector import LanguageDetector
from .language_policy import LanguagePolicyEngine
from .prompt_artifacts import AllowAllPromptArtifactScanner, BasePromptArtifactScanner, prompt_artifact_sort_key
from .translation_adapter import BaseTranslationAdapter
from .variant_store import VariantStore
from .types import (
    CompressionInput,
    DelegationPayload,
    DetectionResult,
    GatewayMessage,
    InternalTranscriptView,
    MediatedToolResult,
    LocalizedResponse,
    MemoryPayload,
    MessageVariant,
    NormalizedMessage,
    PersistedCompressionSummary,
    PreparedPromptArtifact,
    PreparedPromptArtifacts,
    PromptArtifact,
    PromptArtifactScanResult,
    ToolResultDecision,
)

_FENCED_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_INLINE_LITERAL_RE = re.compile(
    r"(`[^`\n]+`|https?://[^\s)\]>]+|[A-Za-z]:\\[^\s`]+|(?:\./|\.\./|/)[^\s`]+|\$[A-Z_][A-Z0-9_]*|%[A-Z_][A-Z0-9_]*%)"
)
_TOOL_LITERAL_LINE_RE = re.compile(
    r"^(\$ |PS>|>>> |Traceback |INFO\b|WARN\b|WARNING\b|ERROR\b|DEBUG\b|Exception\b|Caused by:|\s*at\s)"
)
_STACK_TRACE_RE = re.compile(r'^\s*File ".+", line \d+')
_STRUCTURED_LINE_RE = re.compile(r'^\s*[\[{<].*[\]}>]\s*$|^\s*"[^"]+"\s*:\s*.+$|^\s*[A-Za-z0-9_.\-/]+:\s+.+$')
_COMMAND_PREFIXES = (
    "python ",
    "pytest",
    "npm ",
    "pnpm ",
    "yarn ",
    "git ",
    "node ",
    "pip ",
    "ls ",
    "dir ",
    "curl ",
    "docker ",
)


@dataclass(slots=True)
class SessionContext:
    session_id: str
    config: LanguageMediationConfig = field(default_factory=LanguageMediationConfig)
    last_user_language: str | None = None
    prepared_prompt_artifacts: PreparedPromptArtifacts | None = None
    metadata: dict = field(default_factory=dict)


class LanguageRuntime:
    def __init__(
        self,
        *,
        policy: LanguagePolicyEngine,
        detector: LanguageDetector,
        classifier: ContentClassifier,
        adapter: BaseTranslationAdapter,
        cache: LanguageCache | None = None,
        variant_store: VariantStore | None = None,
        prompt_artifact_scanner: BasePromptArtifactScanner | None = None,
    ) -> None:
        self.policy = policy
        self.detector = detector
        self.classifier = classifier
        self.adapter = adapter
        self.cache = cache
        self.variant_store = variant_store
        self.prompt_artifact_scanner = prompt_artifact_scanner or AllowAllPromptArtifactScanner()

    def normalize_user_message(self, session_ctx: SessionContext, raw_text: str) -> NormalizedMessage:
        config = session_ctx.config
        started_at = time.perf_counter()
        detection = self._detect(raw_text, config=config)
        content_kind = self.classifier.classify(raw_text)
        decision = self.policy.decide_user_input(
            text=raw_text,
            detected_language=detection.language_code,
            content_kind=content_kind,
            config=config,
        )

        provider_text = raw_text
        transform_metadata = self._passthrough_metadata(config=config, transform_type="translation")
        if decision.should_transform and decision.source_language and decision.target_language:
            provider_text, transform_metadata = self._cached_transform(
                text=raw_text,
                source_language=decision.source_language,
                target_language=decision.target_language,
                transform_type="translation",
                transform=lambda: self.adapter.translate(
                    text=raw_text,
                    source_language=decision.source_language,
                    target_language=decision.target_language,
                    preserve_literal_segments=config.output.preserve_literals,
                ),
                config=config,
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
            metadata={
                "content_kind": content_kind,
                "reason": decision.reason,
                "transform": transform_metadata,
            },
        )
        if self.variant_store:
            self.variant_store.save_message_variants(
                message_id=message_id,
                legacy_content=provider_text,
                variants=[raw_variant, provider_variant],
                role="user",
                metadata={
                    "session_id": session_ctx.session_id,
                    "content_kind": content_kind,
                },
            )
        return NormalizedMessage(
            raw_text=raw_text,
            provider_text=provider_text,
            detection=detection,
            content_kind=content_kind,
            decision=decision,
            raw_variant=raw_variant,
            provider_variant=provider_variant,
            metadata={
                "session_id": session_ctx.session_id,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                "detection": {
                    "language_code": detection.language_code,
                    "confidence": detection.confidence,
                    "reason": detection.reason,
                },
                "decision_reason": decision.reason,
                "transform": transform_metadata,
            },
        )

    def localize_assistant_output(self, session_ctx: SessionContext, provider_text: str, *, message_id: str | None = None) -> LocalizedResponse:
        config = session_ctx.config
        started_at = time.perf_counter()
        content_kind = self.classifier.classify(provider_text)
        decision = self.policy.decide_output_render(
            provider_text=provider_text,
            user_language=session_ctx.last_user_language,
            content_kind=content_kind,
            config=config,
        )

        render_text = provider_text
        transform_metadata = self._passthrough_metadata(config=config, transform_type="localization")
        if decision.should_transform and decision.source_language and decision.target_language:
            render_text, transform_metadata = self._cached_transform(
                text=provider_text,
                source_language=decision.source_language,
                target_language=decision.target_language,
                transform_type="localization",
                transform=lambda: self.adapter.localize(
                    text=provider_text,
                    source_language=decision.source_language,
                    target_language=decision.target_language,
                    preserve_literal_segments=config.output.preserve_literals,
                ),
                config=config,
            )

        response_message_id = message_id or str(uuid.uuid4())
        provider_variant = MessageVariant(
            message_id=response_message_id,
            variant_kind="provider",
            language_code=config.provider_language,
            content=provider_text,
            transform_name="none",
            source_hash=self._hash(provider_text),
            metadata={"content_kind": content_kind},
        )
        render_variant = MessageVariant(
            message_id=response_message_id,
            variant_kind="render",
            language_code=decision.target_language or config.provider_language,
            content=render_text,
            transform_name="localization" if decision.should_transform else "none",
            source_hash=self._hash(provider_text),
            metadata={
                "content_kind": content_kind,
                "reason": decision.reason,
                "transform": transform_metadata,
            },
        )
        if self.variant_store:
            legacy_content = render_text if render_text != provider_text else provider_text
            self.variant_store.save_message_variants(
                message_id=response_message_id,
                legacy_content=legacy_content,
                variants=[provider_variant, render_variant],
                role="assistant",
                metadata={
                    "session_id": session_ctx.session_id,
                    "content_kind": content_kind,
                },
            )

        return LocalizedResponse(
            provider_content=provider_text,
            render_content=render_text,
            render_language=decision.target_language or config.provider_language,
            provider_variant=provider_variant,
            render_variant=render_variant,
            metadata={
                "content_kind": content_kind,
                "decision_reason": decision.reason,
                "user_language": session_ctx.last_user_language,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                "transform": transform_metadata,
            },
        )

    def mediate_tool_result(
        self,
        session_ctx: SessionContext,
        tool_output: str,
        *,
        tool_name: str | None = None,
        message_id: str | None = None,
    ) -> MediatedToolResult:
        config = session_ctx.config
        started_at = time.perf_counter()
        content_kind = self.classifier.classify(tool_output)
        detection = self._detect(self._tool_detection_text(tool_output) or tool_output, config=config)
        decision = self.policy.decide_tool_result(
            tool_name=tool_name,
            text=tool_output,
            detected_language=detection.language_code,
            detection_confidence=detection.confidence,
            content_kind=content_kind,
            config=config,
        )

        provider_text = tool_output
        segmentation_metadata = self._tool_segmentation_metadata(tool_output)
        transform_metadata = self._passthrough_metadata(config=config, transform_type="tool_result")
        if decision.action == "segment_then_normalize" and decision.source_language and decision.target_language:
            provider_text, transform_metadata = self._cached_transform(
                text=tool_output,
                source_language=decision.source_language,
                target_language=decision.target_language,
                transform_type="tool_result",
                transform=lambda: self._transform_tool_result_text(
                    tool_output,
                    source_language=decision.source_language,
                    target_language=decision.target_language,
                ),
                config=config,
                transform_version=config.tool_results.transform_version,
                policy_version=f"tool_results:{config.tool_results.policy_version}:{content_kind}:{tool_name or 'unknown'}",
            )

        tool_message_id = message_id or str(uuid.uuid4())
        raw_variant = MessageVariant(
            message_id=tool_message_id,
            variant_kind="raw",
            language_code=detection.language_code,
            content=tool_output,
            transform_name=None,
            source_hash=self._hash(tool_output),
            metadata={"content_kind": content_kind, "tool_name": tool_name},
        )
        provider_variant = MessageVariant(
            message_id=tool_message_id,
            variant_kind="provider",
            language_code=decision.target_language or detection.language_code,
            content=provider_text,
            transform_name="tool_result_translation" if decision.action == "segment_then_normalize" else "none",
            source_hash=self._hash(tool_output),
            metadata={
                "content_kind": content_kind,
                "decision_action": decision.action,
                "reason": decision.reason,
                "tool_name": tool_name,
                "transform": transform_metadata,
                "segmentation": segmentation_metadata,
            },
        )
        if self.variant_store:
            self.variant_store.save_message_variants(
                message_id=tool_message_id,
                legacy_content=provider_text,
                variants=[raw_variant, provider_variant],
                role="tool",
                metadata={
                    "session_id": session_ctx.session_id,
                    "content_kind": content_kind,
                    "tool_name": tool_name,
                    "decision_action": decision.action,
                    "decision_reason": decision.reason,
                },
            )

        return MediatedToolResult(
            tool_name=tool_name,
            raw_content=tool_output,
            provider_content=provider_text,
            detection=detection,
            content_kind=content_kind,
            decision=decision,
            raw_variant=raw_variant,
            provider_variant=provider_variant,
            metadata={
                "session_id": session_ctx.session_id,
                "tool_name": tool_name,
                "decision_action": decision.action,
                "decision_reason": decision.reason,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                "detection": {
                    "language_code": detection.language_code,
                    "confidence": detection.confidence,
                    "reason": detection.reason,
                },
                "transform": transform_metadata,
                "segmentation": segmentation_metadata,
            },
        )

    def prepare_prompt_artifacts(
        self,
        session_ctx: SessionContext,
        artifacts: list[PromptArtifact],
        *,
        force_rebuild: bool = False,
    ) -> PreparedPromptArtifacts:
        if session_ctx.prepared_prompt_artifacts is not None and not force_rebuild:
            return session_ctx.prepared_prompt_artifacts

        started_at = time.perf_counter()
        prepared = tuple(
            self._prepare_prompt_artifact(session_ctx, artifact)
            for artifact in sorted(artifacts, key=prompt_artifact_sort_key)
        )
        session_ctx.prepared_prompt_artifacts = PreparedPromptArtifacts(
            session_id=session_ctx.session_id,
            artifacts=prepared,
            metadata={
                "artifact_ids": [artifact.artifact_id for artifact in prepared],
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                "cache_hits": sum(1 for artifact in prepared if artifact.used_cached_variant),
                "provider_variants": sum(1 for artifact in prepared if artifact.used_provider_variant),
            },
        )
        return session_ctx.prepared_prompt_artifacts

    def prepare_compression_input(
        self,
        session_ctx: SessionContext,
        *,
        selector: str | None = None,
    ) -> CompressionInput:
        transcript = self._prepare_internal_transcript(
            session_ctx,
            purpose="compression",
            selector=selector or session_ctx.config.compression.transcript_selector,
        )
        return CompressionInput(
            selector_requested=transcript.selector_requested,
            selector_used=transcript.selector_used,
            messages=transcript.messages,
            content=transcript.content,
            metadata=transcript.metadata,
        )

    def persist_compression_summary(
        self,
        session_ctx: SessionContext,
        provider_summary: str,
        *,
        message_id: str | None = None,
        include_render_variant: bool | None = None,
    ) -> PersistedCompressionSummary:
        if self.variant_store is None:
            raise ValueError("persist_compression_summary requires a configured variant_store")

        config = session_ctx.config
        started_at = time.perf_counter()
        content_kind = self.classifier.classify(provider_summary)
        summary_message_id = message_id or str(uuid.uuid4())
        provider_variant = MessageVariant(
            message_id=summary_message_id,
            variant_kind="provider",
            language_code=config.provider_language,
            content=provider_summary,
            transform_name="compression_summary",
            source_hash=self._hash(provider_summary),
            metadata={
                "content_kind": content_kind,
                "artifact_kind": "compression_summary",
                "persist_mode": config.compression.persist_mode,
            },
        )

        should_include_render = include_render_variant
        if should_include_render is None:
            should_include_render = config.compression.persist_mode == "provider_plus_render"

        render_variant = None
        render_content = None
        render_metadata = self._passthrough_metadata(config=config, transform_type="compression_summary")
        if should_include_render:
            localized = self.localize_assistant_output(session_ctx, provider_summary, message_id=summary_message_id)
            render_content = localized.render_content
            render_variant = MessageVariant(
                message_id=summary_message_id,
                variant_kind="render",
                language_code=localized.render_language,
                content=localized.render_content,
                transform_name="compression_summary_localization" if localized.render_content != provider_summary else "none",
                source_hash=self._hash(provider_summary),
                metadata={
                    "content_kind": content_kind,
                    "artifact_kind": "compression_summary",
                    "transform": localized.metadata.get("transform", {}),
                },
            )
            render_metadata = localized.metadata.get("transform", render_metadata)

        variants = [provider_variant]
        if render_variant is not None:
            variants.append(render_variant)

        # Keep provider text canonical even when a render summary is also stored.
        self.variant_store.save_message_variants(
            message_id=summary_message_id,
            legacy_content=provider_summary,
            variants=variants,
            role="assistant",
            metadata={
                "session_id": session_ctx.session_id,
                "content_kind": content_kind,
                "artifact_kind": "compression_summary",
                "persist_mode": config.compression.persist_mode,
            },
        )
        return PersistedCompressionSummary(
            provider_content=provider_summary,
            render_content=render_content,
            provider_variant=provider_variant,
            render_variant=render_variant,
            metadata={
                "session_id": session_ctx.session_id,
                "persist_mode": config.compression.persist_mode,
                "render_variant_included": render_variant is not None,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                "render_transform": render_metadata,
            },
        )

    def prepare_memory_payload(
        self,
        session_ctx: SessionContext,
        *,
        path_kind: str,
        selector: str | None = None,
        provider_summary: str | None = None,
    ) -> MemoryPayload:
        if provider_summary is not None:
            return MemoryPayload(
                path_kind=path_kind,
                source_kind="summary",
                selector_requested=None,
                selector_used=None,
                messages=(),
                content=provider_summary,
                metadata={
                    "session_id": session_ctx.session_id,
                    "source_kind": "summary",
                    "explicit_render_opt_in": False,
                    "fallback_reason": None,
                },
            )

        purpose = "memory_builtin" if path_kind == "built_in" else "memory_external"
        default_selector = (
            session_ctx.config.memory.built_in_selector
            if path_kind == "built_in"
            else session_ctx.config.memory.external_selector
        )
        transcript = self._prepare_internal_transcript(
            session_ctx,
            purpose=purpose,
            selector=selector or default_selector,
        )
        return MemoryPayload(
            path_kind=path_kind,
            source_kind="transcript",
            selector_requested=transcript.selector_requested,
            selector_used=transcript.selector_used,
            messages=transcript.messages,
            content=transcript.content,
            metadata={
                **transcript.metadata,
                "source_kind": "transcript",
            },
        )

    def prepare_delegation_payload(
        self,
        session_ctx: SessionContext,
        *,
        selector: str | None = None,
    ) -> DelegationPayload:
        transcript = self._prepare_internal_transcript(
            session_ctx,
            purpose="delegation",
            selector=selector or session_ctx.config.delegation.transcript_selector,
        )
        inherit_render_context = session_ctx.config.delegation.inherit_render_context
        return DelegationPayload(
            selector_requested=transcript.selector_requested,
            selector_used=transcript.selector_used,
            messages=transcript.messages,
            content=transcript.content,
            provider_language=session_ctx.config.provider_language,
            render_language=session_ctx.last_user_language if inherit_render_context else None,
            mediation_enabled=session_ctx.config.enabled,
            metadata={
                **transcript.metadata,
                "inherit_render_context": inherit_render_context,
            },
        )

    def build_child_session_context(
        self,
        parent_session_ctx: SessionContext,
        *,
        child_session_id: str,
        enabled: bool | None = None,
        provider_language: str | None = None,
        render_language: str | None = None,
        inherit_render_context: bool | None = None,
    ) -> SessionContext:
        delegation_config = parent_session_ctx.config.delegation
        inherit_render = (
            delegation_config.inherit_render_context
            if inherit_render_context is None
            else inherit_render_context
        )
        inherit_enabled = delegation_config.inherit_enabled
        child_enabled = parent_session_ctx.config.enabled if enabled is None and inherit_enabled else bool(enabled)
        child_provider_language = provider_language or parent_session_ctx.config.provider_language
        child_render_language = render_language or parent_session_ctx.config.render_language
        child_config = replace(
            parent_session_ctx.config,
            enabled=child_enabled,
            provider_language=child_provider_language,
            render_language=child_render_language,
        )
        return SessionContext(
            session_id=child_session_id,
            config=child_config,
            last_user_language=parent_session_ctx.last_user_language if inherit_render else None,
            metadata={
                "delegation_inheritance": {
                    "parent_session_id": parent_session_ctx.session_id,
                    "inherit_enabled": inherit_enabled,
                    "inherit_render_context": inherit_render,
                    "provider_language": child_provider_language,
                    "render_language": child_render_language,
                    "mediation_enabled": child_enabled,
                }
            },
        )

    def prepare_gateway_message(
        self,
        session_ctx: SessionContext,
        provider_text: str,
        *,
        message_id: str | None = None,
        surface: str | None = None,
        selector: str | None = None,
        metadata: dict | None = None,
    ) -> GatewayMessage:
        surface_override = None
        if surface is not None:
            surface_override = session_ctx.config.gateway.surface_overrides.get(surface)
        selector_requested = selector or surface_override or session_ctx.config.gateway.outbound_selector
        selector_used = selector_requested
        fallback_reason = None
        selected_variant_kind = None
        language_code = session_ctx.config.provider_language if selector_used == "provider" else None
        content = provider_text

        if not session_ctx.config.enabled and selector_requested != "legacy":
            selector_used = "legacy"
            fallback_reason = "mediation_disabled"

        if message_id is not None and self.variant_store is not None:
            if selector_used == "legacy":
                content = self.variant_store.get_message_content(message_id) or provider_text
            else:
                variant = self.variant_store.get_variant(message_id, selector_used)
                if variant is not None:
                    content = variant.content
                    selected_variant_kind = variant.variant_kind
                    language_code = variant.language_code
                else:
                    content = self.variant_store.get_message_content(message_id) or provider_text
                    fallback_reason = fallback_reason or f"missing_{selector_used}_variant"
        elif selector_used == "render":
            localized = self.localize_assistant_output(session_ctx, provider_text, message_id=message_id)
            content = localized.render_content
            selected_variant_kind = "render"
            language_code = localized.render_language
        elif selector_used == "provider":
            selected_variant_kind = "provider"

        return GatewayMessage(
            content=content,
            selector_requested=selector_requested,
            selector_used=selector_used,
            selected_variant_kind=selected_variant_kind,
            language_code=language_code,
            message_id=message_id,
            surface=surface,
            metadata={
                "session_id": session_ctx.session_id,
                "fallback_reason": fallback_reason,
                "surface_override_applied": surface_override is not None and selector is None,
                "preserved_metadata": metadata or {},
            },
        )

    def _detect(self, text: str, *, config: LanguageMediationConfig) -> DetectionResult:
        if not config.turn_input.detect_language:
            return DetectionResult(language_code=config.provider_language, confidence=1.0, reason="detection_disabled")
        return self.detector.detect(text, min_chars=config.turn_input.min_chars_for_detection)

    def _prepare_internal_transcript(
        self,
        session_ctx: SessionContext,
        *,
        purpose: str,
        selector: str,
    ) -> InternalTranscriptView:
        if self.variant_store is None:
            raise ValueError("internal transcript selection requires a configured variant_store")

        started_at = time.perf_counter()
        selector_requested = selector
        selector_used = selector
        fallback_reason = None
        if not session_ctx.config.enabled and selector != "legacy":
            selector_used = "legacy"
            fallback_reason = "mediation_disabled"

        messages = tuple(self.variant_store.get_transcript(selector_used))
        fallback_count = 0
        if selector_used != "legacy":
            fallback_count = sum(1 for message in messages if message.selected_variant_kind != selector_used)
            if fallback_count:
                fallback_reason = f"missing_{selector_used}_variants"

        return InternalTranscriptView(
            purpose=purpose,
            selector_requested=selector_requested,
            selector_used=selector_used,
            messages=messages,
            content=self._serialize_transcript(messages),
            metadata={
                "session_id": session_ctx.session_id,
                "fallback_count": fallback_count,
                "fallback_reason": fallback_reason,
                "explicit_render_opt_in": selector_requested == "render",
                "message_count": len(messages),
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
            },
        )

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _serialize_transcript(self, messages: tuple) -> str:
        lines = []
        for message in messages:
            role = message.role or "message"
            lines.append(f"{role}: {message.content}")
        return "\n".join(lines)

    def _prepare_prompt_artifact(self, session_ctx: SessionContext, artifact: PromptArtifact) -> PreparedPromptArtifact:
        config = session_ctx.config
        detection = self._detect_prompt_artifact(artifact, config=config)
        content_kind = self.classifier.classify(artifact.content)
        scan_result = self.prompt_artifact_scanner.scan(artifact)
        passthrough_metadata = self._passthrough_metadata(config=config, transform_type=f"prompt_artifact:{artifact.kind}")

        decision_reason = self._prompt_artifact_passthrough_reason(
            artifact=artifact,
            config=config,
            content_kind=content_kind,
            source_language=detection.language_code,
            scan_result=scan_result,
        )
        if decision_reason is not None:
            return PreparedPromptArtifact(
                artifact_id=artifact.artifact_id,
                kind=artifact.kind,
                source_text=artifact.content,
                prepared_text=artifact.content,
                source_language=detection.language_code,
                prepared_language=detection.language_code or config.provider_language,
                content_kind=content_kind,
                decision_reason=decision_reason,
                used_cached_variant=False,
                used_provider_variant=False,
                scan_result=scan_result,
                metadata={
                    "source_name": artifact.source_name,
                    "transform": passthrough_metadata,
                    "source_hash": self._hash(artifact.content),
                },
            )

        prepared_text, transform_metadata = self._cached_transform(
            text=artifact.content,
            source_language=detection.language_code or config.provider_language,
            target_language=config.provider_language,
            transform_type=f"prompt_artifact:{artifact.kind}",
            transform=lambda: self.adapter.translate(
                text=artifact.content,
                source_language=detection.language_code or config.provider_language,
                target_language=config.provider_language,
                preserve_literal_segments=config.output.preserve_literals,
            ),
            config=config,
            transform_version=config.prompt_artifacts.transform_version,
            policy_version=f"prompt_artifacts:{config.prompt_artifacts.policy_version}:{config.prompt_artifacts.privacy_mode}",
        )
        return PreparedPromptArtifact(
            artifact_id=artifact.artifact_id,
            kind=artifact.kind,
            source_text=artifact.content,
            prepared_text=prepared_text,
            source_language=detection.language_code,
            prepared_language=config.provider_language,
            content_kind=content_kind,
            decision_reason="normalize_to_provider_language",
            used_cached_variant=bool(transform_metadata.get("cached")),
            used_provider_variant=prepared_text != artifact.content,
            scan_result=scan_result,
            metadata={
                "source_name": artifact.source_name,
                "transform": transform_metadata,
                "source_hash": self._hash(artifact.content),
            },
        )

    def _detect_prompt_artifact(self, artifact: PromptArtifact, *, config: LanguageMediationConfig) -> DetectionResult:
        if artifact.language_code:
            return DetectionResult(language_code=artifact.language_code, confidence=1.0, reason="artifact_language_supplied")
        return self._detect(artifact.content, config=config)

    def _prompt_artifact_passthrough_reason(
        self,
        *,
        artifact: PromptArtifact,
        config: LanguageMediationConfig,
        content_kind: str,
        source_language: str | None,
        scan_result: PromptArtifactScanResult,
    ) -> str | None:
        if not config.enabled:
            return "mediation_disabled"
        if not config.prompt_artifacts.enabled:
            return "prompt_artifacts_disabled"
        if not scan_result.allowed:
            return f"scan_blocked:{scan_result.reason}"
        if content_kind in {"code", "terminal", "structured"}:
            return "literal_content_passthrough"
        if not source_language:
            return "unknown_language_passthrough"
        if source_language == config.provider_language:
            return "already_in_provider_language"
        if not self._prompt_artifact_translation_allowed(artifact=artifact, config=config):
            return f"privacy_blocked:{config.prompt_artifacts.privacy_mode}"
        return None

    def _prompt_artifact_translation_allowed(self, *, artifact: PromptArtifact, config: LanguageMediationConfig) -> bool:
        privacy_mode = config.prompt_artifacts.privacy_mode
        provider = config.translator.provider.lower()
        is_local_route = provider == "local"
        if privacy_mode == "permissive":
            return True
        if privacy_mode == "local_only":
            return is_local_route
        if is_local_route:
            return True
        return artifact.allow_external_translation

    def _transform_tool_result_text(self, text: str, *, source_language: str, target_language: str) -> str:
        segments = self._segment_tool_output(text)
        transformed: list[str] = []
        for segment_text, is_literal in segments:
            if is_literal or not segment_text:
                transformed.append(segment_text)
                continue
            transformed.append(
                self.adapter.translate(
                    text=segment_text,
                    source_language=source_language,
                    target_language=target_language,
                    preserve_literal_segments=False,
                )
            )
        return "".join(transformed)

    def _segment_tool_output(self, text: str) -> list[tuple[str, bool]]:
        segments: list[tuple[str, bool]] = []
        cursor = 0
        for match in _FENCED_BLOCK_RE.finditer(text):
            if match.start() > cursor:
                segments.extend(self._segment_tool_text_block(text[cursor:match.start()]))
            segments.append((match.group(0), True))
            cursor = match.end()
        if cursor < len(text):
            segments.extend(self._segment_tool_text_block(text[cursor:]))
        return segments

    def _segment_tool_text_block(self, text: str) -> list[tuple[str, bool]]:
        segments: list[tuple[str, bool]] = []
        for line in text.splitlines(keepends=True):
            if self._is_literal_tool_line(line):
                segments.append((line, True))
                continue
            segments.extend(self._segment_inline_literals(line))
        return segments

    def _segment_inline_literals(self, text: str) -> list[tuple[str, bool]]:
        segments: list[tuple[str, bool]] = []
        cursor = 0
        for match in _INLINE_LITERAL_RE.finditer(text):
            if match.start() > cursor:
                segments.append((text[cursor:match.start()], False))
            segments.append((match.group(0), True))
            cursor = match.end()
        if cursor < len(text):
            segments.append((text[cursor:], False))
        return segments

    def _is_literal_tool_line(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if _TOOL_LITERAL_LINE_RE.match(stripped):
            return True
        if _STACK_TRACE_RE.match(stripped):
            return True
        if _STRUCTURED_LINE_RE.match(stripped) and not self.classifier._looks_like_prose(stripped):
            return True
        lowered = stripped.lower()
        if lowered.startswith(_COMMAND_PREFIXES):
            return True
        if stripped.startswith(("|", "+-", "---")) and stripped.count("|") >= 2:
            return True
        return False

    def _tool_segmentation_metadata(self, text: str) -> dict:
        segments = self._segment_tool_output(text)
        literal_segments = sum(1 for segment_text, is_literal in segments if is_literal and segment_text)
        prose_segments = sum(1 for segment_text, is_literal in segments if not is_literal and segment_text.strip())
        return {
            "segment_count": len(segments),
            "literal_segments": literal_segments,
            "prose_segments": prose_segments,
        }

    def _tool_detection_text(self, text: str) -> str:
        segments = self._segment_tool_output(text)
        return " ".join(segment_text.strip() for segment_text, is_literal in segments if not is_literal and segment_text.strip())

    def _cached_transform(
        self,
        *,
        text: str,
        source_language: str,
        target_language: str,
        transform_type: str,
        transform,
        config: LanguageMediationConfig,
        transform_version: str = "v1",
        policy_version: str = "v1",
    ) -> tuple[str, dict]:
        started_at = time.perf_counter()
        metadata = {
            "status": "pass_through",
            "cached": False,
            "fallback_reason": None,
            "transform_type": transform_type,
            "provider": config.translator.provider,
            "model": config.translator.model,
            "timeout_seconds": config.translator.timeout_seconds,
            "duration_ms": 0.0,
        }

        def finalize(result: str, *, status: str, cached: bool = False, fallback_reason: str | None = None) -> tuple[str, dict]:
            metadata["status"] = status
            metadata["cached"] = cached
            metadata["fallback_reason"] = fallback_reason
            metadata["duration_ms"] = round((time.perf_counter() - started_at) * 1000, 3)
            return result, metadata

        if not self.cache:
            try:
                return finalize(transform(), status="transformed")
            except Exception as exc:
                return finalize(text, status="pass_through", fallback_reason=type(exc).__name__)

        key = TransformCacheKey(
            source_hash=self._hash(text),
            source_language=source_language,
            target_language=target_language,
            transform_type=transform_type,
            transform_version=transform_version,
            policy_version=policy_version,
            model_provider=config.translator.provider,
            model_name=config.translator.model,
        )
        lookup = self.cache.lookup(key)
        metadata["cache_lookup_status"] = lookup.status
        if lookup.content is not None:
            return finalize(lookup.content, status="cache_hit", cached=True)
        try:
            result = transform()
        except Exception as exc:
            return finalize(text, status="pass_through", fallback_reason=type(exc).__name__)
        metadata["cache_store_status"] = "stored" if self.cache.store(key, result) else "store_failure"
        return finalize(result, status="transformed")

    def _passthrough_metadata(self, *, config: LanguageMediationConfig, transform_type: str) -> dict:
        return {
            "status": "pass_through",
            "cached": False,
            "fallback_reason": None,
            "transform_type": transform_type,
            "provider": config.translator.provider,
            "model": config.translator.model,
            "timeout_seconds": config.translator.timeout_seconds,
            "duration_ms": 0.0,
        }
