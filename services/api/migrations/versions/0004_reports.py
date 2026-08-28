"""Berichte, Volltext, Erwaehnungen, Story-Cluster.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from alembic import op

from argus_migrations import guard_destructive_downgrade

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE argus.reports (
            report_id      text PRIMARY KEY,
            schema_version text NOT NULL,
            kind           argus.report_kind NOT NULL DEFAULT 'unspecified',

            url            text,
            canonical_url  text,
            title          text NOT NULL,
            summary        text,

            -- Volltext nur, wenn die Lizenz es erlaubt. Sonst bleibt die
            -- Spalte leer und body_ref zeigt auf das Bronze-Objekt.
            body_text      text,
            body_ref       text,
            body_withheld_for_license boolean NOT NULL DEFAULT false,

            lang           text NOT NULL DEFAULT 'und',
            lang_confidence double precision
                CHECK (lang_confidence IS NULL OR (lang_confidence >= 0 AND lang_confidence <= 1)),

            published_at   timestamptz,
            modified_at    timestamptz,

            publisher      text,
            publisher_country text
                CHECK (publisher_country IS NULL OR publisher_country ~ '^[A-Z]{2}$'),
            authors        text[] NOT NULL DEFAULT '{}',

            sentiment      double precision
                CHECK (sentiment IS NULL OR (sentiment >= -1 AND sentiment <= 1)),
            sentiment_model text,

            -- Der Vektor selbst liegt in OpenSearch; hier steht nur der
            -- Verweis und das Modell, damit ein Modellwechsel erkennbar ist.
            embedding_id   text,
            embedding_model text,

            -- Deduplizierung (Kapitel 6.3). simhash als bigint, weil die
            -- Hamming-Distanz auf Ganzzahlen gerechnet wird.
            simhash        bigint,
            content_hash   bytea,
            story_cluster_id text,
            is_cluster_representative boolean NOT NULL DEFAULT false,
            cluster_similarity double precision
                CHECK (cluster_similarity IS NULL OR (cluster_similarity >= 0 AND cluster_similarity <= 1)),
            duplicate_of_report_id text,

            is_paywalled   boolean NOT NULL DEFAULT false,
            license_id     text,
            attribution_text text,

            priority       double precision
                CHECK (priority IS NULL OR (priority >= 0 AND priority <= 100)),

            retracted_at   timestamptz,
            retraction_reason text,

            tags           text[] NOT NULL DEFAULT '{}',
            attributes     jsonb NOT NULL DEFAULT '{}'::jsonb,

            dedupe_key     text,
            source_id      text REFERENCES argus.sources (source_id) ON DELETE SET NULL,
            raw_ref        text,
            observed_at    timestamptz,
            ingested_at    timestamptz NOT NULL DEFAULT clock_timestamp(),
            version        integer NOT NULL DEFAULT 1,

            search_tsv tsvector GENERATED ALWAYS AS (
                setweight(to_tsvector(argus.ts_config(lang), coalesce(title, '')), 'A') ||
                setweight(to_tsvector(argus.ts_config(lang), coalesce(summary, '')), 'B') ||
                setweight(to_tsvector(argus.ts_config(lang), coalesce(body_text, '')), 'D')
            ) STORED,

            CONSTRAINT reports_body_or_ref
                CHECK (NOT body_withheld_for_license OR body_text IS NULL),
            CONSTRAINT reports_retraction_complete
                CHECK (retracted_at IS NULL OR retraction_reason IS NOT NULL)
        )
        """
    )
    op.execute(
        "ALTER TABLE argus.reports ADD CONSTRAINT reports_duplicate_of_fk "
        "FOREIGN KEY (duplicate_of_report_id) REFERENCES argus.reports (report_id) "
        "ON DELETE SET NULL"
    )
    op.execute(
        "COMMENT ON COLUMN argus.reports.body_withheld_for_license IS "
        "'true, wenn der Volltext aus Lizenzgruenden nicht gespeichert wurde. "
        'Unterscheidet "kein Text vorhanden" von "Text vorhanden, aber nicht '
        "speicherbar\".'"
    )

    op.execute("CREATE INDEX reports_published_idx ON argus.reports (published_at DESC NULLS LAST)")
    op.execute("CREATE INDEX reports_ingested_idx ON argus.reports (ingested_at DESC)")
    op.execute("CREATE INDEX reports_search_idx ON argus.reports USING gin (search_tsv)")
    op.execute("CREATE INDEX reports_source_idx ON argus.reports (source_id, ingested_at DESC)")
    op.execute(
        "CREATE INDEX reports_cluster_idx ON argus.reports (story_cluster_id, published_at) "
        "WHERE story_cluster_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX reports_simhash_idx ON argus.reports (simhash) WHERE simhash IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX reports_content_hash_idx ON argus.reports (content_hash) "
        "WHERE content_hash IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX reports_canonical_url_idx ON argus.reports (canonical_url) "
        "WHERE canonical_url IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX reports_dedupe_key_idx ON argus.reports (dedupe_key) "
        "WHERE dedupe_key IS NOT NULL"
    )
    op.execute("CREATE INDEX reports_tags_idx ON argus.reports USING gin (tags)")
    op.execute("CREATE INDEX reports_lang_idx ON argus.reports (lang)")

    # --- Uebersetzungen: Original bleibt immer erhalten -----------------
    op.execute(
        """
        CREATE TABLE argus.report_translations (
            report_id    text NOT NULL
                REFERENCES argus.reports (report_id) ON DELETE CASCADE,
            lang         text NOT NULL,
            title        text,
            body_text    text,
            model        text NOT NULL,
            model_version text NOT NULL,
            prompt_hash  text,
            translated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (report_id, lang)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE argus.report_translations IS "
        "'Maschinelle Uebersetzungen. Das Original bleibt in argus.reports; "
        "eine Uebersetzung ersetzt es nie (Kapitel 11).'"
    )

    # --- Erwaehnungen ---------------------------------------------------
    op.execute(
        """
        CREATE TABLE argus.report_mentions (
            report_id    text NOT NULL
                REFERENCES argus.reports (report_id) ON DELETE CASCADE,
            entity_id    text REFERENCES argus.entities (entity_id) ON DELETE SET NULL,
            ref_type     argus.entity_type NOT NULL,
            ref_id       text NOT NULL,
            resolution_status argus.resolution_status NOT NULL DEFAULT 'pending',
            match_confidence double precision
                CHECK (match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1)),
            -- Fundstelle im Text, fuer die Hervorhebung in der UI.
            char_start   integer CHECK (char_start IS NULL OR char_start >= 0),
            char_end     integer CHECK (char_end IS NULL OR char_end >= 0),
            PRIMARY KEY (report_id, ref_id),
            CONSTRAINT report_mentions_span CHECK (char_end IS NULL OR char_start IS NULL OR char_end >= char_start)
        )
        """
    )
    op.execute(
        "CREATE INDEX report_mentions_entity_idx ON argus.report_mentions (entity_id) WHERE entity_id IS NOT NULL"
    )

    # --- Bericht <-> Ereignis -------------------------------------------
    op.execute(
        """
        CREATE TABLE argus.event_reports (
            event_id   text NOT NULL
                REFERENCES argus.events (event_id) ON DELETE CASCADE,
            report_id  text NOT NULL
                REFERENCES argus.reports (report_id) ON DELETE CASCADE,
            -- true fuer den Bericht, der das Ereignis zuerst gemeldet hat.
            is_first_report boolean NOT NULL DEFAULT false,
            linked_at  timestamptz NOT NULL DEFAULT clock_timestamp(),
            linked_by  text NOT NULL DEFAULT 'argus:service:correlator',
            PRIMARY KEY (event_id, report_id)
        )
        """
    )
    op.execute("CREATE INDEX event_reports_report_idx ON argus.event_reports (report_id)")
    op.execute(
        "CREATE UNIQUE INDEX event_reports_one_first_idx ON argus.event_reports (event_id) "
        "WHERE is_first_report"
    )

    # --- Georeferenzen aus dem Geoparsing --------------------------------
    op.execute(
        """
        CREATE TABLE argus.report_places (
            place_row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            report_id    text NOT NULL
                REFERENCES argus.reports (report_id) ON DELETE CASCADE,
            geo_point    geography(Point, 4326),
            geo_precision argus.geo_precision NOT NULL DEFAULT 'unspecified',
            place_name   text NOT NULL,
            place_country text CHECK (place_country IS NULL OR place_country ~ '^[A-Z]{2}$'),
            wikidata_qid text,
            geonames_id  text,
            h3_r7        bigint,
            confidence   double precision
                CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
            char_start   integer,
            char_end     integer
        )
        """
    )
    op.execute("CREATE INDEX report_places_report_idx ON argus.report_places (report_id)")
    op.execute(
        "CREATE INDEX report_places_geo_idx ON argus.report_places USING gist (geo_point) "
        "WHERE geo_point IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX report_places_h3_idx ON argus.report_places (h3_r7) WHERE h3_r7 IS NOT NULL"
    )


def downgrade() -> None:
    guard_destructive_downgrade(
        "report_places", "event_reports", "report_mentions", "report_translations", "reports"
    )
    op.execute("DROP TABLE IF EXISTS argus.report_places")
    op.execute("DROP TABLE IF EXISTS argus.event_reports")
    op.execute("DROP TABLE IF EXISTS argus.report_mentions")
    op.execute("DROP TABLE IF EXISTS argus.report_translations")
    op.execute("DROP TABLE IF EXISTS argus.reports")
