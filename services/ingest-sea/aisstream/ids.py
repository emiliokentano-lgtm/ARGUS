"""Kennungen: ULIDs, die eine Wiederholung ueberleben.

WARUM NICHT EINFACH ULID.NEW()
------------------------------
Der Bronze-Layer ist der Wiederherstellungspfad des Systems (ADR 0001): faellt
die Verarbeitung aus, wird aus den archivierten Rohnachrichten neu gerechnet.
Das funktioniert nur, wenn dieselbe Rohnachricht dabei dieselbe `obs_id`
ergibt. Eine zufaellige ULID je Lauf erzeugt bei jedem Replay einen neuen
Datensatz - aus einer Wiederherstellung wird eine Verdopplung.

Deshalb sind die IDs hier deterministisch: gleiche Rohnachricht, gleiche ID,
auf jeder Maschine und zu jeder Zeit.

WIE
---
Eine ULID besteht aus 48 Bit Zeit in Millisekunden und 80 Bit Zufall. Das
Zeitfeld wird hier aus dem Beobachtungszeitpunkt gefuellt - das ist genau
seine Bedeutung und macht die ID nach Ereigniszeit sortierbar. Die 80 Bit
Zufall werden durch die ersten 80 Bit eines BLAKE2b-Hashes ueber die stabilen
Identitaetsfelder ersetzt.

Das ist zulaessig - das ULID-Format schreibt fuer die unteren 80 Bit nichts
vor ausser der Laenge -, aber es ist bemerkenswert genug, um es hier
hinzuschreiben: der hintere Teil einer ARGUS-ULID ist kein Zufall, sondern ein
Hash. Wer sich auf Unvorhersehbarkeit verlaesst, verlaesst sich auf etwas, das
hier nicht zugesichert wird.

Kollisionen: 80 Bit ueber die Nachrichten einer Millisekunde. Bei 2.000
Nachrichten pro Sekunde sind das im Mittel zwei je Millisekunde. Die
Wahrscheinlichkeit einer Kollision ist damit jenseits jeder Betriebsrelevanz -
und eine Kollision waere ohnehin nur zwischen zwei Nachrichten mit identischem
Identitaetsschluessel moeglich, also zwischen zwei Kopien derselben Nachricht.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Crockford Base32: ohne I, L, O und U - die Zeichen, die man beim Abschreiben
# verwechselt oder die Woerter bilden, die niemand in einer Kennung sehen will.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

_ULID_LENGTH = 26
_TIME_BITS = 48
_RANDOM_BITS = 80
# Groesster Zeitwert, den 48 Bit Millisekunden fassen: 10889-08-02.
_MAX_TIME_MS = (1 << _TIME_BITS) - 1


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def deterministic_ulid(*, timestamp_s: float, seed: str) -> str:
    """ULID aus Zeitpunkt und Identitaetsschluessel.

    `timestamp_s` ist der Beobachtungszeitpunkt in Unix-Sekunden, `seed` der
    Schluessel, der die Nachricht eindeutig macht.

    Negative Zeitpunkte (vor 1970) und Zeitpunkte jenseits des 48-Bit-Bereichs
    werden geklemmt statt umgebrochen. Ein Umbruch waere hier besonders
    tueckisch: die ID saehe gueltig aus und sortierte sich an eine voellig
    falsche Stelle.
    """
    millis = int(timestamp_s * 1000.0)
    millis = max(0, min(millis, _MAX_TIME_MS))
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=10).digest()
    randomness = int.from_bytes(digest, "big") & ((1 << _RANDOM_BITS) - 1)
    return _encode(millis, 10) + _encode(randomness, 16)


def is_ulid(value: str) -> bool:
    """Formpruefung: 26 Zeichen aus dem Crockford-Alphabet."""
    if len(value) != _ULID_LENGTH:
        return False
    return all(char in _CROCKFORD for char in value)


def identity_seed(source_id: str, parts: dict[str, Any]) -> str:
    """Kanonischer Identitaetsschluessel aus benannten Feldern.

    Benannt und nicht positionell: eine Umbenennung faellt beim Lesen auf, eine
    vertauschte Reihenfolge nicht. Der Preis ist ein laengerer Schluessel, und
    da er ohnehin gehasht wird, kostet das nichts.
    """
    canonical = json.dumps(
        parts, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return f"{source_id}|{canonical}"


def entity_ref_id(*, imo: int | None, mmsi: int | None) -> str:
    """Der quellnative Bezeichner fuer EntityRef.id.

    Die Regel aus der Aufgabenstellung und aus ADR 0005: IMO wenn vorhanden,
    sonst MMSI als provisorischer Bezeichner. Beides mit Schema-Praefix, damit
    aus der Kennung selbst hervorgeht, wie stabil sie ist - eine IMO gehoert
    dem Rumpf bis zur Verschrottung, eine MMSI der Funkanlage bis zum
    naechsten Flaggenwechsel.

    Der Aufrufer hat die IMO vorher mit `ais.is_valid_imo` zu pruefen. Diese
    Funktion vertraut ihrem Eingang.
    """
    if imo is not None:
        return f"imo:{imo}"
    if mmsi is not None:
        return f"mmsi:{mmsi}"
    raise ValueError(
        "Weder IMO noch MMSI vorhanden. Eine Beobachtung ohne jeden Bezeichner "
        "hat keinen Adressaten und darf nicht erzeugt werden."
    )
