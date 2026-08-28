-- ARGUS — DDL-Referenz des Schemas argus.
--
-- ERZEUGT, NICHT VON HAND GEPFLEGT.
-- Quelle der Wahrheit sind die Alembic-Migrationen unter
-- services/api/migrations/. Diese Datei entsteht daraus mit
--     services/api/scripts/dump_schema.sh
-- und dient zwei Zwecken:
--   * Nachschlagewerk beim Schreiben von Abfragen, ohne acht Migrationen zu lesen
--   * Grundlage fuer Code-Review: eine Aenderung am Schema ist hier sichtbar
--
-- Die Tagespartitionen von argus.observations sind ausgelassen - sie entstehen
-- zur Laufzeit und wiederholen nur die Definition der Elterntabelle.
--
-- Ebenfalls entfernt: die \\restrict-Marken neuerer pg_dump-Versionen. Sie
-- enthalten bei jedem Lauf ein anderes Zufallstoken und wuerden die Datei bei
-- jedem Erzeugen aendern, ohne dass sich am Schema etwas geaendert haette.
--
-- Der Test tests/test_ddl_reference.py schlaegt fehl, sobald diese Datei von
-- den Migrationen abweicht.

--
--

--
-- Name: argus; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA argus;

--
-- Name: alert_severity; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.alert_severity AS ENUM (
    'unspecified',
    'watch',
    'notify',
    'alert',
    'critical'
);

--
-- Name: alert_status; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.alert_status AS ENUM (
    'unspecified',
    'new',
    'acked',
    'investigating',
    'resolved',
    'false_positive',
    'suppressed',
    'expired'
);

--
-- Name: alias_kind; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.alias_kind AS ENUM (
    'unspecified',
    'name',
    'former_name',
    'transliteration',
    'translation',
    'abbreviation',
    'callsign',
    'trade_name'
);

--
-- Name: aoi_kind; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.aoi_kind AS ENUM (
    'unspecified',
    'polygon',
    'circle',
    'corridor',
    'named_zone',
    'dynamic'
);

--
-- Name: assessment_kind; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.assessment_kind AS ENUM (
    'unspecified',
    'hypothesis',
    'judgement',
    'forecast',
    'classification',
    'correlation',
    'risk',
    'attribution'
);

--
-- Name: author_type; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.author_type AS ENUM (
    'unspecified',
    'human',
    'model',
    'rule',
    'detector',
    'external'
);

--
-- Name: case_priority; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.case_priority AS ENUM (
    'unspecified',
    'low',
    'medium',
    'high',
    'urgent'
);

--
-- Name: case_status; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.case_status AS ENUM (
    'unspecified',
    'open',
    'investigating',
    'on_hold',
    'closed',
    'archived'
);

--
-- Name: confidence_basis; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.confidence_basis AS ENUM (
    'unspecified',
    'model',
    'rule',
    'human_judgement',
    'statistical',
    'corroboration'
);

--
-- Name: entity_role; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.entity_role AS ENUM (
    'unspecified',
    'actor',
    'target',
    'affected',
    'location',
    'mentioned',
    'source',
    'operator',
    'owner'
);

--
-- Name: entity_type; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.entity_type AS ENUM (
    'unspecified',
    'unknown',
    'vessel',
    'aircraft',
    'organization',
    'person',
    'place',
    'port',
    'airport',
    'facility',
    'pipeline',
    'submarine_cable',
    'vehicle',
    'satellite',
    'financial_instrument',
    'commodity',
    'admin_area',
    'maritime_zone',
    'airspace',
    'network_asset',
    'event_series'
);

--
-- Name: event_link_type; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.event_link_type AS ENUM (
    'unspecified',
    'duplicate_of',
    'part_of',
    'follows',
    'caused_by_hypothesis',
    'contradicts',
    'updates',
    'correlated_with'
);

--
-- Name: event_status; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.event_status AS ENUM (
    'unspecified',
    'rumored',
    'reported',
    'confirmed',
    'disputed',
    'retracted',
    'superseded',
    'scheduled'
);

--
-- Name: evidence_kind; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.evidence_kind AS ENUM (
    'unspecified',
    'report',
    'observation',
    'event',
    'entity',
    'relation',
    'track',
    'detector_hit',
    'external_document',
    'human_statement'
);

--
-- Name: gap_reason; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.gap_reason AS ENUM (
    'unspecified',
    'source_unavailable',
    'rate_limited',
    'no_coverage',
    'signal_loss',
    'filtered',
    'license_restricted',
    'pipeline_failure',
    'unknown'
);

--
-- Name: geo_precision; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.geo_precision AS ENUM (
    'unspecified',
    'exact',
    'building',
    'city',
    'admin1',
    'country',
    'maritime_zone',
    'unknown'
);

--
-- Name: identifier_stability; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.identifier_stability AS ENUM (
    'unspecified',
    'stable',
    'mutable',
    'ephemeral'
);

--
-- Name: information_credibility; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.information_credibility AS ENUM (
    'unspecified',
    '1',
    '2',
    '3',
    '4',
    '5',
    '6'
);

--
-- Name: match_mode; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.match_mode AS ENUM (
    'unspecified',
    'exact_id',
    'entity',
    'pattern',
    'fuzzy_name',
    'attribute'
);

--
-- Name: object_kind; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.object_kind AS ENUM (
    'unspecified',
    'observation',
    'event',
    'entity',
    'relation',
    'report',
    'track',
    'assessment',
    'source',
    'aoi',
    'watchlist',
    'alert',
    'case'
);

--
-- Name: observation_kind; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.observation_kind AS ENUM (
    'unspecified',
    'position',
    'status',
    'measurement',
    'static_data'
);

--
-- Name: outcome_verdict; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.outcome_verdict AS ENUM (
    'unspecified',
    'confirmed',
    'partially_confirmed',
    'refuted',
    'undecidable',
    'expired'
);

--
-- Name: relation_type; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.relation_type AS ENUM (
    'unspecified',
    'owns',
    'beneficial_owner_of',
    'controls',
    'operates',
    'manages',
    'subsidiary_of',
    'parent_of',
    'director_of',
    'employed_by',
    'member_of',
    'registered_in',
    'flagged_in',
    'located_at',
    'docked_at',
    'supplies_to',
    'customer_of',
    'transported_by',
    'sanctioned_by',
    'part_of',
    'connected_to',
    'rendezvous_with',
    'successor_of',
    'associated_with',
    'other'
);

--
-- Name: report_kind; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.report_kind AS ENUM (
    'unspecified',
    'news_article',
    'agency_wire',
    'press_release',
    'government_notice',
    'regulatory_filing',
    'social_post',
    'blog',
    'situation_report',
    'advisory',
    'dataset_record'
);

--
-- Name: resolution_disposition; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.resolution_disposition AS ENUM (
    'unspecified',
    'true_positive',
    'false_positive',
    'benign',
    'duplicate',
    'data_quality',
    'undetermined'
);

--
-- Name: resolution_status; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.resolution_status AS ENUM (
    'unspecified',
    'pending',
    'unresolved',
    'resolved',
    'ambiguous',
    'conflicted',
    'merged'
);

--
-- Name: sanction_status; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.sanction_status AS ENUM (
    'unspecified',
    'none',
    'listed',
    'delisted',
    'associated',
    'possible_match',
    'not_checked'
);

--
-- Name: source_domain; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.source_domain AS ENUM (
    'unspecified',
    'aviation',
    'maritime',
    'news',
    'economic',
    'conflict',
    'disaster',
    'corporate',
    'sanctions',
    'geo',
    'weather',
    'space',
    'cyber',
    'infrastructure'
);

--
-- Name: source_kind; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.source_kind AS ENUM (
    'unspecified',
    'rest_api',
    'stream',
    'feed',
    'batch_file',
    'webhook',
    'sensor',
    'manual',
    'derived'
);

--
-- Name: source_reliability; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.source_reliability AS ENUM (
    'unspecified',
    'a',
    'b',
    'c',
    'd',
    'e',
    'f'
);

--
-- Name: time_precision; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.time_precision AS ENUM (
    'unspecified',
    'second',
    'minute',
    'hour',
    'day',
    'month',
    'year',
    'unknown'
);

--
-- Name: time_quality; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.time_quality AS ENUM (
    'unspecified',
    'source_provided',
    'source_provided_coarse',
    'inferred_from_ingest',
    'implausible',
    'missing'
);

--
-- Name: visibility; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.visibility AS ENUM (
    'unspecified',
    'private',
    'team',
    'org',
    'public'
);

--
-- Name: zone_type; Type: TYPE; Schema: argus; Owner: -
--

CREATE TYPE argus.zone_type AS ENUM (
    'unspecified',
    'eez',
    'territorial_waters',
    'strait',
    'port_limit',
    'anchorage',
    'fir',
    'restricted_airspace',
    'admin_area',
    'sanction_zone',
    'chokepoint'
);

--
-- Name: assert_foreign_keys_have_delete_rule(); Type: FUNCTION; Schema: argus; Owner: -
--

CREATE FUNCTION argus.assert_foreign_keys_have_delete_rule() RETURNS void
    LANGUAGE plpgsql
    AS $$
        DECLARE
            offenders text;
        BEGIN
            SELECT string_agg(format('%s.%s', c.relname, con.conname), ', ' ORDER BY c.relname)
              INTO offenders
              FROM pg_constraint con
              JOIN pg_class c ON c.oid = con.conrelid
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'argus'
               AND con.contype = 'f'
               AND con.confdeltype = 'a';  -- 'a' = NO ACTION, also nicht gesetzt
            IF offenders IS NOT NULL THEN
                RAISE EXCEPTION
                    'Fremdschluessel ohne ausdrueckliches ON DELETE: %', offenders;
            END IF;
        END $$;

--
-- Name: assert_no_naive_timestamps(); Type: FUNCTION; Schema: argus; Owner: -
--

CREATE FUNCTION argus.assert_no_naive_timestamps() RETURNS void
    LANGUAGE plpgsql
    AS $$
        DECLARE
            offenders text;
        BEGIN
            SELECT string_agg(format('%s.%s (%s)', table_name, column_name, data_type), ', '
                              ORDER BY table_name, column_name)
              INTO offenders
              FROM information_schema.columns
             WHERE table_schema = 'argus'
               AND data_type IN ('timestamp without time zone', 'time without time zone');
            IF offenders IS NOT NULL THEN
                RAISE EXCEPTION
                    'Zeitzonenfalle: % - ARGUS rechnet ausschliesslich in UTC, '
                    'alle Zeitspalten muessen timestamptz sein', offenders;
            END IF;
        END $$;

--
-- Name: current_user_id(); Type: FUNCTION; Schema: argus; Owner: -
--

CREATE FUNCTION argus.current_user_id() RETURNS text
    LANGUAGE sql STABLE
    AS $$
            SELECT nullif(current_setting('argus.user_id', true), '')
        $$;

--
-- Name: current_user_teams(); Type: FUNCTION; Schema: argus; Owner: -
--

CREATE FUNCTION argus.current_user_teams() RETURNS text[]
    LANGUAGE sql STABLE
    AS $$
            SELECT coalesce(
                string_to_array(nullif(current_setting('argus.teams', true), ''), ','),
                ARRAY[]::text[]
            )
        $$;

--
-- Name: drop_observation_partitions_older_than(interval); Type: FUNCTION; Schema: argus; Owner: -
--

CREATE FUNCTION argus.drop_observation_partitions_older_than(p_age interval DEFAULT '90 days'::interval) RETURNS TABLE(dropped_partition text)
    LANGUAGE plpgsql
    AS $_$
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
            END $_$;

--
-- Name: ensure_observation_partitions(date, date); Type: FUNCTION; Schema: argus; Owner: -
--

CREATE FUNCTION argus.ensure_observation_partitions(p_from date DEFAULT (CURRENT_DATE - 1), p_to date DEFAULT (CURRENT_DATE + 7)) RETURNS integer
    LANGUAGE plpgsql
    AS $$
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
            END $$;

