"""H3-Indizes zwischen Zeichenkette und Ganzzahl.

Die Protobuf-Schemas fuehren H3-Indizes als Zeichenkette (`"871f0d4c2ffffff"`),
die Datenbank als `bigint` (Prompt 3, ADR 0003). Der Grund fuer die Ganzzahl:
ein Vergleich auf 64 Bit ist um ein Vielfaches billiger als auf einer
Zeichenkette, und Viewport-Abfragen machen nichts anderes als vergleichen.

Ein H3-v4-Index hat das hoechstwertige Bit stets auf 0, passt also in einen
vorzeichenbehafteten 64-Bit-Wert - genau das, was PostgreSQL als `bigint`
speichert. Diese Zusicherung wird hier geprueft und nicht angenommen.
"""

from __future__ import annotations

import re

# Ein H3-Index ist genau 15 Hexstellen lang (Aufloesungen 0-15).
_H3_PATTERN = re.compile(r"^[0-9a-f]{15}$")

# Groesster Wert, der in ein PostgreSQL-bigint passt.
_BIGINT_MAX = 2**63 - 1


class InvalidH3IndexError(ValueError):
    """Der uebergebene Wert ist kein H3-Index."""


def is_valid_h3(value: str) -> bool:
    """Prueft die Form, nicht die Gueltigkeit der Zelle.

    Eine echte Gueltigkeitspruefung braucht die H3-Bibliothek. Hier geht es
    darum, offensichtlichen Unsinn abzufangen, bevor er in die Datenbank
    wandert - eine Aufgabe, die keine Abhaengigkeit rechtfertigt.
    """
    return bool(_H3_PATTERN.match(value.lower()))


def h3_to_int(value: str) -> int:
    """Wandelt einen H3-Index in die Datenbankdarstellung.

    >>> h3_to_int("871f0d4c2ffffff")
    608495261123674111
    """
    normalized = value.strip().lower()
    if not is_valid_h3(normalized):
        raise InvalidH3IndexError(
            f"{value!r} ist kein H3-Index: erwartet werden 15 Hexstellen, "
            f"gefunden {len(normalized)} Zeichen"
        )
    as_int = int(normalized, 16)
    if as_int > _BIGINT_MAX:
        # Kann bei einem H3-v4-Index nicht auftreten; die Pruefung faengt den
        # Fall ab, dass hier etwas anderes ankommt, das zufaellig 15 Hexstellen
        # hat - statt es still in einen negativen bigint zu kippen.
        raise InvalidH3IndexError(
            f"{value!r} passt nicht in ein bigint (Wert {as_int}). Das ist kein gueltiger H3-Index."
        )
    return as_int


def int_to_h3(value: int) -> str:
    """Gegenstueck zu h3_to_int.

    >>> int_to_h3(608495261123674111)
    '871f0d4c2ffffff'
    """
    if value < 0:
        raise InvalidH3IndexError(
            f"H3-Indizes sind nie negativ; {value} deutet auf einen Ueberlauf beim Speichern hin"
        )
    return format(value, "015x")
