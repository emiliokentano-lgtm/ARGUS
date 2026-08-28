# `packages/schemas` — kanonische Datenstrukturen

Dieses Paket ist die **einzige Wahrheitsquelle** für alle Datenstrukturen in
ARGUS. Python, TypeScript und die JSON-Schemas werden daraus generiert. Es gibt
keine handgeschriebene Kopie einer dieser Strukturen, in keiner Sprache. Wer
ein Feld braucht, ändert es hier — nicht im Konnektor, nicht im Frontend.

---

## 1. Zweck

Kapitel 3 des Konzepts fordert _ein_ Datenmodell für alles: ein Flugzeug, ein
Erdbeben und ein Zinsentscheid teilen sich dieselbe Grundstruktur. Dieses Paket
ist die Umsetzung dieser Forderung.

Zwölf Kernobjekte, je eine `.proto`-Datei:

| Objekt        | Datei               | Kurzbeschreibung                                        |
| ------------- | ------------------- | ------------------------------------------------------- |
| `Observation` | `observation.proto` | Messung/Meldung über eine Entität zu einem Zeitpunkt    |
| `Event`       | `event.proto`       | abgegrenztes Geschehen mit Ort und Zeit                 |
| `Entity`      | `entity.proto`      | Ding, das über Zeit existiert und identifizierbar ist   |
| `Relation`    | `relation.proto`    | gerichtete, zeitlich begrenzte Kante zwischen Entitäten |
| `Report`      | `report.proto`      | Medienartikel oder Meldung                              |
| `Track`       | `track.proto`       | zeitgeordnete Folge von Beobachtungen                   |
| `Assessment`  | `assessment.proto`  | bewertende Aussage mit Konfidenz und Urheber            |
| `Source`      | `source.proto`      | Quelle mit Zuverlässigkeit, Lizenz, Gesundheit          |
| `Aoi`         | `aoi.proto`         | Interessengebiet                                        |
| `Watchlist`   | `watchlist.proto`   | benannte Entitätsmenge mit Alarmbindung                 |
| `Alert`       | `alert.proto`       | ausgelöster Regel-/Detektortreffer mit Lebenszyklus     |
| `Case`        | `case.proto`        | Arbeitsbehälter für eine Untersuchung                   |

Dazu `common.proto` mit allem, was mindestens zwei Kernobjekte benutzen:
`Provenance`, `EntityRef`, `ObjectRef`, `TimeRange`, `Geometry`, `GeoPoint`,
`GeoLocation`, `Confidence`, `Evidence`, `ModelProvenance`, `Score`,
`ScoreFactor`, `Corroboration`, `Retraction`, `Contradiction`, `VersionInfo`,
`DataGap` sowie die geteilten Enums.

`EntityRef` ist bewusst ein eigener Typ und kein String: ein Verweis, der nicht
aufgelöst werden konnte, bleibt vollständig erhalten (`id` trägt den
quellnativen Bezeichner, `resolution_status` erklärt warum) statt verworfen
oder geraten zu werden.

---

## 2. Die Record-Header-Konvention

Jedes Kernobjekt belegt die Feldnummern 1–6 mit demselben Header, in derselben
Reihenfolge, mit derselben Bedeutung:

| Nr. | Feld             | Typ                  | Bedeutung                               |
| --- | ---------------- | -------------------- | --------------------------------------- |
| 1   | `<objekt>_id`    | `string`             | ULID, monoton sortierbar                |
| 2   | `schema_version` | `string`             | SemVer des Schema-Bundles               |
| 3   | `observed_at`    | `optional Timestamp` | Valid Time — wann ist es passiert       |
| 4   | `ingested_at`    | `Timestamp`          | Transaction Time — wann wusste ARGUS es |
| 5   | `source`         | `Provenance`         | Herkunft                                |
| 6   | `raw_ref`        | `string`             | Zeiger ins Bronze-Archiv                |
| 7–9 | —                | —                    | `reserved`, für Header-Erweiterungen    |
| 10+ |                  |                      | objektspezifisch                        |

**Warum flach statt als gemeinsame `meta`-Submessage?** Eine eingebettete
Message wäre DRY-er, hätte aber die JSON-Form der in Kapitel 3.2 festgelegten
Payloads verändert und jeden Zugriff um eine Ebene vertieft. Protobuf kennt
ohnehin keine Vererbung; die einheitlichen Feldnummern liefern denselben
Wiedererkennungswert ohne die Umbaukosten.

