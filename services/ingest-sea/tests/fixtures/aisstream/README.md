# Fixtures — AISStream

## Woher diese Daten stammen

**Sie sind nicht vom Live-Feed mitgeschnitten.** Sie sind nach der Drahtform von
AISStream.io und nach ITU-R M.1371 erzeugt. Feldnamen, Datentypen, Wertebereiche
und Sentinelwerte entsprechen dem, was der Dienst liefert; die Schiffe, ihre
Namen, Kennungen und Fahrten sind erfunden.

Der Grund: ein Mitschnitt braucht einen API-Schlüssel und eine Verbindung zu
`aisstream.io`. Die Netzrichtlinie dieser Entwicklungsumgebung lässt beides nicht
zu (`aisstream.io` antwortet mit `CONNECT tunnel failed, 403`). Statt echte
Nachrichten zu behaupten, die keine sind, steht hier, was der Fall ist.

**Was das für die Tests bedeutet.** Sie prüfen die Übersetzung und die
Fehlerbehandlung vollständig — jeder Zweig des Parsers läuft mit Daten in der
richtigen Form. Was sie _nicht_ prüfen können, ist eine Abweichung zwischen der
dokumentierten und der tatsächlichen Drahtform von AISStream. Genau dafür gibt es
die Schema-Drift-Erkennung des SDK: sie meldet ein unerwartetes Feld im Betrieb,
nicht im Test.

**Beim ersten echten Mitschnitt** gehören diese Dateien ersetzt — dieselben
Dateinamen, echte Nachrichten, dieser Abschnitt umgeschrieben. Die Tests laufen
unverändert weiter; sie hängen an der Form, nicht am Inhalt.

## Dateien

| Datei                 | Nachrichten | Inhalt                                                |
| --------------------- | ----------: | ----------------------------------------------------- |
| `stream-sample.jsonl` |         652 | Gemischte Viertelstunde über drei Seegebiete          |
| `edge-cases.jsonl`    |          22 | Ein Fall je Fehlerbild, jeder mit `_case` beschrieben |

Format: ein JSON-Objekt je Zeile (JSON Lines), Schlüssel sortiert, UTF-8.

### Verteilung in `stream-sample.jsonl`

| AISStream-Typ                  | AIS   | Anzahl |
| ------------------------------ | ----- | -----: |
| `PositionReport`               | 1/2/3 |    473 |
| `StandardClassBPositionReport` | 18    |     82 |
| `AidsToNavigationReport`       | 21    |     38 |
| `StaticDataReport`             | 24    |     30 |
| `ShipStaticData`               | 5     |     29 |
| `ExtendedClassBPositionReport` | 19    |     10 |
| nicht unterstützte Typen       | —     |     12 |

Die zwölf nicht unterstützten Nachrichten (`BaseStationReport`,
`BinaryBroadcastMessage`, `SafetyBroadcastMessage`,
`DataLinkManagementMessage`, `LongRangeAisBroadcastMessage`) sind Absicht: der
Überspringpfad des Konnektors soll mit Daten laufen, die im Feed tatsächlich
vorkommen, statt nur mit einem eigens gebauten Testfall.

Die Verteilung ist der Realität nachempfunden — Positionsberichte dominieren,
Stammdaten kommen alle paar Minuten. `stream-sample.jsonl` enthält außerdem
gestreut die Sentinelwerte des Standards (Heading 511, COG 360, SOG 102.3,
Rate of Turn −128 und ±127, Timestamp 60–63), damit sie nicht nur in den
Sonderfällen auftreten, sondern auch im Normalbetrieb durchlaufen.

### `_case` in `edge-cases.jsonl`

Jede Zeile trägt einen Schlüssel `_case` mit einer Beschreibung des Falls. Er ist
Dokumentation und **nicht Teil der Drahtform**; die Tests entfernen ihn vor dem
Parsen (`conftest.load_edge_cases`).

## Neu erzeugen

```
python tests/tools/make_fixtures.py
```

Deterministisch über einen festen Startwert und einen festen Startzeitpunkt:
derselbe Aufruf erzeugt byteweise dieselbe Datei. Die Fixtures altern nicht — ein
Test, der in sechs Monaten fehlschlägt, weil ein Zeitstempel inzwischen alt ist,
prüft die Uhr und nicht den Code.
