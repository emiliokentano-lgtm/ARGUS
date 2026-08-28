#!/usr/bin/env python3
"""buf lint und buf format fuer die Protos.

Laeuft nur, wenn eine .proto-Datei angefasst wurde - buf braucht sonst
mehrere Sekunden fuer nichts.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCHEMAS = Path("packages/schemas")
BUF = SCHEMAS / "node_modules" / ".bin" / "buf"


def main() -> int:
    if not BUF.exists():
        print(f"{BUF} fehlt - 'make bootstrap' ausfuehren.", file=sys.stderr)
        return 1
    for args in (["lint"], ["format", "--diff", "--exit-code"]):
        result = subprocess.run(
            ["./node_modules/.bin/buf", *args],
            cwd=SCHEMAS,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(result.stdout or result.stderr)
            if args[0] == "format":
                print("\nFormatierung korrigieren: make -C packages/schemas lint")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
