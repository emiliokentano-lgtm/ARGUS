# Beispiel-Payloads

Zwei Gruppen:

- **`concept/`** — die Payloads aus Kapitel 3.2 des Konzepts, angepasst an die
  kanonische Protobuf-JSON-Abbildung. Abweichungen sind unten vollständig
  aufgeführt.
- **`error-cases/`** — die fünf ausdrücklich modellierten Fehlerfälle.

Alle Fixtures werden von `tests/test_examples.py` gegen beide Schema-Varianten
validiert und durch einen vollständigen Round-Trip geschickt. Sie sind damit
keine Dokumentation _über_ das Schema, sondern geprüfte Beispiele _aus_ ihm.

Fixtures dürfen einen Schlüssel `_case` tragen, der den abgebildeten Fall
beschreibt. Er ist nicht Teil des Schemas und wird vor der Validierung
entfernt (`conftest.load_fixture`).

---

## Abweichungen von Kapitel 3.2

Das Konzept bezeichnet die Payloads selbst als „Auszug". Sie wurden nicht
verworfen, sondern an drei Stellen angepasst. Jede Abweichung mit Grund:

### 1. Enums als kanonische Wertnamen

| Kapitel 3.2   | hier                       | betroffen               |
| ------------- | -------------------------- | ----------------------- |
| `"vessel"`    | `"ENTITY_TYPE_VESSEL"`     | `entity_ref.type`       |
| `"B"`         | `"SOURCE_RELIABILITY_B"`   | `source.reliability`    |
| `"minute"`    | `"TIME_PRECISION_MINUTE"`  | `occurred_at.precision` |
| `"city"`      | `"GEO_PRECISION_CITY"`     | `geo.precision`         |
| `"confirmed"` | `"EVENT_STATUS_CONFIRMED"` | `status`                |

**Grund:** Protobuf-JSON schreibt den Enum-Wertnamen vor, und `buf lint`
verlangt den Enum-Namen als Präfix. Die Alternative wäre gewesen, diese Felder
als freie Strings zu führen — das hätte Typsicherheit gegen Schreibweise
getauscht. `nav_status: "under_way"` bleibt unverändert: es liegt in
`attributes` (`google.protobuf.Struct`) und ist damit bewusst untypisiert.

### 2. `entities[].ref` ist ein Objekt, kein String

```jsonc
// Kapitel 3.2
{ "ref": "org:lei:529900...", "role": "actor" }

// hier
{ "ref": { "type": "ENTITY_TYPE_ORGANIZATION", "id": "lei:529900...",
           "resolution_status": "RESOLUTION_STATUS_RESOLVED",
           "resolved_entity_id": "01HZW..." },
  "role": "ENTITY_ROLE_ACTOR" }
```

**Grund:** Die Aufgabenstellung verlangt `EntityRef` ausdrücklich als eigenen
Typ mit `type`, `id` und optionalem `resolved_entity_id`, damit unaufgelöste
Verweise erhalten bleiben. Ein String kann den Auflösungszustand nicht tragen —
und genau der ist der Unterschied zwischen „dieses Schiff" und „eine MMSI, zu
der wir nichts gefunden haben".

### 3. Ausgelassene Felder ergänzt

Die Payloads im Konzept sind gekürzt (`"…"`, `{...}`, `[...]`). Ergänzt wurden:

- **`Event`**: `schema_version`, `ingested_at`, `source`, `raw_ref` — der
  Record-Header, den jedes Objekt trägt. Ohne ihn hätte das Beispiel die
  strenge Schema-Fassung nicht erfüllt.
- **`Event.geo.geometry`**: ein konkreter Punkt statt `{...}`.
- **`Event.scores.explanation`**: das Array aus Kapitel 7.3, ergänzt um zwei
  weitere Faktoren.
- **`Observation.dedupe_key`**: Pflichtfeld nach Kapitel 5.2 (Idempotenz).
- **`Observation.quality.time_quality`**: Herkunft des Zeitstempels.
- **`Observation.geo.precision`**: `GEO_PRECISION_EXACT`. Die Regel aus
  Kapitel 3.5 verlangt, dass Ortsgenauigkeit immer markiert ist.
- **`Observation.geo.h3_r5` / `h3_r9`**: die beiden anderen der drei in
  Kapitel 3.5 genannten Auflösungen.

Die im Konzept vorhandenen Werte wurden dabei **nicht** verändert.
`tests/test_examples.py::test_concept_observation_keeps_documented_values`
und das Gegenstück für `Event` prüfen genau das.

### Hinweis zu Bezeichnern

IDs, LEIs und ULIDs in den Beispielen sind Platzhalter im richtigen Format,
keine realen Kennungen. Das Konzept kürzt sie ebenfalls ab (`"01HZX..."`,
`"lei:529900..."`).

---

## Fehlerfälle

| Datei                                | Abgebildeter Fall           | Kernaussage                                                                                     |
| ------------------------------------ | --------------------------- | ----------------------------------------------------------------------------------------------- |
| `unknown-entity.observation.json`    | unbekannte Entität          | `entity_ref.id` behält den Rohbezug, `resolved_entity_id` fehlt, `resolution_status` erklärt es |
| `missing-timestamp.observation.json` | Position ohne Zeitstempel   | `observed_at` fehlt ganz; es wird nicht `ingested_at` untergeschoben                            |
| `country-only.event.json`            | Ereignis nur mit Landangabe | keine Geometrie, `GEO_PRECISION_COUNTRY`, kein erfundener Punkt in der Landesmitte              |
| `disputed.event.json`                | widersprüchliche Meldungen  | beide Behauptungen bleiben mit eigener Quelle erhalten, kein Sieger                             |
| `retracted.event.json`               | zurückgezogene Meldung      | Datensatz bleibt vollständig, Status und Versionskette dokumentieren den Widerruf               |
