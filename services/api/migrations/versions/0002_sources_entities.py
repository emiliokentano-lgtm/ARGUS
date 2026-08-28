"""Quellen, Entitaeten, Alias-Bezeichner.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from alembic import op

from argus_migrations import guard_destructive_downgrade

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # sources — Quellenregister mit Zuverlaessigkeit, Lizenz, Betriebszustand
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE argus.sources (
            source_id            text PRIMARY KEY,
            schema_version       text NOT NULL,
            name                 text NOT NULL,
            publisher            text,
            url                  text,
            description          text,
            kind                 argus.source_kind NOT NULL DEFAULT 'unspecified',
            domains              argus.source_domain[] NOT NULL DEFAULT '{}',

            reliability          argus.source_reliability NOT NULL DEFAULT 'unspecified',
            default_credibility  argus.information_credibility NOT NULL DEFAULT 'unspecified',

            -- Lizenzregister (Kapitel 14). license_id ist Pflicht: eine Quelle
            -- ohne Lizenzeintrag darf nicht in Betrieb gehen.
            license_id           text NOT NULL,
            license_name         text,
            license_spdx_id      text,
            license_url          text,
            license_allowed_uses text[] NOT NULL DEFAULT '{}',
            attribution_text     text,
            attribution_required boolean NOT NULL DEFAULT false,
            license_expires_at   timestamptz,
            max_retention_days   integer CHECK (max_retention_days IS NULL OR max_retention_days > 0),

            expected_latency_s   double precision CHECK (expected_latency_s IS NULL OR expected_latency_s >= 0),
            poll_interval_s      double precision CHECK (poll_interval_s IS NULL OR poll_interval_s > 0),
            rate_limit_requests  integer,
            rate_limit_per_seconds integer,

            connector_id         text,
            credential_ref       text,
            enabled              boolean NOT NULL DEFAULT true,
            disabled_reason      text,

            may_contain_personal_data boolean NOT NULL DEFAULT false,
            retention_days       integer CHECK (retention_days IS NULL OR retention_days > 0),

            coverage_area        geography(MultiPolygon, 4326),
            coverage_countries   text[] NOT NULL DEFAULT '{}',
            coverage_languages   text[] NOT NULL DEFAULT '{}',

            -- Freiform: nur quellspezifische Zusatzfelder ohne eigene Spalte.
            attributes           jsonb NOT NULL DEFAULT '{}'::jsonb,
            tags                 text[] NOT NULL DEFAULT '{}',

            observed_at          timestamptz,
            ingested_at          timestamptz NOT NULL DEFAULT clock_timestamp(),
            created_at           timestamptz NOT NULL DEFAULT clock_timestamp(),
            updated_at           timestamptz NOT NULL DEFAULT clock_timestamp(),

            CONSTRAINT sources_disabled_needs_reason
                CHECK (enabled OR disabled_reason IS NOT NULL)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE argus.sources IS "
        "'Quellenregister. license_id ist Pflicht - das CI-Gate aus Kapitel 14 "
        "lehnt Quellen ohne Lizenzeintrag ab.'"
    )
    op.execute("CREATE INDEX sources_enabled_idx ON argus.sources (enabled) WHERE enabled")
    op.execute("CREATE INDEX sources_domains_idx ON argus.sources USING gin (domains)")
    op.execute("CREATE INDEX sources_tags_idx ON argus.sources USING gin (tags)")
    op.execute(
        "CREATE TRIGGER sources_set_updated_at BEFORE UPDATE ON argus.sources "
        "FOR EACH ROW EXECUTE FUNCTION argus.set_updated_at()"
    )

    # Verlauf der Zuverlaessigkeitsbewertung (Kapitel 7.2): Aenderungen an der
    # Bewertung einer Quelle brauchen einen Audit-Trail.
    op.execute(
        """
        CREATE TABLE argus.source_reliability_changes (
            change_id    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_id    text NOT NULL
                REFERENCES argus.sources (source_id) ON DELETE CASCADE,
            changed_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
            from_value   argus.source_reliability NOT NULL,
            to_value     argus.source_reliability NOT NULL,
            reason       text NOT NULL,
            changed_by   text NOT NULL,
            evidence     jsonb NOT NULL DEFAULT '[]'::jsonb,
            CONSTRAINT source_reliability_changes_actually_changed
                CHECK (from_value <> to_value)
        )
        """
    )
    op.execute(
        "CREATE INDEX source_reliability_changes_source_idx "
        "ON argus.source_reliability_changes (source_id, changed_at DESC)"
    )

    # ------------------------------------------------------------------
    # entities — kanonische Entitaeten, bitemporal versioniert
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE argus.entities (
            entity_id        text PRIMARY KEY,
            schema_version   text NOT NULL,
            type             argus.entity_type NOT NULL,
            display_name     text NOT NULL,

            -- Denormalisiert, weil f_watchlist bei jeder Bewertung gebraucht wird.
            watchlist_ids    text[] NOT NULL DEFAULT '{}',
            tags             text[] NOT NULL DEFAULT '{}',

            sanction_status  argus.sanction_status NOT NULL DEFAULT 'not_checked',

            -- Letzte bekannte Position: denormalisiert fuer Kartenabfragen,
            -- die Historie steht in argus.observations.
            last_position    geography(Point, 4326),
            last_position_h3_r7 bigint,
            last_position_at timestamptz,

            first_seen_at    timestamptz,
            last_seen_at     timestamptz,
            existence        tstzrange,
            is_active        boolean NOT NULL DEFAULT true,

            merged_into_entity_id text
                REFERENCES argus.entities (entity_id) ON DELETE SET NULL,
            resolution_status argus.resolution_status NOT NULL DEFAULT 'resolved',
            resolver_version text,

            contains_personal_data boolean NOT NULL DEFAULT false,
            personal_data_basis text,
            purge_after      timestamptz,

            attributes       jsonb NOT NULL DEFAULT '{}'::jsonb,

            source_id        text REFERENCES argus.sources (source_id) ON DELETE SET NULL,
            raw_ref          text,
            observed_at      timestamptz,
            ingested_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
            version          integer NOT NULL DEFAULT 1,
            sys_period       tstzrange NOT NULL DEFAULT tstzrange(clock_timestamp(), NULL, '[)'),

            CONSTRAINT entities_personal_data_needs_basis
                CHECK (NOT contains_personal_data OR personal_data_basis IS NOT NULL),
            CONSTRAINT entities_merge_not_self
                CHECK (merged_into_entity_id IS DISTINCT FROM entity_id)
        )
        """
    )
    op.execute(
        "COMMENT ON COLUMN argus.entities.merged_into_entity_id IS "
        "'Gesetzt, wenn die Entitaet als Dublette eingezogen wurde. Der Datensatz "
        "bleibt erhalten, damit alte Verweise aufloesbar bleiben.'"
    )
    op.execute(
        """
        CREATE TABLE argus.entities_history (LIKE argus.entities);
        COMMENT ON TABLE argus.entities_history IS
            'Abgeloeste Fassungen. Wird ausschliesslich vom Trigger befuellt.';
        """
    )
    op.execute(
        "CREATE TRIGGER entities_versioning BEFORE UPDATE OR DELETE ON argus.entities "
        "FOR EACH ROW EXECUTE FUNCTION argus.versioning_trigger('argus.entities_history')"
    )

    op.execute("CREATE INDEX entities_type_idx ON argus.entities (type)")
    op.execute("CREATE INDEX entities_tags_idx ON argus.entities USING gin (tags)")
    op.execute("CREATE INDEX entities_watchlists_idx ON argus.entities USING gin (watchlist_ids)")
    op.execute(
        "CREATE INDEX entities_last_position_idx ON argus.entities USING gist (last_position) "
        "WHERE last_position IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX entities_last_position_h3_idx ON argus.entities (last_position_h3_r7) "
        "WHERE last_position_h3_r7 IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX entities_sanctioned_idx ON argus.entities (sanction_status) "
        "WHERE sanction_status IN ('listed', 'associated', 'possible_match')"
    )
    # Unscharfe Namenssuche fuer die Blocking-Stufe der Entity Resolution.
    op.execute(
        "CREATE INDEX entities_display_name_trgm_idx ON argus.entities "
        "USING gin (display_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX entities_purge_after_idx ON argus.entities (purge_after) "
        "WHERE purge_after IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX entities_history_id_period_idx ON argus.entities_history USING gist (entity_id, sys_period)"
    )

    # ------------------------------------------------------------------
    # entity_aliases — alle externen Bezeichner und Namensvarianten
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE argus.entity_aliases (
            alias_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            entity_id    text NOT NULL
                REFERENCES argus.entities (entity_id) ON DELETE CASCADE,

            -- Bezeichnerart: 'imo', 'mmsi', 'icao24', 'lei', 'callsign',
            -- 'wikidata', 'name', 'former_name', ...
            id_type      text NOT NULL,
            id_value     text NOT NULL,

            stability    argus.identifier_stability NOT NULL DEFAULT 'unspecified',
            alias_kind   argus.alias_kind NOT NULL DEFAULT 'unspecified',
            lang         text,
            script       text,
            is_primary   boolean NOT NULL DEFAULT false,

            -- Ein Bezeichner gilt oft nur zeitweise: eine MMSI gehoert nur
            -- zeitweise zu einem Schiff.
            validity     tstzrange NOT NULL DEFAULT tstzrange(NULL, NULL, '[)'),

            source_id    text REFERENCES argus.sources (source_id) ON DELETE SET NULL,
            confidence   double precision CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
            ingested_at  timestamptz NOT NULL DEFAULT clock_timestamp(),

            CONSTRAINT entity_aliases_id_type_lowercase CHECK (id_type = lower(id_type)),
            CONSTRAINT entity_aliases_value_not_blank CHECK (length(btrim(id_value)) > 0)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE argus.entity_aliases IS "
        "'Externe Bezeichner und Namensvarianten. Die Eindeutigkeit ueber "
        "(id_type, id_value) ist der Kern der Entity Resolution: derselbe "
        "Bezeichner darf nie auf zwei Entitaeten zeigen.'"
    )
    # Der geforderte Unique-Constraint. Er ist die Stelle, an der eine doppelte
    # Alias-Zuordnung auffaellt - bevor zwei Entitaeten stillschweigend
    # dieselbe IMO tragen.
    op.execute(
        "ALTER TABLE argus.entity_aliases "
        "ADD CONSTRAINT entity_aliases_id_type_value_key UNIQUE (id_type, id_value)"
    )
    op.execute("CREATE INDEX entity_aliases_entity_idx ON argus.entity_aliases (entity_id)")
    op.execute(
        "CREATE INDEX entity_aliases_value_trgm_idx ON argus.entity_aliases "
        "USING gin (id_value gin_trgm_ops)"
    )
    # Hoechstens ein primaerer Bezeichner je Entitaet und Art.
    op.execute(
        "CREATE UNIQUE INDEX entity_aliases_one_primary_idx "
        "ON argus.entity_aliases (entity_id, id_type) WHERE is_primary"
    )

    # ------------------------------------------------------------------
    # entity_sanctions — Treffer gegen Sanktions- und PEP-Listen
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE argus.entity_sanctions (
            listing_row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            entity_id     text NOT NULL
                REFERENCES argus.entities (entity_id) ON DELETE CASCADE,
            list_id       text NOT NULL,
            listing_id    text NOT NULL,
            program       text,
            listed_at     timestamptz,
            delisted_at   timestamptz,
            match_confidence double precision NOT NULL
                CHECK (match_confidence >= 0 AND match_confidence <= 1),
            matched_on    text NOT NULL,
            url           text,
            source_id     text REFERENCES argus.sources (source_id) ON DELETE SET NULL,
            ingested_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
            CONSTRAINT entity_sanctions_unique UNIQUE (entity_id, list_id, listing_id),
            CONSTRAINT entity_sanctions_dates CHECK (delisted_at IS NULL OR listed_at IS NULL OR delisted_at >= listed_at)
        )
        """
    )
    op.execute(
        "CREATE INDEX entity_sanctions_list_idx ON argus.entity_sanctions (list_id, listing_id)"
    )
    op.execute(
        "CREATE INDEX entity_sanctions_active_idx ON argus.entity_sanctions (entity_id) "
        "WHERE delisted_at IS NULL"
    )


def downgrade() -> None:
    guard_destructive_downgrade(
        "entity_sanctions", "entity_aliases", "entities", "source_reliability_changes", "sources"
    )
    op.execute("DROP TABLE IF EXISTS argus.entity_sanctions")
    op.execute("DROP TABLE IF EXISTS argus.entity_aliases")
    op.execute("DROP TABLE IF EXISTS argus.entities_history")
    op.execute("DROP TABLE IF EXISTS argus.entities")
    op.execute("DROP TABLE IF EXISTS argus.source_reliability_changes")
    op.execute("DROP TABLE IF EXISTS argus.sources")
