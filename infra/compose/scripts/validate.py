#!/usr/bin/env python3
"""ARGUS — statische Pruefung des Compose-Stacks.

Prueft die Zusagen, die der Stack macht, ohne ihn zu starten: Digest-Pinning,
echte Healthchecks, Startreihenfolge, Speicherbudget, vollstaendige .env.example
und kollisionsfreie Ports.

Laeuft ohne Docker-Daemon - nur "docker compose config" wird gebraucht, und das
merged und validiert die Dateien rein lokal. Damit ist die Pruefung auch dort
moeglich, wo keine Images gezogen werden koennen.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

COMPOSE_DIR = Path(__file__).resolve().parent.parent
BASE = COMPOSE_DIR / "docker-compose.yml"
OVERRIDE = COMPOSE_DIR / "docker-compose.override.yml"
ENV_EXAMPLE = COMPOSE_DIR / ".env.example"

# Container, die einmalig laufen und sich beenden. Sie brauchen keinen
# healthcheck; ihr Erfolg wird ueber service_completed_successfully abgebildet.
ONE_SHOT = {"minio-init", "opensearch-init", "nats-init"}

# Obergrenze der Summe aller Speicherlimits. Der Stack soll auf einem Rechner
# mit 16 GB laufen; der Rest ist Reserve fuer Betriebssystem, Container-Laufzeit
# und die Werkzeuge des Entwicklers.
MEMORY_BUDGET_GB = 12.0

RED, GRN, YEL, DIM, OFF = "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[0m"
if not sys.stdout.isatty():
    RED = GRN = YEL = DIM = OFF = ""

problems: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    problems.append(msg)


def note(msg: str) -> None:
    notes.append(msg)


def compose_config(files: list[Path]) -> dict:
    args = ["docker", "compose"]
    for f in files:
        args += ["-f", str(f)]
    args += ["--env-file", str(COMPOSE_DIR / ".env"), "config", "--format", "json"]
    result = subprocess.run(args, capture_output=True, text=True, cwd=COMPOSE_DIR)
    if result.returncode != 0:
        fail(f"'docker compose config' schlaegt fehl fuer {[f.name for f in files]}:\n{result.stderr.strip()}")
        return {}
    return json.loads(result.stdout)


def parse_memory(value) -> float:
    """Compose gibt Limits je nach Version als Byte-Zahl oder als '2g' aus."""
    if isinstance(value, (int, float)):
        return float(value)
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kmgKMG]?)b?", str(value).strip())
    if not m:
        fail(f"Speicherangabe nicht lesbar: {value!r}")
        return 0.0
    factor = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}[m.group(2).lower()]
    return float(m.group(1)) * factor


def main() -> int:
    print(f"{DIM}Pruefe {BASE.name} + {OVERRIDE.name}{OFF}\n")

    # 1. Beide Konfigurationen muessen fuer sich gueltig sein: die Basis allein
    #    (CI) und die Basis mit Override (Entwicklung).
    base_only = compose_config([BASE])
    merged = compose_config([BASE, OVERRIDE])
    if not merged:
        print(f"{RED}Konfiguration ungueltig - weitere Pruefungen entfallen.{OFF}")
        for p in problems:
            print(f"  {RED}FEHLER{OFF} {p}")
        return 1
    print(f"  {GRN}ok{OFF}  docker compose config (Basis allein und mit Override)")

    services = merged.get("services", {})
    if not services:
        fail("Keine Dienste in der Konfiguration.")

    # 2. Images: fester Digest, kein :latest.
    for name, svc in sorted(services.items()):
        image = svc.get("image")
        if not image:
            if "build" in svc:
                note(f"{name}: wird gebaut statt gezogen (kein Digest moeglich)")
                continue
            fail(f"{name}: weder image noch build gesetzt")
            continue
        if "@sha256:" not in image:
            fail(f"{name}: Image ohne Digest festgenagelt -> {image}")
        if re.search(r":latest(@|$)", image):
            fail(f"{name}: benutzt :latest -> {image}")
    print(f"  {GRN}ok{OFF}  Images mit Digest festgenagelt, kein :latest ({len(services)} Dienste)")

    # 3. Healthchecks fuer alle dauerhaft laufenden Dienste.
    for name, svc in sorted(services.items()):
        if name in ONE_SHOT:
            if "healthcheck" in svc:
                note(f"{name}: Init-Container mit healthcheck - unnoetig")
            continue
        hc = svc.get("healthcheck")
        if not hc or not hc.get("test"):
            fail(f"{name}: kein healthcheck")
            continue
        test = " ".join(hc["test"]) if isinstance(hc["test"], list) else str(hc["test"])
        # Ein Healthcheck, der nur einen Port anfasst, sagt nichts ueber die
        # Benutzbarkeit des Dienstes aus.
        if re.search(r"\b(nc|netcat)\b|/dev/tcp", test):
            fail(f"{name}: healthcheck prueft nur den Port -> {test}")
        for key in ("interval", "timeout", "retries", "start_period"):
            if key not in hc:
                note(f"{name}: healthcheck ohne {key}")
    print(f"  {GRN}ok{OFF}  Alle dauerhaften Dienste haben einen fachlichen healthcheck")

    # 4. depends_on immer mit Bedingung.
    dep_count = 0
    for name, svc in sorted(services.items()):
        deps = svc.get("depends_on") or {}
        if isinstance(deps, list):
            fail(f"{name}: depends_on ohne Bedingung (Listenform) -> {deps}")
            continue
        for dep, spec in deps.items():
            dep_count += 1
            cond = (spec or {}).get("condition")
            if cond not in ("service_healthy", "service_completed_successfully"):
                fail(f"{name}: depends_on {dep} mit Bedingung {cond!r}")
            if dep not in services:
                fail(f"{name}: depends_on verweist auf unbekannten Dienst {dep!r}")
    print(f"  {GRN}ok{OFF}  {dep_count} depends_on-Beziehungen mit expliziter Bedingung")

    # 5. Speicherbudget.
    total = 0.0
    rows = []
    for name, svc in sorted(services.items()):
        limits = ((svc.get("deploy") or {}).get("resources") or {}).get("limits") or {}
        mem = limits.get("memory")
        if mem is None:
            fail(f"{name}: kein Speicherlimit")
            continue
        b = parse_memory(mem)
        total += b
        rows.append((name, b))
    gb = total / 1024**3
    for name, b in rows:
        print(f"      {DIM}{name:<18}{b / 1024**3:>6.2f} GB{OFF}")
    if gb > MEMORY_BUDGET_GB:
        fail(f"Speicherbudget ueberschritten: {gb:.2f} GB > {MEMORY_BUDGET_GB} GB")
    else:
        print(f"  {GRN}ok{OFF}  Speicherbudget: {gb:.2f} GB von {MEMORY_BUDGET_GB} GB")

    # 6. Jede in den Compose-Dateien referenzierte Variable steht in
    #    .env.example - sonst laeuft der Stack nur auf dem Rechner, auf dem er
    #    entstanden ist.
    documented = {
        line.split("=", 1)[0].strip()
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if re.match(r"^[A-Z_][A-Z0-9_]*=", line.strip())
    }
    referenced: set[str] = set()
    for f in (BASE, OVERRIDE):
        referenced |= set(re.findall(r"\$\{([A-Z_][A-Z0-9_]*)", f.read_text(encoding="utf-8")))
    # COMPOSE_PROJECT_NAME wird von Compose selbst gesetzt, POSTGRES_IMAGE ist
    # bewusst optional (auskommentiert in .env.example).
    optional = {"POSTGRES_IMAGE"}
    undocumented = referenced - documented - optional
    if undocumented:
        fail(f"In .env.example fehlen: {', '.join(sorted(undocumented))}")
    else:
        print(f"  {GRN}ok{OFF}  Alle {len(referenced)} referenzierten Variablen sind in .env.example dokumentiert")

    unused = documented - referenced - {"TZ", "COMPOSE_PROJECT_NAME"}
    # Variablen, die nur die Skripte benutzen, sind kein Fehler.
    script_text = "".join(
        p.read_text(encoding="utf-8") for p in (COMPOSE_DIR / "scripts").glob("*")
        if p.is_file()
    ) + "".join(
        p.read_text(encoding="utf-8") for p in (COMPOSE_DIR / "init").rglob("*")
        if p.is_file()
    )
    truly_unused = {v for v in unused if v not in script_text}
    if truly_unused:
        note(f".env.example dokumentiert ungenutzte Variablen: {', '.join(sorted(truly_unused))}")

    # 7. Host-Ports eindeutig.
    seen: dict[str, str] = {}
    for name, svc in sorted(services.items()):
        for port in svc.get("ports") or []:
            published = str(port.get("published", ""))
            if not published:
                continue
            if published in seen:
                fail(f"Port {published} doppelt vergeben: {seen[published]} und {name}")
            seen[published] = name
    print(f"  {GRN}ok{OFF}  {len(seen)} veroeffentlichte Ports, keine Kollision")

    # 8. Die Basis allein darf keine Ports veroeffentlichen - sonst waere sie
    #    in CI nicht neben anderen Stacks benutzbar.
    for name, svc in (base_only.get("services") or {}).items():
        if svc.get("ports"):
            fail(f"{name}: veroeffentlicht Ports schon in der Basis, nicht erst im Override")

    # 9. Alle eingebundenen Pfade existieren.
    for name, svc in sorted(services.items()):
        for vol in svc.get("volumes") or []:
            if vol.get("type") != "bind":
                continue
            src = Path(vol["source"])
            if not src.exists():
                fail(f"{name}: eingebundener Pfad fehlt -> {src}")
    print(f"  {GRN}ok{OFF}  Alle eingebundenen Pfade vorhanden")

    # 10. Neustartverhalten gesetzt.
    for name, svc in sorted(services.items()):
        if "restart" not in svc:
            fail(f"{name}: kein restart-Verhalten gesetzt")

    print()
    for n in notes:
        print(f"  {YEL}Hinweis{OFF} {n}")
    if problems:
        print()
        for p in problems:
            print(f"  {RED}FEHLER{OFF} {p}")
        print(f"\n{RED}{len(problems)} Problem(e).{OFF}")
        return 1
    print(f"\n{GRN}Compose-Stack erfuellt alle Zusagen.{OFF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
