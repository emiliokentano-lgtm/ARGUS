"""Ereignisse mit bitemporaler Versionierung und Volltext.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from alembic import op

from argus_migrations import guard_destructive_downgrade

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE argus.events (
            event_id         text PRIMARY KEY,
            schema_version   text NOT NULL,

            -- Hierarchischer Taxonomiepfad, punktgetrennt und von grob nach
            -- fein: 'economic.rate_decision'. Bewusst kein Enum - die
            -- Taxonomie waechst schneller als das Schema (siehe ADR 0003).
            type             text NOT NULL,
            title            text NOT NULL,
            summary          text,
            lang             text NOT NULL DEFAULT 'und',

            -- Valid Time des Geschehens. occurred_end ist NULL bei laufenden
            -- oder offenen Ereignissen; das ist etwas anderes als "endet jetzt".
            occurred_start   timestamptz NOT NULL,
            occurred_end     timestamptz,
            occurred_precision argus.time_precision NOT NULL DEFAULT 'unspecified',
            is_ongoing       boolean NOT NULL DEFAULT false,

            -- Ortsangabe. geo ist NULL, wenn nur ein benannter Ort ohne
            -- Geometrie bekannt ist (Fehlerfall "nur Landangabe"). geo_point
            -- ist dann entweder ebenfalls NULL oder als abgeleitet markiert -
            -- ein Punkt in der Landesmitte darf nie unmarkiert erscheinen.
            geo              geography(Geometry, 4326),
            geo_point        geography(Point, 4326),
            geo_point_is_derived boolean NOT NULL DEFAULT false,
            geo_precision    argus.geo_precision NOT NULL DEFAULT 'unspecified',
            geo_uncertainty_radius_m double precision
                CHECK (geo_uncertainty_radius_m IS NULL OR geo_uncertainty_radius_m >= 0),
            place_name       text,
            place_country    text CHECK (place_country IS NULL OR place_country ~ '^[A-Z]{2}$'),
            place_wikidata_qid text,
            h3_r5            bigint,
            h3_r7            bigint,

            severity         double precision NOT NULL DEFAULT 0
                CHECK (severity >= 0 AND severity <= 1),
            confidence       double precision NOT NULL DEFAULT 0
                CHECK (confidence >= 0 AND confidence <= 1),
            status           argus.event_status NOT NULL DEFAULT 'reported',

            magnitude_scale  text,
            magnitude_value  double precision,
            magnitude_unit   text,
            magnitude_expected double precision,
            magnitude_previous double precision,

            independent_sources integer NOT NULL DEFAULT 0 CHECK (independent_sources >= 0),
            contradicting_sources integer NOT NULL DEFAULT 0 CHECK (contradicting_sources >= 0),
            first_seen_source text,
            first_seen_at    timestamptz,

            story_cluster_id text,
            priority         double precision CHECK (priority IS NULL OR (priority >= 0 AND priority <= 100)),

            -- Zurueckgezogene Meldung: der Datensatz bleibt vollstaendig,
            -- nur der Status und dieser Block kommen hinzu.
            retracted_at     timestamptz,
            retracted_by_source text,
            retraction_reason text,
            retraction_inferred boolean NOT NULL DEFAULT false,
            superseded_by_event_id text,

            tags             text[] NOT NULL DEFAULT '{}',
            attributes       jsonb NOT NULL DEFAULT '{}'::jsonb,

            dedupe_key       text,
            source_id        text REFERENCES argus.sources (source_id) ON DELETE SET NULL,
            raw_ref          text,
            observed_at      timestamptz,
            ingested_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
            version          integer NOT NULL DEFAULT 1,
            sys_period       tstzrange NOT NULL DEFAULT tstzrange(clock_timestamp(), NULL, '[)'),

            -- Volltext, sprachabhaengig konfiguriert. Generierte Spalte statt
            -- Trigger: kann nicht veralten, solange die Zeile nicht geaendert
            -- wird, und ist ohne Zusatzcode korrekt.
            search_tsv tsvector GENERATED ALWAYS AS (
                setweight(to_tsvector(argus.ts_config(lang), coalesce(title, '')), 'A') ||
                setweight(to_tsvector(argus.ts_config(lang), coalesce(summary, '')), 'B') ||
                setweight(to_tsvector('simple', coalesce(place_name, '')), 'C')
            ) STORED,

            CONSTRAINT events_time_order
                CHECK (occurred_end IS NULL OR occurred_end >= occurred_start),
            CONSTRAINT events_retraction_complete
                CHECK ((status <> 'retracted') OR
                       (retracted_at IS NOT NULL AND retraction_reason IS NOT NULL)),
            -- Der Kern der Geo-Praezisionsregel: ein Punkt, der nicht aus der
            -- Quelle stammt, muss als abgeleitet gekennzeichnet sein, sobald
            -- die Genauigkeit gruber als 'building' ist.
            CONSTRAINT events_derived_point_marked
                CHECK (geo_point IS NULL
                       OR geo_precision IN ('exact', 'building')
                       OR geo_point_is_derived),
            CONSTRAINT events_type_path
                CHECK (type ~ '^[a-z0-9]+(\\.[a-z0-9_]+)*$')
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE argus.events IS "
        "'Ereignisse, bitemporal versioniert. occurred_* ist die Valid Time, "
        "observed_at/ingested_at die Transaction Time, sys_period die "
        "Gueltigkeit dieser Fassung im System.'"
    )
    op.execute(
        "ALTER TABLE argus.events ADD CONSTRAINT events_superseded_by_fk "
        "FOREIGN KEY (superseded_by_event_id) REFERENCES argus.events (event_id) "
        "ON DELETE SET NULL"
    )

    op.execute("CREATE TABLE argus.events_history (LIKE argus.events)")
    op.execute(
        "COMMENT ON TABLE argus.events_history IS "
        "'Abgeloeste Ereignisfassungen. Nur der Trigger schreibt hierher.'"
    )
    op.execute(
        "CREATE TRIGGER events_versioning BEFORE UPDATE OR DELETE ON argus.events "
        "FOR EACH ROW EXECUTE FUNCTION argus.versioning_trigger('argus.events_history')"
    )

    # --- Indizes ------------------------------------------------------
    op.execute("CREATE INDEX events_occurred_idx ON argus.events (occurred_start DESC)")
    op.execute("CREATE INDEX events_ingested_idx ON argus.events (ingested_at DESC)")
    op.execute("CREATE INDEX events_type_idx ON argus.events (type text_pattern_ops)")
    op.execute("CREATE INDEX events_status_idx ON argus.events (status)")
    op.execute(
        "CREATE INDEX events_priority_idx ON argus.events (priority DESC NULLS LAST, occurred_start DESC)"
    )
    op.execute("CREATE INDEX events_geo_idx ON argus.events USING gist (geo) WHERE geo IS NOT NULL")
    op.execute(
        "CREATE INDEX events_geo_point_idx ON argus.events USING gist (geo_point) "
        "WHERE geo_point IS NOT NULL"
    )
    op.execute("CREATE INDEX events_h3_r7_idx ON argus.events (h3_r7) WHERE h3_r7 IS NOT NULL")
    op.execute("CREATE INDEX events_h3_r5_idx ON argus.events (h3_r5) WHERE h3_r5 IS NOT NULL")
    op.execute("CREATE INDEX events_search_idx ON argus.events USING gin (search_tsv)")
    op.execute("CREATE INDEX events_tags_idx ON argus.events USING gin (tags)")
    op.execute(
        "CREATE INDEX events_cluster_idx ON argus.events (story_cluster_id) "
        "WHERE story_cluster_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX events_dedupe_key_idx ON argus.events (dedupe_key) "
        "WHERE dedupe_key IS NOT NULL"
    )
    # Zeitreise: "welche Fassung galt zum Zeitpunkt T" wird ueber diesen Index
    # beantwortet.
    op.execute(
        "CREATE INDEX events_history_id_period_idx "
        "ON argus.events_history USING gist (event_id, sys_period)"
    )

    # --- Beteiligte Entitaeten ----------------------------------------
    op.execute(
        """
        CREATE TABLE argus.event_entities (
            event_id     text NOT NULL
                REFERENCES argus.events (event_id) ON DELETE CASCADE,
            -- Unaufgeloeste Verweise bleiben erhalten: entity_id ist NULL,
            -- ref_type/ref_id tragen weiterhin die Rohaussage der Quelle.
            entity_id    text REFERENCES argus.entities (entity_id) ON DELETE SET NULL,
            ref_type     argus.entity_type NOT NULL,
            ref_id       text NOT NULL,
            resolution_status argus.resolution_status NOT NULL DEFAULT 'pending',
            role         argus.entity_role NOT NULL DEFAULT 'unspecified',
            role_confidence double precision
                CHECK (role_confidence IS NULL OR (role_confidence >= 0 AND role_confidence <= 1)),
            match_confidence double precision
                CHECK (match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1)),
            PRIMARY KEY (event_id, ref_id, role)
        )
        """
    )
    op.execute("CREATE INDEX event_entities_entity_idx ON argus.event_entities (entity_id) WHERE entity_id IS NOT NULL")
    op.execute("CREATE INDEX event_entities_ref_idx ON argus.event_entities (ref_id)")
    op.execute(
        "CREATE INDEX event_entities_unresolved_idx ON argus.event_entities (resolution_status) "
        "WHERE resolution_status IN ('pending', 'unresolved', 'ambiguous')"
    )

    # --- Verknuepfungen zwischen Ereignissen --------------------------
    op.execute(
        """
        CREATE TABLE argus.event_links (
            from_event_id text NOT NULL
                REFERENCES argus.events (event_id) ON DELETE CASCADE,
            to_event_id   text NOT NULL
                REFERENCES argus.events (event_id) ON DELETE CASCADE,
            link_type     argus.event_link_type NOT NULL,
            -- Kausalitaet wird nie als Fakt behauptet: eine Hypothese braucht
            -- eine Staerke.
            strength      double precision
                CHECK (strength IS NULL OR (strength >= 0 AND strength <= 1)),
            rationale     text,
            created_by    text NOT NULL,
            created_at    timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (from_event_id, to_event_id, link_type),
            CONSTRAINT event_links_not_self CHECK (from_event_id <> to_event_id),
            CONSTRAINT event_links_hypothesis_needs_strength
                CHECK (link_type <> 'caused_by_hypothesis' OR strength IS NOT NULL)
        )
        """
    )
    op.execute("CREATE INDEX event_links_to_idx ON argus.event_links (to_event_id)")

    # --- Widersprueche -------------------------------------------------
    op.execute(
        """
        CREATE TABLE argus.event_contradictions (
            contradiction_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            event_id     text NOT NULL
                REFERENCES argus.events (event_id) ON DELETE CASCADE,
            -- JSON-Pointer auf das strittige Feld: '/magnitude/value'
            field_path   text NOT NULL,
            -- Die konkurrierenden Behauptungen. Echte Freiform: der Wert kann
            -- jeden JSON-Typ haben, und die Zahl der Behauptungen ist offen.
            claims       jsonb NOT NULL,
            preferred_claim_index integer
                CHECK (preferred_claim_index IS NULL OR preferred_claim_index >= 0),
            note         text,
            detected_at  timestamptz NOT NULL DEFAULT clock_timestamp(),
            resolved_at  timestamptz,
            CONSTRAINT event_contradictions_claims_is_array
                CHECK (jsonb_typeof(claims) = 'array' AND jsonb_array_length(claims) >= 2)
        )
        """
    )
    op.execute(
        "COMMENT ON COLUMN argus.event_contradictions.claims IS "
        "'Array konkurrierender Behauptungen, je mit Wert, Quelle und Beleg. "
        "Der Widerspruch wird gefuehrt, nicht durch Auswahl eines Siegers "
        "aufgeloest - preferred_claim_index bleibt NULL, solange er offen ist.'"
    )
    op.execute("CREATE INDEX event_contradictions_event_idx ON argus.event_contradictions (event_id)")
    op.execute(
        "CREATE INDEX event_contradictions_open_idx ON argus.event_contradictions (detected_at DESC) "
        "WHERE resolved_at IS NULL"
    )

    # --- Zeitreise-Funktion --------------------------------------------
    # "Zustand von Event X zum Zeitpunkt T" ueber aktuelle und historische
    # Fassungen hinweg. Genau eine Zeile, weil sich die sys_period-Intervalle
    # lueckenlos aneinanderreihen und nicht ueberlappen.
    op.execute(
        """
        CREATE FUNCTION argus.event_as_of(p_event_id text, p_at timestamptz)
        RETURNS SETOF argus.events
        LANGUAGE sql STABLE AS $$
            SELECT * FROM argus.events
             WHERE event_id = p_event_id AND sys_period @> p_at
            UNION ALL
            SELECT * FROM argus.events_history
             WHERE event_id = p_event_id AND sys_period @> p_at
        $$
        """
    )
    op.execute(
        "COMMENT ON FUNCTION argus.event_as_of(text, timestamptz) IS "
        "'Fassung eines Ereignisses zum Zeitpunkt T - was wusste das System "
        "damals, nicht was es heute weiss.'"
    )


def downgrade() -> None:
    guard_destructive_downgrade(
        "event_contradictions", "event_links", "event_entities", "events"
    )
    op.execute("DROP FUNCTION IF EXISTS argus.event_as_of(text, timestamptz)")
    op.execute("DROP TABLE IF EXISTS argus.event_contradictions")
    op.execute("DROP TABLE IF EXISTS argus.event_links")
    op.execute("DROP TABLE IF EXISTS argus.event_entities")
    op.execute("DROP TABLE IF EXISTS argus.events_history")
    op.execute("DROP TABLE IF EXISTS argus.events")
