from unilang import (
    BaseTranslationAdapter,
    ContentClassifier,
    LanguageDetector,
    LanguageMediationConfig,
    LanguagePolicyEngine,
    LanguageRuntime,
    SessionContext,
)
import re


class FakeTranslationAdapter(BaseTranslationAdapter):
    def _transform_prose(self, text: str, source_language: str, target_language: str) -> str:
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


def build_runtime() -> LanguageRuntime:
    return LanguageRuntime(
        policy=LanguagePolicyEngine(),
        detector=LanguageDetector(),
        classifier=ContentClassifier(),
        adapter=FakeTranslationAdapter(),
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
