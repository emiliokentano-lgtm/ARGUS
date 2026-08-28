#!/usr/bin/env python3
"""Erzeugt einen synthetischen Beobachtungsbestand und misst die Ladezeit.

Dient zwei Zwecken:

* Abnahmekriterium: 1 Mio. Beobachtungen muessen in unter 90 Sekunden geladen
  sein - mit allen Indizes und Fremdschluesseln aktiv, so wie im Betrieb.
* Grundlage fuer die Abfrageplaene: ohne realistische Zeilenzahl und ohne
  ANALYZE entscheidet der Planer anders als in der Wirklichkeit.

Aufruf:
    DATABASE_URL=... python scripts/load_testdata.py --observations 1000000
"""

from __future__ import annotations

import argparse
import io
import math
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone

import psycopg

SCHEMA_VERSION = "1.0.0"
SOURCE_ID = "loadtest"

# Kurs von Fudschaira durch die Strasse von Hormus - realistische Koordinaten
# ergeben realistische Geo-Indexselektivitaet.
LON_MIN, LON_MAX = 54.5, 58.5
LAT_MIN, LAT_MAX = 24.0, 27.5


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://"))


def seed_reference_data(conn: psycopg.Connection, entity_count: int) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO argus.sources (source_id, schema_version, name, kind, license_id,
                                       reliability)
            VALUES (%s, %s, 'Lasttest-Generator', 'derived', 'internal-test', 'f')
            ON CONFLICT (source_id) DO NOTHING
            """,
            (SOURCE_ID, SCHEMA_VERSION),
        )
        entity_ids = [f"01LOADTEST{i:016d}" for i in range(entity_count)]
        with cur.copy(
            "COPY argus.entities (entity_id, schema_version, type, display_name, source_id) "
            "FROM STDIN"
        ) as copy:
            for i, eid in enumerate(entity_ids):
                copy.write_row((eid, SCHEMA_VERSION, "vessel", f"Testschiff {i}", SOURCE_ID))
        # Alias-Bezeichner: ohne sie waere die Entity Resolution im Test
        # unrealistisch schlank.
        with cur.copy(
            "COPY argus.entity_aliases (entity_id, id_type, id_value, stability) FROM STDIN"
        ) as copy:
            for i, eid in enumerate(entity_ids):
                copy.write_row((eid, "imo", f"9{i:06d}", "stable"))
    conn.commit()
    return entity_ids


def generate_rows(entity_ids: list[str], count: int, hours: int, rng: random.Random):
    """Erzeugt Zeilen als Text-Tupel fuer COPY.

    Die Beobachtungen verteilen sich gleichmaessig ueber die letzten `hours`
    Stunden und ueber die Entitaeten, damit sowohl die Zeit- als auch die
    Entitaetsselektivitaet realistisch sind.
    """
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now - timedelta(hours=hours)
    span = (now - start).total_seconds()
    n_entities = len(entity_ids)

    for i in range(count):
        entity_id = entity_ids[i % n_entities]
        offset = span * (i / count) + rng.uniform(0, span / count)
        ts = start + timedelta(seconds=offset)
        lon = rng.uniform(LON_MIN, LON_MAX)
        lat = rng.uniform(LAT_MIN, LAT_MAX)
        # H3-Indizes werden im Betrieb von der Pipeline berechnet. Hier genuegt
        # ein deterministischer Ersatz mit vergleichbarer Kardinalitaet, damit
        # der Planer realistische Statistiken bekommt.
        h3_r7 = int(abs(hash((round(lon, 2), round(lat, 2)))) % (2**52))
        yield (
            f"01OBS{i:021d}",
            SCHEMA_VERSION,
            entity_id,
            "vessel",
            f"imo:9{i % n_entities:06d}",
            "resolved",
            "position",
            ts.isoformat(),
            "source_provided",
            ts.isoformat(),
            SOURCE_ID,
            f"SRID=4326;POINT({lon:.5f} {lat:.5f})",
            "exact",
            h3_r7,
            f"{rng.uniform(0, 22):.1f}",
            f"{rng.uniform(0, 359.9):.1f}",
            f"loadtest:{i}",
        )


def load(conn: psycopg.Connection, entity_ids: list[str], count: int, hours: int) -> float:
    rng = random.Random(20260828)
    columns = (
        "obs_id, schema_version, entity_id, ref_type, ref_id, resolution_status, kind, "
        "observed_at, time_quality, ingested_at, source_id, geo, geo_precision, h3_r7, "
        "sog_kn, cog_deg, dedupe_key"
    )
    started = time.perf_counter()
    with conn.cursor() as cur:
        with cur.copy(f"COPY argus.observations ({columns}) FROM STDIN") as copy:
            for row in generate_rows(entity_ids, count, hours, rng):
                copy.write_row(row)
    conn.commit()
    return time.perf_counter() - started


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--observations", type=int, default=1_000_000)
    ap.add_argument("--entities", type=int, default=5_000)
    ap.add_argument("--hours", type=int, default=72,
                    help="Zeitraum, ueber den die Beobachtungen verteilt werden")
    ap.add_argument("--budget-seconds", type=float, default=90.0)
    ap.add_argument("--no-analyze", action="store_true")
    args = ap.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL fehlt.", file=sys.stderr)
        return 2

    with connect(url) as conn:
        print(f"Lege {args.entities} Entitaeten an ...")
        entity_ids = seed_reference_data(conn, args.entities)

        print(f"Lade {args.observations:,} Beobachtungen ueber {args.hours} h ...".replace(",", "."))
        elapsed = load(conn, entity_ids, args.observations, args.hours)
        rate = args.observations / elapsed

        if not args.no_analyze:
            t0 = time.perf_counter()
            with conn.cursor() as cur:
                cur.execute("ANALYZE argus.observations")
            conn.commit()
            print(f"ANALYZE: {time.perf_counter() - t0:.1f} s")

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM argus.observations")
            total = cur.fetchone()[0]
            # Bei einer partitionierten Tabelle liefert pg_total_relation_size
            # auf der Elterntabelle 0 - die Groesse steckt in den Partitionen.
            cur.execute(
                """
                SELECT pg_size_pretty(coalesce(sum(pg_total_relation_size(c.oid)), 0)
                                      + pg_total_relation_size('argus.observations'))
                  FROM pg_class c
                  JOIN pg_inherits i ON i.inhrelid = c.oid
                 WHERE i.inhparent = 'argus.observations'::regclass
                """
            )
            size = cur.fetchone()[0]

    print()
    print(f"  Ladezeit          {elapsed:.1f} s")
    print(f"  Durchsatz         {rate:,.0f} Zeilen/s".replace(",", "."))
    print(f"  Zeilen gesamt     {total:,}".replace(",", "."))
    print(f"  Groesse (inkl. Indizes)  {size}")
    print(f"  Budget            {args.budget_seconds:.0f} s")

    if elapsed > args.budget_seconds:
        print(f"\nBudget ueberschritten ({elapsed:.1f} s > {args.budget_seconds:.0f} s).")
        return 1
    print(f"\nBudget eingehalten ({elapsed:.1f} s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
