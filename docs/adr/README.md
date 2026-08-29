# Architecture Decision Records

Ein ADR beantwortet die Frage, die in zwei Jahren jemand stellt: _„Warum ist das
so und nicht anders?"_ Es ist kein Protokoll und keine Dokumentation. Wenn eine
Entscheidung offensichtlich ist, braucht sie kein ADR; wenn sie es nicht ist, ist
der Abschnitt über die verworfenen Alternativen der wichtigste des Dokuments.

Vorlage: [`0000-template.md`](0000-template.md).

## Bestand

| Nr.                             | Titel                                                  | Status     |
| ------------------------------- | ------------------------------------------------------ | ---------- |
| [0001](0001-message-bus.md)     | NATS JetStream als Nachrichtenbus                      | angenommen |
| [0002](0002-primaerspeicher.md) | PostgreSQL als Primärspeicher, mit benannten Ausnahmen | angenommen |
| [0003](0003-geo-indexierung.md) | H3 als Vorfilter, PostGIS als Antwort                  | angenommen |
| [0004](0004-zeitmodell.md)      | Bitemporalität selektiv, nicht überall                 | angenommen |
| [0005](0005-id-strategie.md)    | ULID intern, externe Kennungen niemals als Schlüssel   | angenommen |
| [0006](0006-datenmodell.md)     | Datenmodell in PostgreSQL                              | angenommen |

## Regeln

- **Fortlaufend, keine Lücken, keine Wiederverwendung.** Eine einmal vergebene
  Nummer bleibt bei ihrem Dokument.
- **Ein zurückgezogenes ADR bleibt stehen** und wird als zurückgezogen oder als
  abgelöst markiert. Die Historie ist der Punkt; ein gelöschtes ADR
  hinterlässt eine Frage ohne Antwort.
- **Jede Entscheidung hat einen Preis, und er wird benannt.** Ein ADR ohne
  negative Konsequenzen ist nicht zu Ende gedacht.
- **Jede Entscheidung hat Revisionsbedingungen**, möglichst messbar. Ohne sie
  wird ein ADR zum Dogma.
- **Nachweise trennen Gemessenes von Angenommenem.** Was nicht gemessen wurde,
  steht als solches da.

### Umnummerierung

Am 2026-08-29 wurde `0003-datenmodell.md` zu
[`0006-datenmodell.md`](0006-datenmodell.md), damit die Nummern 0001–0005 den
Grundsatzentscheidungen zufallen, auf denen es aufbaut. Das ist eine Abweichung
von der Regel „keine Wiederverwendung" und bleibt die einzige: Sie war möglich,
weil kein Release existierte und sämtliche Verweise im Repository mitgezogen
wurden. Ab dem ersten Release gilt die Regel ohne Ausnahme.
