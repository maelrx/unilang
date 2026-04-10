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

    content = store.select_content("missing", "render", fallback_content="legacy")

    assert content == "legacy"
