#!/usr/bin/env python3
"""Sucht nach offensichtlichen Zugangsdaten.

Kein Ersatz fuer einen richtigen Secret-Scanner - der laeuft in der CI. Das
hier faengt die haeufigsten Faelle ab, bevor sie in der Historie stehen, wo
sie auch nach dem Loeschen noch abrufbar sind.

Bewusst wenige, praezise Muster: ein Hook mit vielen Fehlalarmen wird
uebersprungen, und dann faengt er gar nichts mehr.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS-Zugriffsschluessel", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Privater Schluessel", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("GitHub-Token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Slack-Token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    # Zugangsdaten in einer URL: postgres://nutzer:geheim@host
    ("Zugangsdaten in URL", re.compile(r"://[^/\s:@]+:[^/\s:@]{6,}@")),
]

# Werte, die in diesem Repository als Entwicklungsvorgabe erlaubt sind.
ALLOWED_SUBSTRINGS = (
    "argus_dev_only",
    "argus:argus@",
    "postgres@",
    "argus_ci",
    "argus:argus_dev_only@",
)


def main(paths: list[str]) -> int:
    findings: list[tuple[str, int, str]] = []
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            continue
        # Diese Datei enthaelt die Muster selbst - sonst meldet der Hook sich
        # bei jedem Lauf selbst an.
        if path.resolve() == Path(__file__).resolve():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # Binaerdatei
        for lineno, line in enumerate(text.splitlines(), start=1):
            if any(allowed in line for allowed in ALLOWED_SUBSTRINGS):
                continue
            for label, pattern in PATTERNS:
                if pattern.search(line):
                    findings.append((raw, lineno, label))

    if not findings:
        return 0

    print("Moegliche Zugangsdaten gefunden:")
    for name, lineno, label in findings:
        print(f"  {name}:{lineno}: {label}")
    print()
    print("Zugangsdaten gehoeren in den Secret-Manager, nie ins Repository")
    print("(Konzept, Kapitel 13). Wenn es ein Fehlalarm ist, das Muster in")
    print("scripts/hooks/check_secrets.py anpassen - nicht den Hook ueberspringen.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
