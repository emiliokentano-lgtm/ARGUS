# ADR 0005 — ULID intern, externe Kennungen niemals als Schlüssel

**Status:** angenommen
**Datum:** 2026-08-29
**Betrifft:** `packages/schemas/`, `services/api/migrations/`, alle Konnektoren

---

## Kontext

Jedes Objekt braucht eine Kennung. Zwei Fragen, die gern vermengt werden:

1. Wie sieht der **interne** Primärschlüssel aus?
2. Was passiert mit **externen** Kennungen — MMSI, IMO, ICAO24, ISIN, LEI, USGS
   Event-ID —, die von den Quellen mitgeliefert werden?

Was unabhängig von der Wahl gilt:

- Kennungen werden verteilt vergeben: Konnektoren erzeugen sie, bevor die
  Datenbank die Zeile sieht. Eine Sequenz aus Postgres scheidet damit aus.
- Zeitliche Sortierbarkeit ist wertvoll: Beobachtungen sind zeitpartitioniert,
  und ein monoton wachsender Schlüssel hält B-Tree-Einfügungen am rechten Rand
  statt über den ganzen Index verstreut.
- Kennungen erscheinen in URLs, Logs und Fehlerberichten. Lesbarkeit und
  Kopierbarkeit sind keine Kosmetik.
- **Externe Kennungen sind nicht stabil.** Eine MMSI wird bei Flaggenwechsel neu
  vergeben; eine IMO kann in einer Quelle schlicht falsch sein; eine LEI ist
  bei Fusionen übertragbar. Das ist der eigentliche Kern dieses ADRs.

---

## Betrachtete Optionen

**A — UUIDv4.** Zufällig, 128 Bit, überall verfügbar. _Dafür:_ nativer
Postgres-Typ, keine Bibliothek. _Dagegen:_ keinerlei Sortierung; Einfügungen
verteilen sich über den ganzen Index und zerlegen den Cache.

**B — Snowflake.** 64 Bit aus Zeitstempel, Maschinen-ID und Zähler. _Dafür:_
kompakt, sortierbar, `bigint`. _Dagegen:_ braucht eine koordinierte Vergabe von
Maschinen-IDs — eine Betriebsaufgabe, die bei einem Konnektor pro Container zur
Fehlerquelle wird. Epochenabhängig und damit endlich.

**C — UUIDv7.** RFC 9562: Zeitstempel in den oberen Bits, Rest zufällig.
_Dafür:_ sortierbar _und_ nativer `uuid`-Typ, 16 Byte. Standardisiert.
_Dagegen:_ in PostgreSQL erst ab Version 18 als eingebaute Funktion; in Text
dargestellt nicht als zeitlich lesbar erkennbar.

**D — ULID.** 128 Bit, Crockford-Base32, 26 Zeichen, zeitlich sortierbar.
_Dafür:_ das Konzept nennt sie ausdrücklich; sortierbar, gut lesbar, keine
Koordination nötig. _Dagegen:_ siehe Konsequenzen.

Für die zweite Frage gibt es nur zwei Antworten: externe Kennung als
Primärschlüssel verwenden — oder nicht.

---

## Bewertungskriterien

| Kriterium                        | Gewicht | UUIDv4 | Snowflake | UUIDv7 | ULID |
| -------------------------------- | ------- | ------ | --------- | ------ | ---- |
| Verteilte Vergabe ohne Absprache | hoch    | ++     | −−        | ++     | ++   |
| Zeitliche Sortierbarkeit         | hoch    | −−     | ++        | ++     | ++   |
| Speicher pro Zeile               | mittel  | +      | ++        | +      | −    |
| Lesbarkeit in Logs und URLs      | mittel  | ∘      | ++        | ∘      | ++   |
| Standardisierung                 | niedrig | ++     | −         | ++     | −    |
| Umkehrbarkeit                    | hoch    | ∘      | −         | +      | +    |

---

## Entscheidung

**Wir benutzen ULIDs als interne Kennungen — und externe Kennungen niemals als
Primärschlüssel.**

Externe Kennungen leben in `entity_aliases` mit `UNIQUE(id_type, id_value)` und
eigener Gültigkeitsspanne. `EntityRef.id` transportiert die schema-präfixierte
Behauptung der Quelle (`"imo:9284435"`, `"mmsi:211331640"`); die Auflösung auf
eine interne Entität ist ein eigener, protokollierter Schritt und keine
Gleichsetzung.

