"""Fundament: Erweiterungen, Schema, Aufzaehlungstypen, Hilfsfunktionen.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


# Aufzaehlungstypen spiegeln die Protobuf-Enums aus packages/schemas.
# Die Bezeichner sind kleingeschrieben und ohne Praefix: der Typname
# (argus.entity_type) traegt den Namensraum bereits, das Praefix waere in jeder
# Abfrage Rauschen. Die Abbildung Proto -> SQL ist damit mechanisch:
# ENTITY_TYPE_VESSEL -> 'vessel'.
#
# 'unspecified' ist ueberall der erste Wert und bedeutet - wie im Protobuf -
# "nicht gesetzt". Wo "geprueft, aber unbekannt" gemeint ist, gibt es einen
# eigenen Wert 'unknown'.
ENUMS: dict[str, tuple[str, ...]] = {
    "entity_type": (
        "unspecified",
        "unknown",
        "vessel",
        "aircraft",
        "organization",
        "person",
        "place",
        "port",
        "airport",
        "facility",
        "pipeline",
        "submarine_cable",
        "vehicle",
        "satellite",
        "financial_instrument",
        "commodity",
        "admin_area",
        "maritime_zone",
        "airspace",
        "network_asset",
        "event_series",
    ),
    "resolution_status": (
        "unspecified",
        "pending",
        "unresolved",
        "resolved",
        "ambiguous",
        "conflicted",
        "merged",
    ),
    "identifier_stability": ("unspecified", "stable", "mutable", "ephemeral"),
    "alias_kind": (
        "unspecified",
        "name",
        "former_name",
        "transliteration",
        "translation",
        "abbreviation",
        "callsign",
        "trade_name",
    ),
    "source_reliability": ("unspecified", "a", "b", "c", "d", "e", "f"),
    "information_credibility": ("unspecified", "1", "2", "3", "4", "5", "6"),
    "source_kind": (
        "unspecified",
        "rest_api",
        "stream",
        "feed",
        "batch_file",
        "webhook",
        "sensor",
        "manual",
        "derived",
    ),
    "source_domain": (
        "unspecified",
        "aviation",
        "maritime",
        "news",
        "economic",
        "conflict",
        "disaster",
        "corporate",
        "sanctions",
        "geo",
        "weather",
        "space",
        "cyber",
        "infrastructure",
    ),
    "time_precision": (
        "unspecified",
        "second",
        "minute",
        "hour",
        "day",
        "month",
        "year",
        "unknown",
    ),
    "time_quality": (
        "unspecified",
        "source_provided",
        "source_provided_coarse",
        "inferred_from_ingest",
        "implausible",
        "missing",
    ),
    "geo_precision": (
        "unspecified",
        "exact",
        "building",
        "city",
        "admin1",
        "country",
        "maritime_zone",
        "unknown",
    ),
    "observation_kind": (
        "unspecified",
        "position",
        "status",
        "measurement",
        "static_data",
    ),
    "event_status": (
        "unspecified",
        "rumored",
        "reported",
        "confirmed",
        "disputed",
        "retracted",
        "superseded",
        "scheduled",
    ),
    "entity_role": (
        "unspecified",
        "actor",
        "target",
        "affected",
        "location",
        "mentioned",
        "source",
        "operator",
        "owner",
    ),
    "event_link_type": (
        "unspecified",
        "duplicate_of",
        "part_of",
        "follows",
        "caused_by_hypothesis",
        "contradicts",
        "updates",
        "correlated_with",
    ),
    "report_kind": (
        "unspecified",
        "news_article",
        "agency_wire",
        "press_release",
        "government_notice",
        "regulatory_filing",
        "social_post",
        "blog",
        "situation_report",
        "advisory",
        "dataset_record",
    ),
    "relation_type": (
        "unspecified",
        "owns",
        "beneficial_owner_of",
        "controls",
        "operates",
        "manages",
        "subsidiary_of",
        "parent_of",
        "director_of",
        "employed_by",
        "member_of",
        "registered_in",
        "flagged_in",
        "located_at",
        "docked_at",
        "supplies_to",
        "customer_of",
        "transported_by",
        "sanctioned_by",
        "part_of",
        "connected_to",
        "rendezvous_with",
        "successor_of",
        "associated_with",
        "other",
    ),
    "sanction_status": (
        "unspecified",
        "none",
        "listed",
        "delisted",
        "associated",
        "possible_match",
        "not_checked",
    ),
    "assessment_kind": (
        "unspecified",
        "hypothesis",
        "judgement",
        "forecast",
        "classification",
        "correlation",
        "risk",
        "attribution",
    ),
    "author_type": ("unspecified", "human", "model", "rule", "detector", "external"),
    "confidence_basis": (
        "unspecified",
        "model",
        "rule",
        "human_judgement",
        "statistical",
        "corroboration",
    ),
    "outcome_verdict": (
        "unspecified",
        "confirmed",
        "partially_confirmed",
        "refuted",
        "undecidable",
        "expired",
    ),
    "evidence_kind": (
        "unspecified",
        "report",
        "observation",
        "event",
        "entity",
        "relation",
        "track",
        "detector_hit",
        "external_document",
        "human_statement",
    ),
    "object_kind": (
        "unspecified",
        "observation",
        "event",
        "entity",
        "relation",
        "report",
        "track",
        "assessment",
        "source",
        "aoi",
        "watchlist",
        "alert",
        "case",
    ),
    "alert_severity": ("unspecified", "watch", "notify", "alert", "critical"),
    "alert_status": (
        "unspecified",
        "new",
        "acked",
        "investigating",
        "resolved",
        "false_positive",
        "suppressed",
        "expired",
    ),
    "resolution_disposition": (
        "unspecified",
        "true_positive",
        "false_positive",
        "benign",
        "duplicate",
        "data_quality",
        "undetermined",
    ),
    "aoi_kind": ("unspecified", "polygon", "circle", "corridor", "named_zone", "dynamic"),
    "zone_type": (
        "unspecified",
        "eez",
        "territorial_waters",
        "strait",
        "port_limit",
        "anchorage",
        "fir",
        "restricted_airspace",
        "admin_area",
        "sanction_zone",
        "chokepoint",
    ),
    "match_mode": (
        "unspecified",
        "exact_id",
        "entity",
        "pattern",
        "fuzzy_name",
        "attribute",
    ),
    "case_status": (
        "unspecified",
        "open",
        "investigating",
        "on_hold",
        "closed",
        "archived",
    ),
    "case_priority": ("unspecified", "low", "medium", "high", "urgent"),
    "visibility": ("unspecified", "private", "team", "org", "public"),
    "gap_reason": (
        "unspecified",
        "source_unavailable",
        "rate_limited",
        "no_coverage",
        "signal_loss",
        "filtered",
        "license_restricted",
        "pipeline_failure",
        "unknown",
    ),
}


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Erweiterungen. Sind sie nicht verfuegbar, hat env.py bereits mit einer
    # Handlungsanweisung abgebrochen - hier kann nur noch das Recht fehlen.
    # ------------------------------------------------------------------
    for ext in ("postgis", "vector", "pg_trgm", "btree_gist"):
        op.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}"')

    op.execute("CREATE SCHEMA IF NOT EXISTS argus")
    op.execute(
        "COMMENT ON SCHEMA argus IS "
        "'Silver-Layer: kanonisierte, angereicherte Daten. "
        "Bronze liegt im Objektspeicher, Gold in ClickHouse.'"
    )

    for name, labels in ENUMS.items():
        values = ", ".join(f"'{label}'" for label in labels)
        op.execute(f"CREATE TYPE argus.{name} AS ENUM ({values})")

    # ------------------------------------------------------------------
    # Hilfsfunktionen
    # ------------------------------------------------------------------

    # Volltextkonfiguration je Sprache. Muss IMMUTABLE sein, damit sie in
    # generierten tsvector-Spalten benutzt werden darf. Eine spaetere Aenderung
    # der Zuordnung macht bestehende tsvector-Spalten veraltet; dann ist ein
    # UPDATE der betroffenen Zeilen noetig (siehe docs/adr/0006).
    op.execute(
        """
        CREATE FUNCTION argus.ts_config(lang text) RETURNS regconfig
        LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
            SELECT CASE lower(coalesce(substring(lang from 1 for 2), ''))
                WHEN 'de' THEN 'german'::regconfig
                WHEN 'en' THEN 'english'::regconfig
                WHEN 'fr' THEN 'french'::regconfig
                WHEN 'es' THEN 'spanish'::regconfig
                WHEN 'it' THEN 'italian'::regconfig
                WHEN 'pt' THEN 'portuguese'::regconfig
                WHEN 'nl' THEN 'dutch'::regconfig
                WHEN 'ru' THEN 'russian'::regconfig
                WHEN 'sv' THEN 'swedish'::regconfig
                WHEN 'no' THEN 'norwegian'::regconfig
                WHEN 'da' THEN 'danish'::regconfig
                WHEN 'fi' THEN 'finnish'::regconfig
                WHEN 'tr' THEN 'turkish'::regconfig
                -- 'simple' zerlegt nur, ohne Stammformen. Richtige Wahl fuer
                -- alles, wofuer PostgreSQL kein Woerterbuch hat: besser keine
                -- Stammformbildung als eine falsche.
                ELSE 'simple'::regconfig
            END
        $$
        """
    )
    op.execute(
        "COMMENT ON FUNCTION argus.ts_config(text) IS "
        "'Sprachtag (BCP-47) auf Volltextkonfiguration abbilden. IMMUTABLE, "
        "damit generierte tsvector-Spalten sie benutzen duerfen.'"
    )

    op.execute(
        """
        CREATE FUNCTION argus.set_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at := clock_timestamp();
            RETURN NEW;
        END $$
        """
    )

    # Bitemporale Versionierung (Kapitel 3.4).
    #
    # Vor jedem UPDATE/DELETE wandert die bisherige Fassung in die
    # Verlaufstabelle, mit geschlossenem sys_period. Die aktuelle Zeile bekommt
    # ein neu geoeffnetes Intervall. So entsteht eine lueckenlose Kette:
    # zu jedem Zeitpunkt T gibt es genau eine Fassung mit sys_period @> T.
    #
    # clock_timestamp() statt transaction_timestamp(): mehrere Aenderungen
    # innerhalb einer Transaktion bleiben so unterscheidbar und erzeugen keine
    # leeren Intervalle. Preis: die Transaktionszeit ist die Anweisungszeit,
    # nicht der Commit-Zeitpunkt.
    op.execute(
        """
        CREATE FUNCTION argus.versioning_trigger() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            history_table text := TG_ARGV[0];
            now_ts timestamptz := clock_timestamp();
        BEGIN
            IF TG_ARGV[0] IS NULL THEN
                RAISE EXCEPTION
                    'argus.versioning_trigger benoetigt die Verlaufstabelle als Argument';
            END IF;

            OLD.sys_period := tstzrange(lower(OLD.sys_period), now_ts, '[)');
            EXECUTE format('INSERT INTO %s SELECT ($1).*', history_table) USING OLD;

            IF TG_OP = 'UPDATE' THEN
                NEW.sys_period := tstzrange(now_ts, NULL, '[)');
                RETURN NEW;
            END IF;
            RETURN OLD;
        END $$
        """
    )
    op.execute(
        "COMMENT ON FUNCTION argus.versioning_trigger() IS "
        "'Bitemporale Versionierung: schreibt die abgeloeste Fassung in die als "
        "Argument genannte Verlaufstabelle und oeffnet fuer die neue Fassung ein "
        "neues sys_period-Intervall.'"
    )

    # Identitaet des aufrufenden Nutzers fuer Row-Level Security. Die Anwendung
    # setzt sie pro Verbindung: SET LOCAL argus.user_id = '01HZ...'.
    op.execute(
        """
        CREATE FUNCTION argus.current_user_id() RETURNS text
        LANGUAGE sql STABLE AS $$
            SELECT nullif(current_setting('argus.user_id', true), '')
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION argus.current_user_teams() RETURNS text[]
        LANGUAGE sql STABLE AS $$
            SELECT coalesce(
                string_to_array(nullif(current_setting('argus.teams', true), ''), ','),
                ARRAY[]::text[]
            )
        $$
        """
    )


def downgrade() -> None:
    for fn in (
        "argus.current_user_teams()",
        "argus.current_user_id()",
        "argus.versioning_trigger()",
        "argus.set_updated_at()",
        "argus.ts_config(text)",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}")

    for name in reversed(list(ENUMS)):
        op.execute(f"DROP TYPE IF EXISTS argus.{name}")

    # Das Schema wird nur entfernt, wenn es leer ist: ein CASCADE wuerde
    # Objekte mitnehmen, die nicht aus diesen Migrationen stammen.
    op.execute("DROP SCHEMA IF EXISTS argus RESTRICT")

    # Erweiterungen bleiben bestehen. Sie koennen von anderen Datenbanken oder
    # Schemata benutzt werden, und ihr Anlegen ist ohnehin idempotent.
