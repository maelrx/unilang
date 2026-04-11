#!/usr/bin/env python3
"""
E2E Multilingual Benchmark for unilang Language Mediation Runtime.
Uses MiniMaxTranslationAdapter for real translation.

Tests across multiple languages measuring:
  - Language detection accuracy
  - Translation latency overhead (input + output)
  - Cache hit rates
  - Tool result mediation quality
  - Compression input preparation
  - Delegation payload handling
  - Memory usage

Languages tested: EN, ES (Spanish), PT-BR (Portuguese), ZH (Chinese),
FR (French), DE (German), AR (Arabic), JA (Japanese), KO (Korean),
IT (Italian), RU (Russian), HI (Hindi), NL (Dutch), PL (Polish),
TR (Turkish), VI (Vietnamese), TH (Thai), HE (Hebrew)
"""

import gc
import json
import os
import random
import sqlite3
import sys
import tempfile
import time
import tracemalloc
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, "/home/hermes/projects/unilang-hermes-dev/workspace/unilang/src")

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY")
if not MINIMAX_API_KEY:
    raise ValueError("MINIMAX_API_KEY environment variable not set")

LANGUAGES = [
    ("en",    "English",        "Hello, how are you today? I need help with my code."),
    ("es",    "Spanish",        "Hola, ¿cómo estás hoy? Necesito ayuda con mi código."),
    ("pt-BR", "Portuguese",    "Olá, como você está hoje? Preciso de ajuda com meu código."),
    ("zh",    "Chinese",        "你好，今天怎么样？我需要帮助写代码。"),
    ("fr",    "French",         "Bonjour, comment allez-vous aujourd'hui? J'ai besoin d'aide avec mon code."),
    ("de",    "German",          "Hallo, wie geht es dir heute? Ich brauche Hilfe mit meinem Code."),
    ("ar",    "Arabic",         "مرحبا، كيف حالك اليوم؟ أحتاج إلى مساعدة في الكود الخاص بي."),
    ("ja",    "Japanese",        "こんにちは、今日はどうですか？コードのヘルプが必要です。"),
    ("ko",    "Korean",          "안녕하세요, 오늘 어떻게 지내고 있나요? 코드 도움이 필요해요."),
    ("it",    "Italian",         "Ciao, come stai oggi? Ho bisogno di aiuto con il mio codice."),
    ("ru",    "Russian",         "Привет, как дела сегодня? Мне нужна помощь с кодом."),
    ("hi",    "Hindi",          "नमस्ते, आज आप कैसे हैं? मुझे अपने कोड में मदद चाहिए।"),
    ("nl",    "Dutch",           "Hallo, hoe gaat het vandaag? Ik heb hulp nodig met mijn code."),
    ("pl",    "Polish",          "Cześć, jak się masz dzisiaj? Potrzebuję pomocy z kodem."),
    ("tr",    "Turkish",         "Merhaba, bugün nasılsın? Kodum için yardıma ihtiyacım var."),
    ("vi",    "Vietnamese",      "Xin chào, bạn khỏe không hôm nay? Tôi cần giúp đỡ với code của mình."),
    ("th",    "Thai",            "สวัสดีครับ วันนี้เป็นอย่างไร? ผมต้องการความช่วยเหลือเรื่องโค้ด"),
    ("he",    "Hebrew",          "שלום, מה שלומך היום? אני צריך עזרה עם הקוד שלי."),
]

TOOL_RESULTS = [
    ("terminal", "The command completed successfully.\n/workspace\nREADME.md\nsrc/\ntests/\npackage.json\nrequirements.txt\ntotal 24"),
    ("read_file", "# Project Configuration\n\n```json\n{\n  \"name\": \"my-project\",\n  \"version\": \"1.0.0\",\n  \"dependencies\": {\n    \"lodash\": \"^4.17.21\"\n  }\n}\n```\n\nThe configuration file has been read successfully. It contains the project metadata and dependencies."),
    ("web_search", "Found 3 relevant results:\n1. Python Documentation - https://docs.python.org/\n2. Real Python - https://realpython.com/\n3. Python Tutorial - https://www.w3schools.com/python/\n\nThe search returned 3 results in 0.34 seconds."),
    ("browser_navigate", "Page loaded successfully.\nTitle: GitHub - nousresearch/hermes-agent\nURL: https://github.com/nousresearch/hermes-agent\nContent length: 45,231 chars\nImages: 12, Links: 847"),
]

