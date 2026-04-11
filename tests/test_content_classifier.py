from unilang.content_classifier import ContentClassifier


def test_classifies_natural_text() -> None:
    classifier = ContentClassifier()

    assert classifier.classify("This is a normal explanatory paragraph about the runtime.") == "natural_text"


def test_classifies_structured_json() -> None:
    classifier = ContentClassifier()

    assert classifier.classify('{"language": "pt-BR", "enabled": true}') == "structured"


def test_classifies_terminal_output() -> None:
    classifier = ContentClassifier()

    assert classifier.classify("$ pytest\nERROR failed test") == "terminal"


def test_classifies_code() -> None:
    classifier = ContentClassifier()

    code = "def greet(name):\n    return f'hello {name}'\n"

    assert classifier.classify(code) == "code"


def test_classifies_mixed_markdown_with_fence() -> None:
    classifier = ContentClassifier()
    mixed = "Please review this snippet:\n```python\ndef greet():\n    return 1\n```\nIt is used in the runtime."

    assert classifier.classify(mixed) == "mixed"


def test_classifies_mixed_prose_and_terminal_output() -> None:
    classifier = ContentClassifier()
    mixed = "Please review the failure below.\nERROR failed test\n$ pytest tests/test_language_runtime.py\nThe command reproduces the issue."

    assert classifier.classify(mixed) == "mixed"
