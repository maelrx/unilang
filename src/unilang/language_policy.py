from __future__ import annotations

from .config import LanguageMediationConfig
from .types import ContentKind, TransformDecision


class LanguagePolicyEngine:
    def decide_user_input(
        self,
        *,
        text: str,
        detected_language: str | None,
        content_kind: ContentKind,
        config: LanguageMediationConfig,
    ) -> TransformDecision:
        if not config.enabled:
            return TransformDecision(False, "mediation_disabled", detected_language, config.provider_language, content_kind)
        if not config.turn_input.normalize_user_messages:
            return TransformDecision(False, "input_normalization_disabled", detected_language, config.provider_language, content_kind)
        if content_kind in {"code", "terminal", "structured"}:
            return TransformDecision(False, "literal_content_passthrough", detected_language, config.provider_language, content_kind)
        if not detected_language:
            return self._unknown_input_decision(config=config, content_kind=content_kind)
        if detected_language == config.provider_language:
            return TransformDecision(False, "already_in_provider_language", detected_language, config.provider_language, content_kind)
        return TransformDecision(True, "normalize_to_provider_language", detected_language, config.provider_language, content_kind)

    def decide_output_render(
        self,
        *,
        provider_text: str,
        user_language: str | None,
        content_kind: ContentKind,
        config: LanguageMediationConfig,
    ) -> TransformDecision:
        target_language = self._resolve_render_language(user_language=user_language, config=config)
        if not config.enabled:
            return TransformDecision(False, "mediation_disabled", config.provider_language, target_language, content_kind)
        if not config.output.localize_assistant_messages:
            return TransformDecision(False, "output_localization_disabled", config.provider_language, target_language, content_kind)
        if content_kind in {"code", "terminal", "structured"}:
            return TransformDecision(False, "literal_content_passthrough", config.provider_language, target_language, content_kind)
        if not target_language or target_language == config.provider_language:
            return TransformDecision(False, "render_matches_provider_language", config.provider_language, target_language, content_kind)
        return TransformDecision(True, "localize_to_render_language", config.provider_language, target_language, content_kind)

    def _resolve_render_language(self, *, user_language: str | None, config: LanguageMediationConfig) -> str:
        policy = config.output.response_language_policy
        if policy == "provider_language":
            return config.provider_language
        if policy == "fixed_render_language":
            return config.render_language if config.render_language != "auto" else config.provider_language
        if user_language:
            return user_language
        return config.render_language if config.render_language != "auto" else config.provider_language

    def _unknown_input_decision(self, *, config: LanguageMediationConfig, content_kind: ContentKind) -> TransformDecision:
        fallback = config.turn_input.fallback_on_unknown
        if fallback == "pass_through":
            return TransformDecision(False, "unknown_language_passthrough", None, config.provider_language, content_kind)
        if fallback == "assume_provider_language":
            return TransformDecision(False, "unknown_language_assumed_provider", config.provider_language, config.provider_language, content_kind)
        if config.render_language != "auto" and config.render_language != config.provider_language:
            return TransformDecision(True, "unknown_language_assumed_render", config.render_language, config.provider_language, content_kind)
        return TransformDecision(False, "unknown_language_no_render_hint", None, config.provider_language, content_kind)