Warum das die wichtigere Hälfte ist: Wer MMSI zum Primärschlüssel macht, hat
ein System gebaut, in dem zwei Schiffe über die Jahre dieselbe Zeile teilen —
und keine Möglichkeit, das nachträglich zu trennen, weil die Fremdschlüssel
bereits gesetzt sind. Der Fehler ist beim Schreiben billig und später unbezahlbar.

Die zweitbeste Option für Frage 1 ist UUIDv7. Sie ist ULID technisch ebenbürtig,
standardisiert und im Speicher kompakter; ULID gewinnt über die Lesbarkeit und
darüber, dass das Konzept sie nennt. Der Abstand ist klein — deshalb ist der
Migrationspfad unten Teil der Entscheidung, nicht ein Zugeständnis.

---

## Konsequenzen

**Positiv**

- Konnektoren vergeben Kennungen ohne Rückfrage an die Datenbank; das
  Zwei-Phasen-Cursor-Verfahren aus Prompt 4 braucht genau das.
- Einfügungen landen am rechten Indexrand — passend zur Zeitpartitionierung.
- Eine ULID im Log verrät auf einen Blick, wann sie erzeugt wurde.
- Eine falsch zugeordnete MMSI ist eine korrigierbare Alias-Zeile, kein
  Datenmodellschaden.

**Negativ**

- **26 Byte Text statt 16 Byte `uuid`.** Bei 10⁹ Beobachtungen sind das rund
  **10 GB** allein in der Schlüsselspalte, plus jeder Fremdschlüssel, plus jeder
  Index. Der Preis dieser Entscheidung ist in Gigabyte messbar.
- **Kein nativer Typ.** Vergleiche sind Textvergleiche; Kollation und
  Groß-/Kleinschreibung müssen festgelegt sein, sonst sortiert die Datenbank
  anders als die Anwendung.
- **Keine Monotonie über Prozesse hinweg.** Innerhalb einer Millisekunde ist die
  Reihenfolge zweier ULIDs aus zwei Konnektoren zufällig. Wer ULID-Sortierung mit
  Ereignisreihenfolge verwechselt, baut einen Fehler, der nur unter Last auftritt.
- **ULID ist kein IETF-Standard**, UUIDv7 ist es. Bei Integration in fremde
  Systeme ist das ein Argument, das man verliert.
- **Der Alias-Umweg kostet bei jedem Lesezugriff einen Join** und bei jeder
  Erfassung eine Auflösung. Die Alternative wäre schneller — und falsch.

**Was jetzt anders gemacht werden muss**

- Die Auflösung externe Kennung → Entität ist mit Zeitbezug und Konfidenz zu
  protokollieren; sie ist eine Behauptung, keine Tatsache.
- Kein Fremdschlüssel darf je auf `id_value` zeigen, ausschließlich auf die
  interne ULID. Diese Regel gehört in die Schema-Invarianten.

---

## Bedingungen für eine Revision

- Über **10⁹ Beobachtungen**: dann wiegen 10 GB Schlüsselspeicher schwerer als
  die Lesbarkeit — auf UUIDv7 im nativen `uuid`-Typ wechseln.
- **PostgreSQL 18** wird Zielversion: `uuidv7()` ist eingebaut, das
  Speicherargument verliert seine Gegenkraft.
- Ein **anzubindendes Fremdsystem verlangt UUIDs** in seinem Datenmodell.
- Die Alias-Auflösung wird zum Engpass (über **10 %** der Erfassungslatenz) —
  dann Materialisierung des Ergebnisses, nicht Aufgabe des Prinzips.

---

## Nachweise

- Prompt 1: `EntityRef.id` trägt die schema-präfixierte Quellbehauptung; die
  Schemas sind in 155 Tests geprüft.
- Prompt 3: `entity_aliases` mit `UNIQUE(id_type, id_value)` und
  Gültigkeitsspanne liegt im Schema; die Invarianten-Sicht prüft, dass jeder
  Fremdschlüssel eine Löschregel hat.
- **Nicht gemessen:** der Speicherunterschied ULID gegenüber `uuid` in der
  Praxis; die 10 GB sind gerechnet (10 Byte × 10⁹), nicht gewogen. Und die
  Alias-Auflösung ist noch nicht unter Last gelaufen.