--
-- Name: ts_config(text); Type: FUNCTION; Schema: argus; Owner: -
--

CREATE FUNCTION argus.ts_config(lang text) RETURNS regconfig
    LANGUAGE sql IMMUTABLE PARALLEL SAFE
    AS $$
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
        $$;

--
-- Name: events; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.events (
    event_id text NOT NULL,
    schema_version text NOT NULL,
    type text NOT NULL,
    title text NOT NULL,
    summary text,
    lang text DEFAULT 'und'::text NOT NULL,
    occurred_start timestamp with time zone NOT NULL,
    occurred_end timestamp with time zone,
    occurred_precision argus.time_precision DEFAULT 'unspecified'::argus.time_precision NOT NULL,
    is_ongoing boolean DEFAULT false NOT NULL,
    geo public.geography(Geometry,4326),
    geo_point public.geography(Point,4326),
    geo_point_is_derived boolean DEFAULT false NOT NULL,
    geo_precision argus.geo_precision DEFAULT 'unspecified'::argus.geo_precision NOT NULL,
    geo_uncertainty_radius_m double precision,
    place_name text,
    place_country text,
    place_wikidata_qid text,
    h3_r5 bigint,
    h3_r7 bigint,
    severity double precision DEFAULT 0 NOT NULL,
    confidence double precision DEFAULT 0 NOT NULL,
    status argus.event_status DEFAULT 'reported'::argus.event_status NOT NULL,
    magnitude_scale text,
    magnitude_value double precision,
    magnitude_unit text,
    magnitude_expected double precision,
    magnitude_previous double precision,
    independent_sources integer DEFAULT 0 NOT NULL,
    contradicting_sources integer DEFAULT 0 NOT NULL,
    first_seen_source text,
    first_seen_at timestamp with time zone,
    story_cluster_id text,
    priority double precision,
    retracted_at timestamp with time zone,
    retracted_by_source text,
    retraction_reason text,
    retraction_inferred boolean DEFAULT false NOT NULL,
    superseded_by_event_id text,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    attributes jsonb DEFAULT '{}'::jsonb NOT NULL,
    dedupe_key text,
    source_id text,
    raw_ref text,
    observed_at timestamp with time zone,
    ingested_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    sys_period tstzrange DEFAULT tstzrange(clock_timestamp(), NULL::timestamp with time zone, '[)'::text) NOT NULL,
    search_tsv tsvector GENERATED ALWAYS AS (((setweight(to_tsvector(argus.ts_config(lang), COALESCE(title, ''::text)), 'A'::"char") || setweight(to_tsvector(argus.ts_config(lang), COALESCE(summary, ''::text)), 'B'::"char")) || setweight(to_tsvector('simple'::regconfig, COALESCE(place_name, ''::text)), 'C'::"char"))) STORED,
    CONSTRAINT events_confidence_check CHECK (((confidence >= (0)::double precision) AND (confidence <= (1)::double precision))),
    CONSTRAINT events_contradicting_sources_check CHECK ((contradicting_sources >= 0)),
    CONSTRAINT events_derived_point_marked CHECK (((geo_point IS NULL) OR (geo_precision = ANY (ARRAY['exact'::argus.geo_precision, 'building'::argus.geo_precision])) OR geo_point_is_derived)),
    CONSTRAINT events_geo_uncertainty_radius_m_check CHECK (((geo_uncertainty_radius_m IS NULL) OR (geo_uncertainty_radius_m >= (0)::double precision))),
    CONSTRAINT events_independent_sources_check CHECK ((independent_sources >= 0)),
    CONSTRAINT events_place_country_check CHECK (((place_country IS NULL) OR (place_country ~ '^[A-Z]{2}$'::text))),
    CONSTRAINT events_priority_check CHECK (((priority IS NULL) OR ((priority >= (0)::double precision) AND (priority <= (100)::double precision)))),
    CONSTRAINT events_retraction_complete CHECK (((status <> 'retracted'::argus.event_status) OR ((retracted_at IS NOT NULL) AND (retraction_reason IS NOT NULL)))),
    CONSTRAINT events_severity_check CHECK (((severity >= (0)::double precision) AND (severity <= (1)::double precision))),
    CONSTRAINT events_time_order CHECK (((occurred_end IS NULL) OR (occurred_end >= occurred_start))),
    CONSTRAINT events_type_path CHECK ((type ~ '^[a-z0-9]+(\.[a-z0-9_]+)*$'::text))
);

--
-- Name: event_as_of(text, timestamp with time zone); Type: FUNCTION; Schema: argus; Owner: -
--

CREATE FUNCTION argus.event_as_of(p_event_id text, p_at timestamp with time zone) RETURNS SETOF argus.events
    LANGUAGE sql STABLE
    AS $$
            SELECT * FROM argus.events
             WHERE event_id = p_event_id AND sys_period @> p_at
            UNION ALL
            SELECT * FROM argus.events_history
             WHERE event_id = p_event_id AND sys_period @> p_at
        $$;

--
-- Name: observations_maintenance(); Type: FUNCTION; Schema: argus; Owner: -
--

CREATE FUNCTION argus.observations_maintenance() RETURNS TABLE(action text, detail text)
    LANGUAGE plpgsql
    AS $$
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
            END $$;

--
-- Name: set_updated_at(); Type: FUNCTION; Schema: argus; Owner: -
--

CREATE FUNCTION argus.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            NEW.updated_at := clock_timestamp();
            RETURN NEW;
        END $$;

--
-- Name: versioning_trigger(); Type: FUNCTION; Schema: argus; Owner: -
--

CREATE FUNCTION argus.versioning_trigger() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
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
        END $_$;

--
-- Name: alert_notifications; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.alert_notifications (
    notification_id bigint NOT NULL,
    alert_id text NOT NULL,
    channel text NOT NULL,
    status text NOT NULL,
    sent_at timestamp with time zone,
    attempts integer DEFAULT 0 NOT NULL,
    error text,
    batch_id text,
    CONSTRAINT alert_notifications_attempts_check CHECK ((attempts >= 0))
);

--
-- Name: alert_notifications_notification_id_seq; Type: SEQUENCE; Schema: argus; Owner: -
--

ALTER TABLE argus.alert_notifications ALTER COLUMN notification_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME argus.alert_notifications_notification_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: alerts; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.alerts (
    alert_id text NOT NULL,
    schema_version text NOT NULL,
    rule_id text NOT NULL,
    rule_version text NOT NULL,
    detector_id text,
    detector_version text,
    severity argus.alert_severity NOT NULL,
    status argus.alert_status DEFAULT 'new'::argus.alert_status NOT NULL,
    title text NOT NULL,
    description text,
    entity_id text,
    subject_ref_id text,
    aoi_id text,
    watchlist_ids text[] DEFAULT '{}'::text[] NOT NULL,
    geo public.geography(Point,4326),
    h3_r7 bigint,
    priority double precision,
    confidence double precision,
    dedupe_key text NOT NULL,
    occurrence_count integer DEFAULT 1 NOT NULL,
    first_seen_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    aggregated_into_alert_id text,
    assignee_id text,
    acked_by text,
    acked_at timestamp with time zone,
    ack_note text,
    resolved_by text,
    resolved_at timestamp with time zone,
    resolution_disposition argus.resolution_disposition,
    resolution_note text,
    case_id text,
    context_snapshot_ref text,
    runbook_ref text,
    expires_at timestamp with time zone,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    attributes jsonb DEFAULT '{}'::jsonb NOT NULL,
    observed_at timestamp with time zone,
    ingested_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    CONSTRAINT alerts_acked_complete CHECK (((acked_at IS NULL) = (acked_by IS NULL))),
    CONSTRAINT alerts_confidence_check CHECK (((confidence IS NULL) OR ((confidence >= (0)::double precision) AND (confidence <= (1)::double precision)))),
    CONSTRAINT alerts_occurrence_count_check CHECK ((occurrence_count >= 1)),
    CONSTRAINT alerts_priority_check CHECK (((priority IS NULL) OR ((priority >= (0)::double precision) AND (priority <= (100)::double precision)))),
    CONSTRAINT alerts_resolved_needs_disposition CHECK (((status <> ALL (ARRAY['resolved'::argus.alert_status, 'false_positive'::argus.alert_status])) OR ((resolved_at IS NOT NULL) AND (resolution_disposition IS NOT NULL)))),
    CONSTRAINT alerts_seen_order CHECK ((last_seen_at >= first_seen_at))
);

--
-- Name: aois; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.aois (
    aoi_id text NOT NULL,
    schema_version text NOT NULL,
    name text NOT NULL,
    description text,
    kind argus.aoi_kind NOT NULL,
    geom public.geography(Geometry,4326),
    zone_type argus.zone_type DEFAULT 'unspecified'::argus.zone_type NOT NULL,
    zone_id text,
    zone_dataset text,
    anchor_entity_id text,
    anchor_radius_m double precision,
    h3_r5_cells bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    h3_r7_cells bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    proximity_decay_km double precision DEFAULT 50 NOT NULL,
    weight double precision DEFAULT 1 NOT NULL,
    min_priority double precision,
    event_type_filter text[] DEFAULT '{}'::text[] NOT NULL,
    area_m2 double precision,
    owner_id text NOT NULL,
    visibility argus.visibility DEFAULT 'private'::argus.visibility NOT NULL,
    shared_with text[] DEFAULT '{}'::text[] NOT NULL,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    active boolean DEFAULT true NOT NULL,
    attributes jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT aois_anchor_radius_m_check CHECK (((anchor_radius_m IS NULL) OR (anchor_radius_m > (0)::double precision))),
    CONSTRAINT aois_area_m2_check CHECK (((area_m2 IS NULL) OR (area_m2 >= (0)::double precision))),
    CONSTRAINT aois_dynamic_has_anchor CHECK (((kind <> 'dynamic'::argus.aoi_kind) OR ((anchor_entity_id IS NOT NULL) AND (anchor_radius_m IS NOT NULL)))),
    CONSTRAINT aois_geometry_present CHECK (((kind = 'dynamic'::argus.aoi_kind) OR (geom IS NOT NULL))),
    CONSTRAINT aois_min_priority_check CHECK (((min_priority IS NULL) OR ((min_priority >= (0)::double precision) AND (min_priority <= (100)::double precision)))),
    CONSTRAINT aois_named_zone_has_id CHECK (((kind <> 'named_zone'::argus.aoi_kind) OR (zone_id IS NOT NULL))),
    CONSTRAINT aois_proximity_decay_km_check CHECK ((proximity_decay_km > (0)::double precision)),
    CONSTRAINT aois_weight_check CHECK ((weight >= (0)::double precision))
);

ALTER TABLE ONLY argus.aois FORCE ROW LEVEL SECURITY;

--
-- Name: assessments; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.assessments (
    assessment_id text NOT NULL,
    schema_version text NOT NULL,
    kind argus.assessment_kind NOT NULL,
    subject_kind argus.object_kind NOT NULL,
    subject_id text NOT NULL,
    statement text NOT NULL,
    rationale text,
    confidence double precision NOT NULL,
    confidence_lower double precision,
    confidence_upper double precision,
    confidence_basis argus.confidence_basis DEFAULT 'unspecified'::argus.confidence_basis NOT NULL,
    confidence_method text,
    author_type argus.author_type NOT NULL,
    author_id text NOT NULL,
    author_display_name text,
    model text,
    model_version text,
    prompt_id text,
    prompt_hash text,
    model_temperature double precision,
    model_parameters jsonb,
    evidence jsonb DEFAULT '[]'::jsonb NOT NULL,
    validity tstzrange,
    superseded_by text,
    supersedes text,
    outcome_verdict argus.outcome_verdict,
    outcome_decided_at timestamp with time zone,
    outcome_decided_by text,
    outcome_error double precision,
    outcome_note text,
    visibility argus.visibility DEFAULT 'org'::argus.visibility NOT NULL,
    owner_id text NOT NULL,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    attributes jsonb DEFAULT '{}'::jsonb NOT NULL,
    source_id text,
    raw_ref text,
    observed_at timestamp with time zone,
    ingested_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT assessments_confidence_check CHECK (((confidence >= (0)::double precision) AND (confidence <= (1)::double precision))),
    CONSTRAINT assessments_confidence_interval CHECK ((((confidence_lower IS NULL) AND (confidence_upper IS NULL)) OR ((confidence_lower <= confidence) AND (confidence <= confidence_upper)))),
    CONSTRAINT assessments_evidence_is_array CHECK ((jsonb_typeof(evidence) = 'array'::text)),
    CONSTRAINT assessments_forecast_needs_validity CHECK (((kind <> 'forecast'::argus.assessment_kind) OR (validity IS NOT NULL))),
    CONSTRAINT assessments_machine_needs_evidence CHECK (((author_type <> ALL (ARRAY['model'::argus.author_type, 'detector'::argus.author_type])) OR (jsonb_array_length(evidence) > 0))),
    CONSTRAINT assessments_model_provenance CHECK (((author_type <> 'model'::argus.author_type) OR ((model IS NOT NULL) AND (model_version IS NOT NULL) AND (prompt_hash IS NOT NULL))))
);

