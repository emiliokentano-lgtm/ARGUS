# ADR 0004 — Bitemporalität selektiv, nicht überall

**Status:** angenommen
**Datum:** 2026-08-29
**Betrifft:** `services/api/migrations/`, ADR 0006, Replay und Zeitreise

---

## Kontext

Der dritte definierende Satz des Konzepts lautet: der Nutzer kann in der Zeit
zurückreisen. Kapitel 3.4 macht daraus eine konkrete Anforderung — die Frage
„was wussten wir am 12.03. um 04:00?" muss beantwortbar sein, nicht nur „was
wissen wir heute über den 12.03. um 04:00?".

Das sind zwei verschiedene Zeitachsen:

- **Gültigkeitszeit** — wann galt der Sachverhalt in der Welt (`observed_at`,
  `occurred_at`).
- **Transaktionszeit** — wann wusste das System davon (`ingested_at`,
  `sys_period`).

Was unabhängig von der Wahl gilt:

- Korrekturen sind der Normalfall, nicht die Ausnahme. Ein Erdbeben wird von
  M 6,1 auf M 5,8 revidiert; eine Meldung wird zurückgezogen. Prinzip 6 des
  Konzepts sagt: Ereignisse sind unveränderlich, Korrekturen erzeugen Versionen.
- Nachvollziehbarkeit ist der Zweck. Ein Alarm, der gestern ausgelöst hat, muss
  aus dem Wissensstand von gestern erklärbar sein — nicht aus dem von heute.
- Beobachtungen sind ihrer Natur nach unveränderlich. Ein Sensor misst; eine
  spätere, bessere Messung _ersetzt_ die frühere nicht, sie tritt daneben.

---

## Betrachtete Optionen

**A — nur Gültigkeitszeit.** Zeitstempel in den Zeilen, `UPDATE` überschreibt.
_Dafür:_ einfach, ein Datensatz je Sachverhalt. _Dagegen:_ die Frage „was wussten
wir gestern?" ist unbeantwortbar. Verletzt den dritten definierenden Satz.

**B — Vollständige Bitemporalität für alle Objekte.** Jede Tabelle bekommt
`sys_period` und eine Historientabelle. _Dafür:_ eine Regel für alles, keine
Ausnahmefälle im Kopf. _Dagegen:_ verdoppelt Schreiblast und Speicher auch dort,
wo nie korrigiert wird — bei Beobachtungen, die 99 % des Volumens ausmachen.

**C — Ereignis-Log, alles abgeleitet.** Nur ein Append-Log, jeder Zustand ist
eine Projektion. _Dafür:_ die reine Lehre; jeder vergangene Zustand ist
rekonstruierbar. _Dagegen:_ jede Ad-hoc-Abfrage braucht erst eine Projektion.
Für ein System, dessen Kernabfrage „Punkte im Ausschnitt" lautet, ist das der
falsche Zuschnitt — und für eine Person zu viel Maschinerie.

**D — Bitemporalität selektiv.** `sys_period` plus Historientabelle nur für
Objekte, die tatsächlich korrigiert werden. Für den Rest: Unveränderlichkeit als
Modelleigenschaft statt als Mechanik.

---

## Bewertungskriterien

| Kriterium                        | Gewicht | A   | B   | C   | D   |
| -------------------------------- | ------- | --- | --- | --- | --- |
| Erfüllt „was wussten wir wann?"  | hoch    | −−  | ++  | ++  | ++  |
| Schreibkosten bei 10⁶ Zeilen/Tag | hoch    | ++  | −−  | −   | +   |
| Verständlichkeit für Neue        | mittel  | ++  | +   | −−  | ∘   |
| Abfragbarkeit ohne Projektion    | hoch    | ++  | ++  | −−  | ++  |
| Umkehrbarkeit                    | hoch    | −−  | +   | −−  | +   |

Umkehrbarkeit ist bei A negativ, weil sie asymmetrisch ist: Historie später
_einzuführen_ geht, aber sie ist für die Vergangenheit unwiederbringlich
verloren. Diese Zeile entscheidet gegen A.

---

## Entscheidung

**Wir führen Bitemporalität über `sys_period` (`tstzrange`) plus
Historientabellen ein — für Event, Entity und Relation. Beobachtungen bekommen
sie nicht.**

