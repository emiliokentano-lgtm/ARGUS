#!/usr/bin/env sh
# Prueft die Protos gegen den letzten veroeffentlichten Stand.
#
# Bevorzugt wird der Stand auf dem Default-Branch: das ist die Wahrheit, gegen
# die ein Pull Request geprueft werden muss. Existiert dort noch kein
# Schema-Verzeichnis (frisches Repository, erster Commit), faellt die Pruefung
# auf das eingecheckte Baseline-Image zurueck.
set -eu

SCHEMA_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "${SCHEMA_DIR}"

BUF="${BUF:-./node_modules/.bin/buf}"
BASE_BRANCH="${ARGUS_BASE_BRANCH:-main}"
BASELINE="baseline/argus-v1.binpb"

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "${repo_root}" ]; then
  subdir="${SCHEMA_DIR#"${repo_root}"/}"
  if git cat-file -e "origin/${BASE_BRANCH}:${subdir}/buf.yaml" 2>/dev/null; then
    echo "buf breaking gegen origin/${BASE_BRANCH}"
    exec "${BUF}" breaking --against "${repo_root}/.git#branch=origin/${BASE_BRANCH},subdir=${subdir}"
  fi
  if git cat-file -e "${BASE_BRANCH}:${subdir}/buf.yaml" 2>/dev/null; then
    echo "buf breaking gegen ${BASE_BRANCH}"
    exec "${BUF}" breaking --against "${repo_root}/.git#branch=${BASE_BRANCH},subdir=${subdir}"
  fi
fi

if [ -f "${BASELINE}" ]; then
  echo "buf breaking gegen ${BASELINE} (kein Schema auf ${BASE_BRANCH})"
  exec "${BUF}" breaking --against "${BASELINE}"
fi

echo "Weder ${BASE_BRANCH} noch ${BASELINE} vorhanden - 'make baseline' ausfuehren." >&2
exit 1
