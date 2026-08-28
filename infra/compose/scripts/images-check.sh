#!/usr/bin/env bash
# ARGUS — prueft, ob die festgenagelten Images noch dem Tag entsprechen.
#
# Digest-Pinning heisst nicht "nie aktualisieren", sondern "nur bewusst
# aktualisieren". Dieses Skript zeigt, wo Tag und Digest auseinandergelaufen
# sind; das Anpassen bleibt ein Commit von Hand.
set -Eeuo pipefail

COMPOSE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${COMPOSE_DIR}"

GRN=$'\033[32m'; YEL=$'\033[33m'; DIM=$'\033[2m'; OFF=$'\033[0m'
[ -t 1 ] || { GRN=""; YEL=""; DIM=""; OFF=""; }

outdated=0

resolve() {
  local repo="$1" tag="$2" token
  case "${repo}" in */*) ;; *) repo="library/${repo}";; esac
  token="$(curl -fsS "https://auth.docker.io/token?service=registry.docker.io&scope=repository:${repo}:pull" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')"
  curl -fsS -D- -o /dev/null \
    -H "Authorization: Bearer ${token}" \
    -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json" \
    "https://registry-1.docker.io/v2/${repo}/manifests/${tag}" \
    | tr -d '\r' | awk 'tolower($1)=="docker-content-digest:"{print $2}'
}

echo "Vergleiche gepinnte Digests mit den aktuellen Tags..."
echo

while IFS= read -r ref; do
  name="${ref%@*}"
  pinned="${ref#*@}"
  repo="${name%:*}"
  tag="${name##*:}"
  current="$(resolve "${repo}" "${tag}" || true)"
  if [ -z "${current}" ]; then
    printf '  %s %s\n' "${YEL}?${OFF}" "${name} ${DIM}(Digest nicht abrufbar)${OFF}"
  elif [ "${current}" = "${pinned}" ]; then
    printf '  %s %s\n' "${GRN}aktuell${OFF}" "${name}"
  else
    outdated=$((outdated + 1))
    printf '  %s %s\n' "${YEL}NEUER${OFF}   ${name}"
    printf '      gepinnt: %s\n' "${pinned}"
    printf '      aktuell: %s\n' "${current}"
  fi
done < <(grep -ohE '[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}' \
           docker-compose.yml images/*/Dockerfile 2>/dev/null \
         | sed 's/^[^a-z0-9]*//' | sort -u)

echo
if [ "${outdated}" -gt 0 ]; then
  echo "${YEL}${outdated} Image(s) haben unter demselben Tag einen neuen Digest.${OFF}"
  echo "Bewusst aktualisieren: Digest in docker-compose.yml eintragen, 'make up',"
  echo "'make health' und erst dann committen."
else
  echo "${GRN}Alle Digests entsprechen ihrem Tag.${OFF}"
fi
