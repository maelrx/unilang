from unilang import (
    BaseTranslationAdapter,
    ContentClassifier,
    LanguageDetector,
    LanguageCache,
    LanguageMediationConfig,
    LanguagePolicyEngine,
    LanguageRuntime,
    SessionContext,
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
            transformed = transformed.replace("Please read ", "Por favor leia ")
            transformed = transformed.replace(" and explain it.", " e explique isso.")
            return transformed
        return text


def build_runtime(*, cache: LanguageCache | None = None, variant_store: VariantStore | None = None, adapter: FakeTranslationAdapter | None = None) -> LanguageRuntime:
    adapter = adapter or FakeTranslationAdapter()
    return LanguageRuntime(
        policy=LanguagePolicyEngine(),
        detector=LanguageDetector(),
        classifier=ContentClassifier(),
        adapter=adapter,
        cache=cache,
        variant_store=variant_store,
    )


def test_runtime_normalizes_pt_br_input_to_provider_language() -> None:
    runtime = build_runtime()
    session_ctx = SessionContext(session_id="s1", config=LanguageMediationConfig())

    normalized = runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")

    assert normalized.provider_text.startswith("Read this file")
    assert normalized.detection.language_code == "pt-BR"
    assert session_ctx.last_user_language == "pt-BR"


def test_runtime_localizes_final_output_to_last_user_language() -> None:
    runtime = build_runtime()
    session_ctx = SessionContext(session_id="s1", config=LanguageMediationConfig())
    session_ctx.last_user_language = "pt-BR"

    localized = runtime.localize_assistant_output(session_ctx, "The module initializes the runtime.")

    assert localized.render_content == "O módulo inicializa o runtime."
    assert localized.render_language == "pt-BR"
    assert localized.render_variant is not None


def test_runtime_leaves_english_input_unchanged() -> None:
    runtime = build_runtime()
    session_ctx = SessionContext(session_id="s1", config=LanguageMediationConfig())

    normalized = runtime.normalize_user_message(session_ctx, "Read this file and explain what the runtime does.")

    assert normalized.provider_text == normalized.raw_text
    assert normalized.decision.should_transform is False


def test_runtime_preserves_code_fences_during_localization() -> None:
    runtime = build_runtime()
    session_ctx = SessionContext(session_id="s1", config=LanguageMediationConfig())
    session_ctx.last_user_language = "pt-BR"
    provider_text = "Please read `run_agent.py` and explain it."

    localized = runtime.localize_assistant_output(session_ctx, provider_text)

    assert "`run_agent.py`" in localized.render_content
    assert localized.render_content.startswith("Por favor leia `run_agent.py`")


def test_runtime_persists_variants_when_store_is_configured(tmp_path) -> None:
    store = VariantStore(tmp_path / "variants.db")
    runtime = build_runtime(variant_store=store)
    session_ctx = SessionContext(session_id="s1", config=LanguageMediationConfig())

    normalized = runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")
    localized = runtime.localize_assistant_output(session_ctx, "The module initializes the runtime.", message_id="a1")

    assert store.get_variant(normalized.raw_variant.message_id, "raw") is not None
    assert store.get_variant(normalized.provider_variant.message_id, "provider") is not None
    assert store.get_variant("a1", "render") is not None
    assert localized.render_variant is not None


def test_runtime_reuses_cache_to_avoid_duplicate_transforms(tmp_path) -> None:
    cache = LanguageCache(tmp_path / "cache.db")
    adapter = FakeTranslationAdapter()
    runtime = build_runtime(cache=cache, adapter=adapter)
    session_ctx = SessionContext(session_id="s1", config=LanguageMediationConfig())

    runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")
    runtime.normalize_user_message(session_ctx, "Leia esse arquivo e me diga o que esse modulo faz")

    assert adapter.calls == 1
