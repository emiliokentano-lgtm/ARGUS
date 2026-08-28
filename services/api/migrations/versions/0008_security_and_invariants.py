"""Rollen, Row-Level Security, Schema-Invarianten.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


# Tabellen mit Eigentuemer und Sichtbarkeit. Fuer sie gilt die
# Sichtbarkeitsregel aus Kapitel 13: sehen darf, wem es gehoert, wer es geteilt
# bekommen hat, oder wer zur Organisation gehoert, wenn es so freigegeben ist.
OWNED_TABLES = ("aois", "watchlists", "cases", "assessments")


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Rollen. NOLOGIN: die Anmeldung erfolgt ueber Rollen, die diese hier
    # erben, mit Zugangsdaten aus dem Secret-Manager (Kapitel 13). Rollen sind
    # clusterweit, deshalb idempotent angelegt.
    # ------------------------------------------------------------------
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'argus_readonly') THEN
                CREATE ROLE argus_readonly NOLOGIN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'argus_app') THEN
                CREATE ROLE argus_app NOLOGIN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'argus_admin') THEN
                CREATE ROLE argus_admin NOLOGIN BYPASSRLS;
            END IF;
        END $$
        """
    )
    op.execute("COMMENT ON ROLE argus_readonly IS 'Nur lesend, RLS gilt.'")
    op.execute("COMMENT ON ROLE argus_app IS 'Anwendungsrolle: lesen und schreiben, RLS gilt.'")
    op.execute(
        "COMMENT ON ROLE argus_admin IS "
        "'Wartung und Migration. BYPASSRLS - jede Nutzung ist im Audit-Log zu belegen.'"
    )

    op.execute("GRANT USAGE ON SCHEMA argus TO argus_readonly, argus_app, argus_admin")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA argus TO argus_readonly")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA argus TO argus_app")
    op.execute("GRANT ALL ON ALL TABLES IN SCHEMA argus TO argus_admin")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA argus TO argus_app, argus_admin")
    op.execute("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA argus TO argus_readonly, argus_app, argus_admin")
    # Auch fuer spaeter angelegte Objekte, sonst muss jede neue Migration die
    # Rechte nachziehen.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA argus "
        "GRANT SELECT ON TABLES TO argus_readonly"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA argus "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO argus_app"
    )

    # ------------------------------------------------------------------
    # Row-Level Security.
    #
    # Grundgeruest, nicht das fertige Berechtigungsmodell: die feingranulare
    # Autorisierung nach AOI, Quelle und Klassifikationsstufe laeuft ueber
    # OpenFGA (Prompt 40). RLS ist die zweite Verteidigungslinie - selbst wenn
    # die Anwendung eine Pruefung vergisst, gibt die Datenbank nichts heraus.
    #
    # Die Anwendung setzt je Verbindung:
    #     SET LOCAL argus.user_id = '01HZ...';
    #     SET LOCAL argus.teams   = 'watchfloor,analysts';
    # Ohne gesetzte user_id liefert eine RLS-geschuetzte Tabelle nichts. Das
    # ist Absicht: ein vergessenes SET soll leere Ergebnisse liefern, nicht
    # alle Daten.
    # ------------------------------------------------------------------
    for table in OWNED_TABLES:
        op.execute(f"ALTER TABLE argus.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE argus.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_select ON argus.{table}
            FOR SELECT USING (
                argus.current_user_id() IS NOT NULL AND (
                    owner_id = argus.current_user_id()
                    OR visibility IN ('org', 'public')
                    OR argus.current_user_id() = ANY (shared_with)
                    OR (visibility = 'team' AND shared_with && argus.current_user_teams())
                )
            )
            """
            if table != "assessments"
            else f"""
            CREATE POLICY {table}_select ON argus.{table}
            FOR SELECT USING (
                argus.current_user_id() IS NOT NULL AND (
                    owner_id = argus.current_user_id()
                    OR visibility IN ('org', 'public')
                )
            )
            """
        )
        # Schreiben darf nur der Eigentuemer. Teilen macht lesbar, nicht
        # aenderbar - alles andere waere eine stille Rechteausweitung.
        op.execute(
            f"""
            CREATE POLICY {table}_insert ON argus.{table}
            FOR INSERT WITH CHECK (owner_id = argus.current_user_id())
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_update ON argus.{table}
            FOR UPDATE USING (owner_id = argus.current_user_id())
                       WITH CHECK (owner_id = argus.current_user_id())
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table}_delete ON argus.{table}
            FOR DELETE USING (owner_id = argus.current_user_id())
            """
        )

    # Case-Inhalte erben die Sichtbarkeit ihres Cases.
    for table, fk in (("case_items", "case_id"), ("case_notes", "case_id")):
        op.execute(f"ALTER TABLE argus.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE argus.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_all ON argus.{table}
            USING (EXISTS (SELECT 1 FROM argus.cases c WHERE c.case_id = argus.{table}.{fk}))
            WITH CHECK (EXISTS (SELECT 1 FROM argus.cases c WHERE c.case_id = argus.{table}.{fk}))
            """
        )

    # ------------------------------------------------------------------
    # Schema-Invarianten
    # ------------------------------------------------------------------

    # Zeitzonenfalle: eine einzige Spalte vom Typ "timestamp without time zone"
    # genuegt, um jeden Zeitvergleich still zu verfaelschen. Die Funktion macht
    # daraus eine pruefbare Zusicherung - fuer Tests und fuer die CI.
    op.execute(
        """
        CREATE FUNCTION argus.assert_no_naive_timestamps() RETURNS void
        LANGUAGE plpgsql AS $$
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
        END $$
        """
    )
    op.execute("SELECT argus.assert_no_naive_timestamps()")

    # Fremdschluessel ohne ausdrueckliches ON DELETE laufen still auf NO ACTION.
    # Das ist selten gewollt und faellt sonst erst beim ersten Loeschversuch auf.
    op.execute(
        """
        CREATE FUNCTION argus.assert_foreign_keys_have_delete_rule() RETURNS void
        LANGUAGE plpgsql AS $$
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
        END $$
        """
    )
    op.execute("SELECT argus.assert_foreign_keys_have_delete_rule()")

    op.execute(
        """
        CREATE VIEW argus.schema_invariants AS
        SELECT 'no_naive_timestamps' AS invariant,
               NOT EXISTS (
                   SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'argus'
                      AND data_type IN ('timestamp without time zone',
                                        'time without time zone')
               ) AS holds
        UNION ALL
        SELECT 'all_fks_have_delete_rule',
               NOT EXISTS (
                   SELECT 1 FROM pg_constraint con
                     JOIN pg_class c ON c.oid = con.conrelid
                     JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'argus' AND con.contype = 'f'
                      AND con.confdeltype = 'a'
               )
        """
    )
    op.execute(
        "COMMENT ON VIEW argus.schema_invariants IS "
        "'Zusicherungen ueber das Schema selbst. Von den Tests und der CI "
        "abgefragt; holds = false ist ein Fehler, kein Hinweis.'"
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS argus.schema_invariants")
    op.execute("DROP FUNCTION IF EXISTS argus.assert_foreign_keys_have_delete_rule()")
    op.execute("DROP FUNCTION IF EXISTS argus.assert_no_naive_timestamps()")

    for table in ("case_notes", "case_items"):
        op.execute(f"DROP POLICY IF EXISTS {table}_all ON argus.{table}")
        op.execute(f"ALTER TABLE argus.{table} DISABLE ROW LEVEL SECURITY")

    for table in OWNED_TABLES:
        for action in ("select", "insert", "update", "delete"):
            op.execute(f"DROP POLICY IF EXISTS {table}_{action} ON argus.{table}")
        op.execute(f"ALTER TABLE argus.{table} DISABLE ROW LEVEL SECURITY")

    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA argus REVOKE SELECT ON TABLES FROM argus_readonly")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA argus "
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM argus_app"
    )
    # Rollen bleiben bestehen: sie sind clusterweit und koennen von anderen
    # Datenbanken benutzt werden. Ein DROP ROLE waere ein Eingriff ausserhalb
    # der Zustaendigkeit dieser Migration.
