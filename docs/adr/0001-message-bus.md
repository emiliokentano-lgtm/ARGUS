# ADR 0001 — NATS JetStream als Nachrichtenbus

**Status:** angenommen
**Datum:** 2026-08-29
**Betrifft:** `packages/connector-sdk/`, `infra/compose/`, alle Ingest-Dienste

---

## Kontext

Zwischen Konnektoren und Verarbeitung liegt ein Bus. Er muss mindestens einmal
zustellen, Konsumenten unabhängig voneinander vorankommen lassen und einen
Rückstau überstehen, wenn ein Verarbeitungsschritt ausfällt.

Was unabhängig von der Wahl gilt:

- Erwartete Last in Phase 0–4: 500–5.000 Nachrichten/s, Spitzen bis 20.000
  (ADS-B ist der Treiber). Zwei Größenordnungen unter dem, was ein einzelner
  Kafka-Broker leistet.
- Betrieb: eine Person, nebenher. Kein Plattform-Team, keine Rufbereitschaft.
- Ein Wiederherstellungspfad existiert bereits _neben_ dem Bus: jede Rohnachricht
  liegt vor der Normalisierung in der Bronze-Schicht in MinIO (Prompt 4). Der Bus
  muss Stunden bis Tage halten, keine Monate.
- Zielbild ist Self-Hosting auf einem einzelnen Server, nicht ein Cluster.

---

## Betrachtete Optionen

**A — Apache Kafka.** Der Industriestandard: partitionierter, replizierter
Commit-Log, Log Compaction, riesiges Ökosystem. _Dafür:_ unbegrenzt skalierbar,
jeder kennt es, Kafka-Protokoll als De-facto-Integrationsschnittstelle.
_Dagegen:_ KRaft hat ZooKeeper abgelöst, der Betriebsaufwand bleibt —
Partitionsplanung, Rebalancing, JVM-Tuning, Consumer-Group-Diagnose. Für 5.000
msg/s zahlt man einen Preis, der bei 500.000 msg/s gerechtfertigt wäre.

**B — Redpanda.** Kafka-protokollkompatibel, in C++, ohne JVM, ein Binary.
_Dafür:_ deutlich einfacher zu betreiben als Kafka bei gleicher API, sehr gute
Latenz. _Dagegen:_ Kernfunktionen stehen unter der Business Source License, nicht
unter Apache 2.0 — für ein self-hostbares Projekt eine Bindung, die man erst
merkt, wenn sie stört. Ökosystem kleiner als Kafka, größer als NATS: in beiden
Vergleichen die zweite Wahl.

**C — NATS JetStream.** Leichtgewichtiger Messaging-Kern mit persistenter
Stream-Schicht. Ein Binary, ~20 MB im Leerlauf, Apache 2.0. _Dafür:_ Streams,
Consumer und Limits in Minuten konfiguriert; Request/Reply und Key-Value im
selben System, das ohnehin gebraucht wird. _Dagegen:_ siehe Konsequenzen — die
Liste ist nicht kurz.

**D — nichts tun**, Konnektoren schreiben direkt nach Postgres. Ein bewegliches
Teil weniger, aber jeder Konnektorfehler wird zum Datenbankfehler, kein Rückstau,
keine Mehrfachkonsumenten, kein Replay. Verworfen, weil Kapitel 4 mehrere
unabhängige Konsumenten pro Beobachtung vorsieht.

---

## Bewertungskriterien

| Kriterium                       | Gewicht | Kafka | Redpanda | JetStream |
| ------------------------------- | ------- | ----- | -------- | --------- |
| Betriebsaufwand für eine Person | hoch    | −−    | +        | ++        |
| Lizenz (Apache-2.0-kompatibel)  | hoch    | ++    | −        | ++        |
| Durchsatz bei erwarteter Last   | mittel  | ++    | ++       | ++        |
| Durchsatz bei 100-facher Last   | niedrig | ++    | ++       | ∘         |
| Ökosystem, Fremdkonsumenten     | mittel  | ++    | ++       | −         |
| Umkehrbarkeit                   | hoch    | ∘     | ∘        | ∘         |

