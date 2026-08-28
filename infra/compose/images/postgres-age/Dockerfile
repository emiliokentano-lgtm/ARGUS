# ARGUS — Postgres mit Apache AGE zusaetzlich zu PostGIS/TimescaleDB/pgvector.
#
# WOFUER: Der Graph-Layer (Kapitel 8.3) braucht Apache AGE. Das Basis-Image
# timescale/timescaledb-ha bringt PostGIS, TimescaleDB und pgvector mit, aber
# kein AGE - es gibt kein oeffentliches Image mit allen fuenf Erweiterungen.
#
# WANN: Erst ab Phase 5. Bis dahin meldet das Init-Skript AGE als "offen" und
# der Stack laeuft ohne. Wer ihn jetzt braucht:
#
#   make postgres-age-build
#   # in infra/compose/.env setzen:
#   #   POSTGRES_IMAGE=argus/postgres-age:local
#   make reset && make up
#
# WARNUNG: Dieser Build wurde in der Entwicklungsumgebung, in der er entstanden
# ist, nicht ausgefuehrt (kein Netzzugriff auf die Paketquellen). Er ist nach
# der offiziellen AGE-Bauanleitung geschrieben, aber ungetestet. Wenn er
# fehlschlaegt, ist die AGE-Version gegen die Postgres-Hauptversion des
# Basis-Image zu pruefen: AGE veroeffentlicht pro Postgres-Major einen eigenen
# Zweig (PG16, PG17).

ARG BASE_IMAGE=timescale/timescaledb-ha:pg17.10-ts2.29.2@sha256:a693dd7fbb75b51c3d717507a9956501686edb123b48dd90b094fd5612d53abe

FROM ${BASE_IMAGE} AS builder

# AGE-Zweig passend zur Postgres-Hauptversion des Basis-Image.
ARG AGE_VERSION=PG17
ARG AGE_REPO=https://github.com/apache/age.git

USER root

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
        bison \
        flex \
        postgresql-server-dev-17; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    git clone --depth 1 --branch "${AGE_VERSION}" "${AGE_REPO}" /tmp/age; \
    cd /tmp/age; \
    make PG_CONFIG="$(command -v pg_config)"; \
    make PG_CONFIG="$(command -v pg_config)" install; \
    rm -rf /tmp/age

FROM ${BASE_IMAGE}

USER root

# Nur die gebauten Artefakte uebernehmen - die Build-Werkzeuge bleiben draussen.
COPY --from=builder /usr/lib/postgresql /usr/lib/postgresql
COPY --from=builder /usr/share/postgresql /usr/share/postgresql

USER postgres

LABEL org.opencontainers.image.title="ARGUS Postgres (PostGIS + TimescaleDB + pgvector + AGE)" \
      org.opencontainers.image.description="Basis-Image plus Apache AGE fuer den Graph-Layer" \
      org.opencontainers.image.source="infra/compose/images/postgres-age/Dockerfile"
