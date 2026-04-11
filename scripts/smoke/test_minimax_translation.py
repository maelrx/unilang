import os
import sys
sys.path.insert(0, "D:/SSOTA/unilang/src")

from unilang.minimax_adapter import MiniMaxTranslationAdapter

API_KEY = os.environ.get("MINIMAX_API_KEY")
if not API_KEY:
    raise ValueError("MINIMAX_API_KEY environment variable not set")

adapter = MiniMaxTranslationAdapter(api_key=API_KEY, model="MiniMax-M2.7-highspeed")

print("Testing MiniMax Translation Adapter...")
print("=" * 60)

test_cases = [
    ("Hello, how are you today?", "en", "es"),
    ("Hola, como estas hoy?", "es", "en"),
    ("Bonjour, comment allez-vous?", "fr", "en"),
    ("Ola, como voce esta hoje?", "pt-BR", "en"),
    ("Guten Tag, wie geht es Ihnen heute?", "de", "en"),
    ("Bonjour, comment allez-vous aujourd'hui? J'ai besoin d'aide avec mon code.", "fr", "en"),
    ("Translate this Portuguese to English: Nao consigo encontrar o erro no meu codigo.", "pt-BR", "en"),
    ("Good morning, I need help debugging this Python function.", "en", "fr"),
]

for text, source, target in test_cases:
    print(f"\n[{source} -> {target}] Input: {text[:60]}")
    try:
        result = adapter.translate(
            text=text,
            source_language=source,
            target_language=target,
            preserve_literal_segments=True,
        )
        print(f"  Output: {result[:80]}")
    except Exception as e:
        print(f"  ERROR: {e}")

print("\n" + "=" * 60)
print("Test complete.")
