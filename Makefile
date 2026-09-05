# ARGUS — Entwickler-Einstiegspunkt.
#
#   make bootstrap   Entwicklungsumgebung auf einem frischen Rechner einrichten
#   make lint        Alles pruefen, was Stil und Form betrifft
#   make typecheck   Statische Typpruefung, Python und TypeScript
#   make test        Tests aller Sprachen
#   make up          Dev-Stack starten
#
# 'make help' listet alles. 'make ci-local' faehrt dieselbe Kette wie die CI.

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE_DIR := infra/compose
COMPOSE     := docker compose
SCHEMAS_DIR := packages/schemas
SDK_DIR     := packages/connector-sdk
API_DIR     := services/api

# Alles Python laeuft aus der einen Workspace-Umgebung. Kein Paket bringt
# seine eigene .venv mehr mit - das war die Quelle von "bei mir laeuft es".
VENV   := .venv
PY     := $(VENV)/bin/python
RUFF   := $(VENV)/bin/ruff
MYPY   := $(VENV)/bin/mypy
PYTEST := $(PY) -m pytest

# Go arbeitet im Workspace-Modus; './...' greift dort nicht ueber Modulgrenzen
# hinweg, deshalb die ausdrueckliche Liste.
GO_MODULES := packages/go-runtime services/ingest-air
# Nur diese Module haben ein main-Paket und ergeben ein Binary.
GO_SERVICES := services/ingest-air

# Dauerhaft laufende Kerndienste ohne Suche und Observability.
CORE_SERVICES := postgres nats valkey minio minio-init nats-init

DATABASE_URL ?= postgresql://argus:argus_dev_only@localhost:5432/argus

.PHONY: help bootstrap doctor \
        lint lint-py lint-ts lint-go format format-check \
        typecheck typecheck-py typecheck-ts \
        test test-py test-ts test-go test-integration build-go gen \
        ci-local clean \
        up up-core up-base down reset restart logs ps health seed pull \
        preflight validate config images-check postgres-age-build \
        psql clickhouse nats-cli \
        db-upgrade db-downgrade db-current db-test db-ddl db-load \
        schemas sdk-test sbom

## help: Diese Uebersicht
help:
	@echo "ARGUS — verfuegbare Ziele:"
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  /'

# ---------------------------------------------------------------------------
# Einrichtung
# ---------------------------------------------------------------------------

## bootstrap: Vollstaendige Entwicklungsumgebung auf einem frischen Rechner
bootstrap:
	@echo "==> Werkzeuge pruefen"
	@$(MAKE) --no-print-directory doctor
	@echo "==> Python-Workspace (uv)"
	@uv sync --all-packages
	@echo "==> TypeScript-Workspace (pnpm)"
	@pnpm install --frozen-lockfile || pnpm install
	@echo "==> Go-Module"
	@go work sync
	@for m in $(GO_MODULES); do (cd $$m && go mod download) || exit 1; done
	@echo "==> Git-Hooks"
	@$(VENV)/bin/pre-commit install --install-hooks >/dev/null && echo "    pre-commit eingerichtet"
	@echo
	@echo "Fertig. Naechste Schritte:"
	@echo "  make lint test     Pruefungen ohne laufende Dienste"
	@echo "  make up            Dev-Stack starten"
	@echo "  make db-upgrade    Datenbankschema anlegen (braucht den Stack)"

## doctor: Prueft, ob die noetigen Werkzeuge vorhanden sind
doctor:
	@missing=0; \
	for tool in uv pnpm node go git; do \
	  if command -v $$tool >/dev/null 2>&1; then \
	    printf "    ok      %-6s %s\n" "$$tool" "$$($$tool version 2>/dev/null | head -1 || $$tool --version 2>/dev/null | head -1)"; \
	  else \
	    printf "    FEHLT   %s\n" "$$tool"; missing=1; \
	  fi; \
	done; \
	if command -v docker >/dev/null 2>&1; then \
	  printf "    ok      docker\n"; \
	else \
	  printf "    HINWEIS docker fehlt - nur der Dev-Stack braucht ihn\n"; \
	fi; \
	if [ $$missing -ne 0 ]; then \
	  echo; \
	  echo "Fehlende Werkzeuge installieren:"; \
	  echo "  uv    curl -LsSf https://astral.sh/uv/install.sh | sh"; \
	  echo "  pnpm  corepack enable && corepack prepare pnpm@10 --activate"; \
	  echo "  node  https://nodejs.org (>= 22)"; \
	  echo "  go    https://go.dev/dl (>= 1.24)"; \
	  exit 1; \
	fi

# ---------------------------------------------------------------------------
# Pruefen
# ---------------------------------------------------------------------------

## lint: Linting aller Sprachen
lint: lint-py lint-ts lint-go

lint-py:
	@echo "==> ruff"
	@$(RUFF) check .
	@$(RUFF) format --check .