**`observed_at` ist `optional`, `ingested_at` nicht.** Das ist die
schemagewordene Fassung von Prinzip 4: Wenn eine Quelle keinen Zeitstempel
liefert, fehlt das Feld — es wird nicht stillschweigend `ingested_at`
eingesetzt. `Observation.quality.time_quality` hält fest, was der Fall ist.
Ein Wert, der frisch aussieht und es nicht ist, ist der gefährlichste Zustand
des Systems (Kapitel 10.6); dieses Schema macht ihn unmöglich.

---

## 3. Betrieb

```sh
make -C ../.. bootstrap   # Werkzeuge fuer das ganze Monorepo
make gen       # Python, TypeScript und JSON Schemas erzeugen
make check     # lint + gen + typecheck + test + breaking — das, was die CI fährt
```

Einzelne Ziele: `make help`.

### Erzeugte Artefakte (nicht eingecheckt)

| Pfad                                    | Inhalt                                                        | Erzeuger                  |
| --------------------------------------- | ------------------------------------------------------------- | ------------------------- |
| `gen/python/argus/v1/*_pb2.py`, `*.pyi` | Python-Klassen + Typannotationen                              | protoc                    |
| `gen/ts/argus/v1/*.ts`                  | TypeScript-Interfaces, `encode`/`decode`, `fromJSON`/`toJSON` | ts-proto                  |
| `gen/jsonschema/*.schema.json`          | JSON Schema 2020-12, proto3-treu                              | `tools/gen_jsonschema.py` |
| `gen/jsonschema/*.strict.schema.json`   | dieselben Schemas plus Pflichtfelder                          | dito                      |
| `build/descriptor.binpb`                | FileDescriptorSet                                             | buf                       |

`gen/` steht in `.gitignore`. Generierter Code im Repository ist eine zweite
Wahrheitsquelle, die früher oder später abweicht.

### Abhängigkeiten

- **buf** ≥ 1.72 (aus `node_modules`, nicht global) — Compiler, Lint,
  Breaking-Change-Prüfung, Formatierung.
- **ts-proto**, **@bufbuild/protobuf**, **typescript** — TypeScript-Erzeugung
  und Übersetzungsprüfung. `@bufbuild/protobuf` liefert die Draht-Kodierung;
  ts-proto v2 hat `protobufjs` dadurch abgelöst.
- **grpcio-tools** (liefert `protoc`), **protobuf**, **jsonschema**, **pytest**
  im Venv unter `.venv`.

Zwei Besonderheiten der Build-Umgebung, beide bewusst:

1. **Keine Remote-Plugins.** `buf.build` ist aus der Build-Umgebung nicht
   erreichbar, und ein Schema-Build soll ohnehin nicht von einem fremden Dienst
   abhängen. `buf.gen.yaml` benutzt ausschließlich lokale Plugins.
2. **`tools/protoc` ist ein Shim.** Es gibt kein `protoc`-Binary; `grpcio-tools`
   bringt denselben Compiler als Python-Modul mit und reicht alle Argumente
   unverändert weiter. Wer ein echtes `protoc` hat, setzt `ARGUS_PROTOC`.

### Warum protoc und nicht betterproto?

Das Konzept nennt „betterproto oder protoc + Pydantic-Adapter". Die Wahl fiel
auf den protoc-Standardgenerator, weil nur er `google.protobuf.Struct`/`Value`
und die **kanonische Protobuf-JSON-Abbildung** verlustfrei abbildet — genau die
Eigenschaft, die die Round-Trip-Zusicherung dieses Pakets trägt. betterproto
erzeugt angenehmere Dataclasses, weicht aber bei Well-Known-Types und der
JSON-Form ab; das ist an der Systemgrenze, an der Nachrichten zwischen Python,
Go, TypeScript und Postgres wandern, der falsche Tausch. Ein ADR dazu gehört
nach `docs/adr/` (Prompt 6).

---

## 4. JSON-Abbildung

Die JSON-Schemas bilden die **kanonische Protobuf-JSON-Abbildung** ab, keine
Wunschform. Wer JSON an ARGUS schickt, muss diese Regeln kennen:

