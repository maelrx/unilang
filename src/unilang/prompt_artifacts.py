from __future__ import annotations

from abc import ABC, abstractmethod

from .types import PromptArtifact, PromptArtifactScanResult

_ARTIFACT_KIND_ORDER = {
    "memory_snapshot": 0,
    "profile_snapshot": 1,
    "context_file": 2,
}


class BasePromptArtifactScanner(ABC):
    @abstractmethod
    def scan(self, artifact: PromptArtifact) -> PromptArtifactScanResult:
        raise NotImplementedError


class AllowAllPromptArtifactScanner(BasePromptArtifactScanner):
    def scan(self, artifact: PromptArtifact) -> PromptArtifactScanResult:
        return PromptArtifactScanResult(True, "scan_clear")


def prompt_artifact_sort_key(artifact: PromptArtifact) -> tuple[int, str, str]:
    return (
        _ARTIFACT_KIND_ORDER[artifact.kind],
        artifact.source_name or "",
        artifact.artifact_id,
    )
