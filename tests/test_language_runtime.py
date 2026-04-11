from unilang import (
    BasePromptArtifactScanner,
    BaseTranslationAdapter,
    ContentClassifier,
    CompressionConfig,
    DelegationConfig,
    GatewayConfig,
    LanguageDetector,
    LanguageCache,
    LanguageMediationConfig,
    LanguagePolicyEngine,
    LanguageRuntime,
    MemoryConfig,
    MediatedToolResult,
    PromptArtifact,
    PromptArtifactConfig,
    PromptArtifactScanResult,
    SessionContext,
    TransformCacheKey,
    ToolResultConfig,
    VariantStore,
)
import re


class FakeTranslationAdapter(BaseTranslationAdapter):
    def __init__(self) -> None:
        self.calls = 0

    def _transform_prose(self, text: str, source_language: str, target_language: str) -> str:
        self.calls += 1
        if source_language == "pt-BR" and target_language == "en":
            replacements = {
                "Leia": "Read",
                "esse": "this",
                "arquivo": "file",
                "e": "and",
                "me": "me",
                "diga": "tell",
                "o": "the",
                "que": "what",
                "modulo": "module",
                "faz": "does",
            }
            transformed = text
            for source, target in replacements.items():
                transformed = re.sub(rf"\b{re.escape(source)}\b", target, transformed)
            return transformed
        if source_language == "en" and target_language == "pt-BR":
            transformed = text.replace("The module initializes the runtime.", "O módulo inicializa o runtime.")
            transformed = transformed.replace("The runtime starts.", "O runtime inicia.")
            transformed = transformed.replace("Please read ", "Por favor leia ")
            transformed = transformed.replace(" and explain it.", " e explique isso.")
            return transformed
        return text


class FailingTranslationAdapter(BaseTranslationAdapter):
    def _transform_prose(self, text: str, source_language: str, target_language: str) -> str:
        raise RuntimeError("translator unavailable")


class PromptArtifactTranslationAdapter(BaseTranslationAdapter):
    def __init__(self) -> None:
        self.calls = 0

    def _transform_prose(self, text: str, source_language: str, target_language: str) -> str:
        self.calls += 1
        return f"[{target_language}] {text}"


class RecordingPromptArtifactScanner(BasePromptArtifactScanner):
    def __init__(self, *, allowed: bool = True, reason: str = "scan_clear") -> None:
        self.allowed = allowed
        self.reason = reason
        self.calls: list[str] = []

    def scan(self, artifact: PromptArtifact) -> PromptArtifactScanResult:
        self.calls.append(artifact.artifact_id)
        return PromptArtifactScanResult(self.allowed, self.reason)


def build_runtime(
    *,
    cache: LanguageCache | None = None,
    variant_store: VariantStore | None = None,
    adapter: BaseTranslationAdapter | None = None,
    prompt_artifact_scanner: BasePromptArtifactScanner | None = None,
) -> LanguageRuntime:
    adapter = adapter or FakeTranslationAdapter()
    return LanguageRuntime(
        policy=LanguagePolicyEngine(),
        detector=LanguageDetector(),
        classifier=ContentClassifier(),
        adapter=adapter,
        cache=cache,
        variant_store=variant_store,
        prompt_artifact_scanner=prompt_artifact_scanner,
    )


def build_prompt_artifact_config(*, privacy_mode: str = "permissive") -> LanguageMediationConfig:
    return LanguageMediationConfig(
        enabled=True,
        prompt_artifacts=PromptArtifactConfig(enabled=True, privacy_mode=privacy_mode),
    )


def build_tool_result_config(**kwargs) -> LanguageMediationConfig:
    return LanguageMediationConfig(
        enabled=True,
        tool_results=ToolResultConfig(enabled=True, **kwargs),
    )