| Regel                                               | Beispiel                                 |
| --------------------------------------------------- | ---------------------------------------- |
| Zeitstempel sind RFC-3339-Strings in UTC            | `"2026-08-28T09:14:03.221Z"`             |
| Enums sind **Wertnamen**, nicht Kurzformen          | `"ENTITY_TYPE_VESSEL"`, nicht `"vessel"` |
| 64-Bit-Ganzzahlen sind **Strings**                  | `"cost_micros": "1500000"`               |
| `null` bedeutet „nicht gesetzt"                     | `"end": null`                            |
| Feldnamen in `snake_case` **oder** `lowerCamelCase` | `obs_id` oder `obsId`                    |
| Nicht beide Schreibweisen desselben Feldes zugleich | sonst stiller Wertverlust                |
| Unbekannte Felder werden abgelehnt                  | `additionalProperties: false`            |

Die letzten beiden Punkte sind kein Formalismus. Die Python-Implementierung von
Protobuf **erzwingt** das Verbot der doppelten Schreibweise nicht, sondern
übernimmt stillschweigend den zuletzt gelesenen Wert. Das generierte JSON
Schema fängt den Fall ab; `tests/test_examples.py` hält beide Verhaltensweisen
fest.

### Zwei Schema-Varianten

- `<Objekt>.schema.json` — **proto3-treu, ohne Pflichtfelder.** proto3 kennt
  keine `required`-Felder; ein Schema, das welche behauptet, wäre eine Fiktion.
  Diese Variante prüft Struktur und Typen.
- `<Objekt>.strict.schema.json` — zusätzlich die Pflichtfelder aus
  `tools/required.json`. Das ist die **Vertragsebene der Pipeline**: was ein
  Konnektor liefern muss, damit die Nachricht angenommen und nicht in die
  Dead-Letter-Queue geschickt wird.

Ein Feld in `required.json` aufzunehmen ist eine brechende Änderung _für
Produzenten_ und braucht einen CHANGELOG-Eintrag (siehe §5.4).

---

## 5. Versionierung

Es gibt **drei** Versionsbegriffe. Sie werden regelmäßig verwechselt, deshalb
zuerst die Abgrenzung:

| Ebene              | Wo                                       | Ändert sich wann                                  |
| ------------------ | ---------------------------------------- | ------------------------------------------------- |
| **Proto-Package**  | `package argus.v1`                       | nur bei einem unvermeidbaren Bruch → `argus.v2`   |
| **Bundle-Version** | Feld `schema_version` in jeder Nachricht | bei jeder Schemaänderung, SemVer                  |
| **Feldnummern**    | `= 17`                                   | nie. Eine vergebene Nummer ist für immer vergeben |

### 5.1 Proto-Package: `argus.v1`

Das Package wechselt **nur**, wenn eine Änderung nötig ist, die sich nicht
rückwärtskompatibel machen lässt. Dann existieren `argus.v1` und `argus.v2`
nebeneinander, mit einem dokumentierten Migrationsfenster und einem Konverter in
beide Richtungen. Ein Paketwechsel ist ein Projektereignis mit ADR, kein
Refactoring.

### 5.2 Bundle-Version: das Feld `schema_version`

Jede Nachricht trägt die SemVer-Version des Schema-Bundles, mit dem sie erzeugt
wurde — `"1.4.0"`, nicht die Version eines einzelnen Objekts. Das ist die
Angabe, an der ein Konsument erkennt, ob er ein Feld erwarten darf.

- **PATCH** (`1.4.0` → `1.4.1`) — nur Kommentare, Beschreibungen, Werkzeuge.
  Kein Bit auf der Leitung ändert sich.
- **MINOR** (`1.4.0` → `1.5.0`) — additiv: neue Felder, neue Nachrichten, neue
  Enum-Werte, neue optionale Blöcke. Alte Leser funktionieren weiter.
- **MAJOR** (`1.4.0` → `2.0.0`) — brechend. Zieht einen Package-Wechsel nach
  `argus.v2` nach sich; die beiden gehören zusammen.

Produzenten setzen `schema_version` auf die Version, gegen die sie generiert
wurden. Konsumenten dürfen auf **kleiner-gleich** prüfen und **nie** auf
Gleichheit: eine Nachricht mit höherer MINOR-Version ist gültig, sie enthält nur
Felder, die der Leser noch nicht kennt.

### 5.3 Rückwärtskompatibilität: die Regeln

Erzwungen durch `buf breaking` (`FILE`- und `PACKAGE`-Kategorie) in `make check`.
Was die Prüfung nicht sieht, steht als Regel hier.

**Erlaubt (MINOR):**

- Neues Feld mit **neuer** Nummer hinzufügen.
- Neuen Enum-Wert am Ende hinzufügen.
- Neue Nachricht, neue Datei hinzufügen.
- Kommentare ändern.
- Ein Feld als `deprecated` markieren (siehe §5.5).