lint-ts:
	@echo "==> eslint, buf, prettier"
	@pnpm run --silent lint
	@pnpm exec prettier --check . >/dev/null && echo "    Prettier: alles formatiert"

lint-go:
	@echo "==> gofmt, go vet"
	@unformatted=$$(gofmt -l $(GO_MODULES)); \
	 if [ -n "$$unformatted" ]; then echo "    nicht formatiert:"; echo "$$unformatted"; exit 1; fi
	@for m in $(GO_MODULES); do (cd $$m && go vet ./...) || exit 1; done

## format: Formatierer schreiben lassen
format:
	@$(RUFF) format .
	@$(RUFF) check --fix .
	@pnpm exec prettier --write . >/dev/null
	@gofmt -w $(GO_MODULES)

format-check: lint-py lint-ts lint-go

## typecheck: Statische Typpruefung, Python und TypeScript
typecheck: typecheck-py typecheck-ts

typecheck-py:
	@echo "==> mypy"
	@$(MYPY)

typecheck-ts:
	@echo "==> tsc"
	@pnpm run --silent typecheck

## gen: Erzeugte Artefakte herstellen (Protobuf -> Python, TypeScript, JSON Schema)
#
# Die Schema-Tests pruefen die *erzeugten* Artefakte. Ohne diesen Schritt
# scheitert schon das Einsammeln der Tests - und zwar mit einer Meldung, die
# nach einem kaputten Repository aussieht statt nach einem fehlenden Build.
gen:
	@$(MAKE) --no-print-directory -C $(SCHEMAS_DIR) gen

## test: Tests aller Sprachen (ohne Dienste)
test: test-py test-go test-ts

test-py: gen
	@echo "==> pytest"
	@$(PYTEST) packages services

test-ts:
	@echo "==> TypeScript-Tests"
	@pnpm run --silent test

test-go:
	@echo "==> go test"
	@for m in $(GO_MODULES); do (cd $$m && go test ./...) || exit 1; done

## build-go: Go-Dienste nach build/ bauen
#
# Mit -o: ohne die Angabe legt 'go build' das Binary im Modulverzeichnis ab,
# wo es beim naechsten 'git add -A' im Index landet. Der pre-commit-Hook
# faengt das ab, aber es gar nicht erst entstehen zu lassen ist besser.
build-go:
	@mkdir -p build
	@for m in $(GO_SERVICES); do \
	  name=$$(basename $$m); \
	  (cd $$m && go build -o "$(CURDIR)/build/$$name" ./...) || exit 1; \
	done
	@ls -1 build/ | sed 's/^/    /' 

## test-integration: Tests, die laufende Dienste brauchen (Postgres, Valkey)
test-integration: gen
	@ARGUS_TEST_POSTGRES_DSN="$(DATABASE_URL)" DATABASE_URL="$(DATABASE_URL)" \
	  $(PYTEST) packages services -m "integration or not integration"

## ci-local: Dieselbe Kette wie die CI, ohne Dienste
ci-local: lint typecheck test validate
	@echo
	@echo "Lokale CI-Kette vollstaendig."

## clean: Erzeugte Artefakte entfernen
clean:
	@rm -rf $(SCHEMAS_DIR)/gen $(SCHEMAS_DIR)/build .turbo sbom
	@find . -name '__pycache__' -not -path './node_modules/*' -not -path './.venv/*' -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -name '.pytest_cache' -not -path './node_modules/*' -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "Aufgeraeumt. 'make bootstrap' stellt alles wieder her."

## sbom: Stueckliste und Schwachstellen-Scan (braucht syft und grype)
sbom:
	@./scripts/sbom.sh

# ---------------------------------------------------------------------------
# Dev-Stack
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

## up-base: Ohne Entwicklungs-Override starten (keine Ports, fuer CI)
up-base:
	@cd $(COMPOSE_DIR) && $(COMPOSE) -f docker-compose.yml up -d --remove-orphans
	@$(COMPOSE_DIR)/scripts/wait-ready.sh

## down: Stack anhalten. Volumes und damit alle Daten bleiben erhalten.
down:
	@cd $(COMPOSE_DIR) && $(COMPOSE) down --remove-orphans
	@echo "Stack angehalten. Daten sind erhalten - 'make up' setzt dort fort."

## reset: Stack anhalten und ALLE Daten loeschen
reset:
	@echo "Loesche Container, Netzwerk und alle Volumes des Projekts:"
	@cd $(COMPOSE_DIR) && $(COMPOSE) config --volumes | sed 's/^/  - /'
	@cd $(COMPOSE_DIR) && $(COMPOSE) down --volumes --remove-orphans
	@echo "Zuruecksetzen abgeschlossen. 'make up' baut den Stack neu auf."