Der Durchsatz bei 100-facher Last ist bewusst niedrig gewichtet: das ist ein
Problem, das wir gerne hätten. Die Umkehrbarkeit ist für alle drei gleich —
`argus_connector.bus` kapselt den Bus, ein Wechsel kostet einen Adapter und eine
Phase mit Doppelschreibung, keine Neuentwicklung.

---

## Entscheidung

**Wir benutzen NATS JetStream als Nachrichtenbus.**

Die zweitbeste Option ist Redpanda. Sie unterliegt Kafka nicht technisch,
sondern in der Lizenz — und JetStream im Betriebsaufwand, ohne dafür in
Phase 0–4 einen Gegenwert zu liefern.

Kafka wird nicht gewählt, weil der Engpass dieses Projekts nicht der Durchsatz
ist, sondern die Zeit eines einzelnen Menschen. Ein Cluster, der zu 2 %
ausgelastet ist, aber ein Wochenende Rebalancing-Diagnose kostet, ist die
teurere Wahl — auch wenn er auf dem Papier die stärkere ist.

---

## Konsequenzen

**Positiv**

- Der Dev-Stack startet auf einem Laptop; NATS trägt ~20 MB bei, ein Healthcheck
  ersetzt die Cluster-Diagnose.
- Key-Value und Request/Reply für Kill-Switch und Steuerkanal ohne Zusatzsystem.
- Apache 2.0 durchgehend, keine Lizenzfrage beim Self-Hosting.

**Negativ**

- **Keine Log Compaction.** Kafkas „letzter Wert pro Schlüssel, für immer" gibt
  es nicht. Der aktuelle Zustand einer Entität kommt aus Postgres oder Valkey,
  nicht aus dem Bus — eine Einschränkung, die in jeden Konsumentenentwurf
  hineinwirkt.
- **Replay kostet Plattenplatz auf dem Bus.** Wir setzen Stream-Limits auf Tage,
  nicht Wochen. Das Zeitreise-Versprechen des Konzepts löst die Bronze-Schicht in
  MinIO ein, nicht der Bus. Wer das verwechselt, plant einen Wiederanlauf, der
  nicht funktioniert.
- **Kein Kafka Connect.** Jeder Konnektor ist eigener Code — vom SDK abgefedert,
  nicht aufgehoben. Und kein Fremdsystem spricht NATS: wer Kafka-Protokoll
  erwartet, braucht eine Brücke.
- **1 MB Standard-Nachrichtengröße.** Große Nutzlasten (Satellitenkacheln,
  PDF-Berichte) gehen über MinIO, auf dem Bus liegt nur die Referenz — ein
  zusätzlicher Indirektionsschritt in jedem betroffenen Pfad.

**Was jetzt anders gemacht werden muss**

- Streams und Limits explizit in `infra/compose/init/nats/init-streams.sh`
  setzen; Standardwerte sind hier keine Entscheidung, sondern ein Versäumnis.
- Jeder Konsument muss idempotent sein. JetStream stellt _mindestens_ einmal zu;
  das SDK setzt `Nats-Msg-Id`, die Entdopplung gilt aber nur im Fenster.

---

## Bedingungen für eine Revision

- Anhaltend über **50.000 Nachrichten/s** über eine Stunde.
- Replay über mehr als **30 Tage** wird direkt vom Bus verlangt.
- **Drei oder mehr externe Konsumenten**, die das Kafka-Protokoll sprechen.
- Eine **Vollzeitstelle Plattformbetrieb** existiert — dann sinkt das Gewicht von
  „Betriebsaufwand" und die Rechnung kippt.
- Die Apache-2.0-Lizenz von NATS ändert sich.

---

## Nachweise

- Prompt 2: NATS 2.14.6 läuft im Compose-Stack, Healthcheck über
  `/healthz?js-enabled-only=true`.
- Prompt 4: Absturztest mit SIGKILL mitten im Lauf — kein Datenverlust,
  höchstens ein dupliziertes Batch.
- **Nicht gemessen:** Durchsatz unter Last. Die Lastannahme stammt aus Kapitel 5
  des Konzepts, nicht aus einer eigenen Messung.
