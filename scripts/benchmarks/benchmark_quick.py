#!/usr/bin/env python3
"""Quick E2E benchmark with MiniMax - 5 representative languages."""

import gc
import json
import os
import sys
import tempfile
import time
import tracemalloc
from dataclasses import dataclass, asdict
from datetime import datetime

sys.path.insert(0, "/home/hermes/projects/unilang-hermes-dev/workspace/unilang/src")

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY")
if not MINIMAX_API_KEY:
    import pathlib
    env_file = pathlib.Path("/home/hermes/projects/unilang-hermes-dev/workspace/unilang/.env")
    if env_file.exists():
        for line in env_file.read_text().strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                if k == "MINIMAX_API_KEY":
                    MINIMAX_API_KEY = v.strip()

if not MINIMAX_API_KEY:
    raise ValueError("MINIMAX_API_KEY not set")

LANGUAGES = [
    ("en",    "English",   "Hello, how are you today? I need help with my code."),
    ("es",    "Spanish",   "Hola, ¿cómo estás hoy? Necesito ayuda con mi código."),
    ("fr",    "French",    "Bonjour, comment allez-vous aujourd'hui? J'ai besoin d'aide avec mon code."),
    ("de",    "German",    "Hallo, wie geht es dir heute? Ich brauche Hilfe mit meinem Code."),
    ("zh",    "Chinese",   "你好，今天怎么样？我需要帮助写代码。"),
]

TOOL_RESULTS = [
    ("terminal", "The command completed successfully.\n/workspace\nREADME.md\nsrc/\ntests/\npackage.json"),
    ("read_file", "# Project Config\n\n```json\n{\n  \"name\": \"my-project\",\n  \"version\": \"1.0.0\"\n}\n```\n\nFile read successfully."),
]

SYSTEM_PROMPT = "You are a helpful AI assistant with access to tools."

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

def run_test(lang_code, lang_name, text, runtime, ctx):
    r = Result(
        language=lang_code, lang_name=lang_name,
        detected="", detection_ok=False,
        input_norm=False, input_ms=0.0,
        output_loc=False, output_ms=0.0,
        tool_ok=False, tool_ms=0.0,
        output_text=""
    )
    try:
        det = runtime.detector.detect(text)
        r.detected = det.language_code if det else ""
        r.detection_ok = (r.detected == lang_code)
    except:
        pass

    assistant_resp = f"[Response about: {text[:30]}...]\n\nCode:\n```python\ndef hello():\n    print('Hello')\n```"

    try:
        t0 = time.perf_counter()
        norm = runtime.normalize_user_message(ctx, text)
        r.input_ms = (time.perf_counter() - t0) * 1000
        r.input_norm = norm.provider_text != text
    except:
        r.input_ms = -1

    try:
        t0 = time.perf_counter()
        loc = runtime.localize_assistant_output(ctx, assistant_resp)
        r.output_ms = (time.perf_counter() - t0) * 1000
        r.output_loc = loc.render_content != assistant_resp
        r.output_text = loc.render_content[:80].replace("\n", " ")
    except:
        r.output_ms = -1

    try:
        t0 = time.perf_counter()
        for tool_name, raw_content in TOOL_RESULTS:
            mediated = runtime.mediate_tool_result(ctx, raw_content, tool_name=tool_name)
        r.tool_ms = (time.perf_counter() - t0) * 1000
        r.tool_ok = r.tool_ms >= 0
    except:
        r.tool_ms = -1

    return r

def main():
    print("=" * 70)
    print("  UNILANG E2E BENCHMARK (MiniMax) - 5 Languages")
    print(f"  {datetime.now().isoformat()}")
    print("=" * 70)

    from unilang import LanguageRuntime
    from unilang.minimax_adapter import MiniMaxTranslationAdapter
    from unilang.language_policy import LanguagePolicyEngine
    from unilang.language_detector import LanguageDetector
    from unilang.content_classifier import ContentClassifier
    from unilang.prompt_artifacts import AllowAllPromptArtifactScanner
    from unilang.language_cache import LanguageCache
    from unilang.variant_store import VariantStore
    from unilang.language_runtime import SessionContext
    from unilang.config import (
        LanguageMediationConfig, TranslatorConfig, TurnInputConfig,
        OutputConfig, PromptArtifactConfig, ToolResultConfig,
        CompressionConfig, MemoryConfig, DelegationConfig, GatewayConfig,
    )
    import uuid

    cache_db = tempfile.mktemp(suffix=".db")
    variant_db = tempfile.mktemp(suffix=".db")

    runtime = LanguageRuntime(
        policy=LanguagePolicyEngine(),
        detector=LanguageDetector(),
        classifier=ContentClassifier(),
        adapter=MiniMaxTranslationAdapter(api_key=MINIMAX_API_KEY, model="MiniMax-M2.7-highspeed"),
        cache=LanguageCache(cache_db),
        variant_store=VariantStore(variant_db),
        prompt_artifact_scanner=AllowAllPromptArtifactScanner(),
    )

    results = []
    for lang_code, lang_name, text in LANGUAGES:
        config = LanguageMediationConfig(
            enabled=True,
            provider_language="en",
            render_language="auto",
            translator=TranslatorConfig(provider="minimax"),
            turn_input=TurnInputConfig(),
            output=OutputConfig(),
            prompt_artifacts=PromptArtifactConfig(),
            tool_results=ToolResultConfig(),
            compression=CompressionConfig(),
            memory=MemoryConfig(),
            delegation=DelegationConfig(),
            gateway=GatewayConfig(),
        )
        ctx = SessionContext(
            session_id=f"bench-{uuid.uuid4().hex[:8]}",
            config=config,
            last_user_language=lang_code,
        )

        print(f"\n[{lang_name}] Testing...", flush=True)
        r = run_test(lang_code, lang_name, text, runtime, ctx)
        results.append(r)

        det = "Y" if r.detection_ok else "N"
        norm = "Y" if r.input_norm else "N"
        out = "Y" if r.output_loc else "N"
        tool = "Y" if r.tool_ok else "N"
        print(f"  Det: {det} ({r.detected}) | Norm: {norm} ({r.input_ms:.0f}ms) | "
              f"Loc: {out} ({r.output_ms:.0f}ms) | Tool: {tool} ({r.tool_ms:.0f}ms)")

    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)

    det_acc = sum(1 for r in results if r.detection_ok)
    norm_cnt = sum(1 for r in results if r.input_norm)
    loc_cnt = sum(1 for r in results if r.output_loc)
    tool_cnt = sum(1 for r in results if r.tool_ok)
    avg_lat = sum(r.total_ms for r in results if r.total_ms > 0) / len(results)

    print(f"  Detection:    {det_acc}/5")
    print(f"  Normalization: {norm_cnt}/5 (translation applied)")
    print(f"  Localization:  {loc_cnt}/5 (output translated)")
    print(f"  Tool Med:      {tool_cnt}/5")
    print(f"  Avg Latency:   {avg_lat:.0f}ms")

    print("\n  LOCALIZATION SAMPLES:")
    for r in results:
        if r.output_loc and r.output_text:
            print(f"  [{r.language}] {r.output_text}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = f"/tmp/unilang_bench_minimax_{timestamp}.json"
    with open(out_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "adapter": "MiniMax-M2.7-highspeed",
            "results": [asdict(r) for r in results],
        }, f, indent=2)
    print(f"\n  Saved: {out_file}")
    print("=" * 70)

if __name__ == "__main__":
    main()