## restart: Alle Dienste neu starten
restart:
	@cd $(COMPOSE_DIR) && $(COMPOSE) up -d --force-recreate --remove-orphans
	@$(COMPOSE_DIR)/scripts/wait-ready.sh

## logs: Protokolle folgen (SERVICE=<name> fuer einen einzelnen)
logs:
	@cd $(COMPOSE_DIR) && $(COMPOSE) logs -f --tail=100 $(SERVICE)

## ps: Zustand aller Container
ps:
	@cd $(COMPOSE_DIR) && $(COMPOSE) ps --all

## pull: Images vorab ziehen
pull:
	@cd $(COMPOSE_DIR) && $(COMPOSE) pull --quiet
	@echo "Images vorhanden. 'make up' startet jetzt ohne Downloadzeit."

## preflight: Ports, Speicher, vm.max_map_count und .env pruefen
preflight:
	@$(COMPOSE_DIR)/scripts/preflight.sh

## health: Containerzustand UND fachliche Pruefung aller Dienste
health:
	@$(COMPOSE_DIR)/scripts/health.sh

## validate: Compose-Dateien statisch pruefen (ohne Docker-Daemon)
validate:
	@echo "==> Compose-Stack"
	@$(PY) $(COMPOSE_DIR)/scripts/validate.py

## config: Gemergte Compose-Konfiguration ausgeben
config:
	@cd $(COMPOSE_DIR) && $(COMPOSE) config

## images-check: Meldet neuere Digests zu den gepinnten Tags
images-check:
	@$(COMPOSE_DIR)/scripts/images-check.sh

## seed: Beispieldaten einspielen und Zusammenspiel nachweisen
seed:
	@$(COMPOSE_DIR)/scripts/seed.sh

## psql: Interaktive Postgres-Sitzung
psql:
	@cd $(COMPOSE_DIR) && set -a && . ./.env && set +a && \
	  $(COMPOSE) exec postgres psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"

## clickhouse: Interaktive ClickHouse-Sitzung
clickhouse:
	@cd $(COMPOSE_DIR) && set -a && . ./.env && set +a && \
	  $(COMPOSE) exec clickhouse clickhouse-client \
	    --user "$$CLICKHOUSE_USER" --password "$$CLICKHOUSE_PASSWORD"

## nats-cli: NATS-Kommandozeile
nats-cli:
	@cd $(COMPOSE_DIR) && $(COMPOSE) run --rm --no-deps -it nats-init sh

## postgres-age-build: Postgres-Image mit Apache AGE bauen (Phase 5)
postgres-age-build:
	@docker build -t argus/postgres-age:local $(COMPOSE_DIR)/images/postgres-age
	@echo "Gebaut. In $(COMPOSE_DIR)/.env eintragen: POSTGRES_IMAGE=argus/postgres-age:local"

# ---------------------------------------------------------------------------
# Datenbankschema
# ---------------------------------------------------------------------------

## db-upgrade: Schema auf den aktuellen Stand bringen
db-upgrade:
	@cd $(API_DIR) && DATABASE_URL="$(DATABASE_URL)" ../../$(VENV)/bin/alembic upgrade head

## db-downgrade: Eine Migration zurueck (STEP=<ziel> fuer ein anderes Ziel)
db-downgrade:
	@cd $(API_DIR) && DATABASE_URL="$(DATABASE_URL)" ../../$(VENV)/bin/alembic downgrade $(or $(STEP),-1)

## db-current: Aktueller Migrationsstand
db-current:
	@cd $(API_DIR) && DATABASE_URL="$(DATABASE_URL)" ../../$(VENV)/bin/alembic current --verbose

## db-test: Migrations- und Schematests gegen eine echte Datenbank
db-test:
	@DATABASE_URL="$(DATABASE_URL)" $(PYTEST) $(API_DIR)

## db-ddl: DDL-Referenz unter packages/schemas/sql/ neu erzeugen
db-ddl:
	@cd $(API_DIR) && DATABASE_URL="$(DATABASE_URL)" ARGUS_PYTHON=../../$(VENV)/bin/python ./scripts/dump_schema.sh

## db-load: Testbestand laden und Ladezeit messen (N=<zeilen>)
db-load:
	@DATABASE_URL="$(DATABASE_URL)" $(PY) $(API_DIR)/scripts/load_testdata.py \
	  --observations $(or $(N),1000000)

# ---------------------------------------------------------------------------
# Pakete
# ---------------------------------------------------------------------------

## schemas: Schema-Paket vollstaendig pruefen (lint, gen, typecheck, test, breaking)
schemas:
	@$(MAKE) -C $(SCHEMAS_DIR) check

## sdk-test: Konnektor-SDK mit Abdeckung
sdk-test:
	@ARGUS_TEST_POSTGRES_DSN="$(DATABASE_URL)" \
	  $(PYTEST) $(SDK_DIR) --cov=argus_connector --cov-report=term-missing
