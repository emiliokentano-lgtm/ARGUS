#!/usr/bin/env python3
"""Verhindert, dass grosse Dateien versehentlich im Repository landen.

Git vergisst nichts: eine einmal committete 200-MB-Datei bleibt in der
Historie, auch wenn sie im naechsten Commit geloescht wird. Deshalb hier und
nicht im Review.
"""

from __future__ import annotations

import sys
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024

# Binaerdateien, die bewusst im Repository liegen.
ALLOWED = {"packages/schemas/baseline/argus-v1.binpb"}


def main(paths: list[str]) -> int:
    offenders = []
    for raw in paths:
        if raw in ALLOWED:
            continue
        path = Path(raw)
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size > MAX_BYTES:
            offenders.append((raw, size))

    if not offenders:
        return 0

    print("Zu grosse Dateien:")
    for name, size in offenders:
        print(f"  {name}: {size / 1024 / 1024:.1f} MB (Grenze {MAX_BYTES // 1024 // 1024} MB)")
    print()
    print("Git vergisst nichts - eine einmal committete Datei bleibt in der")
    print("Historie. Grosse Daten gehoeren in den Objektspeicher (MinIO), nicht")
    print("ins Repository. Wenn die Datei doch hier hingehoert, in ALLOWED in")
    print("scripts/hooks/check_large_files.py eintragen.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