ALTER TABLE ONLY argus.assessments FORCE ROW LEVEL SECURITY;

--
-- Name: case_items; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.case_items (
    case_id text NOT NULL,
    object_kind argus.object_kind NOT NULL,
    object_id text NOT NULL,
    role text,
    is_key_item boolean DEFAULT false NOT NULL,
    note text,
    added_by text NOT NULL,
    added_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);

ALTER TABLE ONLY argus.case_items FORCE ROW LEVEL SECURITY;

--
-- Name: case_notes; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.case_notes (
    note_id text NOT NULL,
    case_id text NOT NULL,
    author_id text NOT NULL,
    body text NOT NULL,
    mentions text[] DEFAULT '{}'::text[] NOT NULL,
    anchor_kind argus.object_kind,
    anchor_id text,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);

ALTER TABLE ONLY argus.case_notes FORCE ROW LEVEL SECURITY;

--
-- Name: cases; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.cases (
    case_id text NOT NULL,
    schema_version text NOT NULL,
    title text NOT NULL,
    description text,
    status argus.case_status DEFAULT 'open'::argus.case_status NOT NULL,
    priority argus.case_priority DEFAULT 'medium'::argus.case_priority NOT NULL,
    owner_id text NOT NULL,
    assignee_ids text[] DEFAULT '{}'::text[] NOT NULL,
    aoi_ids text[] DEFAULT '{}'::text[] NOT NULL,
    period tstzrange,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    visibility argus.visibility DEFAULT 'team'::argus.visibility NOT NULL,
    shared_with text[] DEFAULT '{}'::text[] NOT NULL,
    closure_reason text,
    closed_at timestamp with time zone,
    contains_personal_data boolean DEFAULT false NOT NULL,
    attributes jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT cases_closed_needs_reason CHECK (((status <> 'closed'::argus.case_status) OR ((closed_at IS NOT NULL) AND (closure_reason IS NOT NULL))))
);

ALTER TABLE ONLY argus.cases FORCE ROW LEVEL SECURITY;

--
-- Name: data_gaps; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.data_gaps (
    gap_id bigint NOT NULL,
    source_id text,
    object_kind argus.object_kind,
    object_id text,
    gap_start timestamp with time zone NOT NULL,
    gap_end timestamp with time zone,
    reason argus.gap_reason NOT NULL,
    detail text,
    area public.geography(Geometry,4326),
    detected_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT data_gaps_time_order CHECK (((gap_end IS NULL) OR (gap_end >= gap_start)))
);

--
-- Name: data_gaps_gap_id_seq; Type: SEQUENCE; Schema: argus; Owner: -
--

ALTER TABLE argus.data_gaps ALTER COLUMN gap_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME argus.data_gaps_gap_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: entities; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.entities (
    entity_id text NOT NULL,
    schema_version text NOT NULL,
    type argus.entity_type NOT NULL,
    display_name text NOT NULL,
    watchlist_ids text[] DEFAULT '{}'::text[] NOT NULL,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    sanction_status argus.sanction_status DEFAULT 'not_checked'::argus.sanction_status NOT NULL,
    last_position public.geography(Point,4326),
    last_position_h3_r7 bigint,
    last_position_at timestamp with time zone,
    first_seen_at timestamp with time zone,
    last_seen_at timestamp with time zone,
    existence tstzrange,
    is_active boolean DEFAULT true NOT NULL,
    merged_into_entity_id text,
    resolution_status argus.resolution_status DEFAULT 'resolved'::argus.resolution_status NOT NULL,
    resolver_version text,
    contains_personal_data boolean DEFAULT false NOT NULL,
    personal_data_basis text,
    purge_after timestamp with time zone,
    attributes jsonb DEFAULT '{}'::jsonb NOT NULL,
    source_id text,
    raw_ref text,
    observed_at timestamp with time zone,
    ingested_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    sys_period tstzrange DEFAULT tstzrange(clock_timestamp(), NULL::timestamp with time zone, '[)'::text) NOT NULL,
    CONSTRAINT entities_merge_not_self CHECK ((merged_into_entity_id IS DISTINCT FROM entity_id)),
    CONSTRAINT entities_personal_data_needs_basis CHECK (((NOT contains_personal_data) OR (personal_data_basis IS NOT NULL)))
);

--
-- Name: entities_history; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.entities_history (
    entity_id text NOT NULL,
    schema_version text NOT NULL,
    type argus.entity_type NOT NULL,
    display_name text NOT NULL,
    watchlist_ids text[] NOT NULL,
    tags text[] NOT NULL,
    sanction_status argus.sanction_status NOT NULL,
    last_position public.geography(Point,4326),
    last_position_h3_r7 bigint,
    last_position_at timestamp with time zone,
    first_seen_at timestamp with time zone,
    last_seen_at timestamp with time zone,
    existence tstzrange,
    is_active boolean NOT NULL,
    merged_into_entity_id text,
    resolution_status argus.resolution_status NOT NULL,
    resolver_version text,
    contains_personal_data boolean NOT NULL,
    personal_data_basis text,
    purge_after timestamp with time zone,
    attributes jsonb NOT NULL,
    source_id text,
    raw_ref text,
    observed_at timestamp with time zone,
    ingested_at timestamp with time zone NOT NULL,
    version integer NOT NULL,
    sys_period tstzrange NOT NULL
);

--
-- Name: entity_aliases; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.entity_aliases (
    alias_id bigint NOT NULL,
    entity_id text NOT NULL,
    id_type text NOT NULL,
    id_value text NOT NULL,
    stability argus.identifier_stability DEFAULT 'unspecified'::argus.identifier_stability NOT NULL,
    alias_kind argus.alias_kind DEFAULT 'unspecified'::argus.alias_kind NOT NULL,
    lang text,
    script text,
    is_primary boolean DEFAULT false NOT NULL,
    validity tstzrange DEFAULT tstzrange(NULL::timestamp with time zone, NULL::timestamp with time zone, '[)'::text) NOT NULL,
    source_id text,
    confidence double precision,
    ingested_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT entity_aliases_confidence_check CHECK (((confidence IS NULL) OR ((confidence >= (0)::double precision) AND (confidence <= (1)::double precision)))),
    CONSTRAINT entity_aliases_id_type_lowercase CHECK ((id_type = lower(id_type))),
    CONSTRAINT entity_aliases_value_not_blank CHECK ((length(btrim(id_value)) > 0))
);

--
-- Name: entity_aliases_alias_id_seq; Type: SEQUENCE; Schema: argus; Owner: -
--

ALTER TABLE argus.entity_aliases ALTER COLUMN alias_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME argus.entity_aliases_alias_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: entity_sanctions; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.entity_sanctions (
    listing_row_id bigint NOT NULL,
    entity_id text NOT NULL,
    list_id text NOT NULL,
    listing_id text NOT NULL,
    program text,
    listed_at timestamp with time zone,
    delisted_at timestamp with time zone,
    match_confidence double precision NOT NULL,
    matched_on text NOT NULL,
    url text,
    source_id text,
    ingested_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT entity_sanctions_dates CHECK (((delisted_at IS NULL) OR (listed_at IS NULL) OR (delisted_at >= listed_at))),
    CONSTRAINT entity_sanctions_match_confidence_check CHECK (((match_confidence >= (0)::double precision) AND (match_confidence <= (1)::double precision)))
);

--
-- Name: entity_sanctions_listing_row_id_seq; Type: SEQUENCE; Schema: argus; Owner: -
--

ALTER TABLE argus.entity_sanctions ALTER COLUMN listing_row_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME argus.entity_sanctions_listing_row_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: event_contradictions; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.event_contradictions (
    contradiction_id bigint NOT NULL,
    event_id text NOT NULL,
    field_path text NOT NULL,
    claims jsonb NOT NULL,
    preferred_claim_index integer,
    note text,
    detected_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    resolved_at timestamp with time zone,
    CONSTRAINT event_contradictions_claims_is_array CHECK (((jsonb_typeof(claims) = 'array'::text) AND (jsonb_array_length(claims) >= 2))),
    CONSTRAINT event_contradictions_preferred_claim_index_check CHECK (((preferred_claim_index IS NULL) OR (preferred_claim_index >= 0)))
);

--
-- Name: event_contradictions_contradiction_id_seq; Type: SEQUENCE; Schema: argus; Owner: -
--

ALTER TABLE argus.event_contradictions ALTER COLUMN contradiction_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME argus.event_contradictions_contradiction_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: event_entities; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.event_entities (
    event_id text NOT NULL,
    entity_id text,
    ref_type argus.entity_type NOT NULL,
    ref_id text NOT NULL,
    resolution_status argus.resolution_status DEFAULT 'pending'::argus.resolution_status NOT NULL,
    role argus.entity_role DEFAULT 'unspecified'::argus.entity_role NOT NULL,
    role_confidence double precision,
    match_confidence double precision,
    CONSTRAINT event_entities_match_confidence_check CHECK (((match_confidence IS NULL) OR ((match_confidence >= (0)::double precision) AND (match_confidence <= (1)::double precision)))),
    CONSTRAINT event_entities_role_confidence_check CHECK (((role_confidence IS NULL) OR ((role_confidence >= (0)::double precision) AND (role_confidence <= (1)::double precision))))
);

--
-- Name: event_links; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.event_links (
    from_event_id text NOT NULL,
    to_event_id text NOT NULL,
    link_type argus.event_link_type NOT NULL,
    strength double precision,
    rationale text,
    created_by text NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT event_links_hypothesis_needs_strength CHECK (((link_type <> 'caused_by_hypothesis'::argus.event_link_type) OR (strength IS NOT NULL))),
    CONSTRAINT event_links_not_self CHECK ((from_event_id <> to_event_id)),
    CONSTRAINT event_links_strength_check CHECK (((strength IS NULL) OR ((strength >= (0)::double precision) AND (strength <= (1)::double precision))))
);

--
-- Name: event_reports; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.event_reports (
    event_id text NOT NULL,
    report_id text NOT NULL,
    is_first_report boolean DEFAULT false NOT NULL,
    linked_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    linked_by text DEFAULT 'argus:service:correlator'::text NOT NULL
);

