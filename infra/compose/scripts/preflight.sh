#!/usr/bin/env bash
# ARGUS — Vorabpruefung vor "make up".
#
# Faengt die Fehler ab, die sonst erst nach zwei Minuten Wartezeit als
# unverstaendlicher Containerabbruch auftauchen: belegte Ports, zu kleines
# vm.max_map_count, fehlende .env, zu wenig Arbeitsspeicher oder Plattenplatz.
set -Eeuo pipefail

COMPOSE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${COMPOSE_DIR}"

RED=$'\033[31m'; YEL=$'\033[33m'; GRN=$'\033[32m'; DIM=$'\033[2m'; OFF=$'\033[0m'
[ -t 1 ] || { RED=""; YEL=""; GRN=""; DIM=""; OFF=""; }

errors=0
warnings=0

fail() { echo "${RED}[FEHLER]${OFF} $*"; errors=$((errors + 1)); }
warn() { echo "${YEL}[HINWEIS]${OFF} $*"; warnings=$((warnings + 1)); }
ok()   { echo "${GRN}[ok]${OFF}     $*"; }
hint() { echo "         ${DIM}$*${OFF}"; }

# --- .env -------------------------------------------------------------------

if [ ! -f .env ]; then
  cp .env.example .env
  ok ".env aus .env.example angelegt"
  hint "Zugangsdaten sind Entwicklungswerte und gehoeren angepasst, sobald der"
  hint "Rechner nicht mehr allein steht."
else
  ok ".env vorhanden"
fi

# shellcheck disable=SC1091
set -a; . ./.env; set +a

# Variablen, die in .env.example dazugekommen sind, aber in einer aelteren
# .env fehlen - haeufigste Ursache fuer "Variable is not set"-Abbrueche.
missing_vars=()
while IFS='=' read -r key _; do
  case "${key}" in ''|\#*) continue;; esac
  [ -n "${!key-}" ] || missing_vars+=("${key}")
done < <(grep -E '^[A-Z_]+=' .env.example)

