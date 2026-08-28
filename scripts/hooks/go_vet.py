#!/usr/bin/env python3
"""go vet ueber alle Module des Workspace.

Im Workspace-Modus greift './...' nicht ueber Modulgrenzen hinweg; deshalb
die ausdrueckliche Liste statt eines Aufrufs an der Wurzel.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

MODULES = ("packages/go-runtime", "services/ingest-air", "services/ingest-sea")


def main() -> int:
    failed = False
    for module in MODULES:
        if not (Path(module) / "go.mod").exists():
            continue
        result = subprocess.run(
            ["go", "vet", "./..."], cwd=module, check=False, capture_output=True, text=True
        )
        if result.returncode != 0:
            failed = True
            print(f"go vet in {module}:")
            print(result.stderr.strip())
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
