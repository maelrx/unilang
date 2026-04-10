from unilang.language_detector import LanguageDetector


def test_detects_english_input() -> None:
    detector = LanguageDetector()

    result = detector.detect("Read this file and tell me what the module does.")

    assert result.language_code == "en"
    assert result.confidence > 0


def test_detects_portuguese_input() -> None:
    detector = LanguageDetector()

    result = detector.detect("Leia esse arquivo e me diga o que esse modulo faz para o usuario.")

    assert result.language_code == "pt-BR"
    assert result.confidence > 0


def test_returns_unknown_for_very_short_input() -> None:
    detector = LanguageDetector()

    result = detector.detect("oi")

    assert result.language_code is None
    assert result.reason == "too_short"
