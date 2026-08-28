"""Alembic-Laufzeitumgebung fuer ARGUS.

Besonderheiten gegenueber dem Standardgeruest:

* Die Verbindung kommt aus DATABASE_URL, nicht aus alembic.ini.
* Vor jeder Migration wird geprueft, ob die Pflicht-Erweiterungen vorhanden
  sind - sonst bricht die Migration mit einer verstaendlichen Meldung ab statt
  mit einem Syntaxfehler tief im DDL.
* Migrationen laufen in einer Transaktion; PostgreSQL kann DDL
  transaktional, also ist eine fehlgeschlagene Migration folgenlos.
* Ein Schutz gegen versehentliche Migration auf eine nicht-leere, fremde
  Datenbank.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool, text

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Kein SQLAlchemy-Metadata: das Schema wird als versioniertes DDL gepflegt,
# nicht aus ORM-Modellen abgeleitet. Autogenerate ist damit bewusst aus -
# es wuerde PostGIS-Typen, Hypertables und Trigger nicht korrekt abbilden.
target_metadata = None

DEFAULT_URL = "postgresql+psycopg://argus:argus@localhost:5432/argus"

# Erweiterungen, ohne die das Schema nicht angelegt werden kann.
REQUIRED_EXTENSIONS = ("postgis", "vector", "pg_trgm", "btree_gist")


def get_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        sys.stderr.write(
            f"\nDATABASE_URL ist nicht gesetzt.\nBeispiel: export DATABASE_URL='{DEFAULT_URL}'\n\n"
        )
        raise SystemExit(2)
    # psycopg3 ist der Treiber; eine alte psycopg2-URL wird still korrigiert.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def check_extensions(connection) -> None:
    """Fehlerfall 'fehlende Extension' - mit Handlungsanweisung statt Stacktrace."""
    installed = {
        row[0] for row in connection.execute(text("SELECT extname FROM pg_extension")).fetchall()
    }
    available = {
        row[0]
        for row in connection.execute(text("SELECT name FROM pg_available_extensions")).fetchall()
    }
    missing = [e for e in REQUIRED_EXTENSIONS if e not in installed]
    if not missing:
        return

    not_installable = [e for e in missing if e not in available]
    lines = [
        "",
        "=" * 78,
        f"ARGUS: Pflicht-Erweiterungen fehlen: {', '.join(missing)}",
        "",
    ]
    if not_installable:
        lines += [
            f"Nicht einmal verfuegbar: {', '.join(not_installable)}.",
            "Das Postgres-Image bringt sie nicht mit. Der Dev-Stack aus",
            "infra/compose verwendet ein Image, das PostGIS, pgvector und",
            "pg_trgm enthaelt:",
            "    make -C ../.. up",
            "",
            "Verfuegbare Erweiterungen anzeigen:",
            "    SELECT name FROM pg_available_extensions ORDER BY name;",
        ]
    else:
        lines += [
            "Sie sind verfuegbar, aber nicht aktiviert. Migration 0001 legt sie",
            "an; dafuer braucht die Rolle CREATE-Recht auf der Datenbank:",
            f"    CREATE EXTENSION IF NOT EXISTS {missing[0]};",
        ]
    lines += ["=" * 78, ""]
    sys.stderr.write("\n".join(lines))
    raise SystemExit(3)


def guard_foreign_database(connection) -> None:
    """Fehlerfall 'Migration auf nicht-leerer Datenbank'.

    Ein bestehendes argus-Schema ohne Alembic-Versionstabelle bedeutet: hier hat
    jemand anders schon gearbeitet. Weitermachen wuerde fremde Objekte
    ueberschreiben.
    """
    if context.get_x_argument(as_dictionary=True).get("force_existing") == "1":
        return
    row = connection.execute(
        text(
            """
            SELECT
              (SELECT count(*) FROM information_schema.tables
                 WHERE table_schema = 'argus') AS argus_tables,
              (SELECT count(*) FROM information_schema.tables
                 WHERE table_schema = 'public' AND table_name = 'alembic_version')
                AS version_table
            """
        )
    ).one()
    if row.argus_tables > 0 and row.version_table == 0:
        sys.stderr.write(
            "\n" + "=" * 78 + "\nARGUS: Das Schema 'argus' enthaelt bereits "
            f"{row.argus_tables} Tabellen, aber es gibt keine\n"
            "alembic_version-Tabelle. Diese Datenbank wurde nicht von Alembic\n"
            "angelegt.\n\n"
            "Moegliche Ursachen und Auswege:\n"
            "  * Schema von Hand oder aus packages/schemas/sql/ eingespielt.\n"
            "    Dann den passenden Stand markieren, statt neu zu migrieren:\n"
            "        alembic stamp head\n"
            "  * Falsche Datenbank in DATABASE_URL.\n"
            "  * Absicht (Testumgebung): erzwingen mit\n"
            "        alembic -x force_existing=1 upgrade head\n" + "=" * 78 + "\n\n"
        )
        raise SystemExit(4)


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_url(), poolclass=pool.NullPool, future=True)

    # Die Vorabpruefungen laufen auf einer EIGENEN Verbindung.
    #
    # Warum das wichtig ist: alembic.context.begin_transaction() prueft, ob auf
    # der Verbindung bereits eine Transaktion laeuft. Ist das der Fall - und
    # eine einzige SELECT-Abfrage genuegt dafuer -, gibt es einen No-Op-Kontext
    # zurueck und ueberlaesst das Commit dem Aufrufer. Wer das uebersieht,
    # bekommt Migrationen, die erfolgreich aussehen und beim
    # Verbindungsabbau stillschweigend zurueckgerollt werden.
    with engine.connect() as precheck:
        check_extensions(precheck)
        guard_foreign_database(precheck)

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # Sperrt parallele Migrationslaeufe gegeneinander aus.
            transaction_per_migration=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
