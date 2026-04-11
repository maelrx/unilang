from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from unilang import (
    BasePromptArtifactScanner,
    BaseTranslationAdapter,
    ContentClassifier,
    LanguageCache,
    LanguageDetector,
    LanguageMediationConfig,
    LanguagePolicyEngine,
    LanguageRuntime,
    PromptArtifact,
    PromptArtifactConfig,
    PromptArtifactScanResult,
    SessionContext,
    ToolResultConfig,
    VariantStore,
)


class BenchmarkTranslationAdapter(BaseTranslationAdapter):
    def __init__(self) -> None:
        self.calls = 0

    def _transform_prose(self, text: str, source_language: str, target_language: str) -> str:
        self.calls += 1
        if source_language == "pt-BR" and target_language == "en":
            replacements = {
                "Leia": "Read",
                "esse": "this",
                "arquivo": "file",
                "e": "and",
                "me": "me",
                "diga": "tell",
                "o": "the",
                "que": "what",
                "modulo": "module",
                "faz": "does",
                "para": "for",
                "usuario": "user",
            }
            transformed = text
            for source, target in replacements.items():
                transformed = transformed.replace(source, target)
            return transformed
        if source_language == "en" and target_language == "pt-BR":
            transformed = text.replace("The module initializes the runtime.", "O modulo inicializa o runtime.")
            transformed = transformed.replace("The runtime starts.", "O runtime inicia.")
            transformed = transformed.replace("Please read ", "Por favor leia ")
            transformed = transformed.replace(" and explain it.", " e explique isso.")
            return transformed
        return text


class AllowAllScanner(BasePromptArtifactScanner):
    def scan(self, artifact: PromptArtifact) -> PromptArtifactScanResult:
        return PromptArtifactScanResult(True, "scan_clear")


def build_runtime(workdir: Path) -> tuple[LanguageRuntime, BenchmarkTranslationAdapter, LanguageCache]:
    adapter = BenchmarkTranslationAdapter()
    cache = LanguageCache(workdir / "benchmark-cache.db")
    store = VariantStore(workdir / "benchmark-variants.db")
    runtime = LanguageRuntime(
        policy=LanguagePolicyEngine(),
        detector=LanguageDetector(),
        classifier=ContentClassifier(),
        adapter=adapter,
        cache=cache,
        variant_store=store,
        prompt_artifact_scanner=AllowAllScanner(),
    )
    return runtime, adapter, cache


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    index = round((len(values) - 1) * fraction)
    return sorted(values)[index]


def run_operation(iterations: int, fn) -> list[float]:
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000)
    return samples


def summarize(name: str, samples: list[float]) -> dict[str, float | str]:
    return {
        "name": name,
        "iterations": len(samples),
        "mean_ms": round(statistics.fmean(samples), 3),
        "p50_ms": round(percentile(samples, 0.50), 3),
        "p95_ms": round(percentile(samples, 0.95), 3),
    }


