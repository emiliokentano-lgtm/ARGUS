"use client";

import { useEffect, useState } from "react";

import { apiBaseUrl, probeApi, type ApiState } from "@/lib/api";

/**
 * Zustand der Verbindung zur ARGUS-API.
 *
 * Vier Zustaende, und keiner davon ist "sieht aus wie null". Der Unterschied
 * zwischen "nicht konfiguriert" und "nicht erreichbar" ist der zwischen einem
 * fehlenden Handgriff und einem Ausfall - er gehoert auf den Schirm, nicht in
 * ein Log.
 */
export function ApiStatus() {
  const [state, setState] = useState<ApiState>(() =>
    apiBaseUrl() === null ? { kind: "nicht-konfiguriert" } : { kind: "pruefe" },
  );

  useEffect(() => {
    if (apiBaseUrl() === null) return;
    const controller = new AbortController();
    void probeApi(controller.signal).then((next) => {
      if (!controller.signal.aborted) setState(next);
    });
    return () => {
      controller.abort();
    };
  }, []);

  return (
    <section className="panel" aria-live="polite">
      <h2>Verbindung zur Lagedatenbank</h2>
      <StatusLine state={state} />
    </section>
  );
}

function StatusLine({ state }: { state: ApiState }) {
  switch (state.kind) {
    case "nicht-konfiguriert":
      return (
        <>
          <div className="row">
            <span className="badge" style={{ background: "#1e293b", color: "#cbd5e1" }}>
              ◇ nicht konfiguriert
            </span>
            <span className="mono" style={{ color: "var(--fg-faint)" }}>
              NEXT_PUBLIC_ARGUS_API_URL
            </span>
          </div>
          <p>
            Diese Oberflaeche kennt keine API. Es werden <strong>keine</strong> Lagedaten angezeigt
            — auch keine leeren. Ein Dashboard, das ohne Backend huebsche Nullen zeigt, sieht aus
            wie ein System, das nichts gefunden hat, statt wie eines, das nichts weiss.
          </p>
        </>
      );
    case "pruefe":
      return (
        <div className="row">
          <span className="badge pulse" style={{ background: "#0e7490", color: "#ecfeff" }}>
            ■ pruefe …
          </span>
        </div>
      );
    case "erreichbar":
      return (
        <>
          <div className="row">
            <span className="badge" style={{ background: "#0e7490", color: "#ecfeff" }}>
              ■ erreichbar
            </span>
            <span className="mono" style={{ color: "var(--fg-muted)" }}>
              {state.latencyMs} ms
              {state.version !== null ? ` · ${state.version}` : ""}
            </span>
          </div>
          <p>Die API antwortet. Lageansichten folgen, sobald sie Daten liefert.</p>
        </>
      );
    case "nicht-erreichbar":
      return (
        <>
          <div className="row">
            <span className="badge" style={{ background: "#c2410c", color: "#fff7ed" }}>
              ▲ nicht erreichbar
            </span>
            <span className="mono" style={{ color: "var(--fg-muted)" }}>
              {state.reason}
            </span>
          </div>
          <p>
            Die API ist konfiguriert, antwortet aber nicht. Alles, was jetzt angezeigt wuerde, waere
            alt — deshalb wird nichts angezeigt.
          </p>
        </>
      );
  }
}
