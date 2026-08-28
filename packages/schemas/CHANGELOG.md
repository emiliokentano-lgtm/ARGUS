# Changelog — ARGUS Schema-Bundle

Alle Änderungen an den kanonischen Datenstrukturen. Format nach
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach
[SemVer](https://semver.org/lang/de/) — die Regeln stehen in `README.md`, §5.

Die hier geführte Version ist die **Bundle-Version**: der Wert, den jede
Nachricht im Feld `schema_version` trägt. Sie ist nicht identisch mit dem
Proto-Package (`argus.v1`), das sich nur bei einem unvermeidbaren Bruch ändert.

## [Unreleased]

## [1.0.0] — 2026-08-28

Erstes Schema-Bundle. Proto-Package `argus.v1`.

### Hinzugefügt

- **Zwölf Kernobjekte**: `Observation`, `Event`, `Entity`, `Relation`,
  `Report`, `Track`, `Assessment`, `Source`, `Aoi`, `Watchlist`, `Alert`,
  `Case` — je eine Datei unter `proto/argus/v1/`.
- **`common.proto`** mit den geteilten Typen: `Provenance`, `EntityRef`,
  `ObjectRef`, `TimeRange`, `Geometry` (Punkt, Linie, Polygon, MultiPolygon,
  BoundingBox, Kreis, Korridor), `GeoPoint`, `GeoLocation`, `PlaceRef`,
  `Confidence`, `Evidence`, `ModelProvenance`, `Score`, `ScoreFactor`,
  `Corroboration`, `Retraction`, `Contradiction`, `ContradictingClaim`,
  `VersionInfo`, `DataGap`.
- **Record-Header-Konvention**: Feldnummern 1–6 in jedem Kernobjekt für
  `<objekt>_id`, `schema_version`, `observed_at`, `ingested_at`, `source`,
  `raw_ref`; 7–9 `reserved`.
- **Bitemporales Zeitmodell**: `observed_at` (Valid Time, `optional`) getrennt
  von `ingested_at` (Transaction Time, immer gesetzt).
- **Admiralty-Bewertung** als zwei getrennte Enums: `SourceReliability` (A–F)
  und `InformationCredibility` (1–6).
- **Erklärbare Scores**: `Score` mit `ScoreFactor`-Array, `weights_version` und
  `profile_id` — ein Score ohne Erklärung ist nicht darstellbar.
- **Reproduzierbarkeit des KI-Layers**: `ModelProvenance` mit Modellversion,
  Prompt-Hash, Temperatur und Parametern; `Evidence` mit Zitat und
  Zeichenoffsets.
- **Datenlücken als First-Class-Objekt**: `DataGap` mit `GapReason`, benutzt
  von `Track`, `Source.health`, `Event` und `Case`.
- **Explizit modellierte Fehlerfälle** (Fixtures unter `examples/error-cases/`):
  unbekannte Entität, Position ohne Zeitstempel, Ereignis nur mit Landangabe,
  widersprüchliche Meldungen, zurückgezogene Meldung.

### Werkzeuge

- `buf.yaml` mit `STANDARD`-Lint plus Kommentarpflicht auf Message- und
  Enum-Ebene; `buf format` als Teil von `make lint`.
- `buf.gen.yaml` für Python (protoc + `pyi`) und TypeScript (ts-proto),
  ausschließlich lokale Plugins.
- `tools/gen_jsonschema.py` erzeugt JSON Schema 2020-12 aus demselben
  Descriptor-Set — je Objekt eine proto3-treue und eine strenge Fassung.
- `tools/required.json` als Pflichtfeld-Vertrag der Pipeline.
- `tools/breaking.sh` prüft gegen `main`, ersatzweise gegen
  `baseline/argus-v1.binpb`.
- 155 Tests: Beispiel-Payloads, vollständiger Round-Trip über jedes Feld jedes
  Kernobjekts, Fehlerfall-Semantik.

### Entwurfsentscheidungen mit Begründung

- **Flacher Header statt `meta`-Submessage** — erhält die JSON-Form der
  Beispiel-Payloads aus Konzept-Kapitel 3.2 und vermeidet eine zusätzliche
  Verschachtelungsebene in jedem Zugriff.
- **`Geometry` typisiert statt GeoJSON-`Struct`** — Geometrien sind Kernfelder;
  ein freies Struct verschiebt jede Validierung in die Laufzeit.
- **`Event.type` als String statt Enum** — die Taxonomie wächst schneller als
  das Schema und wird in `data/taxonomies` gepflegt.
- **protoc statt betterproto für Python** — nur der Standardgenerator bildet
  `google.protobuf.Struct`/`Value` und die kanonische Protobuf-JSON-Abbildung
  verlustfrei ab. Ausführlich in `README.md`, §3.
- **`h3_r5`/`h3_r7`/`h3_r9` als eigene Felder statt Map** — die drei
  Auflösungen aus Konzept-Kapitel 3.5 sind fest, und jede Viewport-Abfrage
  braucht sie als Indexspalten.

### Abweichungen von den Beispiel-Payloads des Konzepts

Die Payloads aus Kapitel 3.2 wurden übernommen, aber an die kanonische
Protobuf-JSON-Abbildung angepasst. Die vollständige Liste mit Begründung steht
in `examples/README.md`.

[Unreleased]: https://example.invalid/argus/compare/schemas-v1.0.0...HEAD
[1.0.0]: https://example.invalid/argus/releases/tag/schemas-v1.0.0
