# ARGUS — Entwickler-Einstiegspunkt.
#
#   make up      Stack starten und warten, bis er benutzbar ist
#   make health  Zustand pruefen
#   make seed    Beispieldaten einspielen und Zusammenspiel nachweisen
#   make down    Stack anhalten (Daten bleiben)
#   make reset   Stack anhalten UND alle Daten loeschen
#
# "make help" listet alles.

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE_DIR := infra/compose
COMPOSE     := docker compose
SCHEMAS_DIR := packages/schemas
API_DIR     := services/api

# Dauerhaft laufende Kerndienste ohne Suche und Observability - fuer Rechner
# mit wenig Arbeitsspeicher.
CORE_SERVICES := postgres nats valkey minio minio-init nats-init

.PHONY: help up up-core up-base down reset restart logs ps health seed pull \
        preflight validate config images-check postgres-age-build \
        psql clickhouse nats-cli schemas check \
        db-setup db-upgrade db-downgrade db-current db-test db-ddl db-load

## help: Diese Uebersicht
help:
	@echo "ARGUS — verfuegbare Ziele:"
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  /'

# ---------------------------------------------------------------------------
# Stack-Lebenszyklus
# ---------------------------------------------------------------------------

## up: Vorabpruefung, Stack starten, warten bis bereit, Zustand melden
up: preflight
	@cd $(COMPOSE_DIR) && $(COMPOSE) up -d --remove-orphans
	@$(COMPOSE_DIR)/scripts/wait-ready.sh
	@$(MAKE) --no-print-directory health

## up-core: Nur Postgres, NATS, Valkey und MinIO (fuer Rechner unter 16 GB)
up-core: preflight
	@cd $(COMPOSE_DIR) && $(COMPOSE) up -d --remove-orphans $(CORE_SERVICES)
	@$(COMPOSE_DIR)/scripts/wait-ready.sh
	@$(MAKE) --no-print-directory health

## up-base: Ohne Entwicklungs-Override starten (keine Ports veroeffentlicht, fuer CI)
up-base:
	@cd $(COMPOSE_DIR) && $(COMPOSE) -f docker-compose.yml up -d --remove-orphans
	@$(COMPOSE_DIR)/scripts/wait-ready.sh

## down: Stack anhalten. Volumes und damit alle Daten bleiben erhalten.
down:
	@cd $(COMPOSE_DIR) && $(COMPOSE) down --remove-orphans
	@echo "Stack angehalten. Daten sind erhalten - 'make up' setzt dort fort."

## reset: Stack anhalten und ALLE Daten loeschen (Volumes, verwaiste Container)
reset:
	@echo "Loesche Container, Netzwerk und alle Volumes des Projekts:"
	@cd $(COMPOSE_DIR) && $(COMPOSE) config --volumes | sed 's/^/  - /'
	@cd $(COMPOSE_DIR) && $(COMPOSE) down --volumes --remove-orphans
	@echo "Zuruecksetzen abgeschlossen. 'make up' baut den Stack neu auf."

## restart: Alle Dienste neu starten (Konfigurationsaenderungen uebernehmen)
restart:
	@cd $(COMPOSE_DIR) && $(COMPOSE) up -d --force-recreate --remove-orphans
	@$(COMPOSE_DIR)/scripts/wait-ready.sh

## logs: Protokolle aller Dienste folgen (SERVICE=<name> fuer einen einzelnen)
logs:
	@cd $(COMPOSE_DIR) && $(COMPOSE) logs -f --tail=100 $(SERVICE)

## ps: Zustand aller Container
ps:
	@cd $(COMPOSE_DIR) && $(COMPOSE) ps --all

## pull: Images vorab ziehen (einmalig, ausserhalb der Startzeit)
pull:
	@cd $(COMPOSE_DIR) && $(COMPOSE) pull --quiet
	@echo "Images vorhanden. 'make up' startet jetzt ohne Downloadzeit."

# ---------------------------------------------------------------------------
# Pruefen
# ---------------------------------------------------------------------------

## preflight: Ports, Speicher, vm.max_map_count und .env pruefen
preflight:
	@$(COMPOSE_DIR)/scripts/preflight.sh

## health: Containerzustand UND fachliche Pruefung aller Dienste
health:
	@$(COMPOSE_DIR)/scripts/health.sh

## validate: Compose-Dateien statisch pruefen (ohne Docker-Daemon)
validate:
	@python3 $(COMPOSE_DIR)/scripts/validate.py