def build_memory_compression_config(
    *,
    compression_persist_mode: str = "provider_only",
    enabled: bool = True,
) -> LanguageMediationConfig:
    return LanguageMediationConfig(
        enabled=enabled,
        compression=CompressionConfig(enabled=True, persist_mode=compression_persist_mode),
        memory=MemoryConfig(enabled=True),
    )


def build_phase06_config(
    *,
    enabled: bool = True,
    inherit_render_context: bool = False,
    surface_overrides: dict[str, str] | None = None,
) -> LanguageMediationConfig:
    return LanguageMediationConfig(
        enabled=enabled,
        delegation=DelegationConfig(inherit_render_context=inherit_render_context),
        gateway=GatewayConfig(surface_overrides=surface_overrides or {}),
    )


def test_runtime_normalizes_pt_br_input_to_provider_language() -> None:
    runtime = build_runtime()
    session_ctx = SessionContext(session_id="s1", config=LanguageMediationConfig(enabled=True))

    normalized = runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")

    assert normalized.provider_text.startswith("Read this file")
    assert normalized.detection.language_code == "pt-BR"
    assert session_ctx.last_user_language == "pt-BR"


def test_runtime_localizes_final_output_to_last_user_language() -> None:
    runtime = build_runtime()
    session_ctx = SessionContext(session_id="s1", config=LanguageMediationConfig(enabled=True))
    session_ctx.last_user_language = "pt-BR"

    localized = runtime.localize_assistant_output(session_ctx, "The module initializes the runtime.")

    assert localized.render_content == "O módulo inicializa o runtime."
    assert localized.render_language == "pt-BR"
    assert localized.render_variant is not None


def test_runtime_leaves_english_input_unchanged() -> None:
    runtime = build_runtime()
    session_ctx = SessionContext(session_id="s1", config=LanguageMediationConfig(enabled=True))

    normalized = runtime.normalize_user_message(session_ctx, "Read this file and explain what the runtime does.")

    assert normalized.provider_text == normalized.raw_text
    assert normalized.decision.should_transform is False


def test_runtime_preserves_code_fences_during_localization() -> None:
    runtime = build_runtime()
    session_ctx = SessionContext(session_id="s1", config=LanguageMediationConfig(enabled=True))
    session_ctx.last_user_language = "pt-BR"
    provider_text = "Please read `run_agent.py` and explain it."

    localized = runtime.localize_assistant_output(session_ctx, provider_text)

    assert "`run_agent.py`" in localized.render_content
    assert localized.render_content.startswith("Por favor leia `run_agent.py`")


def test_runtime_persists_variants_when_store_is_configured(tmp_path) -> None:
    store = VariantStore(tmp_path / "variants.db")
    runtime = build_runtime(variant_store=store)
    session_ctx = SessionContext(session_id="s1", config=LanguageMediationConfig(enabled=True))

    normalized = runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")
    localized = runtime.localize_assistant_output(session_ctx, "The module initializes the runtime.", message_id="a1")

    assert store.get_variant(normalized.raw_variant.message_id, "raw") is not None
    assert store.get_variant(normalized.provider_variant.message_id, "provider") is not None
    assert store.get_variant("a1", "render") is not None
    assert localized.render_variant is not None
    assert [message.content for message in store.get_transcript("provider")] == [normalized.provider_text, localized.provider_content]
    assert [message.content for message in store.get_transcript("render")] == [normalized.provider_text, localized.render_content]


def test_runtime_reuses_cache_to_avoid_duplicate_transforms(tmp_path) -> None:
    cache = LanguageCache(tmp_path / "cache.db")
    adapter = FakeTranslationAdapter()
    runtime = build_runtime(cache=cache, adapter=adapter)
    session_ctx = SessionContext(session_id="s1", config=LanguageMediationConfig(enabled=True))

    runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")
    runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")

    assert adapter.calls == 1


