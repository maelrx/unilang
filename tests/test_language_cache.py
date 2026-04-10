from unilang.language_cache import LanguageCache, TransformCacheKey


def test_language_cache_roundtrip(tmp_path) -> None:
    cache = LanguageCache(tmp_path / "cache.db")
    key = TransformCacheKey(
        source_hash="hash",
        source_language="pt-BR",
        target_language="en",
        transform_type="translation",
        transform_version="v1",
        policy_version="v1",
        model_provider="main",
        model_name="",
    )

    assert cache.get(key) is None

    cache.set(key, "Read this")

    assert cache.get(key) == "Read this"
