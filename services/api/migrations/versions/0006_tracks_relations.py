"""Bewegungsspuren und Beziehungsgraph.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from alembic import op

from argus_migrations import guard_destructive_downgrade

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # tracks — Kopfdaten. Die Punkte liegen in argus.observations; eine
    # zweite Kopie waere eine zweite Wahrheit.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE argus.tracks (
            track_id        text PRIMARY KEY,
            schema_version  text NOT NULL,
            entity_id       text REFERENCES argus.entities (entity_id) ON DELETE SET NULL,
            ref_type        argus.entity_type NOT NULL,
            ref_id          text NOT NULL,

            time_start      timestamptz NOT NULL,
            time_end        timestamptz,
            is_open         boolean NOT NULL DEFAULT true,
            last_point_at   timestamptz,
            point_count     integer NOT NULL DEFAULT 0 CHECK (point_count >= 0),
            distance_m      double precision CHECK (distance_m IS NULL OR distance_m >= 0),

            -- Huellrechteck fuer Viewport-Vorfilterung.
            bbox            geography(Polygon, 4326),
            -- Vereinfachte Linien je Zoomstufe. Vorab materialisiert, damit
            -- nie 50.000 Punkte an den Browser gehen (Kapitel 8.1).
            simplified_geom geography(LineString, 4326),
            simplify_tolerance_m double precision,

            source_ids      text[] NOT NULL DEFAULT '{}',
            attributes      jsonb NOT NULL DEFAULT '{}'::jsonb,
            ingested_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
            updated_at      timestamptz NOT NULL DEFAULT clock_timestamp(),

            CONSTRAINT tracks_time_order CHECK (time_end IS NULL OR time_end >= time_start),
            CONSTRAINT tracks_open_has_no_end CHECK (NOT is_open OR time_end IS NULL)
        )
        """
    )
    op.execute("CREATE INDEX tracks_entity_time_idx ON argus.tracks (entity_id, time_start DESC)")
    op.execute("CREATE INDEX tracks_open_idx ON argus.tracks (last_point_at DESC) WHERE is_open")
    op.execute("CREATE INDEX tracks_bbox_idx ON argus.tracks USING gist (bbox) WHERE bbox IS NOT NULL")
    op.execute(
        "CREATE TRIGGER tracks_set_updated_at BEFORE UPDATE ON argus.tracks "
        "FOR EACH ROW EXECUTE FUNCTION argus.set_updated_at()"
    )

    # Luecken werden als eigene Zeilen gefuehrt, damit sie darstellbar und
    # auswertbar sind - statt durch eine gerade Linie zwischen zwei weit
    # entfernten Punkten kaschiert zu werden (Prinzip 4).
    op.execute(
        """
        CREATE TABLE argus.track_gaps (
            gap_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            track_id     text NOT NULL REFERENCES argus.tracks (track_id) ON DELETE CASCADE,
            gap_start    timestamptz NOT NULL,
            gap_end      timestamptz,
            reason       argus.gap_reason NOT NULL DEFAULT 'unspecified',
            duration_s   double precision NOT NULL CHECK (duration_s >= 0),
            distance_m   double precision CHECK (distance_m IS NULL OR distance_m >= 0),
            is_flagged   boolean NOT NULL DEFAULT false,
            detail       text,
            -- Prognosekorridor nach Signalverlust: eine wachsende Flaeche,
            -- nie ein Punkt (Kapitel 8.1).
            uncertainty_area geography(Polygon, 4326),
            containment_probability double precision
                CHECK (containment_probability IS NULL
                       OR (containment_probability > 0 AND containment_probability <= 1)),
            CONSTRAINT track_gaps_time_order CHECK (gap_end IS NULL OR gap_end >= gap_start)
        )
        """
    )
    op.execute("CREATE INDEX track_gaps_track_idx ON argus.track_gaps (track_id, gap_start DESC)")
    op.execute("CREATE INDEX track_gaps_flagged_idx ON argus.track_gaps (gap_start DESC) WHERE is_flagged")

    op.execute(
        "ALTER TABLE argus.observations ADD CONSTRAINT observations_track_fk "
        "FOREIGN KEY (track_id) REFERENCES argus.tracks (track_id) ON DELETE SET NULL"
    )

    # ------------------------------------------------------------------
    # relations — zeitlich begrenzte, gerichtete Kanten
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE argus.relations (
            relation_id     text PRIMARY KEY,
            schema_version  text NOT NULL,
            relation_type   argus.relation_type NOT NULL,
            -- Nur bei relation_type = 'other': quellnatives Label, damit die
            -- Information nicht verloren geht, bevor der Typ ins Enum kommt.
            type_label      text,

            from_entity_id  text REFERENCES argus.entities (entity_id) ON DELETE CASCADE,
            from_ref_type   argus.entity_type NOT NULL,
            from_ref_id     text NOT NULL,
            to_entity_id    text REFERENCES argus.entities (entity_id) ON DELETE CASCADE,
            to_ref_type     argus.entity_type NOT NULL,
            to_ref_id       text NOT NULL,

            -- Ohne Gueltigkeitszeitraum ist "wer gehoerte 2023 zu wem" nicht
            -- beantwortbar. Offenes Ende = laufende Beziehung.
            validity        tstzrange NOT NULL DEFAULT tstzrange(NULL, NULL, '[)'),

            weight          double precision,
            weight_unit     text,
            confidence      double precision NOT NULL DEFAULT 0.5
                CHECK (confidence >= 0 AND confidence <= 1),
            confidence_basis argus.confidence_basis NOT NULL DEFAULT 'unspecified',
            directed        boolean NOT NULL DEFAULT true,

            evidence        jsonb NOT NULL DEFAULT '[]'::jsonb,
            attributes      jsonb NOT NULL DEFAULT '{}'::jsonb,

            retracted_at    timestamptz,
            retraction_reason text,

            dedupe_key      text,
            source_id       text REFERENCES argus.sources (source_id) ON DELETE SET NULL,
            raw_ref         text,
            observed_at     timestamptz,
            ingested_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
            version         integer NOT NULL DEFAULT 1,
            sys_period      tstzrange NOT NULL DEFAULT tstzrange(clock_timestamp(), NULL, '[)'),

            CONSTRAINT relations_other_needs_label
                CHECK (relation_type <> 'other' OR type_label IS NOT NULL),
            CONSTRAINT relations_not_self
                CHECK (from_ref_id <> to_ref_id OR relation_type = 'associated_with'),
            CONSTRAINT relations_evidence_is_array
                CHECK (jsonb_typeof(evidence) = 'array')
        )
        """
    )
    op.execute("CREATE TABLE argus.relations_history (LIKE argus.relations)")
    op.execute(
        "CREATE TRIGGER relations_versioning BEFORE UPDATE OR DELETE ON argus.relations "
        "FOR EACH ROW EXECUTE FUNCTION argus.versioning_trigger('argus.relations_history')"
    )

    op.execute("CREATE INDEX relations_from_idx ON argus.relations (from_entity_id, relation_type)")
    op.execute("CREATE INDEX relations_to_idx ON argus.relations (to_entity_id, relation_type)")
    op.execute("CREATE INDEX relations_type_idx ON argus.relations (relation_type)")
    # Zeitliche Traversierung: "welche Kanten galten am Stichtag".
    op.execute("CREATE INDEX relations_validity_idx ON argus.relations USING gist (validity)")
    op.execute(
        "CREATE UNIQUE INDEX relations_dedupe_idx ON argus.relations (dedupe_key) "
        "WHERE dedupe_key IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX relations_history_id_period_idx "
        "ON argus.relations_history USING gist (relation_id, sys_period)"
    )


def downgrade() -> None:
    guard_destructive_downgrade("relations", "track_gaps", "tracks")
    op.execute("DROP TABLE IF EXISTS argus.relations_history")
    op.execute("DROP TABLE IF EXISTS argus.relations")
    op.execute("ALTER TABLE argus.observations DROP CONSTRAINT IF EXISTS observations_track_fk")
    op.execute("DROP TABLE IF EXISTS argus.track_gaps")
    op.execute("DROP TABLE IF EXISTS argus.tracks")