def test_runtime_reports_cache_version_mismatch_metadata(tmp_path) -> None:
    cache = LanguageCache(tmp_path / "cache.db")
    adapter = FakeTranslationAdapter()
    runtime = build_runtime(cache=cache, adapter=adapter)
    session_ctx = SessionContext(session_id="s1", config=LanguageMediationConfig(enabled=True))
    old_key = TransformCacheKey(
        source_hash=runtime._hash("Leia esse arquivo e me diga o que esse modulo faz"),
        source_language="pt-BR",
        target_language="en",
        transform_type="translation",
        transform_version="v0",
        policy_version="v0",
        model_provider="main",
        model_name="",
    )
    cache.set(old_key, "stale")

    normalized = runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")

    assert normalized.provider_text.startswith("Read this file")
    assert normalized.metadata["transform"]["cache_lookup_status"] == "version_mismatch"


def test_runtime_uses_safe_disabled_default() -> None:
    runtime = build_runtime()
    session_ctx = SessionContext(session_id="s1", config=LanguageMediationConfig())

    normalized = runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")

    assert normalized.provider_text == normalized.raw_text
    assert normalized.metadata["decision_reason"] == "mediation_disabled"


def test_runtime_falls_back_to_pass_through_on_input_transform_failure() -> None:
    runtime = build_runtime(adapter=FailingTranslationAdapter())
    session_ctx = SessionContext(session_id="s1", config=LanguageMediationConfig(enabled=True))

    normalized = runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")

    assert normalized.provider_text == normalized.raw_text
    assert normalized.metadata["transform"]["status"] == "pass_through"
    assert normalized.metadata["transform"]["fallback_reason"] == "RuntimeError"


def test_runtime_falls_back_to_pass_through_on_output_transform_failure() -> None:
    runtime = build_runtime(adapter=FailingTranslationAdapter())
    session_ctx = SessionContext(session_id="s1", config=LanguageMediationConfig(enabled=True))
    session_ctx.last_user_language = "pt-BR"

    localized = runtime.localize_assistant_output(session_ctx, "The module initializes the runtime.")

    assert localized.render_content == localized.provider_content
    assert localized.metadata["transform"]["status"] == "pass_through"
    assert localized.metadata["transform"]["fallback_reason"] == "RuntimeError"


def test_prepare_prompt_artifacts_normalizes_once_and_freezes_bundle_mid_session() -> None:
    adapter = PromptArtifactTranslationAdapter()
    runtime = build_runtime(adapter=adapter)
    session_ctx = SessionContext(session_id="s1", config=build_prompt_artifact_config())
    artifacts = [
        PromptArtifact("ctx", "context_file", "Leia esse arquivo", source_name="b.md", language_code="pt-BR"),
        PromptArtifact("mem", "memory_snapshot", "Leia esse arquivo", source_name="memory", language_code="pt-BR"),
        PromptArtifact("profile", "profile_snapshot", "Leia esse arquivo", source_name="profile", language_code="pt-BR"),
    ]

    prepared = runtime.prepare_prompt_artifacts(session_ctx, artifacts)
    runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")
    prepared_again = runtime.prepare_prompt_artifacts(
        session_ctx,
        [PromptArtifact("ctx", "context_file", "changed", source_name="b.md", language_code="pt-BR")],
    )

    assert [artifact.artifact_id for artifact in prepared.artifacts] == ["mem", "profile", "ctx"]
    assert all(artifact.prepared_text.startswith("[en]") for artifact in prepared.artifacts)
    assert prepared_again is prepared
    assert adapter.calls == 4


def test_prepare_prompt_artifacts_reuses_cache_across_sessions(tmp_path) -> None:
    cache = LanguageCache(tmp_path / "cache.db")
    adapter = PromptArtifactTranslationAdapter()
    runtime = build_runtime(cache=cache, adapter=adapter)
    artifacts = [
        PromptArtifact("mem", "memory_snapshot", "Leia esse arquivo", source_name="memory", language_code="pt-BR"),
        PromptArtifact("profile", "profile_snapshot", "Leia esse arquivo", source_name="profile", language_code="pt-BR"),
    ]

    first_session = SessionContext(session_id="s1", config=build_prompt_artifact_config())
    second_session = SessionContext(session_id="s2", config=build_prompt_artifact_config())
    first_bundle = runtime.prepare_prompt_artifacts(first_session, artifacts)
    second_bundle = runtime.prepare_prompt_artifacts(second_session, artifacts)

    assert adapter.calls == 2
    assert first_bundle.metadata["cache_hits"] == 0
    assert second_bundle.metadata["cache_hits"] == 2
    assert all(artifact.used_cached_variant for artifact in second_bundle.artifacts)


