import { PRIORITY_LEVELS, priority } from "@argus/ui-kit";

const SHAPE_GLYPH = {
  circle: "●",
  square: "■",
  diamond: "◆",
  triangle: "▲",
  hexagon: "⬢",
} as const;

/**
 * Die Prioritaetsskala aus @argus/ui-kit, sichtbar gemacht.
 *
 * Das ist keine Dekoration, sondern der Beleg fuer eine Zusage aus Kapitel
 * 10.6: Farbe ist nie die einzige Unterscheidung. Jede Stufe traegt zusaetzlich
 * eine Form und einen Rang - wer die Farben nicht unterscheiden kann, liest die
 * Skala trotzdem.
 */
export function PriorityScale() {
  return (
    <section className="panel">
      <h2>Prioritaetsskala</h2>
      <div className="scale">
        {PRIORITY_LEVELS.map((level) => {
          const token = priority[level];
          return (
            <span
              key={level}
              className="badge"
              style={{ background: token.background, color: token.foreground }}
            >
              <span aria-hidden="true">{SHAPE_GLYPH[token.shape]}</span>
              {level}
              <span style={{ opacity: 0.7 }}>{token.rank}</span>
            </span>
          );
        })}
      </div>
      <p>
        Farbenblind-sicher: die Skala laeuft ueber Helligkeit und Saettigung, nicht ueber Rot/Gruen,
        und jede Stufe traegt zusaetzlich eine Form und einen Rang. Die Schwellen liegen in{" "}
        <code>@argus/ui-kit</code> und nicht in den Komponenten — sonst zeigen zwei Panels beim
        selben Ereignis verschiedene Stufen.
      </p>
    </section>
  );
}
