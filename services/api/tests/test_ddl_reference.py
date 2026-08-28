"""Die DDL-Referenz darf nicht von den Migrationen abweichen.

packages/schemas/sql/ wird erzeugt, nicht gepflegt. Dieser Test faengt den Fall
ab, dass jemand eine Migration aendert und den Dump vergisst - sonst ist die
Referenz nach zwei Wochen eine Luege.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest
from conftest import API_DIR, requires_db

pytestmark = requires_db

SQL_DIR = API_DIR.parent.parent / "packages" / "schemas" / "sql"
SCHEMA_FILE = SQL_DIR / "argus_schema.sql"


def test_ddl_reference_exists():
    assert SCHEMA_FILE.exists(), (
        "packages/schemas/sql/argus_schema.sql fehlt - "
        "services/api/scripts/dump_schema.sh ausfuehren"
    )
    assert "ERZEUGT, NICHT VON HAND GEPFLEGT" in SCHEMA_FILE.read_text(encoding="utf-8")


@pytest.mark.slow
def test_ddl_reference_matches_migrations(db_url, tmp_path):
    """Erzeugt den Dump neu und vergleicht ihn mit dem eingecheckten Stand."""
    if shutil.which("pg_dump") is None:
        pytest.skip("pg_dump nicht verfuegbar")

    backup = tmp_path / "committed.sql"
    shutil.copy(SCHEMA_FILE, backup)
    comments = SQL_DIR / "argus_comments.sql"
    comments_backup = tmp_path / "committed_comments.sql"
    if comments.exists():
        shutil.copy(comments, comments_backup)

    try:
        result = subprocess.run(
            [str(API_DIR / "scripts" / "dump_schema.sh")],
            cwd=API_DIR,
            env={**os.environ, "DATABASE_URL": db_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        regenerated = SCHEMA_FILE.read_text(encoding="utf-8")
        committed = backup.read_text(encoding="utf-8")
        assert regenerated == committed, (
            "Die DDL-Referenz weicht von den Migrationen ab. Neu erzeugen mit:\n    make db-ddl"
        )
    finally:
        shutil.copy(backup, SCHEMA_FILE)
        if comments_backup.exists():
            shutil.copy(comments_backup, comments)
