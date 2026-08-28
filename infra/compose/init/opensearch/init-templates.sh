#!/bin/sh
# Legt Component- und Index-Templates in OpenSearch an.
#
# Idempotent: PUT ersetzt ein bestehendes Template vollstaendig. Bereits
# angelegte Indizes werden davon nicht beruehrt - Templates greifen nur bei
# der Neuanlage eines Index.
set -eu

OS="${OPENSEARCH_URL:-http://opensearch:9200}"
TPL=/init/templates

echo "ARGUS: verbinde mit OpenSearch unter ${OS}"

attempt=1
until curl -fsS "${OS}/_cluster/health?wait_for_status=yellow&timeout=5s" >/dev/null 2>&1; do
  if [ "${attempt}" -ge 15 ]; then
    echo "ARGUS: OpenSearch unter ${OS} nicht erreichbar oder Cluster rot." >&2
    echo "       Pruefen: docker compose logs opensearch" >&2
    echo "       Haeufigste Ursache unter Linux: vm.max_map_count zu klein." >&2
    echo "       Abhilfe: sudo sysctl -w vm.max_map_count=262144" >&2
    exit 1
  fi
  echo "  ... Versuch ${attempt} fehlgeschlagen, neuer Versuch in 2 s"
  attempt=$((attempt + 1))
  sleep 2
done

put() {
  kind="$1"; name="$2"; file="$3"
  code=$(curl -sS -o /tmp/resp.json -w '%{http_code}' \
    -X PUT "${OS}/_${kind}/${name}" \
    -H 'Content-Type: application/json' \
    --data-binary "@${file}")
  if [ "${code}" = "200" ] || [ "${code}" = "201" ]; then
    echo "  [ok] ${kind}/${name}"
  else
    echo "ARGUS: Anlegen von ${kind}/${name} fehlgeschlagen (HTTP ${code})" >&2
    sed 's/^/       /' /tmp/resp.json >&2
    exit 1
  fi
}

put component_template argus-base-settings "${TPL}/component-argus-base.json"
put index_template      argus-events       "${TPL}/index-argus-events.json"
put index_template      argus-reports      "${TPL}/index-argus-reports.json"

echo "ARGUS: OpenSearch-Templates bereit."
