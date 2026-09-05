#!/usr/bin/env python3
"""Testmodulnamen muessen im ganzen Repository eindeutig sein.

WARUM
-----
pytest importiert Testdateien ohne __init__.py unter ihrem blossen Dateinamen.
Zwei Dateien namens test_roundtrip.py in verschiedenen Paketen ergeben denselben
Modulnamen - und pytest bricht die Sammlung ab:

    import file mismatch: imported module 'test_roundtrip' has this __file__
    attribute: .../packages/schemas/tests/test_roundtrip.py

Der Fehler tritt erst auf, wenn beide Pakete in einem Lauf gesammelt werden.
Wer nur sein eigenes Paket testet, sieht ihn nie - und die CI dann schon.

conftest.py ist ausgenommen: pytest behandelt sie gesondert.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOTS = ("packages", "services", "apps", "infra")


def main(argv: list[str]) -> int:
    repo = Path(__file__).resolve().parents[2]
    by_name: defaultdict[str, list[Path]] = defaultdict(list)

    for root in ROOTS:
        for path in (repo / root).rglob("test_*.py"):
            if "__pycache__" in path.parts or ".venv" in path.parts:
                continue
            # Ein Verzeichnis mit __init__.py ist ein Paket; dort ist der
            # Modulname vollstaendig qualifiziert und kann nicht kollidieren.
            if (path.parent / "__init__.py").exists():
                continue
            by_name[path.name].append(path.relative_to(repo))

    clashes = {name: paths for name, paths in by_name.items() if len(paths) > 1}
    if not clashes:
        return 0

    print("Testmodulnamen kollidieren - pytest kann sie nicht zusammen sammeln:")
    for name, paths in sorted(clashes.items()):
        print(f"  {name}")
        for path in sorted(paths):
            print(f"    {path}")
    print(
        "\nAbhilfe: eindeutige Dateinamen vergeben (z. B. test_schema_conformance.py\n"
        "statt test_roundtrip.py) - oder das Testverzeichnis mit einer __init__.py\n"
        "zu einem Paket machen."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
