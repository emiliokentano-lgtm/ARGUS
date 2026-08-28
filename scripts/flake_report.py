#!/usr/bin/env python3
"""Macht wiederholte Tests sichtbar.

Die Integrationstests duerfen wiederholt werden - ein Zeitfenster, ein
langsamer Container, ein Port, der eine Sekunde spaeter offen ist. Was nicht
passieren darf: dass die Wiederholung den Befund verschluckt. Ein Test, der
nur beim zweiten Versuch gruen wird, ist kein Erfolg, sondern eine Warnung.

Dieses Skript liest den JUnit-Bericht, meldet jede Wiederholung als
GitHub-Annotation und schreibt eine Zusammenfassung in den Job-Report. Der
Rueckgabewert ist bewusst 0: das Skript blockiert nichts, es macht sichtbar.
Wer Flakes zum Fehler machen will, setzt ARGUS_FLAKES_ARE_ERRORS=1.
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _emit(line: str) -> None:
    print(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and not line.startswith("::"):
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Aufruf: flake_report.py <junit.xml>", file=sys.stderr)
        return 2

    report = Path(argv[1])
    if not report.exists():
        # Kein Bericht heisst: die Tests sind gar nicht erst gelaufen. Das ist
        # ein anderer Fehler und wird an anderer Stelle gemeldet.
        print(f"Kein JUnit-Bericht unter {report} - nichts auszuwerten.")
        return 0

    root = ET.parse(report).getroot()  # noqa: S314 - eigener Bericht, keine Fremddaten
    flaky: list[tuple[str, int]] = []
    total = 0

    for testcase in root.iter("testcase"):
        total += 1
        # pytest-rerunfailures schreibt je Wiederholung ein <rerun>-Element.
        reruns = len(testcase.findall("rerun"))
        if reruns:
            name = f"{testcase.get('classname', '')}::{testcase.get('name', '')}".lstrip(":")
            flaky.append((name, reruns))

    if not flaky:
        _emit(f"Keine Wiederholungen bei {total} Tests.")
        return 0

    _emit("### Flakige Tests")
    _emit("")
    _emit("| Test | Wiederholungen |")
    _emit("| --- | --- |")
    for name, reruns in sorted(flaky, key=lambda item: -item[1]):
        _emit(f"| `{name}` | {reruns} |")
        # Annotation im Pull Request, damit es nicht nur im Protokoll steht.
        print(
            f"::warning title=Flakiger Test::{name} wurde {reruns}x wiederholt, "
            "bevor er gruen war. Ursache klaeren, nicht die Wiederholung erhoehen."
        )
    _emit("")
    _emit(
        f"{len(flaky)} von {total} Tests brauchten eine Wiederholung. "
        "Jeder davon ist ein Befund: entweder der Test hat eine Annahme ueber "
        "Zeit oder Reihenfolge, die nicht haelt, oder der geprüfte Code hat sie."
    )

    if os.environ.get("ARGUS_FLAKES_ARE_ERRORS", "").strip() in ("1", "true", "yes"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