--
-- Name: events_history; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.events_history (
    event_id text NOT NULL,
    schema_version text NOT NULL,
    type text NOT NULL,
    title text NOT NULL,
    summary text,
    lang text NOT NULL,
    occurred_start timestamp with time zone NOT NULL,
    occurred_end timestamp with time zone,
    occurred_precision argus.time_precision NOT NULL,
    is_ongoing boolean NOT NULL,
    geo public.geography(Geometry,4326),
    geo_point public.geography(Point,4326),
    geo_point_is_derived boolean NOT NULL,
    geo_precision argus.geo_precision NOT NULL,
    geo_uncertainty_radius_m double precision,
    place_name text,
    place_country text,
    place_wikidata_qid text,
    h3_r5 bigint,
    h3_r7 bigint,
    severity double precision NOT NULL,
    confidence double precision NOT NULL,
    status argus.event_status NOT NULL,
    magnitude_scale text,
    magnitude_value double precision,
    magnitude_unit text,
    magnitude_expected double precision,
    magnitude_previous double precision,
    independent_sources integer NOT NULL,
    contradicting_sources integer NOT NULL,
    first_seen_source text,
    first_seen_at timestamp with time zone,
    story_cluster_id text,
    priority double precision,
    retracted_at timestamp with time zone,
    retracted_by_source text,
    retraction_reason text,
    retraction_inferred boolean NOT NULL,
    superseded_by_event_id text,
    tags text[] NOT NULL,
    attributes jsonb NOT NULL,
    dedupe_key text,
    source_id text,
    raw_ref text,
    observed_at timestamp with time zone,
    ingested_at timestamp with time zone NOT NULL,
    version integer NOT NULL,
    sys_period tstzrange NOT NULL,
    search_tsv tsvector
);

--
-- Name: observations; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.observations (
    obs_id text NOT NULL,
    schema_version text NOT NULL,
    entity_id text,
    ref_type argus.entity_type NOT NULL,
    ref_id text NOT NULL,
    resolution_status argus.resolution_status DEFAULT 'pending'::argus.resolution_status NOT NULL,
    kind argus.observation_kind DEFAULT 'position'::argus.observation_kind NOT NULL,
    observed_at timestamp with time zone NOT NULL,
    time_quality argus.time_quality DEFAULT 'source_provided'::argus.time_quality NOT NULL,
    ingested_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    source_id text NOT NULL,
    raw_ref text,
    geo public.geography(Point,4326),
    geo_precision argus.geo_precision DEFAULT 'unspecified'::argus.geo_precision NOT NULL,
    h3_r5 bigint,
    h3_r7 bigint,
    h3_r9 bigint,
    position_accuracy_m double precision,
    is_interpolated boolean DEFAULT false NOT NULL,
    is_dead_reckoned boolean DEFAULT false NOT NULL,
    uncertainty_radius_m double precision,
    is_suspected_spoof boolean DEFAULT false NOT NULL,
    seconds_since_previous double precision,
    quality_flags text[] DEFAULT '{}'::text[] NOT NULL,
    sog_kn double precision,
    cog_deg double precision,
    heading_deg double precision,
    track_deg double precision,
    draft_m double precision,
    altitude_m double precision,
    altitude_baro_m double precision,
    vertical_rate_ms double precision,
    rate_of_turn_deg_min double precision,
    ground_speed_kn double precision,
    true_airspeed_kn double precision,
    metric text,
    metric_value double precision,
    metric_unit text,
    metric_revision integer,
    metric_previous_value double precision,
    metric_is_preliminary boolean DEFAULT false NOT NULL,
    metric_period tstzrange,
    attributes jsonb DEFAULT '{}'::jsonb NOT NULL,
    dedupe_key text NOT NULL,
    track_id text,
    CONSTRAINT observations_cog_deg_check CHECK (((cog_deg IS NULL) OR ((cog_deg >= (0)::double precision) AND (cog_deg < (360)::double precision)))),
    CONSTRAINT observations_dr_needs_uncertainty CHECK (((NOT is_dead_reckoned) OR (uncertainty_radius_m IS NOT NULL))),
    CONSTRAINT observations_draft_m_check CHECK (((draft_m IS NULL) OR (draft_m >= (0)::double precision))),
    CONSTRAINT observations_heading_deg_check CHECK (((heading_deg IS NULL) OR ((heading_deg >= (0)::double precision) AND (heading_deg < (360)::double precision)))),
    CONSTRAINT observations_measurement_complete CHECK (((kind <> 'measurement'::argus.observation_kind) OR ((metric IS NOT NULL) AND (metric_value IS NOT NULL)))),
    CONSTRAINT observations_metric_revision_check CHECK (((metric_revision IS NULL) OR (metric_revision >= 0))),
    CONSTRAINT observations_position_accuracy_m_check CHECK (((position_accuracy_m IS NULL) OR (position_accuracy_m >= (0)::double precision))),
    CONSTRAINT observations_position_has_geo CHECK (((kind <> 'position'::argus.observation_kind) OR (geo IS NOT NULL))),
    CONSTRAINT observations_time_quality_consistent CHECK (((time_quality <> 'inferred_from_ingest'::argus.time_quality) OR (observed_at = ingested_at))),
    CONSTRAINT observations_track_deg_check CHECK (((track_deg IS NULL) OR ((track_deg >= (0)::double precision) AND (track_deg < (360)::double precision)))),
    CONSTRAINT observations_uncertainty_radius_m_check CHECK (((uncertainty_radius_m IS NULL) OR (uncertainty_radius_m >= (0)::double precision)))
)
PARTITION BY RANGE (observed_at);

--
-- Name: relations; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.relations (
    relation_id text NOT NULL,
    schema_version text NOT NULL,
    relation_type argus.relation_type NOT NULL,
    type_label text,
    from_entity_id text,
    from_ref_type argus.entity_type NOT NULL,
    from_ref_id text NOT NULL,
    to_entity_id text,
    to_ref_type argus.entity_type NOT NULL,
    to_ref_id text NOT NULL,
    validity tstzrange DEFAULT tstzrange(NULL::timestamp with time zone, NULL::timestamp with time zone, '[)'::text) NOT NULL,
    weight double precision,
    weight_unit text,
    confidence double precision DEFAULT 0.5 NOT NULL,
    confidence_basis argus.confidence_basis DEFAULT 'unspecified'::argus.confidence_basis NOT NULL,
    directed boolean DEFAULT true NOT NULL,
    evidence jsonb DEFAULT '[]'::jsonb NOT NULL,
    attributes jsonb DEFAULT '{}'::jsonb NOT NULL,
    retracted_at timestamp with time zone,
    retraction_reason text,
    dedupe_key text,
    source_id text,
    raw_ref text,
    observed_at timestamp with time zone,
    ingested_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    sys_period tstzrange DEFAULT tstzrange(clock_timestamp(), NULL::timestamp with time zone, '[)'::text) NOT NULL,
    CONSTRAINT relations_confidence_check CHECK (((confidence >= (0)::double precision) AND (confidence <= (1)::double precision))),
    CONSTRAINT relations_evidence_is_array CHECK ((jsonb_typeof(evidence) = 'array'::text)),
    CONSTRAINT relations_not_self CHECK (((from_ref_id <> to_ref_id) OR (relation_type = 'associated_with'::argus.relation_type))),
    CONSTRAINT relations_other_needs_label CHECK (((relation_type <> 'other'::argus.relation_type) OR (type_label IS NOT NULL)))
);

--
-- Name: relations_history; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.relations_history (
    relation_id text NOT NULL,
    schema_version text NOT NULL,
    relation_type argus.relation_type NOT NULL,
    type_label text,
    from_entity_id text,
    from_ref_type argus.entity_type NOT NULL,
    from_ref_id text NOT NULL,
    to_entity_id text,
    to_ref_type argus.entity_type NOT NULL,
    to_ref_id text NOT NULL,
    validity tstzrange NOT NULL,
    weight double precision,
    weight_unit text,
    confidence double precision NOT NULL,
    confidence_basis argus.confidence_basis NOT NULL,
    directed boolean NOT NULL,
    evidence jsonb NOT NULL,
    attributes jsonb NOT NULL,
    retracted_at timestamp with time zone,
    retraction_reason text,
    dedupe_key text,
    source_id text,
    raw_ref text,
    observed_at timestamp with time zone,
    ingested_at timestamp with time zone NOT NULL,
    version integer NOT NULL,
    sys_period tstzrange NOT NULL
);

--
-- Name: report_mentions; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.report_mentions (
    report_id text NOT NULL,
    entity_id text,
    ref_type argus.entity_type NOT NULL,
    ref_id text NOT NULL,
    resolution_status argus.resolution_status DEFAULT 'pending'::argus.resolution_status NOT NULL,
    match_confidence double precision,
    char_start integer,
    char_end integer,
    CONSTRAINT report_mentions_char_end_check CHECK (((char_end IS NULL) OR (char_end >= 0))),
    CONSTRAINT report_mentions_char_start_check CHECK (((char_start IS NULL) OR (char_start >= 0))),
    CONSTRAINT report_mentions_match_confidence_check CHECK (((match_confidence IS NULL) OR ((match_confidence >= (0)::double precision) AND (match_confidence <= (1)::double precision)))),
    CONSTRAINT report_mentions_span CHECK (((char_end IS NULL) OR (char_start IS NULL) OR (char_end >= char_start)))
);

--
-- Name: report_places; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.report_places (
    place_row_id bigint NOT NULL,
    report_id text NOT NULL,
    geo_point public.geography(Point,4326),
    geo_precision argus.geo_precision DEFAULT 'unspecified'::argus.geo_precision NOT NULL,
    place_name text NOT NULL,
    place_country text,
    wikidata_qid text,
    geonames_id text,
    h3_r7 bigint,
    confidence double precision,
    char_start integer,
    char_end integer,
    CONSTRAINT report_places_confidence_check CHECK (((confidence IS NULL) OR ((confidence >= (0)::double precision) AND (confidence <= (1)::double precision)))),
    CONSTRAINT report_places_place_country_check CHECK (((place_country IS NULL) OR (place_country ~ '^[A-Z]{2}$'::text)))
);

--
-- Name: report_places_place_row_id_seq; Type: SEQUENCE; Schema: argus; Owner: -
--

ALTER TABLE argus.report_places ALTER COLUMN place_row_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME argus.report_places_place_row_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: report_translations; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.report_translations (
    report_id text NOT NULL,
    lang text NOT NULL,
    title text,
    body_text text,
    model text NOT NULL,
    model_version text NOT NULL,
    prompt_hash text,
    translated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL
);

--
-- Name: reports; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.reports (
    report_id text NOT NULL,
    schema_version text NOT NULL,
    kind argus.report_kind DEFAULT 'unspecified'::argus.report_kind NOT NULL,
    url text,
    canonical_url text,
    title text NOT NULL,
    summary text,
    body_text text,
    body_ref text,
    body_withheld_for_license boolean DEFAULT false NOT NULL,
    lang text DEFAULT 'und'::text NOT NULL,
    lang_confidence double precision,
    published_at timestamp with time zone,
    modified_at timestamp with time zone,
    publisher text,
    publisher_country text,
    authors text[] DEFAULT '{}'::text[] NOT NULL,
    sentiment double precision,
    sentiment_model text,
    embedding_id text,
    embedding_model text,
    simhash bigint,
    content_hash bytea,
    story_cluster_id text,
    is_cluster_representative boolean DEFAULT false NOT NULL,
    cluster_similarity double precision,
    duplicate_of_report_id text,
    is_paywalled boolean DEFAULT false NOT NULL,
    license_id text,
    attribution_text text,
    priority double precision,
    retracted_at timestamp with time zone,
    retraction_reason text,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    attributes jsonb DEFAULT '{}'::jsonb NOT NULL,
    dedupe_key text,
    source_id text,
    raw_ref text,
    observed_at timestamp with time zone,
    ingested_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    search_tsv tsvector GENERATED ALWAYS AS (((setweight(to_tsvector(argus.ts_config(lang), COALESCE(title, ''::text)), 'A'::"char") || setweight(to_tsvector(argus.ts_config(lang), COALESCE(summary, ''::text)), 'B'::"char")) || setweight(to_tsvector(argus.ts_config(lang), COALESCE(body_text, ''::text)), 'D'::"char"))) STORED,
    CONSTRAINT reports_body_or_ref CHECK (((NOT body_withheld_for_license) OR (body_text IS NULL))),
    CONSTRAINT reports_cluster_similarity_check CHECK (((cluster_similarity IS NULL) OR ((cluster_similarity >= (0)::double precision) AND (cluster_similarity <= (1)::double precision)))),
    CONSTRAINT reports_lang_confidence_check CHECK (((lang_confidence IS NULL) OR ((lang_confidence >= (0)::double precision) AND (lang_confidence <= (1)::double precision)))),
    CONSTRAINT reports_priority_check CHECK (((priority IS NULL) OR ((priority >= (0)::double precision) AND (priority <= (100)::double precision)))),
    CONSTRAINT reports_publisher_country_check CHECK (((publisher_country IS NULL) OR (publisher_country ~ '^[A-Z]{2}$'::text))),
    CONSTRAINT reports_retraction_complete CHECK (((retracted_at IS NULL) OR (retraction_reason IS NOT NULL))),
    CONSTRAINT reports_sentiment_check CHECK (((sentiment IS NULL) OR ((sentiment >= ('-1'::integer)::double precision) AND (sentiment <= (1)::double precision))))
);

