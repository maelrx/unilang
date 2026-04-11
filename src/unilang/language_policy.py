from __future__ import annotations

from .config import LanguageMediationConfig
from .types import ContentKind, ToolResultDecision, TransformDecision


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

    def decide_tool_result(
        self,
        *,
        tool_name: str | None,
        text: str,
        detected_language: str | None,
        detection_confidence: float,
        content_kind: ContentKind,
        config: LanguageMediationConfig,
    ) -> ToolResultDecision:
        target_language = config.provider_language
        normalized_tool_name = (tool_name or "").strip()
        allowlist = set(config.tool_results.allowlisted_tools)
        denylist = set(config.tool_results.denylisted_tools)

        if not config.enabled:
            return ToolResultDecision("pass_through", "mediation_disabled", detected_language, target_language, content_kind)
        if not config.tool_results.enabled:
            return ToolResultDecision("pass_through", "tool_results_disabled", detected_language, target_language, content_kind)
        if normalized_tool_name and normalized_tool_name in denylist:
            return ToolResultDecision("blocked", "tool_denylisted", detected_language, target_language, content_kind)
        if allowlist and normalized_tool_name not in allowlist:
            return ToolResultDecision("blocked", "tool_not_allowlisted", detected_language, target_language, content_kind)
        if content_kind in {"code", "terminal", "structured"}:
            return ToolResultDecision("pass_through", "literal_content_passthrough", detected_language, target_language, content_kind)
        if len(text.strip()) < config.tool_results.min_chars_for_normalization:
            return ToolResultDecision("pass_through", "below_tool_char_threshold", detected_language, target_language, content_kind)
        if len(text) > config.tool_results.max_chars_for_normalization:
            return ToolResultDecision("blocked", "tool_output_too_large", detected_language, target_language, content_kind)
        if not detected_language:
            return ToolResultDecision("pass_through", "unknown_language_passthrough", None, target_language, content_kind)
        if detection_confidence < config.tool_results.min_detection_confidence:
            return ToolResultDecision("pass_through", "low_detection_confidence", detected_language, target_language, content_kind)
        if detected_language == target_language:
            return ToolResultDecision("pass_through", "already_in_provider_language", detected_language, target_language, content_kind)
        return ToolResultDecision("segment_then_normalize", "normalize_tool_result_to_provider_language", detected_language, target_language, content_kind)

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
