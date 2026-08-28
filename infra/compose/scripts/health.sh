#!/usr/bin/env bash
# ARGUS — Gesundheitspruefung des Stacks.
#
# Zwei Ebenen, weil ein Container "healthy" sein kann, ohne dass der Stack
# benutzbar ist:
#   1. Containerzustand laut Docker (der healthcheck aus docker-compose.yml)
#   2. Fachliche Pruefung: sind Erweiterungen, Buckets, Streams und Templates
#      tatsaechlich da?
set -Eeuo pipefail

COMPOSE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${COMPOSE_DIR}"

RED=$'\033[31m'; YEL=$'\033[33m'; GRN=$'\033[32m'; DIM=$'\033[2m'; BLD=$'\033[1m'; OFF=$'\033[0m'
[ -t 1 ] || { RED=""; YEL=""; GRN=""; DIM=""; BLD=""; OFF=""; }

[ -f .env ] || { echo "${RED}.env fehlt. Zuerst 'make up' ausfuehren.${OFF}"; exit 1; }
# shellcheck disable=SC1091
set -a; . ./.env; set +a

failures=0
skipped=0

row() { printf '  %-22s %s\n' "$1" "$2"; }
pass() { row "$1" "${GRN}ok${OFF}   ${DIM}$2${OFF}"; }
bad()  { row "$1" "${RED}FEHLER${OFF} $2"; failures=$((failures + 1)); }
skip() { row "$1" "${YEL}uebersprungen${OFF} ${DIM}$2${OFF}"; skipped=$((skipped + 1)); }

dc() { docker compose "$@"; }

running() { [ -n "$(dc ps -q "$1" 2>/dev/null)" ]; }

# ---------------------------------------------------------------------------
echo "${BLD}Containerzustand${OFF}"
# ---------------------------------------------------------------------------

if ! docker info >/dev/null 2>&1; then
  echo "${RED}Der Docker-Daemon antwortet nicht.${OFF}"
  exit 1
fi

ps_json="$(dc ps --format json 2>/dev/null || true)"
if [ -z "${ps_json}" ]; then
  echo "${RED}Es laeuft kein Container dieses Projekts. Zuerst 'make up'.${OFF}"
  exit 1
fi

# "docker compose ps --format json" liefert je nach Version ein Array oder
# eine Zeile je Dienst. Beides wird hier verarbeitet.
while IFS=$'\t' read -r name state health; do
  [ -n "${name}" ] || continue
  case "${health}" in
    healthy)            pass "${name}" "healthy" ;;
    "" | "<nil>")
      if [ "${state}" = "running" ]; then
        pass "${name}" "laeuft (ohne healthcheck)"
      elif [ "${state}" = "exited" ]; then
        pass "${name}" "beendet (Init-Container)"
      else
        bad "${name}" "Zustand: ${state}"
      fi
      ;;
    starting)           bad "${name}" "startet noch - erneut pruefen" ;;
    *)                  bad "${name}" "healthcheck: ${health}, Zustand: ${state}" ;;
  esac
done < <(printf '%s' "${ps_json}" | python3 -c '
import json, sys
raw = sys.stdin.read().strip()
if not raw:
    sys.exit(0)
try:
    items = json.loads(raw)
    if isinstance(items, dict):
        items = [items]
except json.JSONDecodeError:
    items = [json.loads(line) for line in raw.splitlines() if line.strip()]
for it in items:
    print("\t".join([it.get("Service", "?"), it.get("State", "?"), it.get("Health", "")]))
')

# ---------------------------------------------------------------------------
echo
echo "${BLD}Fachliche Pruefung${OFF}"
# ---------------------------------------------------------------------------

# --- Postgres: sind die Erweiterungen wirklich geladen? ---------------------
if running postgres; then
  if missing="$(dc exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
      "SELECT string_agg(extension, ', ') FROM argus_meta.extension_status
       WHERE is_required AND NOT installed" 2>/dev/null | tr -d '[:space:]')"; then
    if [ -z "${missing}" ]; then
      have="$(dc exec -T postgres psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc \
        "SELECT string_agg(extension || ' ' || coalesce(version, '-'), ', ' ORDER BY extension)
         FROM argus_meta.extension_status WHERE installed" 2>/dev/null | tr -d '\r')"
      pass "postgres/extensions" "${have}"
    else
      bad "postgres/extensions" "fehlen: ${missing}"
    fi
  else
    bad "postgres/extensions" "Abfrage fehlgeschlagen - 'docker compose logs postgres'"
  fi
else
  skip "postgres/extensions" "Container laeuft nicht"
fi

# --- ClickHouse: existieren die Datenbanken? --------------------------------
if running clickhouse; then
  dbs="$(dc exec -T clickhouse clickhouse-client \
        --user "${CLICKHOUSE_USER}" --password "${CLICKHOUSE_PASSWORD}" \
        --query "SELECT groupArray(name) FROM system.databases WHERE name LIKE 'argus%'" 2>/dev/null | tr -d '\r')"
  case "${dbs}" in
    *argus_meta*) pass "clickhouse/databases" "${dbs}" ;;
    *)            bad "clickhouse/databases" "argus_meta fehlt (gefunden: ${dbs:-nichts})" ;;
  esac
