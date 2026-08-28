#!/usr/bin/env bash
# Erzeugt die DDL-Referenz unter packages/schemas/sql/ aus den Migrationen.
#
# Die Referenz wird NICHT von Hand gepflegt. Sie entsteht aus einer frisch
# migrierten Wegwerf-Datenbank, damit sie nie von den Migrationen abweichen
# kann - dieselbe Regel wie bei den generierten Schemas aus Prompt 1.
#
#   DATABASE_URL=postgresql://... ./scripts/dump_schema.sh
#
# DATABASE_URL zeigt auf eine beliebige Datenbank desselben Clusters; das
# Skript legt daneben eine temporaere an und raeumt sie wieder weg.
set -Eeuo pipefail

API_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${API_DIR}/../../packages/schemas/sql"
cd "${API_DIR}"

: "${DATABASE_URL:?DATABASE_URL fehlt}"
PYTHON="${ARGUS_PYTHON:-${API_DIR}/.venv/bin/python}"

TMP_DB="argus_ddl_dump_$$"
# Die URL kann Abfrageparameter mit Schraegstrichen enthalten
# (host=/var/run/postgresql). Deshalb wird sie geparst, nicht mit
# Zeichenketten-Operationen zerlegt.
TMP_URL="$("${PYTHON}" - "${DATABASE_URL}" "${TMP_DB}" <<'PYEOF'
import sys
from urllib.parse import urlsplit, urlunsplit
parts = urlsplit(sys.argv[1])
print(urlunsplit(parts._replace(path="/" + sys.argv[2])))
PYEOF
)"

cleanup() {
  psql "${DATABASE_URL}" -q -c "DROP DATABASE IF EXISTS ${TMP_DB}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Lege temporaere Datenbank ${TMP_DB} an ..."
psql "${DATABASE_URL}" -q -c "CREATE DATABASE ${TMP_DB}"
psql "${TMP_URL}" -q -c "CREATE EXTENSION IF NOT EXISTS postgis;
                         CREATE EXTENSION IF NOT EXISTS vector;
                         CREATE EXTENSION IF NOT EXISTS pg_trgm;
                         CREATE EXTENSION IF NOT EXISTS btree_gist;"

echo "Migriere auf head ..."
DATABASE_URL="${TMP_URL}" "${PYTHON}" -m alembic upgrade head >/dev/null

mkdir -p "${OUT_DIR}"
echo "Schreibe DDL nach ${OUT_DIR} ..."

{
  cat <<'HEADER'
-- ARGUS — DDL-Referenz des Schemas argus.
--
-- ERZEUGT, NICHT VON HAND GEPFLEGT.
-- Quelle der Wahrheit sind die Alembic-Migrationen unter
-- services/api/migrations/. Diese Datei entsteht daraus mit
--     services/api/scripts/dump_schema.sh
-- und dient zwei Zwecken:
--   * Nachschlagewerk beim Schreiben von Abfragen, ohne acht Migrationen zu lesen
--   * Grundlage fuer Code-Review: eine Aenderung am Schema ist hier sichtbar
--
-- Die Tagespartitionen von argus.observations sind ausgelassen - sie entstehen
-- zur Laufzeit und wiederholen nur die Definition der Elterntabelle.
--
-- Ebenfalls entfernt: die \\restrict-Marken neuerer pg_dump-Versionen. Sie
-- enthalten bei jedem Lauf ein anderes Zufallstoken und wuerden die Datei bei
-- jedem Erzeugen aendern, ohne dass sich am Schema etwas geaendert haette.
--
-- Der Test tests/test_ddl_reference.py schlaegt fehl, sobald diese Datei von
-- den Migrationen abweicht.

HEADER
  pg_dump "${TMP_URL}" \
    --schema-only \
    --schema=argus \
    --no-owner \
    --no-privileges \
    --no-comments \
    --exclude-table='argus.observations_2*' \
    --exclude-table='argus.observations_default' \
    2>/dev/null \
  | grep -v '^-- Dumped ' \
  | grep -v '^\\restrict ' \
  | grep -v '^\\unrestrict ' \
  | grep -v '^-- PostgreSQL database dump' \
  | grep -v '^SET ' \
  | grep -v '^SELECT pg_catalog.set_config' \
  | cat -s
} > "${OUT_DIR}/argus_schema.sql"

# Kommentare getrennt: sie sind die eigentliche Dokumentation des Modells und
# gehen im grossen Dump sonst unter.
{
  echo "-- ARGUS — Kommentare zu Tabellen, Spalten und Funktionen."
  echo "-- Erzeugt aus den Migrationen; siehe argus_schema.sql."
  echo
  psql "${TMP_URL}" -qAt -F ' ' -c "
    SELECT format('COMMENT ON %s %s IS %L;',
                  CASE WHEN c.relkind IN ('r','p') THEN 'TABLE'
                       WHEN c.relkind = 'v' THEN 'VIEW' END,
                  format('%I.%I', n.nspname, c.relname),
                  obj_description(c.oid, 'pg_class'))
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'argus' AND c.relkind IN ('r','p','v')
       AND obj_description(c.oid, 'pg_class') IS NOT NULL
     ORDER BY c.relname"
} > "${OUT_DIR}/argus_comments.sql"

lines=$(wc -l < "${OUT_DIR}/argus_schema.sql")
echo "Fertig: argus_schema.sql (${lines} Zeilen), argus_comments.sql"
