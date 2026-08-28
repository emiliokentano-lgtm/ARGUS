#!/bin/sh
# Legt die JetStream-Streams nach dem Subject-Schema aus Kapitel 5.3 an.
#
#   argus.raw.{source}            Rohnachrichten, kurz vorgehalten
#   argus.canon.{domain}.{type}   kanonisiert
#   argus.enriched.{domain}       angereichert
#   argus.alerts.{severity}       Alarme
#
# Idempotent: bestehende Streams werden erkannt und nicht angefasst. Ein
# "stream update" findet hier bewusst nicht statt - eine Aenderung der
# Aufbewahrung ist eine bewusste Entscheidung und gehoert nicht in ein
# Startskript.
set -eu

export NATS_URL="${NATS_URL:-nats://nats:4222}"

echo "ARGUS: verbinde mit NATS unter ${NATS_URL}"

attempt=1
until nats server check jetstream --enabled >/dev/null 2>&1 || nats account info >/dev/null 2>&1; do
  if [ "${attempt}" -ge 10 ]; then
    echo "ARGUS: NATS/JetStream unter ${NATS_URL} nicht erreichbar." >&2
    echo "       Pruefen: docker compose logs nats" >&2
    exit 1
  fi
  echo "  ... Versuch ${attempt} fehlgeschlagen, neuer Versuch in 2 s"
  attempt=$((attempt + 1))
  sleep 2
done

# name | subjects | max-age | Zweck
ensure_stream() {
  name="$1"; subjects="$2"; max_age="$3"; purpose="$4"
  if nats stream info "${name}" >/dev/null 2>&1; then
    echo "  [vorhanden] ${name}"
    return 0
  fi
  nats stream add "${name}" \
    --subjects "${subjects}" \
    --storage file \
    --retention limits \
    --max-age "${max_age}" \
    --discard old \
    --dupe-window 2m \
    --replicas 1 \
    --description "${purpose}" \
    --defaults >/dev/null
  echo "  [angelegt]  ${name}  (${subjects}, max-age ${max_age})"
}

# Roh: nur so lange, wie ein Wiederaufsetzen der Verarbeitung dauern darf.
# Die dauerhafte Ablage ist der Bronze-Layer in MinIO, nicht der Bus.
ensure_stream ARGUS_RAW      'argus.raw.>'      7d  'Rohnachrichten der Konnektoren'
ensure_stream ARGUS_CANON    'argus.canon.>'    30d 'Kanonisierte Nachrichten'
ensure_stream ARGUS_ENRICHED 'argus.enriched.>' 30d 'Angereicherte Nachrichten'
ensure_stream ARGUS_ALERTS   'argus.alerts.>'   90d 'Alarme'

echo "ARGUS: JetStream-Streams bereit:"
nats stream ls | sed 's/^/  /'
