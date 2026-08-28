#!/usr/bin/env python3
"""Prueft das Commit-Format (Conventional Commits).

Warum ueberhaupt ein Format: die Historie ist das einzige Dokument, das
garantiert aktuell ist. Ein einheitlicher Betreff macht sie durchsuchbar
("was ist alles an den Schemas passiert") und erlaubt es spaeter, ein
Changelog daraus zu erzeugen.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TYPES = (
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
)

PATTERN = re.compile(
    rf"^(?P<type>{'|'.join(TYPES)})"
    r"(?:\((?P<scope>[a-z0-9._/-]+)\))?"
    r"(?P<breaking>!)?"
    r": (?P<subject>.+)$"
)

MAX_SUBJECT = 72


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Aufruf: check_commit_message.py <datei>", file=sys.stderr)
        return 2

    lines = Path(argv[0]).read_text(encoding="utf-8").splitlines()
    subject = next((line for line in lines if line.strip() and not line.startswith("#")), "")

    # Von Git erzeugte Commits durchlassen.
    if subject.startswith(("Merge ", "Revert ", "fixup!", "squash!")):
        return 0

    match = PATTERN.match(subject)
    if not match:
        print(f"Betreff entspricht nicht dem Format:\n  {subject}\n")
        print("Erwartet:  <typ>(<bereich>): <beschreibung>")
        print(f"Typen:     {', '.join(TYPES)}")
        print("Beispiele:")
        print("  feat(connector-sdk): Zwei-Phasen-Cursor")
        print("  fix(db): Zeitzone in der Retention-Abfrage")
        print("  docs(adr): ADR 0004 zur Bus-Wahl")
        print("  feat(api)!: Antwortformat auf RFC 9457 umgestellt")
        return 1

    if len(subject) > MAX_SUBJECT:
        print(f"Betreff ist {len(subject)} Zeichen lang, erlaubt sind {MAX_SUBJECT}.")
        print("Details gehoeren in den Rumpf, nicht in den Betreff.")
        return 1

    if match.group("subject")[0].isupper() and match.group("subject").split()[0].isalpha():
        # Kein Fehler, nur ein Hinweis: Grossschreibung am Anfang ist im
        # Deutschen oft richtig (Substantiv).
        pass

    if subject.endswith("."):
        print("Der Betreff endet mit einem Punkt - der ist ueberfluessig.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