else
  skip "clickhouse/databases" "Container laeuft nicht"
fi

# --- Valkey -----------------------------------------------------------------
if running valkey; then
  if dc exec -T valkey valkey-cli -a "${VALKEY_PASSWORD}" --no-auth-warning ping 2>/dev/null | grep -q PONG; then
    pass "valkey/ping" "PONG"
  else
    bad "valkey/ping" "keine Antwort"
  fi
else
  skip "valkey/ping" "Container laeuft nicht"
fi

# --- MinIO: existieren die Buckets? ----------------------------------------
if running minio; then
  buckets="$(dc exec -T minio mc ls local 2>/dev/null | awk '{print $NF}' | tr -d '/' | tr '\n' ' ' | sed 's/ $//')"
  ok_buckets=1
  for want in ${MINIO_BUCKETS:-argus-bronze argus-exports}; do
    case " ${buckets} " in *" ${want} "*) ;; *) ok_buckets=0 ;; esac
  done
  if [ "${ok_buckets}" = "1" ]; then
    pass "minio/buckets" "${buckets}"
  else
    bad "minio/buckets" "erwartet '${MINIO_BUCKETS}', gefunden '${buckets}'"
  fi
else
  skip "minio/buckets" "Container laeuft nicht"
fi

# --- NATS: sind die Streams da? --------------------------------------------
if running nats; then
  jsz="$(curl -fsS "http://127.0.0.1:${NATS_MONITOR_PORT:-8222}/jsz" 2>/dev/null || true)"
  if [ -n "${jsz}" ]; then
    streams="$(printf '%s' "${jsz}" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("streams", 0))' 2>/dev/null || echo 0)"
    if [ "${streams}" -ge 4 ]; then
      pass "nats/jetstream" "${streams} Streams"
    else
      bad "nats/jetstream" "nur ${streams} Streams, erwartet 4 - 'docker compose logs nats-init'"
    fi
  else
    bad "nats/jetstream" "Monitoring-Port ${NATS_MONITOR_PORT:-8222} nicht erreichbar"
  fi
else
  skip "nats/jetstream" "Container laeuft nicht"
fi

# --- OpenSearch: Clusterstatus und Templates -------------------------------
if running opensearch; then
  os="http://127.0.0.1:${OPENSEARCH_PORT:-9200}"
  status="$(curl -fsS "${os}/_cluster/health" 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' 2>/dev/null || true)"
  case "${status}" in
    green|yellow) pass "opensearch/cluster" "Status ${status}" ;;
    red)          bad  "opensearch/cluster" "Status rot" ;;
    *)            bad  "opensearch/cluster" "nicht erreichbar auf ${os}" ;;
  esac
  found=0
  for tpl in argus-events argus-reports; do
    curl -fsS -o /dev/null "${os}/_index_template/${tpl}" 2>/dev/null && found=$((found + 1))
  done
  if [ "${found}" = "2" ]; then
    pass "opensearch/templates" "argus-events, argus-reports"
  else
    bad "opensearch/templates" "${found}/2 vorhanden - 'docker compose logs opensearch-init'"
  fi
else
  skip "opensearch/cluster" "Container laeuft nicht"
fi

# --- Prometheus: erreicht es seine Ziele? ----------------------------------
if running prometheus; then
  targets="$(curl -fsS "http://127.0.0.1:${PROMETHEUS_PORT:-9090}/api/v1/targets?state=active" 2>/dev/null || true)"
  if [ -n "${targets}" ]; then
    read -r up total <<<"$(printf '%s' "${targets}" | python3 -c '
import json, sys
d = json.load(sys.stdin)["data"]["activeTargets"]
print(sum(1 for t in d if t["health"] == "up"), len(d))
' 2>/dev/null || echo "0 0")"
    if [ "${up}" = "${total}" ] && [ "${total}" -gt 0 ]; then
      pass "prometheus/targets" "${up}/${total} erreichbar"
    else
      bad "prometheus/targets" "${up}/${total} erreichbar - http://localhost:${PROMETHEUS_PORT:-9090}/targets"
    fi
  else
    bad "prometheus/targets" "API nicht erreichbar"
  fi
else
  skip "prometheus/targets" "Container laeuft nicht"
fi

# --- Grafana ----------------------------------------------------------------
if running grafana; then
  if curl -fsS "http://127.0.0.1:${GRAFANA_PORT:-3000}/api/health" 2>/dev/null | grep -q ok; then
    pass "grafana/health" "erreichbar"
  else
    bad "grafana/health" "nicht erreichbar auf Port ${GRAFANA_PORT:-3000}"
  fi
else
  skip "grafana/health" "Container laeuft nicht"
fi

# ---------------------------------------------------------------------------
echo
if [ "${failures}" -gt 0 ]; then
  echo "${RED}${failures} Pruefung(en) fehlgeschlagen.${OFF}"
  echo "Protokolle:  make logs        Einzeln:  docker compose logs <dienst>"
  exit 1
fi
if [ "${skipped}" -gt 0 ]; then
  echo "${GRN}Alle laufenden Dienste sind gesund${OFF} (${skipped} nicht gestartet)."
else
  echo "${GRN}Alle Dienste gesund.${OFF}"
fi
