# ADR 0003 — H3 als Vorfilter, PostGIS als Antwort

**Status:** angenommen
**Datum:** 2026-08-29
**Betrifft:** `packages/geo/`, `services/api/migrations/`, AOI-Auswertung

---

## Kontext

Die häufigste Abfrage des Systems lautet: „welche Beobachtungen der letzten
Stunde liegen in diesem Ausschnitt?" — bei viewport-getriebener Last mehrmals pro
Sekunde und Nutzer, gegen eine Tabelle mit 10⁸–10⁹ Zeilen. Die zweithäufigste:
„liegt dieser Punkt in einem der 200 überwachten Gebiete?", ausgewertet für jede
eingehende Beobachtung.

Was unabhängig von der Wahl gilt:

- Postgres mit PostGIS ist gesetzt (ADR 0002). Die Frage ist nicht _ob_ PostGIS,
  sondern _ob zusätzlich_ ein diskretes Gitter.
- Genauigkeit ist nicht verhandelbar: ein Schiff, das 300 m außerhalb eines
  Gebiets fährt, darf keinen Alarm auslösen.
- Ein GiST-Index auf `geography(Point,4326)` ist schnell, aber jede Prüfung ist
  eine Geometrieoperation. Der Preis liegt nicht in der Genauigkeit, sondern in
  den Kosten _pro Prüfung_ — multipliziert mit Millionen Zeilen.
