from unilang.config import LanguageMediationConfig
from unilang.language_policy import LanguagePolicyEngine


def test_policy_normalizes_non_provider_input() -> None:
    policy = LanguagePolicyEngine()
    config = LanguageMediationConfig(enabled=True)

    decision = policy.decide_user_input(
        text="Leia esse arquivo",
        detected_language="pt-BR",
        content_kind="natural_text",
        config=config,
    )

    assert decision.should_transform is True
    assert decision.target_language == "en"


def test_policy_skips_provider_language_input() -> None:
    policy = LanguagePolicyEngine()
    config = LanguageMediationConfig(enabled=True)

    decision = policy.decide_user_input(
        text="Read this file",
        detected_language="en",
        content_kind="natural_text",
        config=config,
    )

    assert decision.should_transform is False
    assert decision.reason == "already_in_provider_language"


def test_policy_localizes_back_to_last_user_language() -> None:
    policy = LanguagePolicyEngine()
    config = LanguageMediationConfig(enabled=True, render_language="auto")

    decision = policy.decide_output_render(
        provider_text="The module initializes the runtime.",
        user_language="pt-BR",
        content_kind="natural_text",
        config=config,
    )

    assert decision.should_transform is True
    assert decision.target_language == "pt-BR"


def test_policy_is_disabled_by_default() -> None:
    policy = LanguagePolicyEngine()
    config = LanguageMediationConfig()

    decision = policy.decide_user_input(
        text="Leia esse arquivo",
        detected_language="pt-BR",
        content_kind="natural_text",
        config=config,
    )

    assert decision.should_transform is False
    assert decision.reason == "mediation_disabled"
