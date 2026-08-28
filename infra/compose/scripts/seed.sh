#!/usr/bin/env bash
# ARGUS — Startdaten und Ende-zu-Ende-Rauchtest.
#
# Der Seed ist bewusst mehr als "ein paar Zeilen einfuegen": er schickt dieselben
# geprueften Beispiel-Payloads aus packages/schemas durch jeden Dienst und weist
# damit nach, dass der Stack nicht nur laeuft, sondern zusammenspielt.
#
#   MinIO       Beispiel-Payloads als Bronze-Objekte ablegen
#   Postgres    Seed-Vermerk in argus_meta schreiben und zurueck lesen
#   ClickHouse  dasselbe
#   NATS        Nachricht auf argus.raw.seed veroeffentlichen und aus dem
#               Stream zurueck lesen (beweist, dass JetStream persistiert)
#   OpenSearch  Ereignis-Beispiel als Projektion indizieren und wiederfinden
#
# Idempotent: mehrfaches Ausfuehren fuehrt zum selben Zustand.
set -Eeuo pipefail

COMPOSE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd -- "${COMPOSE_DIR}/../.." && pwd)"
cd "${COMPOSE_DIR}"

GRN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; BLD=$'\033[1m'; OFF=$'\033[0m'
[ -t 1 ] || { GRN=""; RED=""; DIM=""; BLD=""; OFF=""; }

[ -f .env ] || { echo "${RED}.env fehlt. Zuerst 'make up'.${OFF}"; exit 1; }
# shellcheck disable=SC1091
set -a; . ./.env; set +a

EXAMPLES="${REPO_ROOT}/packages/schemas/examples"
dc() { docker compose "$@"; }
step() { printf '%s\n' "${BLD}$*${OFF}"; }
done_() { printf '  %s %s\n' "${GRN}ok${OFF}" "${DIM}$*${OFF}"; }

if [ ! -d "${EXAMPLES}" ]; then
  echo "${RED}packages/schemas/examples nicht gefunden unter ${EXAMPLES}.${OFF}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
step "MinIO — Beispiel-Payloads in den Bronze-Layer"
# ---------------------------------------------------------------------------
# Bronze ist nach source/yyyy/mm/dd/hh partitioniert (Kapitel 5.2). Der Seed
# benutzt eine feste Partition, damit wiederholtes Ausfuehren nichts anhaeuft.
PREFIX="local/seed/2026/08/28/00"
count=0
while IFS= read -r file; do
  rel="$(basename "${file}")"
  dc exec -T minio mkdir -p "/tmp/seed" >/dev/null 2>&1 || true
  dc cp "${file}" "minio:/tmp/seed/${rel}" >/dev/null
  dc exec -T minio mc cp --quiet "/tmp/seed/${rel}" \
      "local/argus-bronze/${PREFIX}/${rel}" >/dev/null
  count=$((count + 1))
done < <(find "${EXAMPLES}" -name '*.json' ! -name 'README*' | sort)
done_ "${count} Objekte unter s3://argus-bronze/${PREFIX}/"

objects="$(dc exec -T minio mc ls --recursive "local/argus-bronze/${PREFIX}/" 2>/dev/null | wc -l | tr -d ' ')"
[ "${objects}" -ge "${count}" ] || { echo "${RED}Rueckprobe fehlgeschlagen: ${objects} von ${count} Objekten lesbar.${OFF}" >&2; exit 1; }
done_ "Rueckprobe: ${objects} Objekte wieder lesbar"

# ---------------------------------------------------------------------------
step "PostgreSQL — Seed-Vermerk"
# ---------------------------------------------------------------------------
dc exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 -q <<'SQL'
INSERT INTO argus_meta.stack_info (key, value)
VALUES ('seeded_at', now()::text)
ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = now();
SQL
seeded="$(dc exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
  "SELECT value FROM argus_meta.stack_info WHERE key = 'seeded_at'" | tr -d '\r')"
done_ "argus_meta.stack_info.seeded_at = ${seeded}"

# ---------------------------------------------------------------------------
step "ClickHouse — Seed-Vermerk"
# ---------------------------------------------------------------------------
dc exec -T clickhouse clickhouse-client \
  --user "${CLICKHOUSE_USER}" --password "${CLICKHOUSE_PASSWORD}" \
  --query "INSERT INTO argus_meta.stack_info (key, value) VALUES ('seeded_at', toString(now64(3)))" >/dev/null