if [ ${#missing_vars[@]} -gt 0 ]; then
  warn "In .env fehlen Variablen aus .env.example: ${missing_vars[*]}"
  hint "Ergaenzen oder .env loeschen und neu erzeugen lassen."
fi

# --- Docker -----------------------------------------------------------------

if ! command -v docker >/dev/null 2>&1; then
  fail "docker ist nicht installiert."
  hint "https://docs.docker.com/get-docker/"
elif ! docker info >/dev/null 2>&1; then
  fail "Der Docker-Daemon antwortet nicht."
  hint "Docker Desktop starten bzw. 'sudo systemctl start docker'."
else
  ok "Docker erreichbar ($(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?'))"
fi

if ! docker compose version >/dev/null 2>&1; then
  fail "'docker compose' (v2) fehlt. Das alte 'docker-compose' reicht nicht."
else
  ok "Docker Compose $(docker compose version --short 2>/dev/null || echo '?')"
fi

# --- Ports ------------------------------------------------------------------

port_in_use() {
  # Kein ss/lsof vorausgesetzt: Verbindungsversuch ueber /dev/tcp.
  (exec 3<>"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1 && { exec 3<&-; return 0; } || return 1
}

check_port() {
  local port="$1" service="$2" var="$3"
  if port_in_use "${port}"; then
    fail "Port ${port} ist belegt (gebraucht von: ${service})."
    hint "Belegung anzeigen:  ss -ltnp 'sport = :${port}'   (macOS: lsof -i :${port})"
    hint "Oder in infra/compose/.env einen anderen Port setzen: ${var}=<frei>"
  else
    ok "Port ${port} frei (${service})"
  fi
}

check_port "${POSTGRES_PORT:-5432}"          "PostgreSQL"          POSTGRES_PORT
check_port "${CLICKHOUSE_HTTP_PORT:-8123}"   "ClickHouse HTTP"     CLICKHOUSE_HTTP_PORT
check_port "${CLICKHOUSE_NATIVE_PORT:-9000}" "ClickHouse nativ"    CLICKHOUSE_NATIVE_PORT
check_port "${CLICKHOUSE_METRICS_PORT:-9363}" "ClickHouse Metriken" CLICKHOUSE_METRICS_PORT
check_port "${NATS_CLIENT_PORT:-4222}"       "NATS"                NATS_CLIENT_PORT
check_port "${NATS_MONITOR_PORT:-8222}"      "NATS Monitoring"     NATS_MONITOR_PORT
check_port "${VALKEY_PORT:-6379}"            "Valkey"              VALKEY_PORT
check_port "${MINIO_API_PORT:-9002}"         "MinIO S3-API"        MINIO_API_PORT
check_port "${MINIO_CONSOLE_PORT:-9001}"     "MinIO Konsole"       MINIO_CONSOLE_PORT
check_port "${OPENSEARCH_PORT:-9200}"        "OpenSearch"          OPENSEARCH_PORT
check_port "${PROMETHEUS_PORT:-9090}"        "Prometheus"          PROMETHEUS_PORT
check_port "${GRAFANA_PORT:-3000}"           "Grafana"             GRAFANA_PORT

# --- vm.max_map_count (OpenSearch) ------------------------------------------

REQUIRED_MAP_COUNT=262144
if [ "$(uname -s)" = "Linux" ]; then
  current="$(sysctl -n vm.max_map_count 2>/dev/null || echo 0)"
  if [ "${current}" -lt "${REQUIRED_MAP_COUNT}" ]; then
    fail "vm.max_map_count ist ${current}, OpenSearch braucht mindestens ${REQUIRED_MAP_COUNT}."
    hint "Sofort (bis zum Neustart):"
    hint "  sudo sysctl -w vm.max_map_count=${REQUIRED_MAP_COUNT}"
    hint "Dauerhaft:"
    hint "  echo 'vm.max_map_count=${REQUIRED_MAP_COUNT}' | sudo tee /etc/sysctl.d/99-opensearch.conf"
    hint "  sudo sysctl --system"
    hint "Ohne das bricht OpenSearch beim Start mit 'max virtual memory areas"
    hint "vm.max_map_count [${current}] is too low' ab."
  else
    ok "vm.max_map_count = ${current}"
  fi
else
  warn "vm.max_map_count nicht pruefbar (kein Linux-Host)."
  hint "Docker Desktop setzt den Wert in seiner VM selbst. Falls OpenSearch"
  hint "trotzdem abbricht: Docker Desktop > Settings > Resources > mindestens"
  hint "8 GB Arbeitsspeicher zuweisen."
fi

# --- Arbeitsspeicher --------------------------------------------------------

RECOMMENDED_GB=16
MINIMUM_GB=12
total_gb=""
if command -v free >/dev/null 2>&1; then
  total_gb="$(free -g | awk '/^Mem:/ {print $2}')"
elif [ "$(uname -s)" = "Darwin" ]; then
  total_gb="$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))"
fi

if [ -n "${total_gb}" ]; then
  if [ "${total_gb}" -lt "${MINIMUM_GB}" ]; then
    fail "Nur ${total_gb} GB Arbeitsspeicher; der Stack braucht ${MINIMUM_GB} GB, empfohlen ${RECOMMENDED_GB} GB."
    hint "Schlanker starten (ohne Suche und Observability):"
    hint "  make up-core"
  elif [ "${total_gb}" -lt "${RECOMMENDED_GB}" ]; then
    warn "${total_gb} GB Arbeitsspeicher; empfohlen sind ${RECOMMENDED_GB} GB."
    hint "Bei Problemen OPENSEARCH_MEM_LIMIT und OPENSEARCH_JAVA_OPTS senken."
  else
    ok "Arbeitsspeicher: ${total_gb} GB"
  fi
fi

# --- Plattenplatz -----------------------------------------------------------

REQUIRED_DISK_GB=20
avail_gb="$(df -Pk . 2>/dev/null | awk 'NR==2 {print int($4/1024/1024)}')"
if [ -n "${avail_gb}" ]; then
  if [ "${avail_gb}" -lt "${REQUIRED_DISK_GB}" ]; then
    warn "Nur ${avail_gb} GB frei; Images und Volumes brauchen etwa ${REQUIRED_DISK_GB} GB."
    hint "Aufraeumen: docker system prune -a --volumes"
  else
    ok "Plattenplatz: ${avail_gb} GB frei"
  fi
fi

# --- Ergebnis ---------------------------------------------------------------

echo
if [ "${errors}" -gt 0 ]; then
  echo "${RED}Vorabpruefung fehlgeschlagen: ${errors} Fehler, ${warnings} Hinweise.${OFF}"
  echo "Die Punkte oben beheben und 'make up' erneut ausfuehren."
  exit 1
fi
echo "${GRN}Vorabpruefung bestanden${OFF} (${warnings} Hinweise)."
