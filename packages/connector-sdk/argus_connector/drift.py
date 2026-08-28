"""Schema-Drift-Erkennung.

Kapitel 5.2: unbekannte Felder werden protokolliert und loesen einen Hinweis
aus, statt still verworfen zu werden. Der Fall ist haeufiger, als man denkt -
Quellen ergaenzen Felder ohne Ankuendigung, benennen sie um oder aendern den
Typ von Zahl auf Zeichenkette.

Erkannt werden vier Dinge:

* neues Feld            - die Quelle liefert etwas, das wir nicht kennen
* verschwundenes Feld   - ein bisher immer vorhandenes Feld fehlt jetzt
* Typwechsel            - dasselbe Feld hat einen anderen Typ
* Kardinalitaetswechsel - aus einem Wert wird eine Liste oder umgekehrt

Der Detektor lernt die Form aus den ersten Datensaetzen und meldet danach
Abweichungen. Er verwirft nichts: Rohdaten landen unveraendert im Bronze-Layer.
"""

from __future__ import annotations

import enum
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

MAX_DEPTH = 6
# Ein Feld gilt als "immer vorhanden", wenn es in mindestens so vielen Prozent
# der gelernten Datensaetze vorkam. Darunter ist sein Fehlen normal.
REQUIRED_RATIO = 0.95


class DriftKind(enum.StrEnum):
    NEW_FIELD = "new_field"
    MISSING_FIELD = "missing_field"
    TYPE_CHANGE = "type_change"
    CARDINALITY_CHANGE = "cardinality_change"


@dataclass(frozen=True, slots=True)
class DriftFinding:
    kind: DriftKind
    path: str
    detail: str

    def __str__(self) -> str:
        return f"{self.kind.value} at {self.path}: {self.detail}"


@dataclass(slots=True)
class DriftReport:
    findings: list[DriftFinding] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.findings)

    @property
    def kinds(self) -> set[DriftKind]:
        return {f.kind for f in self.findings}

    def summary(self) -> str:
        return "; ".join(str(f) for f in self.findings)


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, list | tuple):
        return "array"
    return type(value).__name__


def _flatten(record: Any, prefix: str = "", depth: int = 0) -> dict[str, str]:
    """Bildet einen Datensatz auf {Pfad: Typname} ab.

    Listen werden auf ein Element reduziert (`feld[]`), weil sonst jede
    Listenlaenge eine andere Form ergaebe.
    """
    shape: dict[str, str] = {}
    if depth >= MAX_DEPTH:
        return shape
    if isinstance(record, Mapping):
        for key, value in record.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            shape[path] = _type_name(value)
            if isinstance(value, Mapping | list | tuple):
                shape.update(_flatten(value, path, depth + 1))
    elif isinstance(record, list | tuple):
        path = f"{prefix}[]"
        for item in record[:1]:  # ein Element genuegt fuer die Form
            shape[path] = _type_name(item)
            if isinstance(item, Mapping | list | tuple):
                shape.update(_flatten(item, path, depth + 1))
    return shape


class SchemaDriftDetector:
    """Lernt die Form einer Quelle und meldet Abweichungen.

    `learn_after` Datensaetze werden zum Lernen benutzt; danach ist die Form
    festgelegt. Ein zu frueher Abschluss meldet jede optionale Spalte als
    Drift, ein zu spaeter merkt eine echte Aenderung nicht.
    """

    def __init__(
        self,
        *,
        learn_after: int = 50,
        known_shape: Mapping[str, str] | None = None,
        field_counts: Mapping[str, int] | None = None,
        samples_seen: int = 0,
        # null zaehlt nicht als Typwechsel: fast jede Quelle liefert
        # gelegentlich null fuer ein optionales Feld.
        ignore_null_type_changes: bool = True,
    ) -> None:
        self.learn_after = learn_after
        self.shape: dict[str, str] = dict(known_shape or {})
        self.field_counts: dict[str, int] = dict(field_counts or {})
        self.samples_seen = samples_seen
        self.ignore_null_type_changes = ignore_null_type_changes
        self._reported: set[tuple[DriftKind, str]] = set()

    @property
    def is_learning(self) -> bool:
        return self.samples_seen < self.learn_after

    def state(self) -> dict[str, Any]:
        """Zustand zum Persistieren, damit ein Neustart nicht neu lernt."""
        return {
            "shape": dict(self.shape),
            "field_counts": dict(self.field_counts),
            "samples_seen": self.samples_seen,
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any], **kwargs: Any) -> SchemaDriftDetector:
        return cls(
            known_shape=state.get("shape"),
            field_counts=state.get("field_counts"),
            samples_seen=int(state.get("samples_seen", 0)),
            **kwargs,
        )

    def _required_fields(self) -> set[str]:
        if self.samples_seen == 0:
            return set()
        threshold = self.samples_seen * REQUIRED_RATIO
        return {path for path, count in self.field_counts.items() if count >= threshold}

    def inspect(self, record: Any) -> DriftReport:
        """Prueft einen Datensatz. Waehrend der Lernphase immer ohne Befund.

        Datensaetze, die keine Abbildung sind (ein blosser Wert, eine Liste auf
        oberster Ebene), haben keine Felder, die man vergleichen koennte. Sie
        werden uebergangen statt als Drift gemeldet - sonst erzeugt eine Quelle,
        die einmal ein leeres Array liefert, eine Fehlmeldung.
        """
        report = DriftReport()
        if not isinstance(record, Mapping):
            return report
        observed = _flatten(record)

        if self.is_learning:
            for path, type_name in observed.items():
                if type_name != "null":
                    self.shape.setdefault(path, type_name)
                self.field_counts[path] = self.field_counts.get(path, 0) + 1
            self.samples_seen += 1
            return report

        required = self._required_fields()

        for path, type_name in observed.items():
            known = self.shape.get(path)
            if known is None:
                self._add(
                    report, DriftKind.NEW_FIELD, path, f"unbekanntes Feld vom Typ {type_name}"
                )
                continue
            if type_name == known:
                continue
            if self.ignore_null_type_changes and (type_name == "null" or known == "null"):
                continue
            if {type_name, known} == {"int", "float"}:
                # Zahlentypen wechseln staendig (1 gegen 1.0) und sind fuer die
                # Verarbeitung gleichwertig.
                continue
            kind = (
                DriftKind.CARDINALITY_CHANGE
                if "array" in (type_name, known)
                else DriftKind.TYPE_CHANGE
            )
            self._add(report, kind, path, f"war {known}, ist jetzt {type_name}")

        for path in required - observed.keys():
            self._add(
                report, DriftKind.MISSING_FIELD, path, "bisher immer vorhanden, jetzt nicht mehr"
            )

        self.samples_seen += 1
        return report

    def _add(self, report: DriftReport, kind: DriftKind, path: str, detail: str) -> None:
        # Jede Abweichung nur einmal melden - sonst erzeugt eine geaenderte
        # Quelle eine Meldung je Datensatz und die Protokolle sind unbrauchbar.
        marker = (kind, path)
        if marker in self._reported:
            return
        self._reported.add(marker)
        report.findings.append(DriftFinding(kind, path, detail))
        logger.warning("Schema-Drift: %s bei %s - %s", kind.value, path, detail)

    def inspect_many(self, records: Iterable[Any]) -> DriftReport:
        combined = DriftReport()
        for record in records:
            combined.findings.extend(self.inspect(record).findings)
        return combined