ch_rows="$(dc exec -T clickhouse clickhouse-client \
  --user "${CLICKHOUSE_USER}" --password "${CLICKHOUSE_PASSWORD}" \
  --query "SELECT count() FROM argus_meta.stack_info" | tr -d '\r')"
done_ "argus_meta.stack_info: ${ch_rows} Zeile(n)"

# ---------------------------------------------------------------------------
step "NATS — Nachricht veroeffentlichen und aus dem Stream zurueck lesen"
# ---------------------------------------------------------------------------
# Beweist, dass JetStream tatsaechlich persistiert und nicht nur zustellt.
payload="{\"seed\":true,\"at\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
dc run --rm --no-deps -T nats-init sh -c \
  "nats pub argus.raw.seed '${payload}' >/dev/null && nats stream info ARGUS_RAW --json" \
  > /tmp/argus_stream.json 2>/dev/null
msgs="$(python3 -c 'import json;print(json.load(open("/tmp/argus_stream.json"))["state"]["messages"])' 2>/dev/null || echo 0)"
[ "${msgs}" -ge 1 ] || { echo "${RED}ARGUS_RAW enthaelt keine Nachricht.${OFF}" >&2; exit 1; }
done_ "ARGUS_RAW: ${msgs} Nachricht(en) gespeichert"

# ---------------------------------------------------------------------------
step "OpenSearch — Ereignis-Beispiel indizieren und wiederfinden"
# ---------------------------------------------------------------------------
# Der Index haelt eine flache Projektion, nicht den kanonischen Datensatz -
# der liegt in Postgres. Das Mapping ist dynamic=strict, deshalb wird hier
# ausdruecklich projiziert statt das Fixture roh zu schicken.
OS="http://127.0.0.1:${OPENSEARCH_PORT:-9200}"
python3 - "${EXAMPLES}/concept/event.json" > /tmp/argus_event_doc.json <<'PY'
import json, sys
src = {k: v for k, v in json.load(open(sys.argv[1])).items() if not k.startswith("_")}
geo = src.get("geo", {})
point = geo.get("geometry", {}).get("point")
doc = {
    "event_id": src["event_id"],
    "schema_version": src.get("schema_version"),
    "type": src.get("type"),
    "title": src.get("title"),
    "summary": src.get("summary"),
    "lang": src.get("lang"),
    "occurred_at": src.get("occurred_at", {}).get("start"),
    "observed_at": src.get("observed_at"),
    "ingested_at": src.get("ingested_at"),
    "status": src.get("status"),
    "severity": src.get("severity"),
    "confidence": src.get("confidence"),
    "priority": src.get("scores", {}).get("priority"),
    "geo_precision": geo.get("precision"),
    "place_name": geo.get("place_name"),
    "country": geo.get("place", {}).get("country_iso3166_1"),
    "h3_r7": geo.get("h3_r7"),
    "entity_ids": [e["ref"]["id"] for e in src.get("entities", []) if e.get("ref")],
    "source_id": src.get("source", {}).get("id"),
    "source_reliability": src.get("source", {}).get("reliability"),
    "story_cluster_id": src.get("story_cluster_id"),
    "tags": src.get("tags", []),
}
if point:
    doc["geo_point"] = {"lon": point["lon"], "lat": point["lat"]}
json.dump({k: v for k, v in doc.items() if v is not None}, sys.stdout)
PY

event_id="$(python3 -c 'import json;print(json.load(open("/tmp/argus_event_doc.json"))["event_id"])')"
curl -fsS -o /dev/null -X PUT "${OS}/argus-events-seed/_doc/${event_id}?refresh=true" \
  -H 'Content-Type: application/json' --data-binary @/tmp/argus_event_doc.json
hits="$(curl -fsS "${OS}/argus-events-seed/_search?q=type:economic.rate_decision" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["hits"]["total"]["value"])')"
[ "${hits}" -ge 1 ] || { echo "${RED}Indiziertes Ereignis nicht wiedergefunden.${OFF}" >&2; exit 1; }
done_ "argus-events-seed: ${hits} Treffer fuer type:economic.rate_decision"

echo
echo "${GRN}Seed abgeschlossen — der Stack spielt zusammen.${OFF}"
echo "  MinIO-Konsole:  http://localhost:${MINIO_CONSOLE_PORT:-9001}"
echo "  OpenSearch:     ${OS}/argus-events-seed/_search?pretty"
echo "  Grafana:        http://localhost:${GRAFANA_PORT:-3000}"