--
-- Name: schema_invariants; Type: VIEW; Schema: argus; Owner: -
--

CREATE VIEW argus.schema_invariants AS
 SELECT 'no_naive_timestamps'::text AS invariant,
    (NOT (EXISTS ( SELECT 1
           FROM information_schema.columns
          WHERE (((columns.table_schema)::name = 'argus'::name) AND ((columns.data_type)::text = ANY ((ARRAY['timestamp without time zone'::character varying, 'time without time zone'::character varying])::text[])))))) AS holds
UNION ALL
 SELECT 'all_fks_have_delete_rule'::text AS invariant,
    (NOT (EXISTS ( SELECT 1
           FROM ((pg_constraint con
             JOIN pg_class c ON ((c.oid = con.conrelid)))
             JOIN pg_namespace n ON ((n.oid = c.relnamespace)))
          WHERE ((n.nspname = 'argus'::name) AND (con.contype = 'f'::"char") AND (con.confdeltype = 'a'::"char"))))) AS holds;

--
-- Name: score_factors; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.score_factors (
    score_id bigint NOT NULL,
    factor text NOT NULL,
    raw double precision NOT NULL,
    weight double precision NOT NULL,
    contribution double precision NOT NULL,
    detail text
);

--
-- Name: scores; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.scores (
    score_id bigint NOT NULL,
    object_kind argus.object_kind NOT NULL,
    object_id text NOT NULL,
    priority double precision NOT NULL,
    weights_version text NOT NULL,
    profile_id text DEFAULT ''::text NOT NULL,
    computed_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT scores_priority_check CHECK (((priority >= (0)::double precision) AND (priority <= (100)::double precision)))
);

--
-- Name: scores_score_id_seq; Type: SEQUENCE; Schema: argus; Owner: -
--

ALTER TABLE argus.scores ALTER COLUMN score_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME argus.scores_score_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: source_reliability_changes; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.source_reliability_changes (
    change_id bigint NOT NULL,
    source_id text NOT NULL,
    changed_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    from_value argus.source_reliability NOT NULL,
    to_value argus.source_reliability NOT NULL,
    reason text NOT NULL,
    changed_by text NOT NULL,
    evidence jsonb DEFAULT '[]'::jsonb NOT NULL,
    CONSTRAINT source_reliability_changes_actually_changed CHECK ((from_value <> to_value))
);

--
-- Name: source_reliability_changes_change_id_seq; Type: SEQUENCE; Schema: argus; Owner: -
--

ALTER TABLE argus.source_reliability_changes ALTER COLUMN change_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME argus.source_reliability_changes_change_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: sources; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.sources (
    source_id text NOT NULL,
    schema_version text NOT NULL,
    name text NOT NULL,
    publisher text,
    url text,
    description text,
    kind argus.source_kind DEFAULT 'unspecified'::argus.source_kind NOT NULL,
    domains argus.source_domain[] DEFAULT '{}'::argus.source_domain[] NOT NULL,
    reliability argus.source_reliability DEFAULT 'unspecified'::argus.source_reliability NOT NULL,
    default_credibility argus.information_credibility DEFAULT 'unspecified'::argus.information_credibility NOT NULL,
    license_id text NOT NULL,
    license_name text,
    license_spdx_id text,
    license_url text,
    license_allowed_uses text[] DEFAULT '{}'::text[] NOT NULL,
    attribution_text text,
    attribution_required boolean DEFAULT false NOT NULL,
    license_expires_at timestamp with time zone,
    max_retention_days integer,
    expected_latency_s double precision,
    poll_interval_s double precision,
    rate_limit_requests integer,
    rate_limit_per_seconds integer,
    connector_id text,
    credential_ref text,
    enabled boolean DEFAULT true NOT NULL,
    disabled_reason text,
    may_contain_personal_data boolean DEFAULT false NOT NULL,
    retention_days integer,
    coverage_area public.geography(MultiPolygon,4326),
    coverage_countries text[] DEFAULT '{}'::text[] NOT NULL,
    coverage_languages text[] DEFAULT '{}'::text[] NOT NULL,
    attributes jsonb DEFAULT '{}'::jsonb NOT NULL,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    observed_at timestamp with time zone,
    ingested_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT sources_disabled_needs_reason CHECK ((enabled OR (disabled_reason IS NOT NULL))),
    CONSTRAINT sources_expected_latency_s_check CHECK (((expected_latency_s IS NULL) OR (expected_latency_s >= (0)::double precision))),
    CONSTRAINT sources_max_retention_days_check CHECK (((max_retention_days IS NULL) OR (max_retention_days > 0))),
    CONSTRAINT sources_poll_interval_s_check CHECK (((poll_interval_s IS NULL) OR (poll_interval_s > (0)::double precision))),
    CONSTRAINT sources_retention_days_check CHECK (((retention_days IS NULL) OR (retention_days > 0)))
);

--
-- Name: track_gaps; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.track_gaps (
    gap_id bigint NOT NULL,
    track_id text NOT NULL,
    gap_start timestamp with time zone NOT NULL,
    gap_end timestamp with time zone,
    reason argus.gap_reason DEFAULT 'unspecified'::argus.gap_reason NOT NULL,
    duration_s double precision NOT NULL,
    distance_m double precision,
    is_flagged boolean DEFAULT false NOT NULL,
    detail text,
    uncertainty_area public.geography(Polygon,4326),
    containment_probability double precision,
    CONSTRAINT track_gaps_containment_probability_check CHECK (((containment_probability IS NULL) OR ((containment_probability > (0)::double precision) AND (containment_probability <= (1)::double precision)))),
    CONSTRAINT track_gaps_distance_m_check CHECK (((distance_m IS NULL) OR (distance_m >= (0)::double precision))),
    CONSTRAINT track_gaps_duration_s_check CHECK ((duration_s >= (0)::double precision)),
    CONSTRAINT track_gaps_time_order CHECK (((gap_end IS NULL) OR (gap_end >= gap_start)))
);

--
-- Name: track_gaps_gap_id_seq; Type: SEQUENCE; Schema: argus; Owner: -
--

ALTER TABLE argus.track_gaps ALTER COLUMN gap_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME argus.track_gaps_gap_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: tracks; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.tracks (
    track_id text NOT NULL,
    schema_version text NOT NULL,
    entity_id text,
    ref_type argus.entity_type NOT NULL,
    ref_id text NOT NULL,
    time_start timestamp with time zone NOT NULL,
    time_end timestamp with time zone,
    is_open boolean DEFAULT true NOT NULL,
    last_point_at timestamp with time zone,
    point_count integer DEFAULT 0 NOT NULL,
    distance_m double precision,
    bbox public.geography(Polygon,4326),
    simplified_geom public.geography(LineString,4326),
    simplify_tolerance_m double precision,
    source_ids text[] DEFAULT '{}'::text[] NOT NULL,
    attributes jsonb DEFAULT '{}'::jsonb NOT NULL,
    ingested_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT tracks_distance_m_check CHECK (((distance_m IS NULL) OR (distance_m >= (0)::double precision))),
    CONSTRAINT tracks_open_has_no_end CHECK (((NOT is_open) OR (time_end IS NULL))),
    CONSTRAINT tracks_point_count_check CHECK ((point_count >= 0)),
    CONSTRAINT tracks_time_order CHECK (((time_end IS NULL) OR (time_end >= time_start)))
);

--
-- Name: watchlist_members; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.watchlist_members (
    member_id bigint NOT NULL,
    watchlist_id text NOT NULL,
    entity_id text,
    ref_type argus.entity_type,
    ref_id text,
    match_mode argus.match_mode DEFAULT 'entity'::argus.match_mode NOT NULL,
    pattern text,
    attribute_path text,
    attribute_value jsonb,
    weight double precision DEFAULT 1 NOT NULL,
    min_similarity double precision,
    validity tstzrange DEFAULT tstzrange(NULL::timestamp with time zone, NULL::timestamp with time zone, '[)'::text) NOT NULL,
    note text,
    added_by text NOT NULL,
    added_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    source_id text,
    CONSTRAINT watchlist_members_min_similarity_check CHECK (((min_similarity IS NULL) OR ((min_similarity >= (0)::double precision) AND (min_similarity <= (1)::double precision)))),
    CONSTRAINT watchlist_members_target CHECK ((((match_mode = ANY (ARRAY['exact_id'::argus.match_mode, 'entity'::argus.match_mode])) AND (ref_id IS NOT NULL)) OR ((match_mode = ANY (ARRAY['pattern'::argus.match_mode, 'fuzzy_name'::argus.match_mode])) AND (pattern IS NOT NULL)) OR ((match_mode = 'attribute'::argus.match_mode) AND (attribute_path IS NOT NULL)))),
    CONSTRAINT watchlist_members_weight_check CHECK (((weight >= (0)::double precision) AND (weight <= (1)::double precision)))
);

--
-- Name: watchlist_members_member_id_seq; Type: SEQUENCE; Schema: argus; Owner: -
--

ALTER TABLE argus.watchlist_members ALTER COLUMN member_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME argus.watchlist_members_member_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

--
-- Name: watchlists; Type: TABLE; Schema: argus; Owner: -
--

CREATE TABLE argus.watchlists (
    watchlist_id text NOT NULL,
    schema_version text NOT NULL,
    name text NOT NULL,
    description text,
    default_weight double precision DEFAULT 1 NOT NULL,
    import_source_id text,
    last_import_at timestamp with time zone,
    is_managed boolean DEFAULT false NOT NULL,
    owner_id text NOT NULL,
    visibility argus.visibility DEFAULT 'private'::argus.visibility NOT NULL,
    shared_with text[] DEFAULT '{}'::text[] NOT NULL,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    active boolean DEFAULT true NOT NULL,
    contains_personal_data boolean DEFAULT false NOT NULL,
    attributes jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    updated_at timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT watchlists_default_weight_check CHECK (((default_weight >= (0)::double precision) AND (default_weight <= (1)::double precision)))
);

ALTER TABLE ONLY argus.watchlists FORCE ROW LEVEL SECURITY;

--
-- Name: alert_notifications alert_notifications_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.alert_notifications
    ADD CONSTRAINT alert_notifications_pkey PRIMARY KEY (notification_id);

--
-- Name: alerts alerts_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.alerts
    ADD CONSTRAINT alerts_pkey PRIMARY KEY (alert_id);

--
-- Name: aois aois_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.aois
    ADD CONSTRAINT aois_pkey PRIMARY KEY (aoi_id);

--
-- Name: assessments assessments_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.assessments
    ADD CONSTRAINT assessments_pkey PRIMARY KEY (assessment_id);

--
-- Name: case_items case_items_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.case_items
    ADD CONSTRAINT case_items_pkey PRIMARY KEY (case_id, object_kind, object_id);

--
-- Name: case_notes case_notes_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.case_notes
    ADD CONSTRAINT case_notes_pkey PRIMARY KEY (note_id);

--
-- Name: cases cases_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.cases
    ADD CONSTRAINT cases_pkey PRIMARY KEY (case_id);

--
-- Name: data_gaps data_gaps_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.data_gaps
    ADD CONSTRAINT data_gaps_pkey PRIMARY KEY (gap_id);

--
-- Name: entities entities_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.entities
    ADD CONSTRAINT entities_pkey PRIMARY KEY (entity_id);

