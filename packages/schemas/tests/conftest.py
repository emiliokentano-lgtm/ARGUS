"""Gemeinsame Testhilfen fuer das Schema-Paket.

Die Tests laufen gegen die *generierten* Artefakte, nicht gegen handgepflegte
Kopien. Wer `make gen` nicht ausgefuehrt hat, bekommt hier einen klaren
Fehler statt eines Importfehlers tief im Testlauf.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCHEMA_DIR = Path(__file__).resolve().parent.parent
GEN_PYTHON = SCHEMA_DIR / "gen" / "python"
GEN_JSONSCHEMA = SCHEMA_DIR / "gen" / "jsonschema"
EXAMPLES = SCHEMA_DIR / "examples"

if not GEN_PYTHON.exists() or not GEN_JSONSCHEMA.exists():
    raise RuntimeError(
        "Generierte Artefakte fehlen. Zuerst 'make gen' im Verzeichnis packages/schemas ausfuehren."
    )

sys.path.insert(0, str(GEN_PYTHON))


def load_fixture(relative: str) -> dict:
    """Laedt ein Fixture und entfernt die Dokumentationsschluessel.

    Fixtures duerfen Schluessel mit fuehrendem Unterstrich tragen (`_case`),
    die den abgebildeten Fall beschreiben. Sie sind nicht Teil des Schemas und
    werden vor der Validierung entfernt.
    """
    data = json.loads((EXAMPLES / relative).read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load_schema(name: str) -> dict:
    return json.loads((GEN_JSONSCHEMA / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def schemas() -> dict[str, dict]:
    return {
        p.name: json.loads(p.read_text(encoding="utf-8"))
        for p in GEN_JSONSCHEMA.glob("*.schema.json")
    }
