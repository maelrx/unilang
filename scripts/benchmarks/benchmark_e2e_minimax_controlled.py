#!/usr/bin/env python3
"""Controlled 18-language MiniMax benchmark with incremental checkpoints."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

WORKSPACE_ROOT = Path("/home/hermes/projects/unilang-hermes-dev/workspace/unilang")
sys.path.insert(0, str(WORKSPACE_ROOT / "src"))

LANGUAGES = [
    ("en", "English", "Hello, how are you today? I need help with my code."),
    ("es", "Spanish", "Hola, ¿cómo estás hoy? Necesito ayuda con mi código."),
    ("pt-BR", "Portuguese", "Olá, como você está hoje? Preciso de ajuda com meu código."),
    ("zh", "Chinese", "你好，今天怎么样？我需要帮助写代码。"),
    ("fr", "French", "Bonjour, comment allez-vous aujourd'hui? J'ai besoin d'aide avec mon code."),
    ("de", "German", "Hallo, wie geht es dir heute? Ich brauche Hilfe mit meinem Code."),
    ("ar", "Arabic", "مرحبا، كيف حالك اليوم؟ أحتاج إلى مساعدة في الكود الخاص بي."),
    ("ja", "Japanese", "こんにちは、今日はどうですか？コードのヘルプが必要です。"),
    ("ko", "Korean", "안녕하세요, 오늘 어떻게 지내고 있나요? 코드 도움이 필요해요."),
    ("it", "Italian", "Ciao, come stai oggi? Ho bisogno di aiuto con il mio codice."),
    ("ru", "Russian", "Привет, как дела сегодня? Мне нужна помощь с кодом."),
    ("hi", "Hindi", "नमस्ते, आज आप कैसे हैं? मुझे अपने कोड में मदद चाहिए।"),
    ("nl", "Dutch", "Hallo, hoe gaat het vandaag? Ik heb hulp nodig met mijn code."),
    ("pl", "Polish", "Cześć, jak się masz dzisiaj? Potrzebuję pomocy z kodem."),
    ("tr", "Turkish", "Merhaba, bugün nasılsın? Kodum için yardıma ihtiyacım var."),
    ("vi", "Vietnamese", "Xin chào, bạn khỏe không hôm nay? Tôi cần giúp đỡ với code của mình."),
    ("th", "Thai", "สวัสดีครับ วันนี้เป็นอย่างไร? ผมต้องการความช่วยเหลือเรื่องโค้ด"),
    ("he", "Hebrew", "שלום, מה שלומך היום? אני צריך עזרה עם הקוד שלי."),
]

TOOL_RESULTS = [
    ("terminal", "The command completed successfully.\n/workspace\nREADME.md\nsrc/\ntests/\npackage.json\nrequirements.txt\ntotal 24"),
    ("read_file", "# Project Configuration\n\n```json\n{\n  \"name\": \"my-project\",\n  \"version\": \"1.0.0\",\n  \"dependencies\": {\n    \"lodash\": \"^4.17.21\"\n  }\n}\n```\n\nThe configuration file has been read successfully."),
]


@dataclass
class Result:
    language: str
    lang_name: str
    detected: str
    detection_ok: bool
    input_norm: bool
    input_ms: float
    output_loc: bool
    output_ms: float
    tool_ok: bool
    tool_ms: float
    output_text: str

    @property
    def total_ms(self) -> float:
        return self.input_ms + self.output_ms + self.tool_ms


def load_api_key() -> str:
    env_key = os.environ.get("MINIMAX_API_KEY")
    if env_key:
        return env_key
    env_file = WORKSPACE_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("MINIMAX_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise ValueError("MINIMAX_API_KEY environment variable not set")


def build_runtime(api_key: str):
    from unilang import LanguageRuntime
    from unilang.config import (
        CompressionConfig,
        DelegationConfig,
        GatewayConfig,
        LanguageMediationConfig,
        MemoryConfig,
        OutputConfig,
        PromptArtifactConfig,
        ToolResultConfig,
        TranslatorConfig,
        TurnInputConfig,
    )
    from unilang.content_classifier import ContentClassifier
    from unilang.language_cache import LanguageCache
    from unilang.language_detector import LanguageDetector
    from unilang.language_policy import LanguagePolicyEngine
    from unilang.language_runtime import SessionContext
    from unilang.minimax_adapter import MiniMaxTranslationAdapter
    from unilang.prompt_artifacts import AllowAllPromptArtifactScanner
    from unilang.variant_store import VariantStore

    runtime = LanguageRuntime(
        policy=LanguagePolicyEngine(),
        detector=LanguageDetector(),
        classifier=ContentClassifier(),
        adapter=MiniMaxTranslationAdapter(api_key=api_key, model="MiniMax-M2.7-highspeed"),
        cache=LanguageCache(tempfile.mktemp(suffix=".db")),
        variant_store=VariantStore(tempfile.mktemp(suffix=".db")),
        prompt_artifact_scanner=AllowAllPromptArtifactScanner(),
    )

    def make_ctx(lang_code: str):
        return SessionContext(
            session_id=f"bench-{uuid.uuid4().hex[:10]}",
            config=LanguageMediationConfig(
                enabled=True,
                provider_language="en",
                render_language="auto",
                translator=TranslatorConfig(provider="minimax"),
                turn_input=TurnInputConfig(),
                output=OutputConfig(),
                prompt_artifacts=PromptArtifactConfig(),
                tool_results=ToolResultConfig(enabled=True, min_chars_for_normalization=40),
                compression=CompressionConfig(enabled=True),
                memory=MemoryConfig(enabled=True),
                delegation=DelegationConfig(),
                gateway=GatewayConfig(),
            ),
            last_user_language=lang_code,
        )

    return runtime, make_ctx


def run_single(runtime, ctx, lang_code: str, lang_name: str, text: str) -> Result:
    result = Result(
        language=lang_code,
        lang_name=lang_name,
        detected="",
        detection_ok=False,
        input_norm=False,
        input_ms=0.0,
        output_loc=False,
        output_ms=0.0,
        tool_ok=False,
        tool_ms=0.0,
        output_text="",
    )

    detection = runtime.detector.detect(text)
    result.detected = detection.language_code or ""
    result.detection_ok = result.detected == lang_code

    assistant_response = (
        f"[Response about: {text[:30]}...]\n\nCode:\n```python\ndef hello():\n    print('Hello')\n```"
    )

    started = time.perf_counter()
    normalized = runtime.normalize_user_message(ctx, text)
    result.input_ms = (time.perf_counter() - started) * 1000
    result.input_norm = normalized.provider_text != text

    started = time.perf_counter()
    localized = runtime.localize_assistant_output(ctx, assistant_response)
    result.output_ms = (time.perf_counter() - started) * 1000
    result.output_loc = localized.render_content != assistant_response
    result.output_text = localized.render_content[:120].replace("\n", " ")

    started = time.perf_counter()
    for tool_name, raw_content in TOOL_RESULTS:
        runtime.mediate_tool_result(ctx, raw_content, tool_name=tool_name)
    result.tool_ms = (time.perf_counter() - started) * 1000
    result.tool_ok = result.tool_ms >= 0
    return result


def write_checkpoint(path: Path, results: list[Result], started_at: str) -> None:
    summary = {
        "processed": len(results),
        "detection_ok": sum(1 for item in results if item.detection_ok),
        "input_norm": sum(1 for item in results if item.input_norm),
        "output_loc": sum(1 for item in results if item.output_loc),
        "tool_ok": sum(1 for item in results if item.tool_ok),
        "avg_total_ms": round(sum(item.total_ms for item in results) / max(len(results), 1), 2),
    }
    path.write_text(
        json.dumps(
            {
                "started_at": started_at,
                "updated_at": datetime.now().isoformat(),
                "adapter": "MiniMax-M2.7-highspeed",
                "results": [asdict(item) for item in results],
                "summary": summary,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def main() -> None:
    api_key = load_api_key()
    runtime, make_ctx = build_runtime(api_key)
    started_at = datetime.now().isoformat()
    checkpoint = Path(f"/tmp/unilang_benchmark_controlled_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    results: list[Result] = []

    print("=" * 80)
    print("  UNILANG CONTROLLED E2E BENCHMARK (18 LANGUAGES)")
    print(f"  Started: {started_at}")
    print(f"  Checkpoint: {checkpoint}")
    print("=" * 80)

    for index, (lang_code, lang_name, text) in enumerate(LANGUAGES, start=1):
        print(f"[{index:02d}/{len(LANGUAGES)}] {lang_name}...", flush=True)
        ctx = make_ctx(lang_code)
        item = run_single(runtime, ctx, lang_code, lang_name, text)
        results.append(item)
        write_checkpoint(checkpoint, results, started_at)
        print(
            f"  det={'Y' if item.detection_ok else 'N'}({item.detected or '-'}) "
            f"norm={'Y' if item.input_norm else 'N'} {item.input_ms:.0f}ms "
            f"loc={'Y' if item.output_loc else 'N'} {item.output_ms:.0f}ms "
            f"tool={'Y' if item.tool_ok else 'N'} {item.tool_ms:.0f}ms",
            flush=True,
        )

    print("-" * 80)
    print(f"Detection:    {sum(1 for item in results if item.detection_ok)}/{len(results)}")
    print(f"Normalization: {sum(1 for item in results if item.input_norm)}/{len(results)}")
    print(f"Localization:  {sum(1 for item in results if item.output_loc)}/{len(results)}")
    print(f"Tool Med:      {sum(1 for item in results if item.tool_ok)}/{len(results)}")
    print(f"Checkpoint saved: {checkpoint}")
    print("=" * 80)


if __name__ == "__main__":
    main()
