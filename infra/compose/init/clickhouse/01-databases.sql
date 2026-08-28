-- ARGUS — ClickHouse-Grundgeruest.
--
-- Nur Datenbanken und Stack-Metadaten. Die Analysetabellen entstehen ueber
-- Migrationen und gehoeren nicht in ein Compose-Init-Skript.

CREATE DATABASE IF NOT EXISTS argus
  COMMENT 'Gold-Layer: Aggregate und Auswertungen';

CREATE DATABASE IF NOT EXISTS argus_staging
  COMMENT 'Zwischenstand fuer Ladevorgaenge und Backfills';

CREATE DATABASE IF NOT EXISTS argus_meta
  COMMENT 'Metadaten des lokalen Stacks (Smoke-Tests, Initialisierungsstand)';

CREATE TABLE IF NOT EXISTS argus_meta.stack_info
(
  key        String,
  value      String,
  updated_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY key
COMMENT 'Schluessel-Wert-Ablage fuer Stackzustand; von "make health" gelesen';

INSERT INTO argus_meta.stack_info (key, value) VALUES ('initialized', '1');