SYSTEM_PROMPT = """You are a helpful AI assistant. You have access to tools for file operations, web search, terminal commands, and more. Always prefer using tools when they can help answer the user's question accurately."""


@dataclass
class BenchmarkResult:
    language: str
    lang_name: str
    enabled: bool
    
    detection_correct: bool = False
    detected_lang: str = ""
    
    input_normalized: bool = False
    input_same_as_output: bool = False
    input_latency_ms: float = 0.0
    
    output_localized: bool = False
    output_text: str = ""
    output_latency_ms: float = 0.0
    
    tool_mediated: bool = False
    tool_latency_ms: float = 0.0
    tool_preserved_code: bool = False
    
    cache_hit_input: bool = False
    cache_hit_output: bool = False
    
    compression_input_ms: float = 0.0
    compression_messages: int = 0
    
    delegation_payload_ms: float = 0.0
    delegation_has_variant: bool = False
    
    peak_memory_kb: float = 0.0
    
    @property
    def total_latency_ms(self) -> float:
        return self.input_latency_ms + self.output_latency_ms + self.tool_latency_ms


def run_benchmark(lang_code: str, lang_name: str, text: str, runtime, enabled: bool, make_ctx) -> BenchmarkResult:
    gc.collect()
    tracemalloc.start()
    start_time = time.perf_counter()
    
    result = BenchmarkResult(
        language=lang_code,
        lang_name=lang_name,
        enabled=enabled,
    )
    
    ctx = make_ctx(lang_code) if make_ctx is not None else None
    
    messages_dict = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    
    if enabled and runtime is not None:
        try:
            detection = runtime.detector.detect(text)
            result.detected_lang = detection.language_code if detection else lang_code
            result.detection_correct = (result.detected_lang == lang_code)
        except Exception as e:
            result.detected_lang = ""
            result.detection_correct = False
    
    assistant_response = f"[This is a response in English about: {text[:30]}...]\n\nCode example:\n```python\ndef hello():\n    print('Hello, World!')\n```"
    
    if enabled and runtime is not None:
        try:
            t0 = time.perf_counter()
            norm_msg = runtime.normalize_user_message(ctx, text)
            result.input_latency_ms = (time.perf_counter() - t0) * 1000
            normalized = norm_msg.provider_text
            result.input_normalized = normalized != text
            result.input_same_as_output = (normalized == text)
        except Exception as e:
            result.input_latency_ms = -1
            normalized = text
    else:
        normalized = text
    
    if enabled and runtime is not None:
        try:
            t0 = time.perf_counter()
            loc_resp = runtime.localize_assistant_output(ctx, assistant_response)
            result.output_latency_ms = (time.perf_counter() - t0) * 1000
            localized = loc_resp.render_content
            result.output_localized = localized != assistant_response
            result.output_text = localized[:200]
        except Exception as e:
            result.output_latency_ms = -1
            localized = assistant_response
    else:
        localized = assistant_response
    
    if enabled and runtime is not None:
        try:
            t0 = time.perf_counter()
            for tool_name, raw_content in TOOL_RESULTS:
                mediated = runtime.mediate_tool_result(
                    ctx, raw_content, tool_name=tool_name,
                )
                if "```" in raw_content and "```" in mediated.raw_content:
                    result.tool_preserved_code = True
            result.tool_latency_ms = (time.perf_counter() - t0) * 1000
            result.tool_mediated = result.tool_latency_ms >= 0
        except Exception as e:
            result.tool_latency_ms = -1
    else:
        result.tool_latency_ms = 0.0
    
    if enabled and runtime is not None:
        try:
            t0 = time.perf_counter()
            _ = runtime.normalize_user_message(ctx, text)
            cache_time = (time.perf_counter() - t0) * 1000
            result.cache_hit_input = cache_time < result.input_latency_ms * 0.1 if result.input_latency_ms > 0 else False
            
            t0 = time.perf_counter()
            _ = runtime.localize_assistant_output(ctx, assistant_response)
            cache_time2 = (time.perf_counter() - t0) * 1000
            result.cache_hit_output = cache_time2 < result.output_latency_ms * 0.1 if result.output_latency_ms > 0 else False
        except:
            pass
    
    if enabled and runtime is not None:
        try:
            t0 = time.perf_counter()
            compr_input = runtime.prepare_compression_input(ctx, selector="provider")
            result.compression_input_ms = (time.perf_counter() - t0) * 1000
            result.compression_messages = len(compr_input.messages)
        except Exception as e:
            result.compression_input_ms = -1
            compr_input_messages = messages_dict
    else:
        compr_input_messages = messages_dict
    
    if enabled and runtime is not None:
        try:
            t0 = time.perf_counter()
            delegation = runtime.prepare_delegation_payload(ctx, selector="provider")
            result.delegation_payload_ms = (time.perf_counter() - t0) * 1000
            result.delegation_has_variant = delegation.selector_used == "provider"
        except Exception as e:
            result.delegation_payload_ms = -1
    else:
        result.delegation_payload_ms = 0.0
    
    _, peak_kb = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    result.peak_memory_kb = peak_kb / 1024
    
    return result