--
-- Name: entity_aliases entity_aliases_id_type_value_key; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.entity_aliases
    ADD CONSTRAINT entity_aliases_id_type_value_key UNIQUE (id_type, id_value);

--
-- Name: entity_aliases entity_aliases_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.entity_aliases
    ADD CONSTRAINT entity_aliases_pkey PRIMARY KEY (alias_id);

--
-- Name: entity_sanctions entity_sanctions_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.entity_sanctions
    ADD CONSTRAINT entity_sanctions_pkey PRIMARY KEY (listing_row_id);

--
-- Name: entity_sanctions entity_sanctions_unique; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.entity_sanctions
    ADD CONSTRAINT entity_sanctions_unique UNIQUE (entity_id, list_id, listing_id);

--
-- Name: event_contradictions event_contradictions_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.event_contradictions
    ADD CONSTRAINT event_contradictions_pkey PRIMARY KEY (contradiction_id);

--
-- Name: event_entities event_entities_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.event_entities
    ADD CONSTRAINT event_entities_pkey PRIMARY KEY (event_id, ref_id, role);

--
-- Name: event_links event_links_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.event_links
    ADD CONSTRAINT event_links_pkey PRIMARY KEY (from_event_id, to_event_id, link_type);

--
-- Name: event_reports event_reports_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.event_reports
    ADD CONSTRAINT event_reports_pkey PRIMARY KEY (event_id, report_id);

--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (event_id);

--
-- Name: observations observations_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.observations
    ADD CONSTRAINT observations_pkey PRIMARY KEY (obs_id, observed_at);

--
-- Name: relations relations_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.relations
    ADD CONSTRAINT relations_pkey PRIMARY KEY (relation_id);

--
-- Name: report_mentions report_mentions_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.report_mentions
    ADD CONSTRAINT report_mentions_pkey PRIMARY KEY (report_id, ref_id);

--
-- Name: report_places report_places_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.report_places
    ADD CONSTRAINT report_places_pkey PRIMARY KEY (place_row_id);

--
-- Name: report_translations report_translations_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.report_translations
    ADD CONSTRAINT report_translations_pkey PRIMARY KEY (report_id, lang);

--
-- Name: reports reports_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.reports
    ADD CONSTRAINT reports_pkey PRIMARY KEY (report_id);

--
-- Name: score_factors score_factors_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.score_factors
    ADD CONSTRAINT score_factors_pkey PRIMARY KEY (score_id, factor);

--
-- Name: scores scores_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.scores
    ADD CONSTRAINT scores_pkey PRIMARY KEY (score_id);

--
-- Name: scores scores_unique_per_profile; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.scores
    ADD CONSTRAINT scores_unique_per_profile UNIQUE (object_kind, object_id, profile_id, computed_at);

--
-- Name: source_reliability_changes source_reliability_changes_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.source_reliability_changes
    ADD CONSTRAINT source_reliability_changes_pkey PRIMARY KEY (change_id);

--
-- Name: sources sources_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.sources
    ADD CONSTRAINT sources_pkey PRIMARY KEY (source_id);

--
-- Name: track_gaps track_gaps_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.track_gaps
    ADD CONSTRAINT track_gaps_pkey PRIMARY KEY (gap_id);

--
-- Name: tracks tracks_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.tracks
    ADD CONSTRAINT tracks_pkey PRIMARY KEY (track_id);

--
-- Name: watchlist_members watchlist_members_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.watchlist_members
    ADD CONSTRAINT watchlist_members_pkey PRIMARY KEY (member_id);

--
-- Name: watchlists watchlists_pkey; Type: CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.watchlists
    ADD CONSTRAINT watchlists_pkey PRIMARY KEY (watchlist_id);

--
-- Name: alert_notifications_alert_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX alert_notifications_alert_idx ON argus.alert_notifications USING btree (alert_id);

--
-- Name: alerts_assignee_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX alerts_assignee_idx ON argus.alerts USING btree (assignee_id) WHERE (assignee_id IS NOT NULL);

--
-- Name: alerts_entity_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX alerts_entity_idx ON argus.alerts USING btree (entity_id) WHERE (entity_id IS NOT NULL);

--
-- Name: alerts_expiry_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX alerts_expiry_idx ON argus.alerts USING btree (expires_at) WHERE (expires_at IS NOT NULL);

--
-- Name: alerts_geo_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX alerts_geo_idx ON argus.alerts USING gist (geo) WHERE (geo IS NOT NULL);

--
-- Name: alerts_open_dedupe_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE UNIQUE INDEX alerts_open_dedupe_idx ON argus.alerts USING btree (dedupe_key) WHERE (status = ANY (ARRAY['new'::argus.alert_status, 'acked'::argus.alert_status, 'investigating'::argus.alert_status]));

--
-- Name: alerts_queue_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX alerts_queue_idx ON argus.alerts USING btree (status, severity DESC, last_seen_at DESC);

--
-- Name: alerts_rule_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX alerts_rule_idx ON argus.alerts USING btree (rule_id, ingested_at DESC);

--
-- Name: aois_geom_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX aois_geom_idx ON argus.aois USING gist (geom) WHERE (geom IS NOT NULL);

--
-- Name: aois_h3_r7_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX aois_h3_r7_idx ON argus.aois USING gin (h3_r7_cells);

--
-- Name: aois_owner_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX aois_owner_idx ON argus.aois USING btree (owner_id) WHERE active;

--
-- Name: aois_visibility_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX aois_visibility_idx ON argus.aois USING btree (visibility);

--
-- Name: assessments_author_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX assessments_author_idx ON argus.assessments USING btree (author_type, author_id);

--
-- Name: assessments_kind_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX assessments_kind_idx ON argus.assessments USING btree (kind, ingested_at DESC);

--
-- Name: assessments_open_forecasts_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX assessments_open_forecasts_idx ON argus.assessments USING btree (validity) WHERE ((kind = 'forecast'::argus.assessment_kind) AND (outcome_verdict IS NULL));

--
-- Name: assessments_subject_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX assessments_subject_idx ON argus.assessments USING btree (subject_kind, subject_id);

--
-- Name: case_items_object_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX case_items_object_idx ON argus.case_items USING btree (object_kind, object_id);

--
-- Name: case_notes_case_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX case_notes_case_idx ON argus.case_notes USING btree (case_id, created_at);

--
-- Name: data_gaps_open_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX data_gaps_open_idx ON argus.data_gaps USING btree (gap_start DESC) WHERE (gap_end IS NULL);

--
-- Name: data_gaps_source_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX data_gaps_source_idx ON argus.data_gaps USING btree (source_id, gap_start DESC);

--
-- Name: entities_display_name_trgm_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX entities_display_name_trgm_idx ON argus.entities USING gin (display_name public.gin_trgm_ops);

--
-- Name: entities_history_id_period_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX entities_history_id_period_idx ON argus.entities_history USING gist (entity_id, sys_period);

--
-- Name: entities_last_position_h3_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX entities_last_position_h3_idx ON argus.entities USING btree (last_position_h3_r7) WHERE (last_position_h3_r7 IS NOT NULL);

--
-- Name: entities_last_position_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX entities_last_position_idx ON argus.entities USING gist (last_position) WHERE (last_position IS NOT NULL);

--
-- Name: entities_purge_after_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX entities_purge_after_idx ON argus.entities USING btree (purge_after) WHERE (purge_after IS NOT NULL);

--
-- Name: entities_sanctioned_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX entities_sanctioned_idx ON argus.entities USING btree (sanction_status) WHERE (sanction_status = ANY (ARRAY['listed'::argus.sanction_status, 'associated'::argus.sanction_status, 'possible_match'::argus.sanction_status]));

--
-- Name: entities_tags_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX entities_tags_idx ON argus.entities USING gin (tags);

--
-- Name: entities_type_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX entities_type_idx ON argus.entities USING btree (type);

--
-- Name: entities_watchlists_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX entities_watchlists_idx ON argus.entities USING gin (watchlist_ids);

--
-- Name: entity_aliases_entity_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX entity_aliases_entity_idx ON argus.entity_aliases USING btree (entity_id);

--
-- Name: entity_aliases_one_primary_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE UNIQUE INDEX entity_aliases_one_primary_idx ON argus.entity_aliases USING btree (entity_id, id_type) WHERE is_primary;

--
-- Name: entity_aliases_value_trgm_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX entity_aliases_value_trgm_idx ON argus.entity_aliases USING gin (id_value public.gin_trgm_ops);

--
-- Name: entity_sanctions_active_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX entity_sanctions_active_idx ON argus.entity_sanctions USING btree (entity_id) WHERE (delisted_at IS NULL);

--
-- Name: entity_sanctions_list_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX entity_sanctions_list_idx ON argus.entity_sanctions USING btree (list_id, listing_id);

--
-- Name: event_contradictions_event_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX event_contradictions_event_idx ON argus.event_contradictions USING btree (event_id);

--
-- Name: event_contradictions_open_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX event_contradictions_open_idx ON argus.event_contradictions USING btree (detected_at DESC) WHERE (resolved_at IS NULL);

--
-- Name: event_entities_entity_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX event_entities_entity_idx ON argus.event_entities USING btree (entity_id) WHERE (entity_id IS NOT NULL);

--
-- Name: event_entities_ref_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX event_entities_ref_idx ON argus.event_entities USING btree (ref_id);

--
-- Name: event_entities_unresolved_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX event_entities_unresolved_idx ON argus.event_entities USING btree (resolution_status) WHERE (resolution_status = ANY (ARRAY['pending'::argus.resolution_status, 'unresolved'::argus.resolution_status, 'ambiguous'::argus.resolution_status]));

--
-- Name: event_links_to_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX event_links_to_idx ON argus.event_links USING btree (to_event_id);

--
-- Name: event_reports_one_first_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE UNIQUE INDEX event_reports_one_first_idx ON argus.event_reports USING btree (event_id) WHERE is_first_report;

--
-- Name: event_reports_report_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX event_reports_report_idx ON argus.event_reports USING btree (report_id);

--
-- Name: events_cluster_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX events_cluster_idx ON argus.events USING btree (story_cluster_id) WHERE (story_cluster_id IS NOT NULL);

--
-- Name: events_dedupe_key_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE UNIQUE INDEX events_dedupe_key_idx ON argus.events USING btree (dedupe_key) WHERE (dedupe_key IS NOT NULL);

--
-- Name: events_geo_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX events_geo_idx ON argus.events USING gist (geo) WHERE (geo IS NOT NULL);

--
-- Name: events_geo_point_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX events_geo_point_idx ON argus.events USING gist (geo_point) WHERE (geo_point IS NOT NULL);

--
-- Name: events_h3_r5_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX events_h3_r5_idx ON argus.events USING btree (h3_r5) WHERE (h3_r5 IS NOT NULL);

--
-- Name: events_h3_r7_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX events_h3_r7_idx ON argus.events USING btree (h3_r7) WHERE (h3_r7 IS NOT NULL);

--
-- Name: events_history_id_period_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX events_history_id_period_idx ON argus.events_history USING gist (event_id, sys_period);

--
-- Name: events_ingested_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX events_ingested_idx ON argus.events USING btree (ingested_at DESC);

--
-- Name: events_occurred_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX events_occurred_idx ON argus.events USING btree (occurred_start DESC);

--
-- Name: events_priority_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX events_priority_idx ON argus.events USING btree (priority DESC NULLS LAST, occurred_start DESC);

--
-- Name: events_search_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX events_search_idx ON argus.events USING gin (search_tsv);

--
-- Name: events_status_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX events_status_idx ON argus.events USING btree (status);

--
-- Name: events_tags_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX events_tags_idx ON argus.events USING gin (tags);

--
-- Name: events_type_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX events_type_idx ON argus.events USING btree (type text_pattern_ops);

--
-- Name: observations_dedupe_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE UNIQUE INDEX observations_dedupe_idx ON ONLY argus.observations USING btree (dedupe_key, observed_at);

