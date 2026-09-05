# `apps/web` — War Room

Frontend der Lageplattform (Konzept, Kapitel 10). Next.js 15 im App Router,
React 19, TypeScript.

**Status:** Gerüst. Es baut, es deployt, und es zeigt bewusst **keine
Lagedaten** — Karte, Zeitleiste und Fallakten kommen mit dem Panel- und
Layoutsystem. Was hier steht, ist die Kette von der Quelle bis zum Browser,
damit sie beim ersten echten Panel schon funktioniert.

---

## Warum die Startseite so leer ist

Sie zeigt den Zustand des **Systems**, nicht den Zustand der Welt: ob eine API
angebunden ist, was gebaut ist und was nicht, und die Prioritätsskala aus
`@argus/ui-kit`.

Das ist Prinzip 4 des Konzepts, zum ersten Mal in der Oberfläche — _„Datenlücken
werden explizit angezeigt, nicht kaschiert."_ Ein Dashboard, das ohne Backend
hübsche Nullen zeigt, sieht aus wie ein System, das nichts gefunden hat, statt
wie eines, das nichts weiß. Der Unterschied ist der ganze Punkt.

`components/ApiStatus.tsx` unterscheidet deshalb vier Zustände und nicht zwei:

| Zustand            | Bedeutung                                      |
| ------------------ | ---------------------------------------------- |
| nicht konfiguriert | `NEXT_PUBLIC_ARGUS_API_URL` ist nicht gesetzt  |
| prüfe              | Anfrage läuft                                  |
| erreichbar         | `/healthz` antwortet, mit Latenz               |
| nicht erreichbar   | konfiguriert, antwortet aber nicht — mit Grund |

Ein fehlender Handgriff und ein Ausfall sehen verschieden aus. Beide gehören auf
den Schirm.

---

## Entwickeln

```sh
pnpm install                          # einmal, an der Wurzel
pnpm --filter @argus/web run dev      # http://localhost:3000
```

Aus der Wurzel über Turborepo:

```sh
pnpm run lint
pnpm run typecheck
pnpm run build
```

`make lint` / `make typecheck` / `make ci-local` schließen das mit ein.

### Konfiguration

| Variable                    | Pflicht | Bedeutung                                                      |
| --------------------------- | ------- | -------------------------------------------------------------- |
| `NEXT_PUBLIC_ARGUS_API_URL` | nein    | Basis-URL der ARGUS-API, z. B. `https://argus.example.org/api` |

`NEXT_PUBLIC_` bedeutet: der Wert landet im ausgelieferten JavaScript und ist
damit öffentlich. Deshalb steht hier **nur eine URL** und niemals ein Schlüssel.
Ohne die Variable läuft die Anwendung — sie sagt dann, dass sie keine API kennt.

---

## Deployment auf Vercel

Vercel ist für das Frontend eine gute Wahl und für den Rest von ARGUS keine:
die Konnektoren halten dauerhafte Verbindungen offen und der Datenbestand
braucht PostgreSQL mit PostGIS, NATS und einen Objektspeicher. Nichts davon
läuft in einer Funktion, die pro Anfrage startet. Der Kern gehört auf einen
eigenen Server (ADR 0002); dieses Verzeichnis spricht mit ihm über das Netz.

### Einrichten

Im Vercel-Projekt **Root Directory auf `apps/web` setzen**. Das ist die
wichtigste Einstellung und der Grund, warum ein Deployment aus dem
Wurzelverzeichnis fehlschlägt: dort liegt `pyproject.toml` (der uv-Workspace),
Vercel hält das Repository dann für eine Python-Anwendung und sucht einen
Einstiegspunkt, den es nicht gibt.

```
Root Directory .................. apps/web
Framework Preset ................ Next.js   (wird erkannt)
Include files outside root ...... an        (für den pnpm-Workspace nötig)
Environment Variables ........... NEXT_PUBLIC_ARGUS_API_URL
```

Das `vercel.json` in der Wurzel deckt den Fall ab, dass das Root Directory
**nicht** umgestellt wird: es baut über Turborepo nur `@argus/web` und zeigt auf
dessen Ausgabe. `turbo-ignore` überspringt dabei Deployments, deren Änderungen
das Frontend nicht berühren — ein Commit an den Migrationen erzeugt kein neues
Frontend-Deployment.

Beides zusammen funktioniert; die Einstellung im Projekt ist der geradere Weg.

---

## Bekannte Grenzen

- **Keine Lagedaten.** Es gibt noch keine API, mit der sich reden ließe.
- **Kein Test.** Es gibt noch keine Logik, die einen verdient — `lint`,
  `typecheck` und der Build sind derzeit die Prüfung. Ein `test`-Skript kommt
  mit der ersten Komponente, die eine Entscheidung trifft.
- **Keine Karte.** MapLibre, Deck.gl und das Kachelschema stehen im Konzept,
  aber noch nicht hier.
- **Kein Auth.** Sitzungen, Rollen und der Zeilenschutz aus Migration 0008
  greifen erst, wenn die API sie durchreicht.
- **Kein Dark/Light-Umschalter.** Das Thema ist dunkel, weil der War Room auf
  Wandschirmen läuft. Eine helle Variante ist kein Aufwand, aber auch noch kein
  Bedarf.
