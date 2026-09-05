/**
 * Was in ARGUS gebaut ist und was nicht.
 *
 * Diese Liste ist von Hand gepflegt und das ist Absicht: sie ist eine Aussage
 * ueber den Stand des Projekts, keine Ableitung aus dem Dateisystem. Ein
 * Verzeichnis, das existiert, sagt nichts darueber, ob das Stueck funktioniert.
 *
 * Sie steht hier, damit die erste Seite des War Room eine ehrliche Antwort auf
 * "was kann das schon?" geben kann - statt einer Kachelwand mit Nullen, die
 * aussieht wie ein funktionierendes System ohne Daten.
 */

export type StageState = "fertig" | "in Arbeit" | "offen";

export interface Stage {
  readonly id: string;
  readonly name: string;
  readonly state: StageState;
  /** Was das Stueck tut - ein Satz, keine Aufzaehlung. */
  readonly detail: string;
  /** Verweis in das Repository, wo es nachzulesen ist. */
  readonly path?: string;
}

export const STAGES: readonly Stage[] = [
  {
    id: "schemas",
    name: "Kanonische Schemas",
    state: "fertig",
    detail:
      "Dreizehn Kernobjekte als Protobuf und JSON Schema, mit Versionsregeln und Bruchpruefung.",
    path: "packages/schemas",
  },
  {
    id: "stack",
    name: "Dev-Stack",
    state: "fertig",
    detail:
      "Elf Dienste als Docker Compose, alle Images mit Digest festgenagelt, jeder Healthcheck fachlich.",
    path: "infra/compose",
  },
  {
    id: "db",
    name: "Datenbankschema",
    state: "fertig",
    detail: "Acht Migrationen, bitemporale Versionierung, Geo- und Volltextindizes, Zeilenschutz.",
    path: "services/api/migrations",
  },
  {
    id: "sdk",
    name: "Konnektor-Framework",
    state: "fertig",
    detail:
      "Cursor, Bronze-Archiv, Rate-Limiting, Circuit Breaker, Kill-Switch - einmal fuer alle Quellen.",
    path: "packages/connector-sdk",
  },
  {
    id: "ingest-sea",
    name: "AIS-Konnektor",
    state: "fertig",
    detail:
      "Schiffspositionen und Stammdaten ueber AISStream.io, gemessen bei 4.200 Nachrichten/s.",
    path: "services/ingest-sea",
  },
  {
    id: "api",
    name: "API",
    state: "offen",
    detail:
      "REST, WebSocket und GraphQL ueber den Datenbestand. Ohne sie zeigt diese Seite keine Lagedaten.",
    path: "apps/api",
  },
  {
    id: "resolver",
    name: "Entity Resolution",
    state: "offen",
    detail:
      "Fuehrt die provisorischen Kandidaten der Konnektoren zu einer Entitaet je Schiff zusammen.",
  },
  {
    id: "scoring",
    name: "Bewertung",
    state: "offen",
    detail: "Prioritaets-Score mit vollstaendiger Zerlegung - jeder Wert erklaerbar.",
  },
  {
    id: "warroom",
    name: "War Room",
    state: "in Arbeit",
    detail: "Karte, Zeitleiste, Fallakten. Das hier ist das Geruest, mehr noch nicht.",
    path: "apps/web",
  },
];

export const STAGE_SUMMARY = {
  fertig: STAGES.filter((s) => s.state === "fertig").length,
  inArbeit: STAGES.filter((s) => s.state === "in Arbeit").length,
  offen: STAGES.filter((s) => s.state === "offen").length,
  gesamt: STAGES.length,
} as const;
