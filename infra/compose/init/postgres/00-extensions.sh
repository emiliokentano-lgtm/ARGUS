#!/usr/bin/env bash
# Aktiviert die von ARGUS benoetigten Postgres-Erweiterungen.
#
# Laeuft ueber /docker-entrypoint-initdb.d, also nur bei einer LEEREN
# Datenbank - genau einmal nach "make reset" oder beim ersten "make up".
# Trotzdem durchgehend idempotent geschrieben (CREATE EXTENSION IF NOT EXISTS),
# damit das Skript auch manuell nachgefahren werden kann:
#   docker compose exec -T postgres bash /docker-entrypoint-initdb.d/00-extensions.sh
set -Eeuo pipefail

DB="${POSTGRES_DB:-argus}"
USR="${POSTGRES_USER:-argus}"

# Ohne diese Erweiterungen ist der Stack fuer ARGUS unbrauchbar; ihr Fehlen
# bricht die Initialisierung ab, statt einen halb funktionsfaehigen Container
# als gesund zu melden.
REQUIRED=(postgis timescaledb vector pg_trgm btree_gist)

# Apache AGE ist im Standard-Image nicht enthalten. Der Graph-Layer kommt erst
# in Phase 5; bis dahin ist sein Fehlen kein Fehler, sondern eine Meldung.
OPTIONAL=(age)

run_sql() {
  psql --username "${USR}" --dbname "${DB}" -v ON_ERROR_STOP=1 -q -c "$1"
}

create_extension() {
  # CASCADE, weil postgis_topology und Aehnliches Abhaengigkeiten mitbringen.
  run_sql "CREATE EXTENSION IF NOT EXISTS \"$1\" CASCADE;" 2>/tmp/ext_err_$1.log
}

echo "ARGUS: aktiviere Postgres-Erweiterungen in Datenbank '${DB}'"

missing_required=()
for ext in "${REQUIRED[@]}"; do
  if create_extension "${ext}"; then
    echo "  [ok]      ${ext}"
  else
    echo "  [FEHLT]   ${ext}"
    missing_required+=("${ext}")
  fi
done

missing_optional=()
for ext in "${OPTIONAL[@]}"; do
  if create_extension "${ext}"; then
    echo "  [ok]      ${ext} (optional)"
  else
    echo "  [offen]   ${ext} (optional, im Standard-Image nicht enthalten)"
    missing_optional+=("${ext}")
  fi
done

if [ ${#missing_required[@]} -gt 0 ]; then
  cat >&2 <<EOF

================================================================================
ARGUS: Pflicht-Erweiterungen fehlen: ${missing_required[*]}

Das Postgres-Image enthaelt sie nicht. Der Stack wird NICHT gestartet, weil ein
Postgres ohne PostGIS oder TimescaleDB fuer ARGUS unbrauchbar ist und ein
halb funktionsfaehiger Container schlimmer waere als gar keiner.

So kommen Sie weiter:

  1. Verwendetes Image pruefen:
       docker compose config | grep -A1 'postgres:' | grep image
     Erwartet wird ein timescaledb-ha-Image; es bringt PostGIS, TimescaleDB
     und pgvector mit.

  2. Verfuegbare Erweiterungen im Container auflisten:
       docker compose exec postgres psql -U ${USR} -d ${DB} \\
         -c "SELECT name, default_version FROM pg_available_extensions ORDER BY name"

  3. Fehlermeldung der jeweiligen Erweiterung ansehen:
EOF
  for ext in "${missing_required[@]}"; do
    echo "       --- ${ext} ---" >&2
    sed 's/^/       /' "/tmp/ext_err_${ext}.log" >&2 || true
  done
  cat >&2 <<EOF

  4. Wenn das Image tatsaechlich nicht passt: POSTGRES_IMAGE in
     infra/compose/.env auf ein Image mit allen Erweiterungen setzen, oder
     das mitgelieferte Image bauen:
       make postgres-age-build
================================================================================

EOF
  exit 1
fi

# Stack-Metadaten. Bewusst NICHT das Domaenenschema - das entsteht ueber
# Migrationen und gehoert nicht in ein Init-Skript des Compose-Stacks.
psql --username "${USR}" --dbname "${DB}" -v ON_ERROR_STOP=1 -q <<'SQL'
CREATE SCHEMA IF NOT EXISTS argus_meta;

COMMENT ON SCHEMA argus_meta IS
  'Metadaten des lokalen Stacks (Erweiterungsstand, Smoke-Tests). '
  'Kein Domaenenschema - das entsteht ueber Migrationen.';

CREATE TABLE IF NOT EXISTS argus_meta.stack_info (
  key         text        PRIMARY KEY,
  value       text        NOT NULL,
  updated_at  timestamptz NOT NULL DEFAULT now()
);

INSERT INTO argus_meta.stack_info (key, value)
VALUES ('initialized_at', now()::text)
ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = now();

CREATE OR REPLACE VIEW argus_meta.extension_status AS
SELECT
  required.name                              AS extension,
  (installed.extname IS NOT NULL)            AS installed,
  installed.extversion                       AS version,
  required.is_required
FROM (
  VALUES
    ('postgis',     true),
    ('timescaledb', true),
    ('vector',      true),
    ('pg_trgm',     true),
    ('btree_gist',  true),
    ('age',         false)
) AS required(name, is_required)
LEFT JOIN pg_extension AS installed ON installed.extname = required.name;

COMMENT ON VIEW argus_meta.extension_status IS
  'Soll-Ist-Vergleich der Erweiterungen. Wird von "make health" gelesen.';
SQL

if [ ${#missing_optional[@]} -gt 0 ]; then
  cat <<EOF

ARGUS: optionale Erweiterungen nicht verfuegbar: ${missing_optional[*]}
       Der Graph-Layer (Kapitel 8.3, Phase 5) braucht Apache AGE. Bis dahin
       ist das kein Problem. Wenn AGE jetzt gebraucht wird:
           make postgres-age-build && make reset && make up
       Der Build ist in infra/compose/images/postgres-age/ beschrieben.

EOF
fi

echo "ARGUS: Postgres-Initialisierung abgeschlossen."