Eine Beobachtung ist eine Messung zu einem Zeitpunkt. Sie wird nicht korrigiert;
eine bessere Messung ist eine _neue_ Beobachtung mit eigener Provenienz, und
welche gilt, entscheidet die Bewertung. Damit trägt der Teil des Systems, der
99 % der Zeilen erzeugt, die Kosten der Versionierung nicht.

Die zweitbeste Option ist B. Sie wird nicht gewählt, weil ihre Kosten dort
anfallen, wo ihr Nutzen null ist. Ihr Vorteil — eine Regel ohne Ausnahme — ist
real und der Preis dieser Entscheidung: siehe unten.

---

## Konsequenzen

**Positiv**

- `argus.event_as_of(text, timestamptz)` beantwortet die Zeitreisefrage in einer
  Funktion; jede Bewertung ist gegen den Wissensstand ihres Zeitpunkts prüfbar.
- Ein zurückgezogener Bericht verschwindet nicht, er bekommt ein Ende in
  `sys_period`. Prinzip 4 („Lücken zeigen, nicht kaschieren") gilt auch für
  Rücknahmen.
- Der heiße Pfad — Beobachtungen schreiben — bleibt ein einfaches `INSERT`.

**Negativ**

- **Doppelter Speicher bei änderungsfreudigen Objekten.** Ein Ereignis, dessen
  Bewertung sich zwanzigmal ändert, hat zwanzig Historienzeilen. Genau deshalb
  liegen Scores in einer eigenen Tabelle — eine Umgehung, die man kennen muss,
  sonst wirkt das Schema unnötig zerlegt.
- **Jede Abfrage muss wissen, welche Sicht sie will.** „Aktuell" ist nicht mehr
  der Standard, sondern ein Filter (`upper(sys_period) IS NULL`). Wer ihn
  vergisst, bekommt Duplikate — und zwar plausibel aussehende.
- **Zwei Modelle im selben Schema.** Beobachtungen sind unveränderlich per
  Konvention, Ereignisse per Mechanik. Wer das nicht weiß, sucht die
  Historientabelle zu `observations` und findet keine. Das ist der Preis für
  Option D gegenüber B, und er wird hier bezahlt, nicht wegdiskutiert.
- **`clock_timestamp()` ist Statementzeit, nicht Commit-Zeit.** Bei langen
  Transaktionen liegt die aufgezeichnete Transaktionszeit vor der Sichtbarkeit.
  Für die Nachvollziehbarkeit reicht das; für eine forensische Aussage auf die
  Millisekunde nicht.
- **Trigger-Schreibverstärkung.** Jedes `UPDATE` auf ein versioniertes Objekt ist
  zwei Schreibvorgänge. Massenaktualisierungen sind entsprechend teurer.
- **Historie wächst unbegrenzt.** Ohne Retention ist das eine Zeitbombe mit sehr
  langer Zündschnur.

**Was jetzt anders gemacht werden muss**

- Jede Sicht auf ein versioniertes Objekt braucht eine ausdrückliche Wahl
  zwischen „aktuell" und „zum Zeitpunkt X"; es gibt keinen sicheren Standard.
- Retention für Historientabellen ist zu definieren, bevor sie gebraucht wird.

---

## Bedingungen für eine Revision

- Eine Historientabelle übersteigt die **fünffache** Größe ihrer Haupttabelle —
  dann Aggregation oder Auslagerung nach ClickHouse.
- Beobachtungen müssen doch korrigierbar werden (etwa weil eine Quelle
  rückwirkend Werte ändert) — dann gilt Option B auch für sie, mit Partitionierung
  der Historie.
- Commit-genaue Transaktionszeit wird rechtlich verlangt — dann `xact_commit`
  aus dem WAL statt `clock_timestamp()`.
- Über **drei Objekttypen hinaus** wird Versionierung nachgerüstet: dann ist die
  Ausnahme die Regel geworden und Option B ist die ehrlichere Wahl.

---

## Nachweise

- Prompt 3: `argus.versioning_trigger()` und `argus.event_as_of()` sind
  implementiert; der bitemporale Test liefert für einen Stichzeitpunkt genau eine
  und die richtige Version.
- Prompt 3: Migrationen dreimal vorwärts und rückwärts sauber.
- **Nicht gemessen:** das Wachstum der Historientabellen im Dauerbetrieb. Die
  Fünffach-Schwelle oben ist gesetzt, nicht abgeleitet.