def test_prepare_prompt_artifacts_blocks_disallowed_external_translation() -> None:
    adapter = PromptArtifactTranslationAdapter()
    runtime = build_runtime(adapter=adapter)
    session_ctx = SessionContext(session_id="s1", config=build_prompt_artifact_config(privacy_mode="strict"))
    artifact = PromptArtifact(
        "ctx",
        "context_file",
        "Leia esse arquivo",
        source_name="secrets.md",
        language_code="pt-BR",
        allow_external_translation=False,
    )

    prepared = runtime.prepare_prompt_artifacts(session_ctx, [artifact]).artifacts[0]

    assert prepared.prepared_text == artifact.content
    assert prepared.decision_reason == "privacy_blocked:strict"
    assert adapter.calls == 0


def test_prepare_prompt_artifacts_scans_original_content_before_translation() -> None:
    adapter = PromptArtifactTranslationAdapter()
    scanner = RecordingPromptArtifactScanner(allowed=False, reason="contains_secret")
    runtime = build_runtime(adapter=adapter, prompt_artifact_scanner=scanner)
    session_ctx = SessionContext(session_id="s1", config=build_prompt_artifact_config())
    artifact = PromptArtifact("ctx", "context_file", "Leia esse arquivo", source_name="ctx.md", language_code="pt-BR")

    prepared = runtime.prepare_prompt_artifacts(session_ctx, [artifact]).artifacts[0]

    assert scanner.calls == ["ctx"]
    assert prepared.scan_result.reason == "contains_secret"
    assert prepared.decision_reason == "scan_blocked:contains_secret"
    assert adapter.calls == 0


def test_tool_result_normalizes_large_natural_language_output() -> None:
    runtime = build_runtime()
    session_ctx = SessionContext(session_id="s1", config=build_tool_result_config(min_chars_for_normalization=40))
    tool_output = (
        "Leia esse arquivo e me diga o que esse modulo faz. "
        "Leia esse arquivo e me diga o que esse modulo faz."
    )

    mediated = runtime.mediate_tool_result(session_ctx, tool_output, tool_name="read")

    assert mediated.decision.action == "segment_then_normalize"
    assert mediated.provider_content.startswith("Read this file")
    assert mediated.metadata["transform"]["status"] == "transformed"


def test_tool_result_preserves_fenced_code_and_inline_literals() -> None:
    runtime = build_runtime()
    session_ctx = SessionContext(session_id="s1", config=build_tool_result_config(min_chars_for_normalization=20))
    tool_output = (
        "Leia esse arquivo e me diga o que esse modulo faz em `run_agent.py`.\n"
        "```python\n"
        "def greet():\n"
        "    return 1\n"
        "```\n"
        "Leia esse arquivo e me diga o que esse modulo faz."
    )

    mediated = runtime.mediate_tool_result(session_ctx, tool_output, tool_name="read")

    assert "`run_agent.py`" in mediated.provider_content
    assert "```python\ndef greet():\n    return 1\n```" in mediated.provider_content
    assert "Read this file" in mediated.provider_content