def run_session_memory_benchmark(lang_code: str, lang_name: str, text: str, runtime, enabled: bool, turns: int = 5, make_ctx=None) -> float:
    gc.collect()
    tracemalloc.start()
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    ctx = make_ctx(lang_code) if make_ctx else None
    
    for i in range(turns):
        if enabled and runtime is not None and ctx is not None:
            try:
                norm_msg = runtime.normalize_user_message(ctx, text)
                normalized = norm_msg.provider_text
            except:
                normalized = text
        else:
            normalized = text
        
        messages.append({"role": "user", "content": normalized})
        
        assistant_response = f"[Response turn {i+1}: This is a response in English about: {text[:30]}...]"
        
        if enabled and runtime is not None and ctx is not None:
            try:
                loc_resp = runtime.localize_assistant_output(ctx, assistant_response)
                localized = loc_resp.render_content
            except:
                localized = assistant_response
        else:
            localized = assistant_response
        
        messages.append({"role": "assistant", "content": localized})
        
        if enabled and runtime is not None and ctx is not None:
            try:
                runtime.prepare_compression_input(ctx, selector="provider")
            except:
                pass
    
    _, peak_kb = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak_kb / 1024


def main():
    print("=" * 80)
    print("  UNILANG E2E MULTILINGUAL BENCHMARK (MiniMax Adapter)")
    print(f"  Started: {datetime.now().isoformat()}")
    print("=" * 80)
    print()
    
    results_enabled = []
    results_disabled = []
    memory_comparison = {}
    
    print("[1/4] Setting up unilang runtime (enabled)...")
    import uuid
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
        LanguageMediationConfig,
        TranslatorConfig,
        TurnInputConfig,
        OutputConfig,
        PromptArtifactConfig,
        ToolResultConfig,
        CompressionConfig,
        MemoryConfig,
        DelegationConfig,
        GatewayConfig,
    )

    _cache_db = tempfile.mktemp(suffix=".db")
    _variant_db = tempfile.mktemp(suffix=".db")

    runtime_enabled = LanguageRuntime(
        policy=LanguagePolicyEngine(),
        detector=LanguageDetector(),
        classifier=ContentClassifier(),
        adapter=MiniMaxTranslationAdapter(api_key=MINIMAX_API_KEY, model="MiniMax-M2.7-highspeed"),
        cache=LanguageCache(_cache_db),
        variant_store=VariantStore(_variant_db),
        prompt_artifact_scanner=AllowAllPromptArtifactScanner(),
    )

    def make_session_ctx(lang_code: str) -> SessionContext:
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
        return SessionContext(
            session_id=f"bench-{uuid.uuid4().hex[:8]}",
            config=config,
            last_user_language=lang_code,
        )
    print("  Runtime (enabled) ready.")
    
    print(f"\n[2/4] Running benchmarks WITH unilang enabled ({len(LANGUAGES)} languages)...")
    print("-" * 80)
    
    header = f"{'Language':<12} {'DetOK':>6} {'Norm':>6} {'In(ms)':>8} {'OutOK':>6} {'Out(ms)':>8} {'ToolOK':>6} {'Tool(ms)':>9} {'CacheIn':>7} {'CacheOut':>8} {'Mem(KB)':>8}"
    print(header)
    print("-" * 80)
    
    for lang_code, lang_name, text in LANGUAGES:
        r = run_benchmark(lang_code, lang_name, text, runtime_enabled, enabled=True, make_ctx=make_session_ctx)
        results_enabled.append(r)
        cache_in = "Y" if r.cache_hit_input else "N"
        cache_out = "Y" if r.cache_hit_output else "N"
        det_ok = "Y" if r.detection_correct else "N"
        norm = "Y" if r.input_normalized else "="
        out_ok = "Y" if r.output_localized else "="
        tool_ok = "Y" if r.tool_mediated else "="
        print(f"{lang_name:<12} {det_ok:>6} {norm:>6} {r.input_latency_ms:>8.2f} {out_ok:>6} {r.output_latency_ms:>8.2f} {tool_ok:>6} {r.tool_latency_ms:>9.2f} {cache_in:>7} {cache_out:>8} {r.peak_memory_kb:>8.1f}")
    
    print("-" * 80)
    
    print(f"\n[3/4] Running benchmarks WITH unilang DISABLED ({len(LANGUAGES)} languages)...")
    print("-" * 80)
    print(header.replace("In(ms)", "In(ms)").replace("Out(ms)", "Out(ms)").replace("Tool(ms)", "Tool(ms)"))
    print("-" * 80)
    
    for lang_code, lang_name, text in LANGUAGES:
        r = run_benchmark(lang_code, lang_name, text, None, enabled=False, make_ctx=None)
        results_disabled.append(r)
        print(f"{lang_name:<12} {'-':>6} {'=':>6} {'-':>8} {'=':>6} {'-':>8} {'-':>6} {'-':>9} {'-':>7} {'-':>8} {r.peak_memory_kb:>8.1f}")
    
    print("-" * 80)
    
    print(f"\n[4/4] Multi-turn session memory simulation (5 turns per language)...")
    print("-" * 60)
    print(f"{'Language':<15} {'Enabled Mem':>14} {'Disabled Mem':>14} {'Delta':>10}")
    print("-" * 60)
    
    for lang_code, lang_name, text in LANGUAGES:
        mem_enabled = run_session_memory_benchmark(lang_code, lang_name, text, runtime_enabled, True, turns=5, make_ctx=make_session_ctx)
        mem_disabled = run_session_memory_benchmark(lang_code, lang_name, text, None, False, turns=5, make_ctx=None)
        delta = mem_enabled - mem_disabled
        delta_pct = (delta / mem_disabled * 100) if mem_disabled > 0 else 0
        print(f"{lang_name:<15} {mem_enabled:>14.1f} KB {mem_disabled:>14.1f} KB {delta:>+10.1f} KB ({delta_pct:+.1f}%)")
        memory_comparison[lang_code] = (mem_enabled, mem_disabled, delta)
    
    print("-" * 60)
    
    print("\n" + "=" * 80)
    print("  SUMMARY STATISTICS")
    print("=" * 80)
    
    enabled_latencies = [r.total_latency_ms for r in results_enabled if r.total_latency_ms >= 0]
    disabled_latencies = [r.total_latency_ms for r in results_disabled]
    
    avg_enabled = sum(enabled_latencies) / len(enabled_latencies) if enabled_latencies else 0
    avg_disabled = sum(disabled_latencies) / len(disabled_latencies) if disabled_latencies else 0
    
    cache_hits_in = sum(1 for r in results_enabled if r.cache_hit_input)
    cache_hits_out = sum(1 for r in results_enabled if r.cache_hit_output)
    total_cache_checks = len(LANGUAGES)
    
    detection_accurate = sum(1 for r in results_enabled if r.detection_correct)
    input_normalized = sum(1 for r in results_enabled if r.input_normalized)
    output_localized = sum(1 for r in results_enabled if r.output_localized)
    tool_mediated = sum(1 for r in results_enabled if r.tool_mediated)
    
    avg_mem_enabled = sum(memory_comparison[k][0] for k in memory_comparison) / len(memory_comparison)
    avg_mem_disabled = sum(memory_comparison[k][1] for k in memory_comparison) / len(memory_comparison)
    avg_mem_delta = avg_mem_enabled - avg_mem_disabled
    
    print(f"""
  Language Detection Accuracy:  {detection_accurate}/{len(LANGUAGES)} ({detection_accurate/len(LANGUAGES)*100:.0f}%)
  Input Normalizations:        {input_normalized}/{len(LANGUAGES)} ({input_normalized/len(LANGUAGES)*100:.0f}%)
  Output Localizations:        {output_localized}/{len(LANGUAGES)} ({output_localized/len(LANGUAGES)*100:.0f}%)
  Tool Result Mediations:      {tool_mediated}/{len(LANGUAGES)} ({tool_mediated/len(LANGUAGES)*100:.0f}%)

  Cache Hit Rate (Input):      {cache_hits_in}/{total_cache_checks} ({cache_hits_in/total_cache_checks*100:.0f}%)
  Cache Hit Rate (Output):     {cache_hits_out}/{total_cache_checks} ({cache_hits_out/total_cache_checks*100:.0f}%)

  Avg Total Latency (enabled):  {avg_enabled:.2f} ms
  Avg Total Latency (disabled): {avg_disabled:.2f} ms
  Latency Overhead:             {avg_enabled - avg_disabled:+.2f} ms ({(avg_enabled - avg_disabled)/max(avg_disabled,0.001)*100:+.1f}%)

  Avg Memory (enabled):        {avg_mem_enabled:.1f} KB
  Avg Memory (disabled):        {avg_mem_disabled:.1f} KB
  Memory Overhead:              {avg_mem_delta:+.1f} KB ({avg_mem_delta/max(avg_mem_disabled,0.001)*100:+.1f}%)
""")
    
    print("\n  PER-LANGUAGE BREAKDOWN (unilang ENABLED)")
    print("-" * 80)
    print(f"{'Lang':<8} {'In Norm':>8} {'In ms':>8} {'Out ms':>8} {'Tool ms':>9} {'Norm?':>6} {'CacheIn':>7} {'CacheOut':>8}")
    print("-" * 80)
    for r in results_enabled:
        norm_flag = "Y" if r.input_normalized else "="
        print(f"{r.language:<8} {norm_flag:>8} {r.input_latency_ms:>8.2f} {r.output_latency_ms:>8.2f} {r.tool_latency_ms:>9.2f} {norm_flag:>6} {'Y' if r.cache_hit_input else 'N':>7} {'Y' if r.cache_hit_output else 'N':>8}")
    print("-" * 80)
    
    print("\n  LATENCY BREAKDOWN (ms) — unilang ENABLED")
    print("-" * 80)
    max_lat = max(max(r.input_latency_ms, 0.01) for r in results_enabled) if results_enabled else 1
    for r in results_enabled:
        bar_width = 50
        in_bar = int((r.input_latency_ms / max_lat) * bar_width) if r.input_latency_ms > 0 else 0
        out_bar = int((r.output_latency_ms / max_lat) * bar_width) if r.output_latency_ms > 0 else 0
        tool_bar = int((r.tool_latency_ms / max_lat) * bar_width) if r.tool_latency_ms > 0 else 0
        print(f"  {r.lang_name:<12} |{'#'*in_bar:<50}| In: {r.input_latency_ms:6.2f}ms")
        print(f"  {'':12} |{'#'*out_bar:<50}| Out: {r.output_latency_ms:6.2f}ms")
        print(f"  {'':12} |{'#'*tool_bar:<50}| Tool: {r.tool_latency_ms:6.2f}ms")
        print()
    print("-" * 80)
    
    print("\n  OUTPUT LOCALIZATION QUALITY (sample)")
    print("-" * 80)
    for r in results_enabled:
        if r.output_localized and r.output_text:
            preview = r.output_text[:80].replace('\n', ' ')
            print(f"  [{r.language}] {preview}...")
    print("-" * 80)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"/tmp/unilang_benchmark_minimax_{timestamp}.json"
    
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "languages_tested": len(LANGUAGES),
        "adapter": "MiniMaxTranslationAdapter",
        "model": "MiniMax-M2.7-highspeed",
        "results_enabled": [asdict(r) for r in results_enabled],
        "results_disabled": [asdict(r) for r in results_disabled],
        "memory_comparison": {
            k: {"enabled_kb": v[0], "disabled_kb": v[1], "delta_kb": v[2]}
            for k, v in memory_comparison.items()
        },
        "summary": {
            "detection_accuracy": detection_accurate / len(LANGUAGES),
            "cache_hit_rate_input": cache_hits_in / total_cache_checks,
            "cache_hit_rate_output": cache_hits_out / total_cache_checks,
            "avg_total_latency_enabled_ms": avg_enabled,
            "avg_total_latency_disabled_ms": avg_disabled,
            "latency_overhead_ms": avg_enabled - avg_disabled,
            "avg_memory_enabled_kb": avg_mem_enabled,
            "avg_memory_disabled_kb": avg_mem_disabled,
            "memory_overhead_kb": avg_mem_delta,
        }
    }
    
    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\n  Results saved to: {output_file}")
    print("\n" + "=" * 80)
    print("  BENCHMARK COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
