"""Deterministische Idempotenzschluessel.

Kapitel 5.2 verlangt einen `dedupe_key` pro Rohnachricht, der aus stabilen
Feldern gebildet wird. Zweimal dieselbe Nachricht - egal ob durch
Wiederholung nach einem Absturz, durch eine ueberlappende Seite oder durch
doppelte Zustellung - muss denselben Schluessel ergeben.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from typing import Any


class DedupeKeyBuilder:
    """Bildet einen stabilen Schluessel aus ausgewaehlten Feldern.

    Der Schluessel ist absichtlich lesbar aufgebaut: Praefix, dann Hash. Das
    Praefix macht ihn in Protokollen und in der Datenbank zuordenbar, der Hash
    haelt ihn kurz und unabhaengig von Feldlaengen.

        builder = DedupeKeyBuilder("aisstream", ("mmsi", "timestamp"))
        builder.build({"mmsi": 211234560, "timestamp": "2026-08-28T09:14:03Z"})
        # 'aisstream:2f1c...'

    Verschachtelte Felder ueber Punktpfade: ("meta.id", "position.lat").
    """

    def __init__(
        self,
        prefix: str,
        fields: Sequence[str],
        *,
        digest_size: int = 16,
        allow_missing: bool = False,
    ) -> None:
        if not fields:
            raise ValueError(
                "Ohne Felder waere jeder Schluessel gleich. Mindestens ein Feld angeben."
            )
        self.prefix = prefix
        self.fields = tuple(fields)
        self.digest_size = digest_size
        self.allow_missing = allow_missing

    @staticmethod
    def _resolve(record: Any, path: str) -> Any:
        current = record
        for part in path.split("."):
            if isinstance(current, dict):
                if part not in current:
                    return _MISSING
                current = current[part]
            elif isinstance(current, list | tuple):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    return _MISSING
            else:
                current = getattr(current, part, _MISSING)
                if current is _MISSING:
                    return _MISSING
        return current

    def extract(self, record: Any) -> list[Any]:
        values: list[Any] = []
        missing: list[str] = []
        for path in self.fields:
            value = self._resolve(record, path)
            if value is _MISSING:
                missing.append(path)
                values.append(None)
            else:
                values.append(value)
        if missing and not self.allow_missing:
            raise KeyError(
                f"Felder fuer den dedupe_key fehlen im Datensatz: {', '.join(missing)}. "
                "Entweder das Feldmapping korrigieren oder allow_missing setzen - "
                "aber dann kollidieren Datensaetze, denen dasselbe Feld fehlt."
            )
        return values

    def build(self, record: Any) -> str:
        values = self.extract(record)
        # Kanonisches JSON: feste Trennzeichen, sortierte Schluessel in
        # verschachtelten Strukturen, keine ASCII-Flucht. Damit ist die
        # Byte-Darstellung eindeutig und plattformunabhaengig.
        canonical = json.dumps(
            values,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
        digest = hashlib.blake2b(canonical, digest_size=self.digest_size).hexdigest()
        return f"{self.prefix}:{digest}"

    def build_many(self, records: Iterable[Any]) -> list[str]:
        return [self.build(record) for record in records]


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover - nur fuer Fehlermeldungen
        return "<fehlt>"


_MISSING = _Missing()