def test_tool_result_preserves_terminal_lines_while_translating_prose() -> None:
    runtime = build_runtime()
    session_ctx = SessionContext(session_id="s1", config=build_tool_result_config(min_chars_for_normalization=20))
    tool_output = (
        "Leia esse arquivo e me diga o que esse modulo faz.\n"
        "ERROR failed test\n"
        "$ pytest tests/test_language_runtime.py\n"
        "Leia esse arquivo e me diga o que esse modulo faz."
    )

    mediated = runtime.mediate_tool_result(session_ctx, tool_output, tool_name="bash")

    assert "ERROR failed test" in mediated.provider_content
    assert "$ pytest tests/test_language_runtime.py" in mediated.provider_content
    assert mediated.provider_content.count("Read this file") == 2


def test_tool_result_passes_through_structured_output() -> None:
    runtime = build_runtime()
    session_ctx = SessionContext(session_id="s1", config=build_tool_result_config(min_chars_for_normalization=10))
    tool_output = '{"mensagem": "Leia esse arquivo e me diga o que esse modulo faz"}'

    mediated = runtime.mediate_tool_result(session_ctx, tool_output, tool_name="json")

    assert mediated.decision.action == "pass_through"
    assert mediated.decision.reason == "literal_content_passthrough"
    assert mediated.provider_content == tool_output


def test_tool_result_respects_threshold_and_provider_language_shortcuts() -> None:
    runtime = build_runtime()
    threshold_session = SessionContext(session_id="s1", config=build_tool_result_config(min_chars_for_normalization=200))
    provider_session = SessionContext(session_id="s2", config=build_tool_result_config(min_chars_for_normalization=20))

    short_result = runtime.mediate_tool_result(threshold_session, "Leia esse arquivo.", tool_name="read")
    provider_result = runtime.mediate_tool_result(
        provider_session,
        "Read this file and explain what the runtime does. Read this file and explain what the runtime does.",
        tool_name="read",
    )

    assert short_result.decision.reason == "below_tool_char_threshold"
    assert short_result.provider_content == "Leia esse arquivo."
    assert provider_result.decision.reason == "already_in_provider_language"


def test_tool_result_respects_allowlist_and_persists_variants(tmp_path) -> None:
    store = VariantStore(tmp_path / "variants.db")
    runtime = build_runtime(variant_store=store)
    session_ctx = SessionContext(
        session_id="s1",
        config=build_tool_result_config(min_chars_for_normalization=20, allowlisted_tools=("read",)),
    )

    blocked = runtime.mediate_tool_result(
        session_ctx,
        "Leia esse arquivo e me diga o que esse modulo faz. Leia esse arquivo e me diga o que esse modulo faz.",
        tool_name="bash",
        message_id="tool-blocked",
    )
    allowed = runtime.mediate_tool_result(
        session_ctx,
        "Leia esse arquivo e me diga o que esse modulo faz. Leia esse arquivo e me diga o que esse modulo faz.",
        tool_name="read",
        message_id="tool-allowed",
    )

    assert blocked.decision.action == "blocked"
    assert blocked.provider_content == blocked.raw_content
    assert store.get_variant("tool-blocked", "raw") is not None
    assert store.get_variant("tool-allowed", "provider") is not None
    assert store.get_transcript("provider")[-1].content.startswith("Read this file")


def test_compression_input_uses_provider_transcript_by_default(tmp_path) -> None:
    store = VariantStore(tmp_path / "variants.db")
    runtime = build_runtime(variant_store=store)
    session_ctx = SessionContext(session_id="s1", config=build_memory_compression_config())

    runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")
    runtime.localize_assistant_output(session_ctx, "The runtime starts.", message_id="a1")

    payload = runtime.prepare_compression_input(session_ctx)

    assert payload.selector_requested == "provider"
    assert payload.selector_used == "provider"
    assert "assistant: The runtime starts." in payload.content
    assert "assistant: O runtime inicia." not in payload.content
    assert payload.metadata["fallback_count"] == 0


