#!/bin/sh
# Legt die ARGUS-Buckets an. Idempotent: laeuft bei jedem "make up" erneut.
#
# Fehlerfall "Bucket existiert bereits" ist ausdruecklich KEIN Fehler -
# "mc mb --ignore-existing" behandelt ihn als Erfolg.
set -eu

ALIAS=argus
ENDPOINT="http://minio:9000"
BUCKETS="${MINIO_BUCKETS:-argus-bronze argus-exports}"

echo "ARGUS: verbinde mit MinIO unter ${ENDPOINT}"

# Der Dienst gilt bereits als gesund (depends_on: service_healthy). Die
# Wiederholung faengt nur das Zeitfenster zwischen Healthcheck und erstem
# API-Aufruf ab.
attempt=1
until mc alias set "${ALIAS}" "${ENDPOINT}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" >/dev/null 2>&1; do
  if [ "${attempt}" -ge 10 ]; then
    echo "ARGUS: MinIO unter ${ENDPOINT} nicht erreichbar." >&2
    echo "       Pruefen: docker compose logs minio" >&2
    exit 1
  fi
  echo "  ... Versuch ${attempt} fehlgeschlagen, neuer Versuch in 2 s"
  attempt=$((attempt + 1))
  sleep 2
done

for bucket in ${BUCKETS}; do
  if mc ls "${ALIAS}/${bucket}" >/dev/null 2>&1; then
    echo "  [vorhanden] ${bucket}"
  else
    mc mb --ignore-existing "${ALIAS}/${bucket}"
    echo "  [angelegt]  ${bucket}"
  fi
  # Bronze und Exporte sind nicht oeffentlich. Explizit setzen, statt sich auf
  # den Standard zu verlassen.
  mc anonymous set none "${ALIAS}/${bucket}" >/dev/null 2>&1 || true
done

echo "ARGUS: MinIO-Buckets bereit:"
mc ls "${ALIAS}" | sed 's/^/  /'
