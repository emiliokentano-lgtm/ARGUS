# ADR NNNN — Titel in einem Satz

**Status:** vorgeschlagen | angenommen | abgelöst durch ADR NNNN | zurückgezogen
**Datum:** JJJJ-MM-TT
**Betrifft:** Pfade oder Komponenten, die diese Entscheidung berührt

> Kopiervorlage. Ein ADR ist kein Protokoll und keine Dokumentation — es ist
> die Antwort auf die Frage, die in zwei Jahren jemand stellt: _„Warum ist das
> so und nicht anders?"_ Wenn eine Entscheidung offensichtlich ist, braucht sie
> kein ADR. Wenn sie es nicht ist, ist der Abschnitt **Verworfene Alternativen**
> der wichtigste des Dokuments.
>
> Reihenfolge der Nummern: fortlaufend, keine Lücken, keine Wiederverwendung.
> Ein zurückgezogenes ADR bleibt stehen; die Historie ist der Punkt.

---

## Kontext

Was ist die Lage, in der die Entscheidung fällt? Welche Kräfte wirken —
fachliche Anforderung, Betriebsrealität, Lizenz, Zeit, vorhandenes Wissen im
Team?

Hier gehört hin, was _unabhängig von der Entscheidung_ wahr ist. Wer diesen
Abschnitt liest und dann selbst nachdenkt, sollte auf dieselben Kandidaten
kommen.

Bezug zum Konzept, wo vorhanden: „Kapitel 7.1 verlangt, dass die Gewichte pro
Nutzer konfigurierbar sind."

---

## Betrachtete Optionen

### Option A — Name

Was ist das, in zwei bis vier Sätzen.

**Dafür:** …
**Dagegen:** …

### Option B — Name

…

### Option C — nichts tun

Fast immer eine ernsthafte Option und fast immer die, die vergessen wird.
Was passiert, wenn wir die Entscheidung vertagen?

---

## Bewertungskriterien

Mit Gewichtung, damit die Entscheidung nachvollziehbar ist und nicht nur
behauptet.

| Kriterium               | Gewicht | A   | B   | C   |
| ----------------------- | ------- | --- | --- | --- |
| Betriebsaufwand         | hoch    |     |     |     |
| Passt zum Kenntnisstand | mittel  |     |     |     |
| Lizenz und Recht        | hoch    |     |     |     |
| Umkehrbarkeit           | hoch    |     |     |     |

**Umkehrbarkeit** verdient fast immer ein hohes Gewicht: eine Entscheidung, die
sich in einer Woche zurücknehmen lässt, darf schneller und mutiger fallen als
eine, die ein Jahr Migration kostet.

---

## Entscheidung

Ein Satz, im Aktiv: „Wir benutzen X für Y."

Dann die Begründung — warum diese Option und nicht die zweitbeste. Die
zweitbeste ausdrücklich benennen.

---

## Konsequenzen

**Positiv**

- …

**Negativ**

- … (Wenn hier nichts steht, ist der Abschnitt nicht zu Ende gedacht. Jede
  Entscheidung kostet etwas.)

**Was jetzt anders gemacht werden muss**

- Konkrete Folgearbeiten, mit Verweis auf Prompts oder Aufgaben.

---

## Bedingungen für eine Revision

Wann sollte diese Entscheidung neu betrachtet werden? Möglichst messbar:

- „wenn der Durchsatz 50.000 Nachrichten/s übersteigt"
- „wenn die Lizenz von X sich ändert"
- „wenn mehr als zwei Personen Vollzeit daran arbeiten"

Ohne diesen Abschnitt wird ein ADR zum Dogma.

---

## Nachweise

Was wurde tatsächlich gemessen oder ausprobiert, bevor entschieden wurde?
Zahlen, Prototypen, Fundstellen. Eine Entscheidung ohne einen einzigen Nachweis
ist eine Meinung — was in Ordnung ist, solange es dasteht.
