import { STAGES, STAGE_SUMMARY } from "@/lib/build-status";

/**
 * Was gebaut ist und was nicht.
 *
 * Die erste Seite eines Systems ohne Daten kann zwei Dinge tun: so aussehen,
 * als waere alles bereit und nur gerade nichts los - oder sagen, wo es steht.
 * Das Zweite ist langweiliger und richtig.
 */
export function BuildStatus() {
  return (
    <section className="panel">
      <h2>Stand der Umsetzung</h2>
      <p style={{ marginTop: 0 }}>
        {STAGE_SUMMARY.fertig} von {STAGE_SUMMARY.gesamt} Bausteinen fertig,{" "}
        {STAGE_SUMMARY.inArbeit} in Arbeit, {STAGE_SUMMARY.offen} offen.
      </p>
      <ul className="stages">
        {STAGES.map((stage) => (
          <li key={stage.id} className="stage" data-state={stage.state}>
            <span className="stage-state">{stage.state}</span>
            <span>
              <strong>{stage.name}</strong>
              <span className="detail">{stage.detail}</span>
              {stage.path !== undefined ? (
                <>
                  {" "}
                  <code>{stage.path}</code>
                </>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
