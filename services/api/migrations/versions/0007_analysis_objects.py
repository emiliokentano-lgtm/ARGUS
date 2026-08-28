"""Bewertungen, AOIs, Watchlists, Alarme, Cases, Scores, Datenluecken.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from alembic import op

from argus_migrations import guard_destructive_downgrade

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # aois
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE argus.aois (
            aoi_id          text PRIMARY KEY,
            schema_version  text NOT NULL,
            name            text NOT NULL,
            description     text,
            kind            argus.aoi_kind NOT NULL,

            geom            geography(Geometry, 4326),
            zone_type       argus.zone_type NOT NULL DEFAULT 'unspecified',
            zone_id         text,
            zone_dataset    text,
            anchor_entity_id text REFERENCES argus.entities (entity_id) ON DELETE SET NULL,
            anchor_radius_m double precision CHECK (anchor_radius_m IS NULL OR anchor_radius_m > 0),

            -- Vorberechnete Ueberdeckung: die Zugehoerigkeitspruefung einer
            -- Beobachtung wird damit zum Indexlookup statt zur Geometrieoperation.
            h3_r5_cells     bigint[] NOT NULL DEFAULT '{}',
            h3_r7_cells     bigint[] NOT NULL DEFAULT '{}',

            -- Bewertungsparameter (Kapitel 7.1): d0 ist pro AOI konfigurierbar.
            proximity_decay_km double precision NOT NULL DEFAULT 50
                CHECK (proximity_decay_km > 0),
            weight          double precision NOT NULL DEFAULT 1
                CHECK (weight >= 0),
            min_priority    double precision
                CHECK (min_priority IS NULL OR (min_priority >= 0 AND min_priority <= 100)),
            event_type_filter text[] NOT NULL DEFAULT '{}',

            area_m2         double precision CHECK (area_m2 IS NULL OR area_m2 >= 0),
            owner_id        text NOT NULL,
            visibility      argus.visibility NOT NULL DEFAULT 'private',
            shared_with     text[] NOT NULL DEFAULT '{}',
            tags            text[] NOT NULL DEFAULT '{}',
            active          boolean NOT NULL DEFAULT true,
            attributes      jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
            updated_at      timestamptz NOT NULL DEFAULT clock_timestamp(),

            CONSTRAINT aois_geometry_present
                CHECK (kind = 'dynamic' OR geom IS NOT NULL),
            CONSTRAINT aois_dynamic_has_anchor
                CHECK (kind <> 'dynamic' OR (anchor_entity_id IS NOT NULL AND anchor_radius_m IS NOT NULL)),
            CONSTRAINT aois_named_zone_has_id
                CHECK (kind <> 'named_zone' OR zone_id IS NOT NULL)
        )
        """
    )
    op.execute("CREATE INDEX aois_geom_idx ON argus.aois USING gist (geom) WHERE geom IS NOT NULL")
    op.execute("CREATE INDEX aois_h3_r7_idx ON argus.aois USING gin (h3_r7_cells)")
    op.execute("CREATE INDEX aois_owner_idx ON argus.aois (owner_id) WHERE active")
    op.execute("CREATE INDEX aois_visibility_idx ON argus.aois (visibility)")
    op.execute(
        "CREATE TRIGGER aois_set_updated_at BEFORE UPDATE ON argus.aois "
        "FOR EACH ROW EXECUTE FUNCTION argus.set_updated_at()"
    )

    # ------------------------------------------------------------------
    # watchlists
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE argus.watchlists (
            watchlist_id    text PRIMARY KEY,
            schema_version  text NOT NULL,
            name            text NOT NULL,
            description     text,
            default_weight  double precision NOT NULL DEFAULT 1
                CHECK (default_weight >= 0 AND default_weight <= 1),
            import_source_id text REFERENCES argus.sources (source_id) ON DELETE SET NULL,
            last_import_at  timestamptz,
            is_managed      boolean NOT NULL DEFAULT false,
            owner_id        text NOT NULL,
            visibility      argus.visibility NOT NULL DEFAULT 'private',
            shared_with     text[] NOT NULL DEFAULT '{}',
            tags            text[] NOT NULL DEFAULT '{}',
            active          boolean NOT NULL DEFAULT true,
            contains_personal_data boolean NOT NULL DEFAULT false,
            attributes      jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
            updated_at      timestamptz NOT NULL DEFAULT clock_timestamp()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE argus.watchlist_members (
            member_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            watchlist_id  text NOT NULL
                REFERENCES argus.watchlists (watchlist_id) ON DELETE CASCADE,
            entity_id     text REFERENCES argus.entities (entity_id) ON DELETE CASCADE,
            ref_type      argus.entity_type,
            ref_id        text,
            match_mode    argus.match_mode NOT NULL DEFAULT 'entity',
            pattern       text,
            attribute_path text,
            attribute_value jsonb,
            weight        double precision NOT NULL DEFAULT 1
                CHECK (weight >= 0 AND weight <= 1),
            min_similarity double precision
                CHECK (min_similarity IS NULL OR (min_similarity >= 0 AND min_similarity <= 1)),
            validity      tstzrange NOT NULL DEFAULT tstzrange(NULL, NULL, '[)'),
            note          text,
            added_by      text NOT NULL,
            added_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
            source_id     text REFERENCES argus.sources (source_id) ON DELETE SET NULL,

            CONSTRAINT watchlist_members_target
                CHECK ((match_mode IN ('exact_id', 'entity') AND ref_id IS NOT NULL)
                    OR (match_mode IN ('pattern', 'fuzzy_name') AND pattern IS NOT NULL)
                    OR (match_mode = 'attribute' AND attribute_path IS NOT NULL))
        )
        """
    )
    op.execute("CREATE INDEX watchlist_members_list_idx ON argus.watchlist_members (watchlist_id)")
    op.execute(
        "CREATE INDEX watchlist_members_entity_idx ON argus.watchlist_members (entity_id) "
        "WHERE entity_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX watchlist_members_unique_ref_idx "
        "ON argus.watchlist_members (watchlist_id, ref_id) WHERE ref_id IS NOT NULL"
    )

    # ------------------------------------------------------------------
    # scores — erklaerbar, deshalb Faktoren als eigene Tabelle statt JSONB
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE argus.scores (
            score_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            object_kind   argus.object_kind NOT NULL,
            object_id     text NOT NULL,
            priority      double precision NOT NULL CHECK (priority >= 0 AND priority <= 100),
            -- Ohne Version des Gewichtssatzes ist ein historischer Score nicht
            -- reproduzierbar.
            weights_version text NOT NULL,
            profile_id    text NOT NULL DEFAULT '',
            computed_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
            CONSTRAINT scores_unique_per_profile UNIQUE (object_kind, object_id, profile_id, computed_at)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE argus.score_factors (
            score_id     bigint NOT NULL REFERENCES argus.scores (score_id) ON DELETE CASCADE,
            factor       text NOT NULL,
            raw          double precision NOT NULL,
            weight       double precision NOT NULL,
            contribution double precision NOT NULL,
            detail       text,
            PRIMARY KEY (score_id, factor)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE argus.score_factors IS "
        "'Zerlegung eines Scores. Eigene Tabelle statt JSONB, weil die Frage "
        '"welcher Faktor dominiert" relational beantwortet werden muss '
        "(Kapitel 7.3).'"
    )
    op.execute(
        "CREATE INDEX scores_object_idx ON argus.scores (object_kind, object_id, computed_at DESC)"
    )
    op.execute("CREATE INDEX scores_priority_idx ON argus.scores (priority DESC, computed_at DESC)")

    # ------------------------------------------------------------------
    # assessments
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE argus.assessments (
            assessment_id  text PRIMARY KEY,
            schema_version text NOT NULL,
            kind           argus.assessment_kind NOT NULL,
            subject_kind   argus.object_kind NOT NULL,
            subject_id     text NOT NULL,
            statement      text NOT NULL,
            rationale      text,

            confidence     double precision NOT NULL
                CHECK (confidence >= 0 AND confidence <= 1),
            confidence_lower double precision,
            confidence_upper double precision,
            confidence_basis argus.confidence_basis NOT NULL DEFAULT 'unspecified',
            confidence_method text,

            author_type    argus.author_type NOT NULL,
            author_id      text NOT NULL,
            author_display_name text,
            -- Reproduzierbarkeit (Kapitel 11): ohne diese Angaben darf kein
            -- Modell-Output persistiert werden.
            model          text,
            model_version  text,
            prompt_id      text,
            prompt_hash    text,
            model_temperature double precision,
            model_parameters jsonb,

            -- Belege. Fuer maschinell erzeugte Aussagen Pflicht.
            evidence       jsonb NOT NULL DEFAULT '[]'::jsonb,

            validity       tstzrange,
            superseded_by  text,
            supersedes     text,

            outcome_verdict argus.outcome_verdict,
            outcome_decided_at timestamptz,
            outcome_decided_by text,
            outcome_error  double precision,
            outcome_note   text,

            visibility     argus.visibility NOT NULL DEFAULT 'org',
            owner_id       text NOT NULL,
            tags           text[] NOT NULL DEFAULT '{}',
            attributes     jsonb NOT NULL DEFAULT '{}'::jsonb,
            source_id      text REFERENCES argus.sources (source_id) ON DELETE SET NULL,
            raw_ref        text,
            observed_at    timestamptz,
            ingested_at    timestamptz NOT NULL DEFAULT clock_timestamp(),

            CONSTRAINT assessments_model_provenance
                CHECK (author_type <> 'model'
                       OR (model IS NOT NULL AND model_version IS NOT NULL AND prompt_hash IS NOT NULL)),
            CONSTRAINT assessments_machine_needs_evidence
                CHECK (author_type NOT IN ('model', 'detector')
                       OR jsonb_array_length(evidence) > 0),
            CONSTRAINT assessments_forecast_needs_validity
                CHECK (kind <> 'forecast' OR validity IS NOT NULL),
            CONSTRAINT assessments_confidence_interval
                CHECK ((confidence_lower IS NULL AND confidence_upper IS NULL)
                       OR (confidence_lower <= confidence AND confidence <= confidence_upper)),
            CONSTRAINT assessments_evidence_is_array
                CHECK (jsonb_typeof(evidence) = 'array')
        )
        """
    )
    op.execute(
        "ALTER TABLE argus.assessments ADD CONSTRAINT assessments_superseded_by_fk "
        "FOREIGN KEY (superseded_by) REFERENCES argus.assessments (assessment_id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX assessments_subject_idx ON argus.assessments (subject_kind, subject_id)"
    )
    op.execute("CREATE INDEX assessments_kind_idx ON argus.assessments (kind, ingested_at DESC)")
    op.execute("CREATE INDEX assessments_author_idx ON argus.assessments (author_type, author_id)")
    op.execute(
        "CREATE INDEX assessments_open_forecasts_idx ON argus.assessments (validity) "
        "WHERE kind = 'forecast' AND outcome_verdict IS NULL"
    )

    # ------------------------------------------------------------------
    # alerts
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE argus.alerts (
            alert_id       text PRIMARY KEY,
            schema_version text NOT NULL,
            rule_id        text NOT NULL,
            rule_version   text NOT NULL,
            detector_id    text,
            detector_version text,

            severity       argus.alert_severity NOT NULL,
            status         argus.alert_status NOT NULL DEFAULT 'new',
            title          text NOT NULL,
            description    text,

            entity_id      text REFERENCES argus.entities (entity_id) ON DELETE SET NULL,
            subject_ref_id text,
            aoi_id         text REFERENCES argus.aois (aoi_id) ON DELETE SET NULL,
            watchlist_ids  text[] NOT NULL DEFAULT '{}',

            geo            geography(Point, 4326),
            h3_r7          bigint,

            priority       double precision CHECK (priority IS NULL OR (priority >= 0 AND priority <= 100)),
            confidence     double precision CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),

            -- Throttling: derselbe Sachverhalt erzeugt keinen zweiten Alarm,
            -- sondern erhoeht occurrence_count.
            dedupe_key     text NOT NULL,
            occurrence_count integer NOT NULL DEFAULT 1 CHECK (occurrence_count >= 1),
            first_seen_at  timestamptz NOT NULL DEFAULT clock_timestamp(),
            last_seen_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
            aggregated_into_alert_id text,

            assignee_id    text,
            acked_by       text,
            acked_at       timestamptz,
            ack_note       text,
            resolved_by    text,
            resolved_at    timestamptz,
            resolution_disposition argus.resolution_disposition,
            resolution_note text,
            case_id        text,

            context_snapshot_ref text,
            runbook_ref    text,
            expires_at     timestamptz,

            tags           text[] NOT NULL DEFAULT '{}',
            attributes     jsonb NOT NULL DEFAULT '{}'::jsonb,
            observed_at    timestamptz,
            ingested_at    timestamptz NOT NULL DEFAULT clock_timestamp(),
            version        integer NOT NULL DEFAULT 1,

            CONSTRAINT alerts_resolved_needs_disposition
                CHECK (status NOT IN ('resolved', 'false_positive')
                       OR (resolved_at IS NOT NULL AND resolution_disposition IS NOT NULL)),
            CONSTRAINT alerts_acked_complete
                CHECK ((acked_at IS NULL) = (acked_by IS NULL)),
            CONSTRAINT alerts_seen_order CHECK (last_seen_at >= first_seen_at)
        )
        """
    )
    op.execute(
        "ALTER TABLE argus.alerts ADD CONSTRAINT alerts_aggregated_into_fk "
        "FOREIGN KEY (aggregated_into_alert_id) REFERENCES argus.alerts (alert_id) ON DELETE SET NULL"
    )
    # Ein offener Alarm je Sachverhalt. Genau hier wirkt die Alarmhygiene aus
    # Kapitel 9.2: ein zweiter Treffer findet die Zeile und zaehlt hoch.
    op.execute(
        "CREATE UNIQUE INDEX alerts_open_dedupe_idx ON argus.alerts (dedupe_key) "
        "WHERE status IN ('new', 'acked', 'investigating')"
    )
    op.execute(
        "CREATE INDEX alerts_queue_idx ON argus.alerts (status, severity DESC, last_seen_at DESC)"
    )
    op.execute(
        "CREATE INDEX alerts_assignee_idx ON argus.alerts (assignee_id) WHERE assignee_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX alerts_entity_idx ON argus.alerts (entity_id) WHERE entity_id IS NOT NULL"
    )
    op.execute("CREATE INDEX alerts_rule_idx ON argus.alerts (rule_id, ingested_at DESC)")
    op.execute("CREATE INDEX alerts_geo_idx ON argus.alerts USING gist (geo) WHERE geo IS NOT NULL")
    op.execute(
        "CREATE INDEX alerts_expiry_idx ON argus.alerts (expires_at) WHERE expires_at IS NOT NULL"
    )

    op.execute(
        """
        CREATE TABLE argus.alert_notifications (
            notification_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            alert_id     text NOT NULL REFERENCES argus.alerts (alert_id) ON DELETE CASCADE,
            channel      text NOT NULL,
            status       text NOT NULL,
            sent_at      timestamptz,
            attempts     integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            error        text,
            batch_id     text
        )
        """
    )
    op.execute("CREATE INDEX alert_notifications_alert_idx ON argus.alert_notifications (alert_id)")

    # ------------------------------------------------------------------
    # cases
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE argus.cases (
            case_id        text PRIMARY KEY,
            schema_version text NOT NULL,
            title          text NOT NULL,
            description    text,
            status         argus.case_status NOT NULL DEFAULT 'open',
            priority       argus.case_priority NOT NULL DEFAULT 'medium',
            owner_id       text NOT NULL,
            assignee_ids   text[] NOT NULL DEFAULT '{}',
            aoi_ids        text[] NOT NULL DEFAULT '{}',
            period         tstzrange,
            tags           text[] NOT NULL DEFAULT '{}',
            visibility     argus.visibility NOT NULL DEFAULT 'team',
            shared_with    text[] NOT NULL DEFAULT '{}',
            closure_reason text,
            closed_at      timestamptz,
            contains_personal_data boolean NOT NULL DEFAULT false,
            attributes     jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
            updated_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
            CONSTRAINT cases_closed_needs_reason
                CHECK (status <> 'closed' OR (closed_at IS NOT NULL AND closure_reason IS NOT NULL))
        )
        """
    )
    op.execute(
        "ALTER TABLE argus.alerts ADD CONSTRAINT alerts_case_fk "
        "FOREIGN KEY (case_id) REFERENCES argus.cases (case_id) ON DELETE SET NULL"
    )
    op.execute(
        """
        CREATE TABLE argus.case_items (
            case_id     text NOT NULL REFERENCES argus.cases (case_id) ON DELETE CASCADE,
            object_kind argus.object_kind NOT NULL,
            object_id   text NOT NULL,
            role        text,
            is_key_item boolean NOT NULL DEFAULT false,
            note        text,
            added_by    text NOT NULL,
            added_at    timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (case_id, object_kind, object_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE argus.case_notes (
            note_id     text PRIMARY KEY,
            case_id     text NOT NULL REFERENCES argus.cases (case_id) ON DELETE CASCADE,
            author_id   text NOT NULL,
            body        text NOT NULL,
            mentions    text[] NOT NULL DEFAULT '{}',
            anchor_kind argus.object_kind,
            anchor_id   text,
            created_at  timestamptz NOT NULL DEFAULT clock_timestamp(),
            updated_at  timestamptz NOT NULL DEFAULT clock_timestamp()
        )
        """
    )
    op.execute("CREATE INDEX case_notes_case_idx ON argus.case_notes (case_id, created_at)")
    op.execute("CREATE INDEX case_items_object_idx ON argus.case_items (object_kind, object_id)")
    op.execute(
        "CREATE TRIGGER cases_set_updated_at BEFORE UPDATE ON argus.cases "
        "FOR EACH ROW EXECUTE FUNCTION argus.set_updated_at()"
    )

    # ------------------------------------------------------------------
    # data_gaps — Luecken sind ein eigenes Objekt, kein Fehlen von Zeilen
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE argus.data_gaps (
            gap_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_id   text REFERENCES argus.sources (source_id) ON DELETE CASCADE,
            object_kind argus.object_kind,
            object_id   text,
            gap_start   timestamptz NOT NULL,
            gap_end     timestamptz,
            reason      argus.gap_reason NOT NULL,
            detail      text,
            area        geography(Geometry, 4326),
            detected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            CONSTRAINT data_gaps_time_order CHECK (gap_end IS NULL OR gap_end >= gap_start)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE argus.data_gaps IS "
        "'Bekannte Luecken. Werden ausdruecklich transportiert und dargestellt, "
        "statt durch Interpolation kaschiert zu werden (Prinzip 4).'"
    )
    op.execute("CREATE INDEX data_gaps_source_idx ON argus.data_gaps (source_id, gap_start DESC)")
    op.execute(
        "CREATE INDEX data_gaps_open_idx ON argus.data_gaps (gap_start DESC) WHERE gap_end IS NULL"
    )


