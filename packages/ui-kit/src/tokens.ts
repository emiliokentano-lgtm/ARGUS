/**
 * Semantische Design-Tokens (Konzept, Kapitel 10.6).
 *
 * Farbe bedeutet Zustand, nicht Dekoration. Deshalb tragen die Tokens
 * Zustandsnamen und keine Farbnamen: wer `priority.critical` schreibt, kann
 * die Palette spaeter tauschen, ohne jede Komponente anzufassen.
 *
 * Die Prioritaetsskala ist farbenblind-sicher: sie laeuft nicht ueber
 * Rot/Gruen, sondern ueber Helligkeit und Saettigung, und jede Stufe traegt
 * zusaetzlich ein Formmerkmal (`shape`) und eine Zahl. Farbe allein darf nie
 * die einzige Unterscheidung sein.
 */

/** Prioritaetsstufen, aufsteigend. */
export const PRIORITY_LEVELS = ["info", "watch", "notify", "alert", "critical"] as const;

export type PriorityLevel = (typeof PRIORITY_LEVELS)[number];

export interface PriorityToken {
  /** Hintergrundfarbe im dunklen Standardthema. */
  readonly background: string;
  /** Vordergrundfarbe mit mindestens 4.5:1 Kontrast zum Hintergrund. */
  readonly foreground: string;
  /** Zusaetzliches, nicht farbliches Merkmal fuer Farbenblinde. */
  readonly shape: "circle" | "square" | "diamond" | "triangle" | "hexagon";
  /** Rang, damit sortiert werden kann, ohne die Reihenfolge zu kennen. */
  readonly rank: number;
}

export const priority: Readonly<Record<PriorityLevel, PriorityToken>> = {
  info: { background: "#1e293b", foreground: "#cbd5e1", shape: "circle", rank: 0 },
  watch: { background: "#0e7490", foreground: "#ecfeff", shape: "square", rank: 1 },
  notify: { background: "#a16207", foreground: "#fefce8", shape: "diamond", rank: 2 },
  alert: { background: "#c2410c", foreground: "#fff7ed", shape: "triangle", rank: 3 },
  critical: { background: "#be123c", foreground: "#fff1f2", shape: "hexagon", rank: 4 },
};

/**
 * Ordnet einen Prioritaets-Score (0..100) einer Stufe zu.
 *
 * Die Grenzen sind bewusst hier und nicht in der UI: sonst zeigt jede
 * Komponente eine andere Schwelle, und zwei Panels widersprechen sich bei
 * demselben Ereignis.
 */
export function priorityLevelForScore(score: number): PriorityLevel {
  if (!Number.isFinite(score)) {
    throw new RangeError(`Prioritaet muss eine Zahl sein, war: ${String(score)}`);
  }
  if (score < 0 || score > 100) {
    throw new RangeError(`Prioritaet liegt ausserhalb von 0..100: ${score}`);
  }
  if (score >= 90) return "critical";
  if (score >= 70) return "alert";
  if (score >= 45) return "notify";
  if (score >= 20) return "watch";
  return "info";
}

/**
 * Alterszustand eines Wertes (Kapitel 10.6).
 *
 * „Ein veralteter Wert, der frisch aussieht, ist der gefaehrlichste Zustand
 * des Systems." Deshalb gibt es fuer Alter eigene Tokens und keine
 * Ad-hoc-Opazitaet in der Komponente.
 */
export const staleness = {
  fresh: { opacity: 1, label: null },
  aging: { opacity: 0.75, label: "aelter als erwartet" },
  stale: { opacity: 0.5, label: "veraltet" },
  unknown: { opacity: 0.4, label: "Alter unbekannt" },
} as const;

export type StalenessLevel = keyof typeof staleness;

/**
 * Vergleicht das Alter eines Wertes mit der erwarteten Latenz seiner Quelle.
 *
 * @param ageSeconds Alter des Wertes in Sekunden.
 * @param expectedLatencySeconds Erwartete Latenz der Quelle, aus dem
 *   Quellenregister. Fehlt sie, ist das Alter nicht bewertbar.
 */
export function stalenessFor(
  ageSeconds: number,
  expectedLatencySeconds: number | null,
): StalenessLevel {
  if (expectedLatencySeconds === null || expectedLatencySeconds <= 0) return "unknown";
  const ratio = ageSeconds / expectedLatencySeconds;
  if (ratio <= 1) return "fresh";
  if (ratio <= 3) return "aging";
  return "stale";
}
