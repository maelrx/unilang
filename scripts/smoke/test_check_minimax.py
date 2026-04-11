import sys
sys.path.insert(0, "/home/hermes/projects/unilang-hermes-dev/workspace/unilang/src")

import os
api_key = os.environ.get("MINIMAX_API_KEY")
if not api_key:
    api_key = open("/home/hermes/projects/unilang-hermes-dev/workspace/unilang/.env").read().split("=")[1].strip()

from unilang.minimax_adapter import MiniMaxTranslationAdapter
adapter = MiniMaxTranslationAdapter(api_key=api_key, model="MiniMax-M2.7-highspeed")

result = adapter.translate(
    text="Hello, how are you today?",
    source_language="en",
    target_language="es",
    preserve_literal_segments=True,
)
print(f"Translation OK: {result[:80]}")
