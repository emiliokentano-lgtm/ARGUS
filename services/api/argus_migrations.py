"""Gemeinsame Helfer fuer die ARGUS-Migrationen.

Liegt neben alembic.ini und wird ueber prepend_sys_path importierbar gemacht.
"""

from __future__ import annotations

import os
import sys

from alembic import op
from sqlalchemy import text

# ---------------------------------------------------------------------------
# TimescaleDB
# ---------------------------------------------------------------------------

TIMESCALE_ENV = "ARGUS_TIMESCALE"


def timescale_mode() -> str:
    """Entscheidet, ob 'observations' eine Hypertable oder eine nativ
    partitionierte Tabelle wird.

    ARGUS_TIMESCALE:
      auto (Standard)  TimescaleDB benutzen, wenn verfuegbar, sonst native
                       Bereichspartitionierung.
      on               TimescaleDB verlangen; fehlt es, bricht die Migration
                       mit einer Handlungsanweisung ab.
      off              immer native Partitionierung, auch wenn TimescaleDB
                       vorhanden waere.

    Warum es die Alternative ueberhaupt gibt: TimescaleDB steht unter der
    Timescale License (TSL), nicht unter Apache. Kompression und Continuous
    Aggregates gibt es nur dort. Wer die Lizenz nicht einsetzen darf oder will,
    bekommt mit der nativen Partitionierung dieselbe Tabellenform und dieselben
    Indizes - nur ohne automatische Kompression.
    """
    mode = os.environ.get(TIMESCALE_ENV, "auto").strip().lower()
    if mode not in ("auto", "on", "off"):
        raise RuntimeError(
            f"{TIMESCALE_ENV}={mode!r} ist ungueltig. Erlaubt: auto, on, off."
        )
    if mode == "off":
        return "off"

    available = op.get_bind().execute(
        text("SELECT count(*) FROM pg_available_extensions WHERE name = 'timescaledb'")
    ).scalar_one()

    if available:
        return "on"

    if mode == "on":
        raise RuntimeError(
            "\n"
            + "=" * 78
            + "\nARGUS: TimescaleDB ist verlangt (ARGUS_TIMESCALE=on), aber in diesem\n"
            "PostgreSQL nicht verfuegbar.\n\n"
            "  * Dev-Stack benutzen, dessen Image TimescaleDB mitbringt:\n"
            "        make -C ../.. up\n"
            "  * Oder ohne TimescaleDB migrieren - 'observations' wird dann eine\n"
            "    nativ nach observed_at partitionierte Tabelle, ohne automatische\n"
            "    Kompression:\n"
            "        ARGUS_TIMESCALE=off alembic upgrade head\n"
            + "=" * 78
        )

    sys.stderr.write(
        "ARGUS: TimescaleDB nicht verfuegbar - 'observations' wird nativ nach\n"
        "       observed_at partitioniert (taeglich). Kompression und\n"
        "       Retention laufen ueber argus.observations_maintenance().\n"
    )
    return "off"


def timescale_active() -> bool:
    """Ob die *bestehende* Datenbank Hypertables benutzt.

    Fuer downgrade-Pfade: dort darf nicht neu entschieden werden, sondern es
    zaehlt, was beim upgrade tatsaechlich angelegt wurde.
    """
    return bool(
        op.get_bind()
        .execute(
            text(
                "SELECT count(*) FROM pg_extension WHERE extname = 'timescaledb'"
            )
        )
        .scalar_one()
    )


# ---------------------------------------------------------------------------
# Schutz vor Datenverlust beim Rollback
# ---------------------------------------------------------------------------

DESTRUCTIVE_ENV = "ARGUS_ALLOW_DESTRUCTIVE_DOWNGRADE"


def guard_destructive_downgrade(*tables: str) -> None:
    """Fehlerfall 'Rollback einer Migration mit bereits geschriebenen Daten'.

    Ein downgrade loescht Tabellen. Auf einer leeren Datenbank ist das
    folgenlos, auf einer befuellten ist es Datenverlust. Deshalb: leer -> lauf
    durch, befuellt -> Abbruch mit Nennung der betroffenen Tabellen und
    Zeilenzahlen, es sei denn, der Aufrufer erklaert es ausdruecklich.

    Der Bronze-Layer im Objektspeicher bleibt davon unberuehrt; ein
    versehentlich gedroppter Silver-Bestand ist aus ihm wiederherstellbar -
    aber das dauert Stunden und ist kein Ersatz fuer diese Pruefung.
    """
    if os.environ.get(DESTRUCTIVE_ENV, "").strip() in ("1", "true", "yes"):
        return

    bind = op.get_bind()
    populated: list[tuple[str, int]] = []
    for table in tables:
        schema, _, name = table.partition(".")
        if not name:
            schema, name = "argus", schema
        exists = bind.execute(
            text(
                "SELECT to_regclass(:qualified) IS NOT NULL"
            ),
            {"qualified": f"{schema}.{name}"},
        ).scalar_one()
        if not exists:
            continue
        count = bind.execute(
            text(f'SELECT count(*) FROM "{schema}"."{name}"')  # noqa: S608 - feste Namen
        ).scalar_one()
        if count:
            populated.append((f"{schema}.{name}", count))

    if not populated:
        return

    details = "\n".join(f"    {name}: {count} Zeilen" for name, count in populated)
    raise RuntimeError(
        "\n"
        + "=" * 78
        + "\nARGUS: Dieser Rollback wuerde Tabellen mit Daten loeschen:\n\n"
        f"{details}\n\n"
        "Wenn das beabsichtigt ist, ausdruecklich erlauben:\n"
        f"    {DESTRUCTIVE_ENV}=1 alembic downgrade <ziel>\n\n"
        "Vorher sichern:\n"
        "    pg_dump --format=custom --file=argus-vor-rollback.dump \"$DATABASE_URL\"\n"
        + "=" * 78
    )
