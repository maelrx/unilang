from __future__ import annotations

import sqlite3
from pathlib import Path

from .types import MessageVariant, VariantKind


class VariantStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._ensure_schema()

    def save_variant(self, variant: MessageVariant) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO message_variants (
                    message_id,
                    variant_kind,
                    language_code,
                    content,
                    content_hash,
                    transform_name,
                    transform_version,
                    source_hash,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    variant.message_id,
                    variant.variant_kind,
                    variant.language_code,
                    variant.content,
                    variant.source_hash or "",
                    variant.transform_name,
                    variant.transform_version,
                    variant.source_hash,
                    json_dumps(variant.metadata),
                ),
            )

    def save_variants(self, variants: list[MessageVariant]) -> None:
        for variant in variants:
            self.save_variant(variant)

    def get_variant(self, message_id: str, variant_kind: VariantKind) -> MessageVariant | None:
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT message_id, variant_kind, language_code, content, transform_name,
                       transform_version, source_hash, metadata_json
                FROM message_variants
                WHERE message_id = ? AND variant_kind = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (message_id, variant_kind),
            ).fetchone()
        return _row_to_variant(row) if row else None

    def list_variants(self, message_id: str) -> list[MessageVariant]:
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT message_id, variant_kind, language_code, content, transform_name,
                       transform_version, source_hash, metadata_json
                FROM message_variants
                WHERE message_id = ?
                ORDER BY id ASC
                """,
                (message_id,),
            ).fetchall()
        return [_row_to_variant(row) for row in rows]

    def select_content(self, message_id: str, preferred_kind: VariantKind, *, fallback_content: str | None = None) -> str | None:
        variant = self.get_variant(message_id, preferred_kind)
        if variant:
            return variant.content
        return fallback_content

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS message_variants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    variant_kind TEXT NOT NULL,
                    language_code TEXT,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    transform_name TEXT,
                    transform_version TEXT,
                    source_hash TEXT,
                    metadata_json TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_message_variants_message_id ON message_variants(message_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_message_variants_kind ON message_variants(variant_kind)"
            )


def _row_to_variant(row: tuple) -> MessageVariant:
    return MessageVariant(
        message_id=row[0],
        variant_kind=row[1],
        language_code=row[2],
        content=row[3],
        transform_name=row[4],
        transform_version=row[5],
        source_hash=row[6],
        metadata=json_loads(row[7]),
    )


def json_dumps(data: dict) -> str:
    import json

    return json.dumps(data, sort_keys=True)


def json_loads(value: str | None) -> dict:
    import json

    if not value:
        return {}
    return json.loads(value)
