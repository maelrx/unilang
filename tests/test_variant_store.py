from unilang.types import MessageVariant
from unilang.variant_store import VariantStore


def test_variant_store_saves_and_reads_variants(tmp_path) -> None:
    store = VariantStore(tmp_path / "variants.db")
    raw = MessageVariant(message_id="m1", variant_kind="raw", language_code="pt-BR", content="Leia isso", source_hash="abc")
    provider = MessageVariant(message_id="m1", variant_kind="provider", language_code="en", content="Read this", source_hash="abc")

    store.save_variants([raw, provider])

    selected = store.get_variant("m1", "provider")

    assert selected is not None
    assert selected.content == "Read this"
    assert len(store.list_variants("m1")) == 2


def test_variant_store_select_content_falls_back_to_legacy_text(tmp_path) -> None:
    store = VariantStore(tmp_path / "variants.db")
    store.save_message("missing", "legacy")

    content = store.select_content("missing", "render")

    assert content == "legacy"


def test_variant_store_returns_selector_specific_transcripts_with_legacy_fallback(tmp_path) -> None:
    store = VariantStore(tmp_path / "variants.db")
    user_raw = MessageVariant(message_id="u1", variant_kind="raw", language_code="pt-BR", content="Leia isso")
    user_provider = MessageVariant(message_id="u1", variant_kind="provider", language_code="en", content="Read this")
    assistant_provider = MessageVariant(message_id="a1", variant_kind="provider", language_code="en", content="The runtime starts.")
    assistant_render = MessageVariant(message_id="a1", variant_kind="render", language_code="pt-BR", content="O runtime inicia.")

    store.save_message_variants(
        message_id="u1",
        legacy_content="Read this",
        variants=[user_raw, user_provider],
        role="user",
    )
    store.save_message_variants(
        message_id="a1",
        legacy_content="O runtime inicia.",
        variants=[assistant_provider, assistant_render],
        role="assistant",
    )
    store.save_message("legacy-only", "legacy replay", role="assistant")

    provider_transcript = store.get_transcript("provider")
    render_transcript = store.get_transcript("render")

    assert [message.content for message in provider_transcript] == ["Read this", "The runtime starts.", "legacy replay"]
    assert [message.content for message in render_transcript] == ["Read this", "O runtime inicia.", "legacy replay"]
    assert provider_transcript[1].selected_variant_kind == "provider"
    assert render_transcript[1].selected_variant_kind == "render"


def test_variant_store_migrates_existing_legacy_messages_table(tmp_path) -> None:
    db_path = tmp_path / "variants.db"
    store = VariantStore(db_path)
    store.save_message("legacy", "legacy content", role="assistant")

    reopened = VariantStore(db_path)

    transcript = reopened.get_transcript("provider")

    assert len(transcript) == 1
    assert transcript[0].content == "legacy content"
