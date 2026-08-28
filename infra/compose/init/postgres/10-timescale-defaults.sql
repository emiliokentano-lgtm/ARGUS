-- ARGUS — TimescaleDB-Grundeinstellungen fuer die Entwicklungsumgebung.
--
-- Hypertables, Retention und Kompression gehoeren in die Migrationen
-- (Prompt 3) und nicht hierher. Hier steht nur, was den Stack betrifft.
--
-- :"DBNAME" ist eine von psql selbst gesetzte Variable und enthaelt die
-- Datenbank, mit der der Entrypoint verbunden ist.

-- Telemetrie aus: eine selbst gehostete Lageplattform meldet ihre
-- Nutzungsdaten nicht nach aussen.
ALTER DATABASE :"DBNAME" SET timescaledb.telemetry_level = 'off';

-- UTC als Datenbankstandard. ARGUS rechnet ausschliesslich in UTC; eine
-- abweichende Serverzeitzone waere eine stille Fehlerquelle bei jedem
-- Zeitvergleich.
ALTER DATABASE :"DBNAME" SET timezone = 'UTC';
