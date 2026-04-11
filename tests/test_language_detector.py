from unilang.language_detector import LanguageDetector
import pytest


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


@pytest.mark.parametrize(
    ("language_code", "text"),
    [
        ("es", "Hola, ¿cómo estás hoy? Necesito ayuda con mi código."),
        ("fr", "Bonjour, comment allez-vous aujourd'hui? J'ai besoin d'aide avec mon code."),
        ("de", "Hallo, wie geht es dir heute? Ich brauche Hilfe mit meinem Code."),
        ("zh", "你好，今天怎么样？我需要帮助写代码。"),
        ("ar", "مرحبا، كيف حالك اليوم؟ أحتاج إلى مساعدة في الكود الخاص بي."),
        ("ja", "こんにちは、今日はどうですか？コードのヘルプが必要です。"),
        ("ko", "안녕하세요, 오늘 어떻게 지내고 있나요? 코드 도움이 필요해요."),
        ("it", "Ciao, come stai oggi? Ho bisogno di aiuto con il mio codice."),
        ("ru", "Привет, как дела сегодня? Мне нужна помощь с кодом."),
        ("hi", "नमस्ते, आज आप कैसे हैं? मुझे अपने कोड में मदद चाहिए।"),
        ("nl", "Hallo, hoe gaat het vandaag? Ik heb hulp nodig met mijn code."),
        ("pl", "Cześć, jak się masz dzisiaj? Potrzebuję pomocy z kodem."),
        ("tr", "Merhaba, bugün nasılsın? Kodum için yardıma ihtiyacım var."),
        ("vi", "Xin chào, bạn khỏe không hôm nay? Tôi cần giúp đỡ với code của mình."),
        ("th", "สวัสดีครับ วันนี้เป็นอย่างไร? ผมต้องการความช่วยเหลือเรื่องโค้ด"),
        ("he", "שלום, מה שלומך היום? אני צריך עזרה עם הקוד שלי."),
    ],
)
def test_detects_supported_multilingual_inputs(language_code: str, text: str) -> None:
    detector = LanguageDetector()

    result = detector.detect(text)

    assert result.language_code == language_code
    assert result.confidence > 0


def test_supported_languages_filter_can_disable_other_languages() -> None:
    detector = LanguageDetector(supported_languages=["en", "pt-BR"])

    result = detector.detect("Hola, ¿cómo estás hoy? Necesito ayuda con mi código.")

    assert result.language_code is None
    assert result.reason in {"unknown_language", "unsupported_languages"}