**Verboten (bricht):**

- **Feldnummer wiederverwenden** — auch nicht nach Jahren. Alte Nachrichten im
  Bronze-Archiv sind unveränderlich und werden mit dem aktuellen Schema
  gelesen; eine wiederverwendete Nummer liefert dann stillschweigend Unsinn.
  Gelöschte Nummern kommen in `reserved`.
- **Feld umbenennen** — die Feldnummer bliebe zwar gleich, aber der JSON-Name
  ändert sich, und ARGUS transportiert JSON über die API und den Bus.
  Umbenennen heißt: neues Feld anlegen, altes deprecaten, migrieren, in einer
  MAJOR-Version entfernen.
- **Feldtyp ändern** — inklusive der scheinbar harmlosen Fälle (`int32` →
  `int64` ändert die JSON-Form von Zahl zu String).
- **Enum-Wert umbenennen oder umnummerieren** — die JSON-Form ist der Name.
- **Die Bedeutung eines `*_UNSPECIFIED`-Wertes festlegen.** Der Nullwert ist
  „nicht gesetzt" und bleibt es. Wer ihn zu „unbekannt" umdeutet, macht jede
  vergessene Zuweisung zu einer Aussage. Für „geprüft, unbekannt" gibt es
  eigene Werte (`GEO_PRECISION_UNKNOWN`, `ENTITY_TYPE_UNKNOWN`).
- **`optional` entfernen** — vernichtet die Unterscheidung zwischen „fehlt" und
  „ist 0". Bei `heading_deg` heißt das: Nordkurs und Nichtmeldung werden
  ununterscheidbar.
- **`optional` nachträglich hinzufügen** — ändert die JSON-Ausgabe (Felder mit
  Standardwert verschwinden) und damit das Verhalten bestehender Leser.
- **Ein Feld in ein `oneof` verschieben** oder umgekehrt.

**Vorwärtskompatibilität — Pflicht für Konsumenten:**

- Unbekannte Enum-Werte müssen toleriert werden. Ein Detektor, der bei einem
  neuen `EventStatus` abstürzt, blockiert jede Schema-Erweiterung. In
  TypeScript sorgt `unrecognizedEnum=false` dafür, dass der Rohwert erhalten
  bleibt; in Python liefert der Reader die Ganzzahl.
- Unbekannte Felder dürfen bei der Weiterverarbeitung **nicht** verloren gehen.
  Protobuf bewahrt sie im binären Pfad automatisch auf; wer über JSON geht,
  muss sie ausdrücklich durchreichen oder verwerfen — aber protokolliert
  (Schema-Drift-Erkennung, Kapitel 5.2).

### 5.4 Was `buf breaking` nicht sieht

Drei Klassen von Brüchen sind für das Werkzeug unsichtbar und deshalb
Review-Aufgabe:

1. **Semantische Umdeutung.** `severity` von 0–1 auf 0–100 umstellen ist
   proto-kompatibel und trotzdem ein schwerer Bruch. Regel: Bedeutungsänderung
   = neues Feld.
2. **Neue Pflichtfelder in `required.json`.** Für Leser harmlos, für
   Produzenten brechend. Verlangt eine MINOR-Version, einen CHANGELOG-Eintrag
   und eine Übergangsfrist, in der die Pipeline nur warnt.
3. **Einheitenwechsel.** `distance_m` → Kilometer ist derselbe Fehler wie (1).
   Deshalb tragen alle Felder ihre Einheit im Namen (`_m`, `_kn`, `_deg`,
   `_ms`, `_micros`).

### 5.5 Deprecation

1. Feld mit `[deprecated = true]` markieren, Kommentar mit Nachfolger und
   frühestem Entfernungsdatum.
2. Produzenten füllen **beide** Felder für mindestens eine MINOR-Version.
3. Konsumenten migrieren; Nutzung wird per Metrik überwacht.
4. Entfernen erst in der nächsten MAJOR-Version. Die Nummer kommt in
   `reserved`, der Name in `reserved` (Namensreservierung verhindert das
   versehentliche Wiederbeleben).

### 5.6 Der `attributes`-Ausweg

Jedes Kernobjekt hat ein `attributes`-Feld vom Typ `google.protobuf.Struct` für
quellspezifische Zusatzfelder. Das ist Absicht — und eine Rutschbahn.

