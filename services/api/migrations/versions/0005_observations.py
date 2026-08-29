"""Beobachtungen: Hypertable (TimescaleDB) oder nativ partitioniert.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from alembic import op

from argus_migrations import guard_destructive_downgrade, timescale_active, timescale_mode

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


# Spalten der Beobachtungstabelle. Als Zeichenkette, weil sich nur die
# Partitionierungsklausel zwischen den beiden Varianten unterscheidet.
COLUMNS = """
    obs_id          text NOT NULL,
    schema_version  text NOT NULL,

    -- Beobachtete Entitaet. entity_id ist NULL, solange nicht aufgeloest;
    -- ref_type/ref_id tragen dann weiterhin die Rohaussage der Quelle
    -- ('mmsi:211234560'), damit nachtraegliche Aufloesung moeglich bleibt.
    entity_id       text,
    ref_type        argus.entity_type NOT NULL,
    ref_id          text NOT NULL,
    resolution_status argus.resolution_status NOT NULL DEFAULT 'pending',

    kind            argus.observation_kind NOT NULL DEFAULT 'position',

    -- Wirksame Valid Time und zugleich Partitionsschluessel. NOT NULL, weil
    -- ein Partitionsschluessel nicht NULL sein darf. Das Protobuf-Feld ist
    -- optional; fehlt es, setzt die Pipeline hier ingested_at ein UND
    -- time_quality auf 'inferred_from_ingest'. Die Unterscheidung geht damit
    -- nicht verloren, sie wandert nur in eine eigene Spalte (siehe ADR 0006).
    observed_at     timestamptz NOT NULL,
    time_quality    argus.time_quality NOT NULL DEFAULT 'source_provided',
    ingested_at     timestamptz NOT NULL DEFAULT clock_timestamp(),

    source_id       text NOT NULL,
    raw_ref         text,

    -- Position. NULL bei Beobachtungen ohne Ortsbezug (Zeitreihenwerte).
    geo             geography(Point, 4326),
    geo_precision   argus.geo_precision NOT NULL DEFAULT 'unspecified',
    h3_r5           bigint,
    h3_r7           bigint,
    h3_r9           bigint,

    -- Qualitaet. Jede nicht gemessene Position ist hier gekennzeichnet.
    position_accuracy_m    double precision CHECK (position_accuracy_m IS NULL OR position_accuracy_m >= 0),
    is_interpolated        boolean NOT NULL DEFAULT false,
    is_dead_reckoned       boolean NOT NULL DEFAULT false,
    uncertainty_radius_m   double precision CHECK (uncertainty_radius_m IS NULL OR uncertainty_radius_m >= 0),
    is_suspected_spoof     boolean NOT NULL DEFAULT false,
    seconds_since_previous double precision,
    quality_flags          text[] NOT NULL DEFAULT '{}',

    -- Bewegungsgroessen. Alle NULL-faehig: 0 Grad ist ein gueltiger Kurs,
    -- "nicht gemeldet" ist etwas anderes als 0.
    sog_kn          double precision,
    cog_deg         double precision CHECK (cog_deg IS NULL OR (cog_deg >= 0 AND cog_deg < 360)),
    heading_deg     double precision CHECK (heading_deg IS NULL OR (heading_deg >= 0 AND heading_deg < 360)),
    track_deg       double precision CHECK (track_deg IS NULL OR (track_deg >= 0 AND track_deg < 360)),
    draft_m         double precision CHECK (draft_m IS NULL OR draft_m >= 0),
    altitude_m      double precision,
    altitude_baro_m double precision,
    vertical_rate_ms double precision,
    rate_of_turn_deg_min double precision,
    ground_speed_kn double precision,
    true_airspeed_kn double precision,

    -- Zeitreihenwert (FRED, Kurse, Sensoren). Revisionen ueberschreiben
    -- historische Werte nicht, sondern erzeugen eine neue Beobachtung mit
    -- hoeherer revision.
    metric          text,
    metric_value    double precision,
    metric_unit     text,
    metric_revision integer CHECK (metric_revision IS NULL OR metric_revision >= 0),
    metric_previous_value double precision,
    metric_is_preliminary boolean NOT NULL DEFAULT false,
    metric_period   tstzrange,

    -- Nur quellspezifische Zusatzfelder ohne eigene Spalte: nav_status,
    -- destination, squawk, callsign.
    attributes      jsonb NOT NULL DEFAULT '{}'::jsonb,

    dedupe_key      text NOT NULL,
    track_id        text,

    CONSTRAINT observations_pkey PRIMARY KEY (obs_id, observed_at),

    -- Fehlt der Quellzeitstempel, muss die Qualitaet das sagen. Verhindert,
    -- dass ein eingesetzter Ersatzwert wie eine echte Messung aussieht.
    CONSTRAINT observations_time_quality_consistent
        CHECK (time_quality <> 'inferred_from_ingest' OR observed_at = ingested_at),

    -- Eine Position, die nicht gemessen wurde, braucht eine Unsicherheit.
    CONSTRAINT observations_dr_needs_uncertainty
        CHECK (NOT is_dead_reckoned OR uncertainty_radius_m IS NOT NULL),

    CONSTRAINT observations_measurement_complete
        CHECK (kind <> 'measurement' OR (metric IS NOT NULL AND metric_value IS NOT NULL)),

    CONSTRAINT observations_position_has_geo
        CHECK (kind <> 'position' OR geo IS NOT NULL)
