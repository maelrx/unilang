from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TransformCacheKey:
    source_hash: str
    source_language: str
    target_language: str
    transform_type: str
    transform_version: str
    policy_version: str
    model_provider: str
    model_name: str


@dataclass(frozen=True, slots=True)
class CacheLookupResult:
    content: str | None
    status: str


class LanguageCache:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._stats = {
            "hit": 0,
            "miss": 0,
            "version_mismatch": 0,
            "store_failure": 0,
        }
        self._ensure_schema()

    def get(self, key: TransformCacheKey) -> str | None:
        return self.lookup(key).content

    def lookup(self, key: TransformCacheKey) -> CacheLookupResult:
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT content
                FROM transform_cache
                WHERE source_hash = ?
                  AND source_language = ?
                  AND target_language = ?
                  AND transform_type = ?
                  AND transform_version = ?
                  AND policy_version = ?
                  AND model_provider = ?
                  AND model_name = ?
                LIMIT 1
                """,
                (
                    key.source_hash,
                    key.source_language,
                    key.target_language,
                    key.transform_type,
                    key.transform_version,
                    key.policy_version,
                    key.model_provider,
                    key.model_name,
                ),
            ).fetchone()
            if row:
                self._stats["hit"] += 1
                return CacheLookupResult(content=row[0], status="hit")

            version_mismatch = connection.execute(
                """
                SELECT 1
                FROM transform_cache
                WHERE source_hash = ?
                  AND source_language = ?
                  AND target_language = ?
                  AND transform_type = ?
                  AND model_provider = ?
                  AND model_name = ?
                LIMIT 1
                """,
                (
                    key.source_hash,
                    key.source_language,
                    key.target_language,
                    key.transform_type,
                    key.model_provider,
                    key.model_name,
                ),
            ).fetchone()

        status = "version_mismatch" if version_mismatch else "miss"
        self._stats[status] += 1
        return CacheLookupResult(content=None, status=status)

    def set(self, key: TransformCacheKey, content: str) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO transform_cache (
                    source_hash,
                    source_language,
                    target_language,
                    transform_type,
                    transform_version,
                    policy_version,
                    model_provider,
                    model_name,
                    content
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key.source_hash,
                    key.source_language,
                    key.target_language,
                    key.transform_type,
                    key.transform_version,
                    key.policy_version,
                    key.model_provider,
                    key.model_name,
                    content,
                ),
            )

    def store(self, key: TransformCacheKey, content: str) -> bool:
        try:
            self.set(key, content)
        except sqlite3.Error:
            self._stats["store_failure"] += 1
            return False
        return True

    def stats_snapshot(self) -> dict[str, int]:
        return dict(self._stats)

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS transform_cache (
                    source_hash TEXT NOT NULL,
                    source_language TEXT NOT NULL,
                    target_language TEXT NOT NULL,
                    transform_type TEXT NOT NULL,
                    transform_version TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    model_provider TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    PRIMARY KEY (
                        source_hash,
                        source_language,
                        target_language,
                        transform_type,
                        transform_version,
                        policy_version,
                        model_provider,
                        model_name
                    )
                )
                """
            )