def test_compression_input_reports_mixed_legacy_fallback(tmp_path) -> None:
    store = VariantStore(tmp_path / "variants.db")
    runtime = build_runtime(variant_store=store)
    session_ctx = SessionContext(session_id="s1", config=build_memory_compression_config())

    runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")
    store.save_message("legacy-only", "legacy replay", role="assistant")

    payload = runtime.prepare_compression_input(session_ctx)

    assert payload.selector_used == "provider"
    assert payload.metadata["fallback_count"] == 1
    assert payload.metadata["fallback_reason"] == "missing_provider_variants"
    assert payload.messages[-1].content == "legacy replay"


def test_persist_compression_summary_keeps_provider_text_canonical(tmp_path) -> None:
    store = VariantStore(tmp_path / "variants.db")
    runtime = build_runtime(variant_store=store)
    session_ctx = SessionContext(
        session_id="s1",
        config=build_memory_compression_config(compression_persist_mode="provider_plus_render"),
    )
    session_ctx.last_user_language = "pt-BR"

    persisted = runtime.persist_compression_summary(
        session_ctx,
        "The module initializes the runtime.",
        message_id="c1",
    )

    assert persisted.render_content == "O módulo inicializa o runtime."
    assert store.get_message_content("c1") == "The module initializes the runtime."
    assert store.get_variant("c1", "provider").content == "The module initializes the runtime."
    assert store.get_variant("c1", "render").content == "O módulo inicializa o runtime."


def test_memory_payload_uses_provider_transcript_by_default(tmp_path) -> None:
    store = VariantStore(tmp_path / "variants.db")
    runtime = build_runtime(variant_store=store)
    session_ctx = SessionContext(session_id="s1", config=build_memory_compression_config())

    runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")
    session_ctx.last_user_language = "pt-BR"
    runtime.localize_assistant_output(session_ctx, "The runtime starts.", message_id="a1")

    payload = runtime.prepare_memory_payload(session_ctx, path_kind="built_in")

    assert payload.selector_requested == "provider"
    assert payload.selector_used == "provider"
    assert "assistant: The runtime starts." in payload.content
    assert "assistant: O runtime inicia." not in payload.content


def test_external_memory_payload_falls_back_to_legacy_when_mediation_is_disabled(tmp_path) -> None:
    store = VariantStore(tmp_path / "variants.db")
    runtime = build_runtime(variant_store=store)
    session_ctx = SessionContext(session_id="s1", config=build_memory_compression_config(enabled=False))
    store.save_message("m1", "legacy memory text", role="assistant")

    payload = runtime.prepare_memory_payload(session_ctx, path_kind="external")

    assert payload.selector_requested == "provider"
    assert payload.selector_used == "legacy"
    assert payload.metadata["fallback_reason"] == "mediation_disabled"
    assert payload.content == "assistant: legacy memory text"


def test_memory_payload_uses_render_only_with_explicit_opt_in(tmp_path) -> None:
    store = VariantStore(tmp_path / "variants.db")
    runtime = build_runtime(variant_store=store)
    session_ctx = SessionContext(session_id="s1", config=build_memory_compression_config())

    runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")
    session_ctx.last_user_language = "pt-BR"
    runtime.localize_assistant_output(session_ctx, "The runtime starts.", message_id="a1")

    default_payload = runtime.prepare_memory_payload(session_ctx, path_kind="external")
    render_payload = runtime.prepare_memory_payload(session_ctx, path_kind="external", selector="render")

    assert "assistant: O runtime inicia." not in default_payload.content
    assert "assistant: O runtime inicia." in render_payload.content
    assert render_payload.metadata["explicit_render_opt_in"] is True


def test_delegation_payload_uses_provider_transcript_by_default(tmp_path) -> None:
    store = VariantStore(tmp_path / "variants.db")
    runtime = build_runtime(variant_store=store)
    session_ctx = SessionContext(session_id="s1", config=build_phase06_config())

    runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")
    session_ctx.last_user_language = "pt-BR"
    runtime.localize_assistant_output(session_ctx, "The runtime starts.", message_id="a1")

    payload = runtime.prepare_delegation_payload(session_ctx)

    assert payload.selector_requested == "provider"
    assert payload.selector_used == "provider"
    assert "assistant: The runtime starts." in payload.content
    assert "assistant: O runtime inicia." not in payload.content
    assert payload.render_language is None