"""


def upgrade() -> None:
    mode = timescale_mode()

    if mode == "on":
        op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
        op.execute(f"CREATE TABLE argus.observations (\n{COLUMNS}\n)")
    else:
        # Native Bereichspartitionierung nach observed_at, taegliche
        # Partitionen - dieselbe Tabellenform und dieselben Indizes wie bei
        # TimescaleDB, nur ohne automatische Kompression.
        op.execute(
            f"CREATE TABLE argus.observations (\n{COLUMNS}\n) PARTITION BY RANGE (observed_at)"
        )

    op.execute(
        "COMMENT ON TABLE argus.observations IS "
        "'Beobachtungen: die haeufigste Nachricht im System. Partitioniert nach "
        "observed_at mit Tagesintervall. Rohpositionen bleiben 90 Tage "
        "detailliert erhalten (Kapitel 14).'"
    )
    op.execute(
        "COMMENT ON COLUMN argus.observations.observed_at IS "
        "'Wirksame Valid Time und Partitionsschluessel. Bei fehlendem "
        "Quellzeitstempel gleich ingested_at; time_quality haelt das fest.'"
    )

    # Fremdschluessel mit ausdruecklichem Verhalten. SET NULL statt CASCADE:
    # eine zusammengefuehrte oder geloeschte Entitaet darf keine Beobachtungen
    # vernichten - die Rohaussage in ref_id bleibt bestehen und ist erneut
    # aufloesbar.
    op.execute(
        "ALTER TABLE argus.observations ADD CONSTRAINT observations_entity_fk "
        "FOREIGN KEY (entity_id) REFERENCES argus.entities (entity_id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE argus.observations ADD CONSTRAINT observations_source_fk "
        "FOREIGN KEY (source_id) REFERENCES argus.sources (source_id) ON DELETE RESTRICT"
    )

    if mode == "on":
        op.execute(
            "SELECT create_hypertable('argus.observations', 'observed_at', "
            "chunk_time_interval => INTERVAL '1 day', migrate_data => false)"
        )
    else:
        op.execute(
            """
            CREATE FUNCTION argus.ensure_observation_partitions(
                p_from date DEFAULT (current_date - 1),
                p_to   date DEFAULT (current_date + 7)
            ) RETURNS integer LANGUAGE plpgsql AS $$
            DECLARE
                d date := p_from;
                created integer := 0;
                part_name text;
            BEGIN
                WHILE d <= p_to LOOP
                    part_name := format('observations_%s', to_char(d, 'YYYYMMDD'));
                    IF to_regclass('argus.' || part_name) IS NULL THEN
                        EXECUTE format(
                            'CREATE TABLE argus.%I PARTITION OF argus.observations '
                            'FOR VALUES FROM (%L) TO (%L)',
                            part_name, d::timestamptz, (d + 1)::timestamptz
                        );
                        created := created + 1;
                    END IF;
                    d := d + 1;
                END LOOP;
                RETURN created;
            END $$
            """
        )
        op.execute(
            "COMMENT ON FUNCTION argus.ensure_observation_partitions(date, date) IS "
            "'Legt taegliche Partitionen fuer den angegebenen Zeitraum an. "
            "Idempotent. Gehoert in einen taeglichen Wartungslauf.'"
        )
        # Auffangpartition: eine Beobachtung mit unerwartetem Zeitstempel
        # landet hier, statt die Aufnahme scheitern zu lassen. Der
        # Wartungslauf meldet, wenn sie nicht leer ist - dort zu liegen ist
        # ein Datenqualitaetsvorfall, kein Normalzustand.
        op.execute(
            "CREATE TABLE argus.observations_default PARTITION OF argus.observations DEFAULT"
        )
        op.execute(
            "COMMENT ON TABLE argus.observations_default IS "
            "'Auffangpartition fuer Zeitstempel ausserhalb der angelegten "
            "Tagespartitionen. Nicht leer = Datenqualitaetsvorfall.'"
        )
        op.execute(
            "SELECT argus.ensure_observation_partitions(current_date - 3, current_date + 14)"
        )

    # --- Indizes ------------------------------------------------------
    # Die zentrale Abfrage der Track-Engine: "alle Beobachtungen einer Entitaet
    # der letzten 24 Stunden". entity_id zuerst, observed_at absteigend.
    op.execute(
        "CREATE INDEX observations_entity_time_idx "
        "ON argus.observations (entity_id, observed_at DESC)"
    )
    # Dieselbe Abfrage fuer noch nicht aufgeloeste Verweise.
    op.execute(
        "CREATE INDEX observations_ref_time_idx ON argus.observations (ref_id, observed_at DESC)"
    )
    op.execute(
        "CREATE INDEX observations_track_time_idx "
        "ON argus.observations (track_id, observed_at DESC) WHERE track_id IS NOT NULL"
    )
    # Viewport-Abfragen: H3-Bucket ist ein Ganzzahlvergleich und schlaegt jede
    # Geometrieoperation, solange die Aufloesung passt.
    op.execute(
        "CREATE INDEX observations_h3_r7_time_idx "
        "ON argus.observations (h3_r7, observed_at DESC) WHERE h3_r7 IS NOT NULL"
    )
    # Exakte Geometrie fuer AOI-Polygone und Entfernungsabfragen.
    op.execute(
        "CREATE INDEX observations_geo_idx ON argus.observations USING gist (geo) "
        "WHERE geo IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX observations_source_time_idx "
        "ON argus.observations (source_id, ingested_at DESC)"
    )
    op.execute(
        "CREATE INDEX observations_metric_time_idx "
        "ON argus.observations (metric, observed_at DESC) WHERE metric IS NOT NULL"
    )
    # Idempotenz der Konnektoren. Der Partitionsschluessel muss Teil jedes
    # Unique-Index einer partitionierten Tabelle sein; dedupe_key enthaelt
    # ohnehin den Zeitbezug.
    op.execute(
        "CREATE UNIQUE INDEX observations_dedupe_idx "
        "ON argus.observations (dedupe_key, observed_at)"
    )

    # --- Kompression und Aufbewahrung ---------------------------------
    if mode == "on":
        op.execute(
            """
            ALTER TABLE argus.observations SET (
                timescaledb.compress,
                timescaledb.compress_segmentby = 'entity_id',
                timescaledb.compress_orderby = 'observed_at DESC'
            )
            """
        )
        op.execute("SELECT add_compression_policy('argus.observations', INTERVAL '7 days')")
        # Kapitel 14: Rohtracks 90 Tage detailliert, danach nur aggregiert.
        # Die Aggregate liegen in ClickHouse und sind nicht Teil dieser
        # Migration.
        op.execute("SELECT add_retention_policy('argus.observations', INTERVAL '90 days')")
    else:
        op.execute(
            """
            CREATE FUNCTION argus.drop_observation_partitions_older_than(
                p_age interval DEFAULT INTERVAL '90 days'
            ) RETURNS TABLE (dropped_partition text) LANGUAGE plpgsql AS $$
            DECLARE
                cutoff date := (current_date - p_age)::date;
                rec record;
            BEGIN
                FOR rec IN
                    SELECT c.relname
                      FROM pg_class c
                      JOIN pg_namespace n ON n.oid = c.relnamespace
                     WHERE n.nspname = 'argus'
                       AND c.relname ~ '^observations_[0-9]{8}$'
                       AND to_date(right(c.relname, 8), 'YYYYMMDD') < cutoff
                LOOP
                    EXECUTE format('DROP TABLE argus.%I', rec.relname);
                    dropped_partition := rec.relname;
                    RETURN NEXT;
                END LOOP;
            END $$
            """
        )
        op.execute(
            """
            CREATE FUNCTION argus.observations_maintenance()
            RETURNS TABLE (action text, detail text) LANGUAGE plpgsql AS $$
            DECLARE
                created integer;
                stray bigint;
            BEGIN
                created := argus.ensure_observation_partitions();
                action := 'partitions_created';
                detail := created::text;
                RETURN NEXT;

                FOR detail IN
                    SELECT dropped_partition
                      FROM argus.drop_observation_partitions_older_than()
                LOOP
                    action := 'partition_dropped';
                    RETURN NEXT;
                END LOOP;

                SELECT count(*) INTO stray FROM argus.observations_default;
                IF stray > 0 THEN
                    action := 'WARNUNG_auffangpartition_nicht_leer';
                    detail := format(
                        '%s Zeilen in argus.observations_default - Zeitstempel '
                        'ausserhalb der angelegten Partitionen pruefen', stray);
                    RETURN NEXT;
                END IF;
            END $$
            """
        )
        op.execute(
            "COMMENT ON FUNCTION argus.observations_maintenance() IS "
            "'Taeglicher Wartungslauf ohne TimescaleDB: Partitionen anlegen, "
            "alte loeschen, Auffangpartition pruefen. Ersetzt die "
            "Timescale-Policies; Kompression gibt es hier nicht.'"
        )


def downgrade() -> None:
    guard_destructive_downgrade("observations")
    if timescale_active():
        # Policies haengen an der Hypertable und verschwinden mit ihr; das
        # ausdrueckliche Entfernen macht den Rollback auch dann sauber, wenn
        # jemand die Tabelle inzwischen umgebaut hat.
        op.execute("SELECT remove_retention_policy('argus.observations', if_exists => true)")
        op.execute("SELECT remove_compression_policy('argus.observations', if_exists => true)")
    else:
        op.execute("DROP FUNCTION IF EXISTS argus.observations_maintenance()")
        op.execute("DROP FUNCTION IF EXISTS argus.drop_observation_partitions_older_than(interval)")
        op.execute("DROP FUNCTION IF EXISTS argus.ensure_observation_partitions(date, date)")
    # Partitionen und Chunks gehen mit der Tabelle.
    op.execute("DROP TABLE IF EXISTS argus.observations")
