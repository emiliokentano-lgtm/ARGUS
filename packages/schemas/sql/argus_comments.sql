-- ARGUS — Kommentare zu Tabellen, Spalten und Funktionen.
-- Erzeugt aus den Migrationen; siehe argus_schema.sql.

COMMENT ON TABLE argus.data_gaps IS 'Bekannte Luecken. Werden ausdruecklich transportiert und dargestellt, statt durch Interpolation kaschiert zu werden (Prinzip 4).';
COMMENT ON TABLE argus.entities_history IS 'Abgeloeste Fassungen. Wird ausschliesslich vom Trigger befuellt.';
COMMENT ON TABLE argus.entity_aliases IS 'Externe Bezeichner und Namensvarianten. Die Eindeutigkeit ueber (id_type, id_value) ist der Kern der Entity Resolution: derselbe Bezeichner darf nie auf zwei Entitaeten zeigen.';
COMMENT ON TABLE argus.events IS 'Ereignisse, bitemporal versioniert. occurred_* ist die Valid Time, observed_at/ingested_at die Transaction Time, sys_period die Gueltigkeit dieser Fassung im System.';
COMMENT ON TABLE argus.events_history IS 'Abgeloeste Ereignisfassungen. Nur der Trigger schreibt hierher.';
COMMENT ON TABLE argus.observations IS 'Beobachtungen: die haeufigste Nachricht im System. Partitioniert nach observed_at mit Tagesintervall. Rohpositionen bleiben 90 Tage detailliert erhalten (Kapitel 14).';
COMMENT ON TABLE argus.observations_default IS 'Auffangpartition fuer Zeitstempel ausserhalb der angelegten Tagespartitionen. Nicht leer = Datenqualitaetsvorfall.';
COMMENT ON TABLE argus.report_translations IS 'Maschinelle Uebersetzungen. Das Original bleibt in argus.reports; eine Uebersetzung ersetzt es nie (Kapitel 11).';
COMMENT ON VIEW argus.schema_invariants IS 'Zusicherungen ueber das Schema selbst. Von den Tests und der CI abgefragt; holds = false ist ein Fehler, kein Hinweis.';
COMMENT ON TABLE argus.score_factors IS 'Zerlegung eines Scores. Eigene Tabelle statt JSONB, weil die Frage "welcher Faktor dominiert" relational beantwortet werden muss (Kapitel 7.3).';
COMMENT ON TABLE argus.sources IS 'Quellenregister. license_id ist Pflicht - das CI-Gate aus Kapitel 14 lehnt Quellen ohne Lizenzeintrag ab.';
