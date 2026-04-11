from __future__ import annotations

import sqlite3
from pathlib import Path

from .types import MessageVariant, TranscriptMessage, TranscriptSelector, VariantKind


class VariantStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._ensure_schema()

    def save_variant(self, variant: MessageVariant) -> None:
        with sqlite3.connect(self.db_path) as connection:
            self._upsert_variant(connection, variant)

    def save_message(
        self,
        message_id: str,
        content: str,
        *,
        role: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        with sqlite3.connect(self.db_path) as connection:
            self._upsert_message(connection, message_id=message_id, content=content, role=role, metadata=metadata)

    def save_message_variants(
        self,
        *,
        message_id: str,
        legacy_content: str,
        variants: list[MessageVariant],
        role: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        with sqlite3.connect(self.db_path) as connection:
            self._upsert_message(connection, message_id=message_id, content=legacy_content, role=role, metadata=metadata)
            for variant in variants:
                self._upsert_variant(connection, variant)

    def save_variants(
        self,
        variants: list[MessageVariant],
        *,
        legacy_content: str | None = None,
        role: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        if not variants:
            return
        if legacy_content is None:
            for variant in variants:
                self.save_variant(variant)
            return
        self.save_message_variants(
            message_id=variants[0].message_id,
            legacy_content=legacy_content,
            variants=variants,
            role=role,
            metadata=metadata,
        )

    def get_message_content(self, message_id: str) -> str | None:
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT content FROM messages WHERE message_id = ? LIMIT 1",
                (message_id,),
            ).fetchone()
        return row[0] if row else None

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

    def select_content(
        self,
        message_id: str,
        preferred_kind: VariantKind,
        *,
        fallback_content: str | None = None,
    ) -> str | None:
        variant = self.get_variant(message_id, preferred_kind)
        if variant:
            return variant.content
        if fallback_content is not None:
            return fallback_content
        return self.get_message_content(message_id)

    def get_transcript(self, selector: TranscriptSelector = "legacy") -> list[TranscriptMessage]:
        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT message_id, content, role, metadata_json
                FROM messages
                ORDER BY id ASC
                """
            ).fetchall()

        transcript: list[TranscriptMessage] = []
        for message_id, legacy_content, role, metadata_json in rows:
            content = legacy_content
            selected_kind = None
            if selector != "legacy":
                variant = self.get_variant(message_id, selector)
                if variant is not None:
                    content = variant.content
                    selected_kind = variant.variant_kind
            transcript.append(
                TranscriptMessage(
                    message_id=message_id,
                    content=content,
                    selector=selector,
                    role=role,
                    selected_variant_kind=selected_kind,
                    metadata=json_loads(metadata_json),
                )
            )
        return transcript

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    role TEXT,
                    content TEXT NOT NULL,
                    metadata_json TEXT
                )
                """
            )
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
            connection.execute("CREATE INDEX IF NOT EXISTS idx_messages_message_id ON messages(message_id)")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_message_variants_message_id ON message_variants(message_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_message_variants_kind ON message_variants(variant_kind)"
            )

    def _upsert_message(
        self,
        connection: sqlite3.Connection,
        *,
        message_id: str,
        content: str,
        role: str | None,
        metadata: dict | None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO messages (message_id, role, content, metadata_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(message_id) DO UPDATE SET
                role = excluded.role,
                content = excluded.content,
                metadata_json = excluded.metadata_json
            """,
            (message_id, role, content, json_dumps(metadata or {})),
        )

    def _upsert_variant(self, connection: sqlite3.Connection, variant: MessageVariant) -> None:
        connection.execute(
            "DELETE FROM message_variants WHERE message_id = ? AND variant_kind = ?",
            (variant.message_id, variant.variant_kind),
        )
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