Regel: **Kernfelder werden typisiert, Randfelder gehen nach `attributes`.**
Ein Feld gehört typisiert, sobald es (a) von mehr als einer Quelle geliefert
wird, (b) in einer Abfrage gefiltert oder sortiert werden soll, oder (c) in
eine Score-Berechnung eingeht. Ein `attributes`-Feld, das eines dieser drei
Kriterien erfüllt und trotzdem dort liegt, ist technische Schuld und gehört in
den nächsten MINOR-Release typisiert.

### 5.7 Baseline und Release

`buf breaking` prüft gegen den Stand auf `main` (`tools/breaking.sh`). Solange
`main` noch kein Schema trägt, greift das eingecheckte Baseline-Image
`baseline/argus-v1.binpb`.

`make baseline` wird **nur beim Release** ausgeführt, zusammen mit dem
CHANGELOG-Eintrag im selben Commit. Wer die Baseline neu setzt, um eine
Prüfung loszuwerden, hat die Prüfung abgeschaltet.

---

## 6. Tests

`make test` — 155 Tests, drei Gruppen:

- **`test_examples.py`** — die Beispiel-Payloads aus Kapitel 3.2 und die
  Fehlerfälle: Validierung gegen beide Schema-Varianten, Parsen ohne unbekannte
  Felder, JSON- und Binär-Round-Trip, camelCase-Ausgabe.
- **`test_roundtrip.py`** — füllt **jedes Feld jedes Kernobjekts**
  programmatisch aus dem Descriptor (auch die, an die beim Schreiben der
  Beispiele niemand gedacht hat) und prüft dann Round-Trip und
  Schema-Konformität. `test_every_field_is_set` stellt sicher, dass der Füller
  wirklich alles erreicht — sonst prüft der Test weniger, als er vorgibt.
- **`test_error_cases.py`** — die fünf modellierten Fehlerfälle, jeweils an der
  Unterscheidung, um die es geht: fehlender Zeitstempel ≠ Epoche 0,
  unaufgelöste Entität behält ihren Rohbezug, Landangabe erfindet keinen Punkt,
  Widerspruch behält beide Seiten, Rückzug löscht nichts.

---

## 7. Bekannte Grenzen

- **Die Ereignis-Taxonomie ist nicht im Schema.** `Event.type` ist ein String
  (`"economic.rate_decision"`). Die Taxonomie wächst schneller als das Schema
  und wird in `data/taxonomies` gepflegt; ihre Validierung gehört in die
  Pipeline, nicht hierher. Preis: ein Tippfehler im Typ fällt nicht beim
  Kompilieren auf.
- **Keine Feldebenen-Provenienz.** `source` gilt für die ganze Nachricht. Ein
  aus drei Quellen fusioniertes `Event` kann heute nicht pro Feld sagen, woher
  der Wert stammt — nur über `Contradiction`, und das auch nur bei Konflikt.
  Falls die Fusion das braucht, ist das eine additive Erweiterung.
- **`Track.points` skaliert nicht als Nachricht.** Ein Jahr AIS eines Schiffes
  sind Millionen Punkte. Das Schema erlaubt es, die API darf es nicht
  ausliefern; dafür gibt es `simplifications`. Die Durchsetzung ist Sache der
  API-Schicht.
- **JSON Schema kann `oneof` nicht exakt abbilden.** Die generierten Schemas
  lassen mehrere Zweige einer `oneof`-Gruppe gleichzeitig zu; erst der
  Protobuf-Parser lehnt das ab. Für `Geometry` heißt das: die Prüfung „genau
  eine Form" passiert eine Stufe später.
- **Kein Go-Codegen.** Kapitel 15 sieht Go für den Hochlast-Ingest vor. Sobald
  `services/ingest-air` und `ingest-sea` entstehen, kommt ein
  `protoc-gen-go`-Eintrag in `buf.gen.yaml` dazu — die Protos ändern sich
  dafür nicht.
- **Die JSON-Schemas sind Validierung, keine Serialisierung.** Sie prüfen, was
  hereinkommt. Erzeugt wird JSON immer über die generierten Klassen.

---

## 8. Änderungen einreichen

1. `.proto` ändern.
2. `make check` — muss grün sein, `buf breaking` eingeschlossen.
3. Bei neuen Pflichtfeldern: `tools/required.json` ergänzen.
4. `CHANGELOG.md` ergänzen, mit Versionssprung nach §5.2.
5. Bei brechender Änderung: ADR unter `docs/adr/`, bevor Code entsteht.