--
-- Name: observations_entity_time_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX observations_entity_time_idx ON ONLY argus.observations USING btree (entity_id, observed_at DESC);

--
-- Name: observations_geo_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX observations_geo_idx ON ONLY argus.observations USING gist (geo) WHERE (geo IS NOT NULL);

--
-- Name: observations_h3_r7_time_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX observations_h3_r7_time_idx ON ONLY argus.observations USING btree (h3_r7, observed_at DESC) WHERE (h3_r7 IS NOT NULL);

--
-- Name: observations_metric_time_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX observations_metric_time_idx ON ONLY argus.observations USING btree (metric, observed_at DESC) WHERE (metric IS NOT NULL);

--
-- Name: observations_ref_time_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX observations_ref_time_idx ON ONLY argus.observations USING btree (ref_id, observed_at DESC);

--
-- Name: observations_source_time_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX observations_source_time_idx ON ONLY argus.observations USING btree (source_id, ingested_at DESC);

--
-- Name: observations_track_time_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX observations_track_time_idx ON ONLY argus.observations USING btree (track_id, observed_at DESC) WHERE (track_id IS NOT NULL);

--
-- Name: relations_dedupe_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE UNIQUE INDEX relations_dedupe_idx ON argus.relations USING btree (dedupe_key) WHERE (dedupe_key IS NOT NULL);

--
-- Name: relations_from_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX relations_from_idx ON argus.relations USING btree (from_entity_id, relation_type);

--
-- Name: relations_history_id_period_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX relations_history_id_period_idx ON argus.relations_history USING gist (relation_id, sys_period);

--
-- Name: relations_to_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX relations_to_idx ON argus.relations USING btree (to_entity_id, relation_type);

--
-- Name: relations_type_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX relations_type_idx ON argus.relations USING btree (relation_type);

--
-- Name: relations_validity_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX relations_validity_idx ON argus.relations USING gist (validity);

--
-- Name: report_mentions_entity_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX report_mentions_entity_idx ON argus.report_mentions USING btree (entity_id) WHERE (entity_id IS NOT NULL);

--
-- Name: report_places_geo_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX report_places_geo_idx ON argus.report_places USING gist (geo_point) WHERE (geo_point IS NOT NULL);

--
-- Name: report_places_h3_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX report_places_h3_idx ON argus.report_places USING btree (h3_r7) WHERE (h3_r7 IS NOT NULL);

--
-- Name: report_places_report_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX report_places_report_idx ON argus.report_places USING btree (report_id);

--
-- Name: reports_canonical_url_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE UNIQUE INDEX reports_canonical_url_idx ON argus.reports USING btree (canonical_url) WHERE (canonical_url IS NOT NULL);

--
-- Name: reports_cluster_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX reports_cluster_idx ON argus.reports USING btree (story_cluster_id, published_at) WHERE (story_cluster_id IS NOT NULL);

--
-- Name: reports_content_hash_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE UNIQUE INDEX reports_content_hash_idx ON argus.reports USING btree (content_hash) WHERE (content_hash IS NOT NULL);

--
-- Name: reports_dedupe_key_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE UNIQUE INDEX reports_dedupe_key_idx ON argus.reports USING btree (dedupe_key) WHERE (dedupe_key IS NOT NULL);

--
-- Name: reports_ingested_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX reports_ingested_idx ON argus.reports USING btree (ingested_at DESC);

--
-- Name: reports_lang_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX reports_lang_idx ON argus.reports USING btree (lang);

--
-- Name: reports_published_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX reports_published_idx ON argus.reports USING btree (published_at DESC NULLS LAST);

--
-- Name: reports_search_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX reports_search_idx ON argus.reports USING gin (search_tsv);

--
-- Name: reports_simhash_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX reports_simhash_idx ON argus.reports USING btree (simhash) WHERE (simhash IS NOT NULL);

--
-- Name: reports_source_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX reports_source_idx ON argus.reports USING btree (source_id, ingested_at DESC);

--
-- Name: reports_tags_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX reports_tags_idx ON argus.reports USING gin (tags);

--
-- Name: scores_object_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX scores_object_idx ON argus.scores USING btree (object_kind, object_id, computed_at DESC);

--
-- Name: scores_priority_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX scores_priority_idx ON argus.scores USING btree (priority DESC, computed_at DESC);

--
-- Name: source_reliability_changes_source_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX source_reliability_changes_source_idx ON argus.source_reliability_changes USING btree (source_id, changed_at DESC);

--
-- Name: sources_domains_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX sources_domains_idx ON argus.sources USING gin (domains);

--
-- Name: sources_enabled_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX sources_enabled_idx ON argus.sources USING btree (enabled) WHERE enabled;

--
-- Name: sources_tags_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX sources_tags_idx ON argus.sources USING gin (tags);

--
-- Name: track_gaps_flagged_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX track_gaps_flagged_idx ON argus.track_gaps USING btree (gap_start DESC) WHERE is_flagged;

--
-- Name: track_gaps_track_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX track_gaps_track_idx ON argus.track_gaps USING btree (track_id, gap_start DESC);

--
-- Name: tracks_bbox_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX tracks_bbox_idx ON argus.tracks USING gist (bbox) WHERE (bbox IS NOT NULL);

--
-- Name: tracks_entity_time_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX tracks_entity_time_idx ON argus.tracks USING btree (entity_id, time_start DESC);

--
-- Name: tracks_open_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX tracks_open_idx ON argus.tracks USING btree (last_point_at DESC) WHERE is_open;

--
-- Name: watchlist_members_entity_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX watchlist_members_entity_idx ON argus.watchlist_members USING btree (entity_id) WHERE (entity_id IS NOT NULL);

--
-- Name: watchlist_members_list_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE INDEX watchlist_members_list_idx ON argus.watchlist_members USING btree (watchlist_id);

--
-- Name: watchlist_members_unique_ref_idx; Type: INDEX; Schema: argus; Owner: -
--

CREATE UNIQUE INDEX watchlist_members_unique_ref_idx ON argus.watchlist_members USING btree (watchlist_id, ref_id) WHERE (ref_id IS NOT NULL);

--
-- Name: aois aois_set_updated_at; Type: TRIGGER; Schema: argus; Owner: -
--

CREATE TRIGGER aois_set_updated_at BEFORE UPDATE ON argus.aois FOR EACH ROW EXECUTE FUNCTION argus.set_updated_at();

--
-- Name: cases cases_set_updated_at; Type: TRIGGER; Schema: argus; Owner: -
--

CREATE TRIGGER cases_set_updated_at BEFORE UPDATE ON argus.cases FOR EACH ROW EXECUTE FUNCTION argus.set_updated_at();

--
-- Name: entities entities_versioning; Type: TRIGGER; Schema: argus; Owner: -
--

CREATE TRIGGER entities_versioning BEFORE DELETE OR UPDATE ON argus.entities FOR EACH ROW EXECUTE FUNCTION argus.versioning_trigger('argus.entities_history');

--
-- Name: events events_versioning; Type: TRIGGER; Schema: argus; Owner: -
--

CREATE TRIGGER events_versioning BEFORE DELETE OR UPDATE ON argus.events FOR EACH ROW EXECUTE FUNCTION argus.versioning_trigger('argus.events_history');

--
-- Name: relations relations_versioning; Type: TRIGGER; Schema: argus; Owner: -
--

CREATE TRIGGER relations_versioning BEFORE DELETE OR UPDATE ON argus.relations FOR EACH ROW EXECUTE FUNCTION argus.versioning_trigger('argus.relations_history');

--
-- Name: sources sources_set_updated_at; Type: TRIGGER; Schema: argus; Owner: -
--

CREATE TRIGGER sources_set_updated_at BEFORE UPDATE ON argus.sources FOR EACH ROW EXECUTE FUNCTION argus.set_updated_at();

--
-- Name: tracks tracks_set_updated_at; Type: TRIGGER; Schema: argus; Owner: -
--

CREATE TRIGGER tracks_set_updated_at BEFORE UPDATE ON argus.tracks FOR EACH ROW EXECUTE FUNCTION argus.set_updated_at();

--
-- Name: alert_notifications alert_notifications_alert_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.alert_notifications
    ADD CONSTRAINT alert_notifications_alert_id_fkey FOREIGN KEY (alert_id) REFERENCES argus.alerts(alert_id) ON DELETE CASCADE;

--
-- Name: alerts alerts_aggregated_into_fk; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.alerts
    ADD CONSTRAINT alerts_aggregated_into_fk FOREIGN KEY (aggregated_into_alert_id) REFERENCES argus.alerts(alert_id) ON DELETE SET NULL;

--
-- Name: alerts alerts_aoi_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.alerts
    ADD CONSTRAINT alerts_aoi_id_fkey FOREIGN KEY (aoi_id) REFERENCES argus.aois(aoi_id) ON DELETE SET NULL;

--
-- Name: alerts alerts_case_fk; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.alerts
    ADD CONSTRAINT alerts_case_fk FOREIGN KEY (case_id) REFERENCES argus.cases(case_id) ON DELETE SET NULL;

--
-- Name: alerts alerts_entity_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.alerts
    ADD CONSTRAINT alerts_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES argus.entities(entity_id) ON DELETE SET NULL;

--
-- Name: aois aois_anchor_entity_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.aois
    ADD CONSTRAINT aois_anchor_entity_id_fkey FOREIGN KEY (anchor_entity_id) REFERENCES argus.entities(entity_id) ON DELETE SET NULL;

--
-- Name: assessments assessments_source_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.assessments
    ADD CONSTRAINT assessments_source_id_fkey FOREIGN KEY (source_id) REFERENCES argus.sources(source_id) ON DELETE SET NULL;

--
-- Name: assessments assessments_superseded_by_fk; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.assessments
    ADD CONSTRAINT assessments_superseded_by_fk FOREIGN KEY (superseded_by) REFERENCES argus.assessments(assessment_id) ON DELETE SET NULL;

--
-- Name: case_items case_items_case_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.case_items
    ADD CONSTRAINT case_items_case_id_fkey FOREIGN KEY (case_id) REFERENCES argus.cases(case_id) ON DELETE CASCADE;

--
-- Name: case_notes case_notes_case_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.case_notes
    ADD CONSTRAINT case_notes_case_id_fkey FOREIGN KEY (case_id) REFERENCES argus.cases(case_id) ON DELETE CASCADE;

--
-- Name: data_gaps data_gaps_source_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.data_gaps
    ADD CONSTRAINT data_gaps_source_id_fkey FOREIGN KEY (source_id) REFERENCES argus.sources(source_id) ON DELETE CASCADE;

--
-- Name: entities entities_merged_into_entity_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.entities
    ADD CONSTRAINT entities_merged_into_entity_id_fkey FOREIGN KEY (merged_into_entity_id) REFERENCES argus.entities(entity_id) ON DELETE SET NULL;

--
-- Name: entities entities_source_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.entities
    ADD CONSTRAINT entities_source_id_fkey FOREIGN KEY (source_id) REFERENCES argus.sources(source_id) ON DELETE SET NULL;

--
-- Name: entity_aliases entity_aliases_entity_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.entity_aliases
    ADD CONSTRAINT entity_aliases_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES argus.entities(entity_id) ON DELETE CASCADE;

--
-- Name: entity_aliases entity_aliases_source_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.entity_aliases
    ADD CONSTRAINT entity_aliases_source_id_fkey FOREIGN KEY (source_id) REFERENCES argus.sources(source_id) ON DELETE SET NULL;

--
-- Name: entity_sanctions entity_sanctions_entity_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.entity_sanctions
    ADD CONSTRAINT entity_sanctions_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES argus.entities(entity_id) ON DELETE CASCADE;

--
-- Name: entity_sanctions entity_sanctions_source_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.entity_sanctions
    ADD CONSTRAINT entity_sanctions_source_id_fkey FOREIGN KEY (source_id) REFERENCES argus.sources(source_id) ON DELETE SET NULL;

--
-- Name: event_contradictions event_contradictions_event_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.event_contradictions
    ADD CONSTRAINT event_contradictions_event_id_fkey FOREIGN KEY (event_id) REFERENCES argus.events(event_id) ON DELETE CASCADE;

