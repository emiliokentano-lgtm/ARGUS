import { ApiStatus } from "@/components/ApiStatus";
import { BuildStatus } from "@/components/BuildStatus";
import { PriorityScale } from "@/components/PriorityScale";

/**
 * Startseite des War Room.
 *
 * Solange keine API angebunden ist, zeigt sie den Zustand des Systems und
 * nicht den Zustand der Welt. Das ist der ehrliche Vorgriff auf Prinzip 4:
 * eine Luecke wird benannt, nicht ueberdeckt.
 */
export default function Home() {
  return (
    <main className="shell">
      <header className="masthead">
        <h1>ARGUS</h1>
        <p>
          Selbst gehostete Echtzeit-Lageplattform. Alles ist eine Beobachtung ueber eine Entitaet zu
          einer Zeit an einem Ort; jede Beobachtung traegt ihre Herkunft, jeder Score ist zerlegbar,
          und der Wissensstand von gestern bleibt abrufbar.
        </p>
      </header>

      <ApiStatus />

      <div className="grid">
        <BuildStatus />
      </div>

      <PriorityScale />

      <section className="panel">
        <h2>Was diese Seite nicht ist</h2>
        <p style={{ marginTop: 0 }}>
          Kein Lagebild. Karte, Zeitleiste und Fallakten kommen, wenn die API steht — die
          Datenschicht darunter ist gebaut und getestet, die Verbindung dazwischen noch nicht. Bis
          dahin zeigt der War Room lieber nichts als etwas Erfundenes.
        </p>
      </section>

      <footer className="footnote">
        <p style={{ margin: 0 }}>
          Keine Ueberwachung von Privatpersonen. Keine Beschaffung nicht-oeffentlicher Daten, kein
          Umgehen von Ratenbegrenzungen. Kein Anspruch auf lueckenlose Abdeckung — Datenluecken
          werden angezeigt, nicht kaschiert.
        </p>
      </footer>
    </main>
  );
}
