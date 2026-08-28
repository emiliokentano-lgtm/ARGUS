#!/usr/bin/env bash
# ARGUS — Stueckliste (SBOM) und Schwachstellen-Scan.
#
# syft erzeugt die Stueckliste, grype prueft sie gegen Schwachstellendatenbanken.
# Beides laeuft in der CI bei jedem Pull Request; lokal ist es der schnellste
# Weg, einen Fund nachzuvollziehen, ohne auf die Pipeline zu warten.
#
# Die Schwelle ist bewusst 'critical': ein Build, der bei jedem 'medium'
# rot wird, wird binnen zwei Wochen mit --ignore gefahren. Alles unterhalb
# von critical erscheint als Bericht und wird im Review entschieden.
set -Eeuo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

OUT_DIR="${SBOM_DIR:-sbom}"
FAIL_ON="${GRYPE_FAIL_ON:-critical}"

for tool in syft grype; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    cat >&2 <<EOF
${tool} ist nicht installiert.

  macOS/Linux:  brew install ${tool}
  oder:         curl -sSfL https://raw.githubusercontent.com/anchore/${tool}/main/install.sh \\
                  | sh -s -- -b /usr/local/bin

In der CI wird ${tool} ueber die offizielle Action installiert; lokal ist es
optional. 'make lint test' laeuft auch ohne.
EOF
    exit 127
  fi
done

mkdir -p "${OUT_DIR}"

echo "==> Stueckliste erzeugen"
syft dir:. \
  --exclude './node_modules' --exclude './.venv' --exclude './**/gen' \
  --output "cyclonedx-json=${OUT_DIR}/argus.cdx.json" \
  --output "spdx-json=${OUT_DIR}/argus.spdx.json" \
  --output "table=${OUT_DIR}/argus.txt"

echo "==> Schwachstellen pruefen (Abbruch ab ${FAIL_ON})"
grype "sbom:${OUT_DIR}/argus.cdx.json" \
  --output table \
  --output "json=${OUT_DIR}/grype.json" \
  --fail-on "${FAIL_ON}"

echo
echo "Stueckliste unter ${OUT_DIR}/ abgelegt."