--
-- Name: event_entities event_entities_entity_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.event_entities
    ADD CONSTRAINT event_entities_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES argus.entities(entity_id) ON DELETE SET NULL;

--
-- Name: event_entities event_entities_event_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.event_entities
    ADD CONSTRAINT event_entities_event_id_fkey FOREIGN KEY (event_id) REFERENCES argus.events(event_id) ON DELETE CASCADE;

--
-- Name: event_links event_links_from_event_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.event_links
    ADD CONSTRAINT event_links_from_event_id_fkey FOREIGN KEY (from_event_id) REFERENCES argus.events(event_id) ON DELETE CASCADE;

--
-- Name: event_links event_links_to_event_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.event_links
    ADD CONSTRAINT event_links_to_event_id_fkey FOREIGN KEY (to_event_id) REFERENCES argus.events(event_id) ON DELETE CASCADE;

--
-- Name: event_reports event_reports_event_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.event_reports
    ADD CONSTRAINT event_reports_event_id_fkey FOREIGN KEY (event_id) REFERENCES argus.events(event_id) ON DELETE CASCADE;

--
-- Name: event_reports event_reports_report_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.event_reports
    ADD CONSTRAINT event_reports_report_id_fkey FOREIGN KEY (report_id) REFERENCES argus.reports(report_id) ON DELETE CASCADE;

--
-- Name: events events_source_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.events
    ADD CONSTRAINT events_source_id_fkey FOREIGN KEY (source_id) REFERENCES argus.sources(source_id) ON DELETE SET NULL;

--
-- Name: events events_superseded_by_fk; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.events
    ADD CONSTRAINT events_superseded_by_fk FOREIGN KEY (superseded_by_event_id) REFERENCES argus.events(event_id) ON DELETE SET NULL;

--
-- Name: observations observations_entity_fk; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE argus.observations
    ADD CONSTRAINT observations_entity_fk FOREIGN KEY (entity_id) REFERENCES argus.entities(entity_id) ON DELETE SET NULL;

--
-- Name: observations observations_source_fk; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE argus.observations
    ADD CONSTRAINT observations_source_fk FOREIGN KEY (source_id) REFERENCES argus.sources(source_id) ON DELETE RESTRICT;

--
-- Name: observations observations_track_fk; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE argus.observations
    ADD CONSTRAINT observations_track_fk FOREIGN KEY (track_id) REFERENCES argus.tracks(track_id) ON DELETE SET NULL;

--
-- Name: relations relations_from_entity_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.relations
    ADD CONSTRAINT relations_from_entity_id_fkey FOREIGN KEY (from_entity_id) REFERENCES argus.entities(entity_id) ON DELETE CASCADE;

--
-- Name: relations relations_source_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.relations
    ADD CONSTRAINT relations_source_id_fkey FOREIGN KEY (source_id) REFERENCES argus.sources(source_id) ON DELETE SET NULL;

--
-- Name: relations relations_to_entity_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.relations
    ADD CONSTRAINT relations_to_entity_id_fkey FOREIGN KEY (to_entity_id) REFERENCES argus.entities(entity_id) ON DELETE CASCADE;

--
-- Name: report_mentions report_mentions_entity_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.report_mentions
    ADD CONSTRAINT report_mentions_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES argus.entities(entity_id) ON DELETE SET NULL;

--
-- Name: report_mentions report_mentions_report_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.report_mentions
    ADD CONSTRAINT report_mentions_report_id_fkey FOREIGN KEY (report_id) REFERENCES argus.reports(report_id) ON DELETE CASCADE;

--
-- Name: report_places report_places_report_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.report_places
    ADD CONSTRAINT report_places_report_id_fkey FOREIGN KEY (report_id) REFERENCES argus.reports(report_id) ON DELETE CASCADE;

--
-- Name: report_translations report_translations_report_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.report_translations
    ADD CONSTRAINT report_translations_report_id_fkey FOREIGN KEY (report_id) REFERENCES argus.reports(report_id) ON DELETE CASCADE;

--
-- Name: reports reports_duplicate_of_fk; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.reports
    ADD CONSTRAINT reports_duplicate_of_fk FOREIGN KEY (duplicate_of_report_id) REFERENCES argus.reports(report_id) ON DELETE SET NULL;

--
-- Name: reports reports_source_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.reports
    ADD CONSTRAINT reports_source_id_fkey FOREIGN KEY (source_id) REFERENCES argus.sources(source_id) ON DELETE SET NULL;

--
-- Name: score_factors score_factors_score_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.score_factors
    ADD CONSTRAINT score_factors_score_id_fkey FOREIGN KEY (score_id) REFERENCES argus.scores(score_id) ON DELETE CASCADE;

--
-- Name: source_reliability_changes source_reliability_changes_source_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.source_reliability_changes
    ADD CONSTRAINT source_reliability_changes_source_id_fkey FOREIGN KEY (source_id) REFERENCES argus.sources(source_id) ON DELETE CASCADE;

--
-- Name: track_gaps track_gaps_track_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.track_gaps
    ADD CONSTRAINT track_gaps_track_id_fkey FOREIGN KEY (track_id) REFERENCES argus.tracks(track_id) ON DELETE CASCADE;

--
-- Name: tracks tracks_entity_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.tracks
    ADD CONSTRAINT tracks_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES argus.entities(entity_id) ON DELETE SET NULL;

--
-- Name: watchlist_members watchlist_members_entity_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.watchlist_members
    ADD CONSTRAINT watchlist_members_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES argus.entities(entity_id) ON DELETE CASCADE;

--
-- Name: watchlist_members watchlist_members_source_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.watchlist_members
    ADD CONSTRAINT watchlist_members_source_id_fkey FOREIGN KEY (source_id) REFERENCES argus.sources(source_id) ON DELETE SET NULL;

--
-- Name: watchlist_members watchlist_members_watchlist_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.watchlist_members
    ADD CONSTRAINT watchlist_members_watchlist_id_fkey FOREIGN KEY (watchlist_id) REFERENCES argus.watchlists(watchlist_id) ON DELETE CASCADE;

--
-- Name: watchlists watchlists_import_source_id_fkey; Type: FK CONSTRAINT; Schema: argus; Owner: -
--

ALTER TABLE ONLY argus.watchlists
    ADD CONSTRAINT watchlists_import_source_id_fkey FOREIGN KEY (import_source_id) REFERENCES argus.sources(source_id) ON DELETE SET NULL;

--
-- Name: aois; Type: ROW SECURITY; Schema: argus; Owner: -
--

ALTER TABLE argus.aois ENABLE ROW LEVEL SECURITY;

--
-- Name: aois aois_delete; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY aois_delete ON argus.aois FOR DELETE USING ((owner_id = argus.current_user_id()));

--
-- Name: aois aois_insert; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY aois_insert ON argus.aois FOR INSERT WITH CHECK ((owner_id = argus.current_user_id()));

--
-- Name: aois aois_select; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY aois_select ON argus.aois FOR SELECT USING (((argus.current_user_id() IS NOT NULL) AND ((owner_id = argus.current_user_id()) OR (visibility = ANY (ARRAY['org'::argus.visibility, 'public'::argus.visibility])) OR (argus.current_user_id() = ANY (shared_with)) OR ((visibility = 'team'::argus.visibility) AND (shared_with && argus.current_user_teams())))));

--
-- Name: aois aois_update; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY aois_update ON argus.aois FOR UPDATE USING ((owner_id = argus.current_user_id())) WITH CHECK ((owner_id = argus.current_user_id()));

--
-- Name: assessments; Type: ROW SECURITY; Schema: argus; Owner: -
--

ALTER TABLE argus.assessments ENABLE ROW LEVEL SECURITY;

--
-- Name: assessments assessments_delete; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY assessments_delete ON argus.assessments FOR DELETE USING ((owner_id = argus.current_user_id()));

--
-- Name: assessments assessments_insert; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY assessments_insert ON argus.assessments FOR INSERT WITH CHECK ((owner_id = argus.current_user_id()));

--
-- Name: assessments assessments_select; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY assessments_select ON argus.assessments FOR SELECT USING (((argus.current_user_id() IS NOT NULL) AND ((owner_id = argus.current_user_id()) OR (visibility = ANY (ARRAY['org'::argus.visibility, 'public'::argus.visibility])))));

--
-- Name: assessments assessments_update; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY assessments_update ON argus.assessments FOR UPDATE USING ((owner_id = argus.current_user_id())) WITH CHECK ((owner_id = argus.current_user_id()));

--
-- Name: case_items; Type: ROW SECURITY; Schema: argus; Owner: -
--

ALTER TABLE argus.case_items ENABLE ROW LEVEL SECURITY;

--
-- Name: case_items case_items_all; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY case_items_all ON argus.case_items USING ((EXISTS ( SELECT 1
   FROM argus.cases c
  WHERE (c.case_id = case_items.case_id)))) WITH CHECK ((EXISTS ( SELECT 1
   FROM argus.cases c
  WHERE (c.case_id = case_items.case_id))));

--
-- Name: case_notes; Type: ROW SECURITY; Schema: argus; Owner: -
--

ALTER TABLE argus.case_notes ENABLE ROW LEVEL SECURITY;

--
-- Name: case_notes case_notes_all; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY case_notes_all ON argus.case_notes USING ((EXISTS ( SELECT 1
   FROM argus.cases c
  WHERE (c.case_id = case_notes.case_id)))) WITH CHECK ((EXISTS ( SELECT 1
   FROM argus.cases c
  WHERE (c.case_id = case_notes.case_id))));

--
-- Name: cases; Type: ROW SECURITY; Schema: argus; Owner: -
--

ALTER TABLE argus.cases ENABLE ROW LEVEL SECURITY;

--
-- Name: cases cases_delete; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY cases_delete ON argus.cases FOR DELETE USING ((owner_id = argus.current_user_id()));

--
-- Name: cases cases_insert; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY cases_insert ON argus.cases FOR INSERT WITH CHECK ((owner_id = argus.current_user_id()));

--
-- Name: cases cases_select; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY cases_select ON argus.cases FOR SELECT USING (((argus.current_user_id() IS NOT NULL) AND ((owner_id = argus.current_user_id()) OR (visibility = ANY (ARRAY['org'::argus.visibility, 'public'::argus.visibility])) OR (argus.current_user_id() = ANY (shared_with)) OR ((visibility = 'team'::argus.visibility) AND (shared_with && argus.current_user_teams())))));

--
-- Name: cases cases_update; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY cases_update ON argus.cases FOR UPDATE USING ((owner_id = argus.current_user_id())) WITH CHECK ((owner_id = argus.current_user_id()));

--
-- Name: watchlists; Type: ROW SECURITY; Schema: argus; Owner: -
--

ALTER TABLE argus.watchlists ENABLE ROW LEVEL SECURITY;

--
-- Name: watchlists watchlists_delete; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY watchlists_delete ON argus.watchlists FOR DELETE USING ((owner_id = argus.current_user_id()));

--
-- Name: watchlists watchlists_insert; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY watchlists_insert ON argus.watchlists FOR INSERT WITH CHECK ((owner_id = argus.current_user_id()));

--
-- Name: watchlists watchlists_select; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY watchlists_select ON argus.watchlists FOR SELECT USING (((argus.current_user_id() IS NOT NULL) AND ((owner_id = argus.current_user_id()) OR (visibility = ANY (ARRAY['org'::argus.visibility, 'public'::argus.visibility])) OR (argus.current_user_id() = ANY (shared_with)) OR ((visibility = 'team'::argus.visibility) AND (shared_with && argus.current_user_teams())))));

--
-- Name: watchlists watchlists_update; Type: POLICY; Schema: argus; Owner: -
--

CREATE POLICY watchlists_update ON argus.watchlists FOR UPDATE USING ((owner_id = argus.current_user_id())) WITH CHECK ((owner_id = argus.current_user_id()));

--
--