def test_child_session_context_inherits_provider_defaults_without_render_context() -> None:
    runtime = build_runtime()
    parent = SessionContext(session_id="parent", config=build_phase06_config())
    parent.last_user_language = "pt-BR"

    child = runtime.build_child_session_context(parent, child_session_id="child")

    assert child.config.provider_language == "en"
    assert child.config.enabled is True
    assert child.last_user_language is None
    assert child.metadata["delegation_inheritance"]["inherit_render_context"] is False


def test_child_session_context_can_explicitly_inherit_render_context() -> None:
    runtime = build_runtime()
    parent = SessionContext(session_id="parent", config=build_phase06_config(inherit_render_context=True))
    parent.last_user_language = "pt-BR"

    child = runtime.build_child_session_context(parent, child_session_id="child")
    localized = runtime.localize_assistant_output(child, "The runtime starts.")

    assert child.last_user_language == "pt-BR"
    assert localized.render_content == "O runtime inicia."


def test_nested_child_context_preserves_provider_canonical_defaults() -> None:
    runtime = build_runtime()
    parent = SessionContext(session_id="parent", config=build_phase06_config())
    parent.last_user_language = "pt-BR"

    child = runtime.build_child_session_context(parent, child_session_id="child")
    grandchild = runtime.build_child_session_context(child, child_session_id="grandchild")

    assert child.config.provider_language == "en"
    assert grandchild.config.provider_language == "en"
    assert child.last_user_language is None
    assert grandchild.last_user_language is None


def test_gateway_message_prefers_render_variant_from_store(tmp_path) -> None:
    store = VariantStore(tmp_path / "variants.db")
    runtime = build_runtime(variant_store=store)
    session_ctx = SessionContext(session_id="s1", config=build_phase06_config())
    session_ctx.last_user_language = "pt-BR"

    runtime.localize_assistant_output(session_ctx, "The runtime starts.", message_id="a1")
    outbound = runtime.prepare_gateway_message(
        session_ctx,
        "The runtime starts.",
        message_id="a1",
        metadata={"channel": "telegram"},
    )

    assert outbound.selector_requested == "render"
    assert outbound.selector_used == "render"
    assert outbound.content == "O runtime inicia."
    assert outbound.selected_variant_kind == "render"
    assert outbound.metadata["preserved_metadata"] == {"channel": "telegram"}


def test_gateway_message_uses_surface_override_when_requested(tmp_path) -> None:
    store = VariantStore(tmp_path / "variants.db")
    runtime = build_runtime(variant_store=store)
    session_ctx = SessionContext(
        session_id="s1",
        config=build_phase06_config(surface_overrides={"diagnostic": "provider"}),
    )
    session_ctx.last_user_language = "pt-BR"

    runtime.localize_assistant_output(session_ctx, "The runtime starts.", message_id="a1")
    outbound = runtime.prepare_gateway_message(session_ctx, "The runtime starts.", message_id="a1", surface="diagnostic")

    assert outbound.selector_requested == "provider"
    assert outbound.selector_used == "provider"
    assert outbound.content == "The runtime starts."
    assert outbound.metadata["surface_override_applied"] is True


def test_gateway_message_falls_back_to_legacy_when_mediation_is_disabled(tmp_path) -> None:
    store = VariantStore(tmp_path / "variants.db")
    runtime = build_runtime(variant_store=store)
    session_ctx = SessionContext(session_id="s1", config=build_phase06_config(enabled=False))
    store.save_message("a1", "legacy gateway text", role="assistant")

    outbound = runtime.prepare_gateway_message(session_ctx, "provider text", message_id="a1")

    assert outbound.selector_requested == "render"
    assert outbound.selector_used == "legacy"
    assert outbound.content == "legacy gateway text"
    assert outbound.metadata["fallback_reason"] == "mediation_disabled"