def print_table(rows: list[dict[str, float | str]]) -> None:
    print("| workload | iterations | mean_ms | p50_ms | p95_ms |")
    print("|---|---:|---:|---:|---:|")
    for row in rows:
        print(
            f"| {row['name']} | {row['iterations']} | {row['mean_ms']:.3f} | {row['p50_ms']:.3f} | {row['p95_ms']:.3f} |"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic LMR benchmarks.")
    parser.add_argument("--iterations", type=int, default=200, help="Iterations per workload.")
    args = parser.parse_args()

    tempdir = Path(tempfile.mkdtemp(prefix="unilang-bench-"))
    runtime, adapter, cache = build_runtime(tempdir)

    user_config = LanguageMediationConfig(enabled=True)
    prompt_config = LanguageMediationConfig(
        enabled=True,
        prompt_artifacts=PromptArtifactConfig(enabled=True, privacy_mode="permissive"),
    )
    tool_config = LanguageMediationConfig(
        enabled=True,
        tool_results=ToolResultConfig(enabled=True, min_chars_for_normalization=20),
    )

    user_text = "Leia esse arquivo e me diga o que esse modulo faz para o usuario."
    provider_text = "The module initializes the runtime."
    tool_text = (
        "Leia esse arquivo e me diga o que esse modulo faz em `run_agent.py`.\n"
        "```python\n"
        "def greet():\n"
        "    return 1\n"
        "```\n"
        "Leia esse arquivo e me diga o que esse modulo faz."
    )
    artifacts = [
        PromptArtifact("mem", "memory_snapshot", "Leia esse arquivo", source_name="memory", language_code="pt-BR"),
        PromptArtifact("ctx", "context_file", "Leia esse arquivo", source_name="ctx.md", language_code="pt-BR"),
    ]

    cold_rows: list[dict[str, float | str]] = []
    warm_rows: list[dict[str, float | str]] = []

    cold_rows.append(
        summarize(
            "normalize_user_message_cold",
            run_operation(
                args.iterations,
                lambda: runtime.normalize_user_message(
                    SessionContext(session_id=f"cold-user-{time.perf_counter_ns()}", config=user_config),
                    f"{user_text} {time.perf_counter_ns()}",
                ),
            ),
        )
    )

    warm_session = SessionContext(session_id="warm-user", config=user_config)
    runtime.normalize_user_message(warm_session, user_text)
    warm_rows.append(
        summarize(
            "normalize_user_message_warm",
            run_operation(args.iterations, lambda: runtime.normalize_user_message(warm_session, user_text)),
        )
    )

    render_session = SessionContext(session_id="render", config=user_config, last_user_language="pt-BR")
    cold_rows.append(
        summarize(
            "localize_assistant_output_cold",
            run_operation(
                args.iterations,
                lambda: runtime.localize_assistant_output(
                    render_session,
                    f"{provider_text} {time.perf_counter_ns()}",
                ),
            ),
        )
    )
    runtime.localize_assistant_output(render_session, provider_text)
    warm_rows.append(
        summarize(
            "localize_assistant_output_warm",
            run_operation(args.iterations, lambda: runtime.localize_assistant_output(render_session, provider_text)),
        )
    )

    cold_rows.append(
        summarize(
            "prepare_prompt_artifacts_cold",
            run_operation(
                args.iterations,
                lambda: runtime.prepare_prompt_artifacts(
                    SessionContext(session_id=f"cold-artifacts-{time.perf_counter_ns()}", config=prompt_config),
                    [
                        PromptArtifact(
                            artifact.artifact_id,
                            artifact.kind,
                            f"{artifact.content} {time.perf_counter_ns()}",
                            source_name=artifact.source_name,
                            language_code=artifact.language_code,
                        )
                        for artifact in artifacts
                    ],
                ),
            ),
        )
    )

    warm_artifact_session = SessionContext(session_id="warm-artifacts", config=prompt_config)
    runtime.prepare_prompt_artifacts(warm_artifact_session, artifacts)
    warm_rows.append(
        summarize(
            "prepare_prompt_artifacts_warm",
            run_operation(args.iterations, lambda: runtime.prepare_prompt_artifacts(warm_artifact_session, artifacts, force_rebuild=True)),
        )
    )

    cold_rows.append(
        summarize(
            "mediate_tool_result_cold",
            run_operation(
                args.iterations,
                lambda: runtime.mediate_tool_result(
                    SessionContext(session_id=f"cold-tool-{time.perf_counter_ns()}", config=tool_config),
                    f"{tool_text}\n{time.perf_counter_ns()}",
                    tool_name="read",
                ),
            ),
        )
    )

    warm_tool_session = SessionContext(session_id="warm-tool", config=tool_config)
    runtime.mediate_tool_result(warm_tool_session, tool_text, tool_name="read")
    warm_rows.append(
        summarize(
            "mediate_tool_result_warm",
            run_operation(args.iterations, lambda: runtime.mediate_tool_result(warm_tool_session, tool_text, tool_name="read")),
        )
    )

    print("# Deterministic LMR Benchmark")
    print()
    print(f"iterations_per_workload: {args.iterations}")
    print(f"workspace: {tempdir}")
    print(f"translation_calls: {adapter.calls}")
    print(f"cache_stats: {cache.stats_snapshot()}")
    print()
    print("## Cold")
    print_table(cold_rows)
    print()
    print("## Warm")
    print_table(warm_rows)


if __name__ == "__main__":
    main()
