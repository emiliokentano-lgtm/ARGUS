/**
 * Verbindung zur ARGUS-API.
 *
 * Die Basis-URL kommt aus der Umgebung, nie aus dem Code. Fehlt sie, ist das
 * kein Fehler, sondern ein Zustand - und dieser Zustand wird angezeigt, nicht
 * durch Beispieldaten ueberdeckt.
 *
 * Prinzip 4 des Konzepts, hier zum ersten Mal in der Oberflaeche: "Datenluecken
 * werden explizit angezeigt, nicht kaschiert." Ein Dashboard, das ohne Backend
 * huebsche Nullen zeigt, ist die gefaehrlichere Variante - man sieht ihm nicht
 * an, dass es nichts weiss.
 */

export type ApiState =
  | { readonly kind: "nicht-konfiguriert" }
  | { readonly kind: "pruefe" }
  | { readonly kind: "erreichbar"; readonly latencyMs: number; readonly version: string | null }
  | { readonly kind: "nicht-erreichbar"; readonly reason: string };

/**
 * NEXT_PUBLIC_, weil der Wert im Browser gebraucht wird und damit ohnehin
 * oeffentlich ist. Genau deshalb gehoert hier auch nur eine URL hinein und
 * niemals ein Schluessel.
 */
export function apiBaseUrl(): string | null {
  const raw = process.env.NEXT_PUBLIC_ARGUS_API_URL?.trim();
  return raw ? raw.replace(/\/+$/, "") : null;
}

const TIMEOUT_MS = 5000;

export async function probeApi(signal?: AbortSignal): Promise<ApiState> {
  const base = apiBaseUrl();
  if (base === null) return { kind: "nicht-konfiguriert" };

  const controller = new AbortController();
  const timer = setTimeout(() => {
    controller.abort();
  }, TIMEOUT_MS);
  signal?.addEventListener("abort", () => {
    controller.abort();
  });

  const started = performance.now();
  try {
    const response = await fetch(`${base}/healthz`, {
      signal: controller.signal,
      cache: "no-store",
    });
    const latencyMs = Math.round(performance.now() - started);
    if (!response.ok) {
      return { kind: "nicht-erreichbar", reason: `HTTP ${response.status}` };
    }
    // Die Version ist optional: eine API, die nur 200 liefert, ist erreichbar.
    let version: string | null = null;
    try {
      const body: unknown = await response.json();
      if (body !== null && typeof body === "object" && "version" in body) {
        const value = (body as { version: unknown }).version;
        version = typeof value === "string" ? value : null;
      }
    } catch {
      version = null;
    }
    return { kind: "erreichbar", latencyMs, version };
  } catch (error) {
    const reason =
      error instanceof DOMException && error.name === "AbortError"
        ? `keine Antwort in ${TIMEOUT_MS} ms`
        : error instanceof Error
          ? error.message
          : "unbekannter Fehler";
    return { kind: "nicht-erreichbar", reason };
  } finally {
    clearTimeout(timer);
  }
}