def downgrade() -> None:
    guard_destructive_downgrade(
        "data_gaps",
        "case_notes",
        "case_items",
        "cases",
        "alert_notifications",
        "alerts",
        "assessments",
        "score_factors",
        "scores",
        "watchlist_members",
        "watchlists",
        "aois",
    )
    op.execute("DROP TABLE IF EXISTS argus.data_gaps")
    op.execute("ALTER TABLE argus.alerts DROP CONSTRAINT IF EXISTS alerts_case_fk")
    op.execute("DROP TABLE IF EXISTS argus.case_notes")
    op.execute("DROP TABLE IF EXISTS argus.case_items")
    op.execute("DROP TABLE IF EXISTS argus.cases")
    op.execute("DROP TABLE IF EXISTS argus.alert_notifications")
    op.execute("DROP TABLE IF EXISTS argus.alerts")
    op.execute("DROP TABLE IF EXISTS argus.assessments")
    op.execute("DROP TABLE IF EXISTS argus.score_factors")
    op.execute("DROP TABLE IF EXISTS argus.scores")
    op.execute("DROP TABLE IF EXISTS argus.watchlist_members")
    op.execute("DROP TABLE IF EXISTS argus.watchlists")
    op.execute("DROP TABLE IF EXISTS argus.aois")
