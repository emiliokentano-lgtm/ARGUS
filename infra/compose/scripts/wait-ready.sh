#!/usr/bin/env bash
# ARGUS — wartet, bis der Stack benutzbar ist.
#
# "docker compose up -d" kehrt sofort zurueck. Dieses Skript wartet, bis jeder
# dauerhafte Dienst healthy ist und jeder Init-Container erfolgreich beendet
# wurde - mit Fortschrittsanzeige, damit die Wartezeit nachvollziehbar bleibt,
# und mit einem harten Zeitlimit, damit ein haengender Dienst nicht ewig blockt.
set -Eeuo pipefail

COMPOSE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${COMPOSE_DIR}"

TIMEOUT="${ARGUS_WAIT_TIMEOUT:-300}"
INTERVAL=3

RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; DIM=$'\033[2m'; OFF=$'\033[0m'
[ -t 1 ] || { RED=""; GRN=""; YEL=""; DIM=""; OFF=""; }

ONE_SHOT="minio-init opensearch-init nats-init"

is_one_shot() {
  case " ${ONE_SHOT} " in *" $1 "*) return 0;; *) return 1;; esac
}

# Gibt je Dienst eine Zeile "name<TAB>state<TAB>health<TAB>exitcode" aus.
snapshot() {
  docker compose ps --all --format json 2>/dev/null | python3 -c '
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
    print("\t".join([
        it.get("Service", "?"),
        it.get("State", "?"),
        it.get("Health", "") or "-",
        str(it.get("ExitCode", "")),
    ]))
'
}

start="$(date +%s)"
printf '%s\n' "${DIM}Warte auf den Stack (Zeitlimit ${TIMEOUT} s)...${OFF}"

while :; do
  pending=()
  broken=()

  while IFS=$'\t' read -r name state health exitcode; do
    [ -n "${name}" ] || continue
    if is_one_shot "${name}"; then
      case "${state}" in
        exited)
          [ "${exitcode}" = "0" ] || broken+=("${name} (Init-Container beendet mit Code ${exitcode})")
          ;;
        running|created|restarting) pending+=("${name}") ;;
        *) broken+=("${name} (Zustand ${state})") ;;
      esac
      continue
    fi

    case "${health}" in
      healthy) ;;
      starting|-) 
        if [ "${state}" = "running" ] && [ "${health}" = "-" ]; then
          : # laeuft ohne healthcheck - gilt als bereit
        else
          pending+=("${name}")
        fi
        ;;
      unhealthy) broken+=("${name} (healthcheck unhealthy)") ;;
      *) pending+=("${name}") ;;
    esac

    case "${state}" in
      exited|dead) broken+=("${name} (Zustand ${state}, Code ${exitcode})") ;;
    esac
  done < <(snapshot)

  if [ ${#broken[@]} -gt 0 ]; then
    echo
    echo "${RED}Der Stack ist nicht hochgekommen:${OFF}"
    printf '  - %s\n' "${broken[@]}"
    echo
    echo "Naechster Schritt - Protokoll des betroffenen Dienstes ansehen:"
    for b in "${broken[@]}"; do
      echo "  docker compose logs --tail=80 ${b%% *}"
    done
    exit 1
  fi

  if [ ${#pending[@]} -eq 0 ]; then
    elapsed=$(( $(date +%s) - start ))
    echo "${GRN}Stack bereit${OFF} nach ${elapsed} s."
    exit 0
  fi

  elapsed=$(( $(date +%s) - start ))
  if [ "${elapsed}" -ge "${TIMEOUT}" ]; then
    echo
    echo "${RED}Zeitlimit von ${TIMEOUT} s ueberschritten.${OFF}"
    echo "Noch nicht bereit: ${pending[*]}"
    echo
    echo "Haeufigste Ursachen:"
    echo "  - OpenSearch bricht ab, weil vm.max_map_count zu klein ist"
    echo "      sudo sysctl -w vm.max_map_count=262144"
    echo "  - Zu wenig Arbeitsspeicher fuer den Container (OOM-Kill)"
    echo "      docker compose ps --all   und   docker inspect <container> | grep OOMKilled"
    echo "  - Erstes Ziehen der Images dauert laenger als das Zeitlimit"
    echo "      make pull   (einmalig vorab, ausserhalb der Startzeit)"
    echo
    echo "Protokolle:  make logs"
    exit 1
  fi

  printf '\r%s' "${DIM}  ${elapsed}s — es fehlen noch: ${pending[*]}$(printf '%*s' 20 '')${OFF}"
  sleep "${INTERVAL}"
done