## config: Gemergte Compose-Konfiguration ausgeben
config:
	@cd $(COMPOSE_DIR) && $(COMPOSE) config

## images-check: Meldet, ob es zu den gepinnten Tags neuere Digests gibt
images-check:
	@$(COMPOSE_DIR)/scripts/images-check.sh

# ---------------------------------------------------------------------------
# Daten
# ---------------------------------------------------------------------------

## seed: Beispieldaten einspielen und Zusammenspiel der Dienste nachweisen
seed:
	@$(COMPOSE_DIR)/scripts/seed.sh

# ---------------------------------------------------------------------------
# Direktzugriff auf einzelne Dienste
# ---------------------------------------------------------------------------

## psql: Interaktive Postgres-Sitzung
psql:
	@cd $(COMPOSE_DIR) && set -a && . ./.env && set +a && \
	  $(COMPOSE) exec postgres psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"

## clickhouse: Interaktive ClickHouse-Sitzung
clickhouse:
	@cd $(COMPOSE_DIR) && set -a && . ./.env && set +a && \
	  $(COMPOSE) exec clickhouse clickhouse-client \
	    --user "$$CLICKHOUSE_USER" --password "$$CLICKHOUSE_PASSWORD"

## nats-cli: NATS-Kommandozeile (nats stream ls, nats sub 'argus.>')
nats-cli:
	@cd $(COMPOSE_DIR) && $(COMPOSE) run --rm --no-deps -it nats-init sh

## postgres-age-build: Postgres-Image mit Apache AGE bauen (Phase 5)
postgres-age-build:
	@docker build -t argus/postgres-age:local $(COMPOSE_DIR)/images/postgres-age
	@echo
	@echo "Gebaut: argus/postgres-age:local"
	@echo "Jetzt in $(COMPOSE_DIR)/.env eintragen:"
	@echo "  POSTGRES_IMAGE=argus/postgres-age:local"
	@echo "Danach: make reset && make up"

# ---------------------------------------------------------------------------
# Datenbankschema (services/api)
# ---------------------------------------------------------------------------

# DATABASE_URL zeigt standardmaessig auf den Dev-Stack aus infra/compose.
DATABASE_URL ?= postgresql://argus:argus_dev_only@localhost:5432/argus
API_PY := $(API_DIR)/.venv/bin/python

## db-setup: Python-Umgebung fuer die Migrationen anlegen
db-setup:
	@cd $(API_DIR) && uv venv .venv && \
	  uv pip install --python .venv/bin/python "alembic>=1.13" "psycopg[binary]>=3.1" pytest

## db-upgrade: Schema auf den aktuellen Stand bringen
db-upgrade:
	@cd $(API_DIR) && DATABASE_URL="$(DATABASE_URL)" .venv/bin/alembic upgrade head

## db-downgrade: Eine Migration zurueck (STEP=<ziel> fuer ein anderes Ziel)
db-downgrade:
	@cd $(API_DIR) && DATABASE_URL="$(DATABASE_URL)" .venv/bin/alembic downgrade $(or $(STEP),-1)

## db-current: Aktueller Migrationsstand
db-current:
	@cd $(API_DIR) && DATABASE_URL="$(DATABASE_URL)" .venv/bin/alembic current --verbose

## db-test: Migrations- und Schematests gegen eine echte Datenbank
db-test:
	@cd $(API_DIR) && DATABASE_URL="$(DATABASE_URL)" .venv/bin/python -m pytest

## db-ddl: DDL-Referenz unter packages/schemas/sql/ neu erzeugen
db-ddl:
	@cd $(API_DIR) && DATABASE_URL="$(DATABASE_URL)" ./scripts/dump_schema.sh

## db-load: Testbestand laden und Ladezeit messen (N=<zeilen>)
db-load:
	@cd $(API_DIR) && DATABASE_URL="$(DATABASE_URL)" \
	  .venv/bin/python scripts/load_testdata.py --observations $(or $(N),1000000)

# ---------------------------------------------------------------------------
# Uebergreifend
# ---------------------------------------------------------------------------

## schemas: Schema-Paket pruefen (lint, generate, typecheck, test, breaking)
schemas:
	@$(MAKE) -C $(SCHEMAS_DIR) check

## check: Alles pruefen, was ohne laufenden Stack pruefbar ist
check: validate schemas
	@echo "Statische Pruefung vollstaendig."