- Kacheln und Aggregate („wie viele Schiffe pro Zelle") sind auf einem Gitter
  trivial und auf roher Geometrie ein Gruppierungsproblem.

---

## Betrachtete Optionen

**A — reines PostGIS.** `ST_DWithin`, `ST_Contains`, GiST. _Dafür:_ exakt, ein
System, kein zusätzlicher Begriff im Modell. _Dagegen:_ Aggregation über Zellen
fehlt; jede Gebietsprüfung ist eine vollwertige Geometrieoperation.

**B — Geohash.** Zeichenketten-Präfixe als Gitter. _Dafür:_ überall vorhanden,
Präfixsuche ist eine `LIKE`-Abfrage. _Dagegen:_ rechteckige Zellen mit stark
schwankender Fläche je Breitengrad; benachbarte Zellen können sehr
unterschiedliche Präfixe haben. Kantenartefakte sind bekannt und lästig.

**C — S2 (Google).** Hilbert-Kurve auf einem Würfel, 64-Bit-Zellen. _Dafür:_
exakte Verschachtelung über alle Ebenen, sehr gute Abdeckungsalgorithmen für
Polygone. _Dagegen:_ quadratische Zellen mit ungleichen Nachbarabständen (Kante
vs. Ecke); die Python-Anbindung ist dünner gepflegt als die von H3.

**D — H3 (Uber).** Hexagonales Gitter, 16 Auflösungen, 64-Bit-Zellindex.
_Dafür:_ alle sechs Nachbarn haben denselben Mittelpunktsabstand — für „Umkreis"
und für Dichteflächen genau die richtige Eigenschaft; gepflegte Bindings für
Python, Go, TypeScript und Postgres. _Dagegen:_ siehe Konsequenzen.

**E — nichts tun**, nur B-Tree auf `(observed_at, lat, lon)`. Erledigt den
Ausschnitt näherungsweise und die Gebietsprüfung gar nicht; verworfen.

---

## Bewertungskriterien

| Kriterium                    | Gewicht | PostGIS | Geohash | S2  | H3  |
| ---------------------------- | ------- | ------- | ------- | --- | --- |
| Genauigkeit der Endantwort   | hoch    | ++      | −       | +   | +   |
| Kosten pro Prüfung bei 10⁸+  | hoch    | −       | ++      | ++  | ++  |
| Gleichmäßige Nachbarschaft   | mittel  | n. a.   | −−      | ∘   | ++  |
| Aggregation, Dichte, Kacheln | mittel  | −       | +       | ++  | ++  |
| Bindings in Py/Go/TS/SQL     | mittel  | ++      | ++      | ∘   | ++  |
| Umkehrbarkeit                | hoch    | ++      | +       | +   | +   |

Die Optionen sind nicht wirklich Alternativen: ein Gitter _ersetzt_ PostGIS
nicht, es verkleinert die Frage, die PostGIS beantworten muss.

---

## Entscheidung

**Wir speichern H3-Indizes in den Auflösungen r5, r7 und r9 als `bigint` neben
der PostGIS-Geometrie und benutzen H3 ausschließlich als Vorfilter. Die
verbindliche Antwort gibt immer PostGIS.**

Die zweitbeste Option ist S2 — technisch sauberer bei der Verschachtelung,
schwächer bei den Bindings und bei der Nachbarschaftsgleichheit, die für
Umkreis-Abfragen und Dichteflächen den Ausschlag gibt.

Warum nicht „nur PostGIS", die naheliegende Wahl: PostGIS scheitert nicht an der
Genauigkeit, sondern an den Kosten pro Prüfung. Ein `bigint`-Vergleich auf einem
B-Tree kostet Nanosekunden, `ST_Contains` gegen ein Polygon mit 400 Stützpunkten
kostet Mikrosekunden. Bei einer Kandidatenmenge von zehn Zeilen ist das
gleichgültig, bei zehn Millionen ist es der Unterschied zwischen 8 ms und 8 s.
H3 beantwortet die Frage nicht — es macht sie kleiner.

---

## Konsequenzen

**Positiv**

- Ausschnitts- und Umkreisabfragen filtern über einen B-Tree, bevor Geometrie
  angefasst wird; Dichteflächen und Kacheln sind ein `GROUP BY h3_r7`.
- `packages/geo` kapselt die Umrechnung; die Datenbank sieht nur `bigint`.

**Negativ**

- **Zwei Wahrheiten, die auseinanderlaufen können.** `geom` und `h3_r*` müssen
  denselben Punkt beschreiben. Keine Datenbank-Constraint erzwingt das — es hängt
  am Schreibpfad. Wenn jemand `geom` per `UPDATE` korrigiert und die H3-Spalten
  vergisst, verschwinden Zeilen aus Abfragen, ohne dass etwas fehlschlägt.
- **H3-Zellen schachteln sich nicht exakt.** Eine r7-Zelle ist nicht die exakte
  Vereinigung ihrer r9-Kinder; hexagonale Gitter können das nicht. Wer r9 zu r7
  aggregiert, bekommt eine Näherung. S2 hätte diesen Fehler nicht.
- **Speicher.** Drei `bigint`-Spalten kosten 24 Byte pro Zeile, bei 10⁹ Zeilen
  rund **24 GB** allein für den Vorfilter, plus Indizes.
- **Zwölf Pentagone je Auflösung.** Sie liegen im offenen Ozean, aber sie
  existieren; Code, der sechs Nachbarn annimmt, ist dort falsch.
- **AOI-Abdeckung ist näherungsweise** — deshalb ist die PostGIS-Nachprüfung
  nicht optional, sondern Teil der Zusage.

**Was jetzt anders gemacht werden muss**

- H3-Spalten dürfen nur über einen gemeinsamen Schreibpfad gesetzt werden
  (Trigger oder generierte Spalten), nie von Hand.
- Jede Abfrage, die H3 benutzt, braucht die PostGIS-Nachprüfung im selben
  Statement. Ein Vorfilter ohne Nachprüfung ist ein Fehlalarm-Generator.

---

## Bedingungen für eine Revision

- Der gemessene Gewinn des Vorfilters liegt unter **Faktor 3** — dann kostet er
  mehr Speicher und Komplexität, als er bringt, und PostGIS allein genügt.
- Exakte hierarchische Aggregation wird fachlich verlangt — dann S2.
- Über **10⁹ Zeilen** und der Speicherpreis der drei Spalten wird spürbar; dann
  auf eine einzige Auflösung reduzieren.
- Ein Gebiet muss auf **unter 10 m genau** ausgewertet werden — dann greift die
  H3-Stufe zu grob und der Vorfilter braucht eine feinere Auflösung.

---

## Nachweise

- Prompt 3: `h3_r7 bigint` mit B-Tree und `geography(Point,4326)` mit GiST liegen
  im Schema; 24-Stunden-Abfrage in 0,8 ms über Bitmap Index Scan.
- Prompt 5: `packages/geo/argus_geo/h3.py` wandelt zwischen H3-Zeichenkette und
  `bigint`; 30 Tests.
- **Nicht gemessen:** der eigentliche Punkt dieses ADRs. Der Geschwindigkeitsgewinn
  von H3-Vorfilter gegenüber reinem PostGIS ist bislang **nicht** verglichen
  worden. Die Entscheidung stützt sich auf das Kostenargument oben, nicht auf eine
  eigene Messung — die Revisionsbedingung „Faktor 3" ist deshalb die wichtigste
  Zeile dieses Dokuments.
