# ARGUS Schema-Paket. Einzige Wahrheitsquelle fuer Datenstrukturen.
#
# Generierte Artefakte liegen unter gen/ und werden nicht eingecheckt.
# 'make check' ist das, was die CI faehrt.

SHELL := /bin/sh
BUF   := ./node_modules/.bin/buf
TSC   := ./node_modules/.bin/tsc
PY    := .venv/bin/python

DESCRIPTOR := build/descriptor.binpb
BASELINE   := baseline/argus-v1.binpb

.DEFAULT_GOAL := check
.PHONY: check setup gen lint breaking baseline descriptor jsonschema test typecheck clean help

## setup: Werkzeuge installieren (npm + Python-Venv)
setup:
	npm ci --no-audit --no-fund || npm install --no-audit --no-fund
	uv venv .venv
	uv pip install --python $(PY) grpcio-tools protobuf jsonschema pytest

## lint: buf lint (Stilregeln, Kommentarpflicht auf Message- und Enum-Ebene)
lint:
	$(BUF) lint
	$(BUF) format --diff --exit-code

## breaking: Pruefung auf brechende Aenderungen gegen den veroeffentlichten Stand
breaking:
	./tools/breaking.sh

## baseline: Baseline-Image neu setzen. NUR beim Release ausfuehren.
baseline:
	@mkdir -p baseline
	$(BUF) build -o $(BASELINE)
	@echo "Baseline aktualisiert. Der CHANGELOG-Eintrag gehoert in denselben Commit."

descriptor:
	@mkdir -p build
	$(BUF) build -o $(DESCRIPTOR) --as-file-descriptor-set

## jsonschema: JSON Schemas aus dem Descriptor-Set erzeugen
jsonschema: descriptor
	$(PY) tools/gen_jsonschema.py \
		--descriptor $(DESCRIPTOR) \
		--out gen/jsonschema \
		--required tools/required.json

## gen: Code fuer Python und TypeScript sowie die JSON Schemas erzeugen
gen:
	$(BUF) generate
	$(MAKE) jsonschema

## typecheck: generierten TypeScript-Code uebersetzen
typecheck:
	$(TSC) -p tsconfig.json

## test: Round-Trip-, Beispiel- und Fehlerfalltests
test:
	PYTHONPATH=tests $(PY) -m pytest tests -q

## check: alles, was die CI prueft
check: lint gen typecheck test breaking
	@echo "OK - Schemas sind sauber, generierbar, uebersetzbar und rueckwaertskompatibel."

## clean: generierte Artefakte entfernen
clean:
	rm -rf gen build .pytest_cache
	find . -name '__pycache__' -not -path './node_modules/*' -not -path './.venv/*' -prune -exec rm -rf {} +

help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  /'
