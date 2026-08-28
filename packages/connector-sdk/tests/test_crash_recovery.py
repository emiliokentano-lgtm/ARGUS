"""Abnahmekriterium: Absturz mitten im Lauf, kein Datenverlust.

Der Konnektor laeuft als eigener Prozess gegen eine Mock-Quelle, wird mit
SIGKILL getoetet - ohne Aufraeumen, ohne Signalbehandlung, wie ein OOM-Kill
oder ein Stromausfall - und neu gestartet. Danach wird geprueft:

* Vollstaendigkeit: jeder Datensatz der Quelle wurde mindestens einmal
  zugestellt. Ein fehlender waere stiller Datenverlust.
* Doppelzustellungen sind erlaubt, muessen aber ueber den dedupe_key
  erkennbar sein - genau die Zusicherung des Zwei-Phasen-Musters.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from conftest import PACKAGE_DIR, requires_postgres
from fixtures.mock_source import MockSource

pytestmark = [requires_postgres, pytest.mark.integration, pytest.mark.slow]

RUNNER = PACKAGE_DIR / "tests" / "fixtures" / "run_connector.py"
TOTAL = 400
PAGE = 20


def _launch(env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, str(RUNNER)],
        env={**os.environ, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _published(path: Path) -> list[tuple[int, str]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record_id, _, dedupe_key = line.partition("\t")
        rows.append((int(record_id), dedupe_key))
    return rows


def _wait_for_lines(path: Path, minimum: int, timeout: float = 30.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        count = len(_published(path))
        if count >= minimum:
            return count
        time.sleep(0.05)
    return len(_published(path))


@pytest.fixture()
def scenario(tmp_path, postgres_dsn):
    connector_id = f"crashtest-{uuid.uuid4().hex[:8]}"
    output = tmp_path / "published.tsv"
    env = {
        "CONNECTOR_ID": connector_id,
        "CURSOR_DSN": postgres_dsn,
        "OUTPUT_FILE": str(output),
        "BRONZE_DIR": str(tmp_path / "bronze"),
        "TOTAL_RECORDS": str(TOTAL),
        "PAGE_SIZE": str(PAGE),
        "PYTHONUNBUFFERED": "1",
    }
    return env, output


def test_kill_and_resume_loses_nothing(scenario):
    env, output = scenario
    # Kleine Verzoegerung je Antwort, damit der Kill zuverlaessig mitten im
    # Lauf trifft und nicht erst nach dem Ende.
    with MockSource(total=TOTAL, delay_s=0.02) as source:
        env = {**env, "SOURCE_URL": source.url}

        first = _launch(env)
        try:
            # Warten, bis ein Teil zugestellt ist - dann mitten im Lauf toeten.
            assert _wait_for_lines(output, PAGE * 3) >= PAGE * 3, (
                "der Konnektor hat nicht angefangen zu liefern"
            )
            os.kill(first.pid, signal.SIGKILL)
            first.wait(timeout=10)
        finally:
            if first.poll() is None:  # pragma: no cover - Aufraeumen
                first.kill()

        assert first.returncode == -signal.SIGKILL
        before = _published(output)
        assert 0 < len(before) < TOTAL, "der Kill kam zu frueh oder zu spaet"

        # Neustart: derselbe Konnektor, derselbe Cursor-Speicher.
        second = _launch(env)
        _, stderr = second.communicate(timeout=180)
        assert second.returncode == 0, f"Neustart fehlgeschlagen:\n{stderr}"

    after = _published(output)
    delivered_ids = [record_id for record_id, _ in after]

    # 1. Kein Verlust.
    missing = set(range(TOTAL)) - set(delivered_ids)
    assert not missing, f"{len(missing)} Datensaetze gingen verloren: {sorted(missing)[:10]}"

    # 2. Wiederaufnahme setzt an der Abbruchstelle an, nicht am Anfang.
    duplicates = len(delivered_ids) - len(set(delivered_ids))
    assert duplicates <= PAGE, (
        f"{duplicates} Doppelzustellungen - erwartet ist hoechstens ein Batch "
        f"({PAGE}), sonst hat der Cursor nicht gegriffen"
    )

    # 3. Duplikate sind erkennbar: gleicher Datensatz, gleicher dedupe_key.
    keys_by_id: dict[int, set[str]] = {}
    for record_id, dedupe_key in after:
        keys_by_id.setdefault(record_id, set()).add(dedupe_key)
    assert all(len(keys) == 1 for keys in keys_by_id.values()), (
        "derselbe Datensatz muss immer denselben dedupe_key ergeben - sonst ist "
        "eine Doppelzustellung nicht erkennbar"
    )


def test_repeated_kills_still_lose_nothing(scenario):
    """Haerter: dreimal toeten. Jeder Neustart muss sauber aufsetzen."""
    env, output = scenario
    with MockSource(total=TOTAL, delay_s=0.01) as source:
        env = {**env, "SOURCE_URL": source.url}

        for round_number in range(3):
            process = _launch(env)
            target = min(TOTAL, PAGE * 2 * (round_number + 1))
            _wait_for_lines(output, target, timeout=30)
            if process.poll() is None:
                os.kill(process.pid, signal.SIGKILL)
                process.wait(timeout=10)

        final = _launch(env)
        _, stderr = final.communicate(timeout=180)
        assert final.returncode == 0, stderr

    delivered = [record_id for record_id, _ in _published(output)]
    assert set(delivered) == set(range(TOTAL)), "nach drei Abstuerzen fehlt nichts"


def test_graceful_sigterm_completes_the_batch(scenario):
    """SIGTERM ist kein SIGKILL: der laufende Batch wird zu Ende gefuehrt und
    der Bronze-Puffer geschrieben."""
    env, output = scenario
    with MockSource(total=TOTAL, delay_s=0.02) as source:
        env = {**env, "SOURCE_URL": source.url}
        process = _launch(env)
        _wait_for_lines(output, PAGE * 2)
        process.send_signal(signal.SIGTERM)
        _, stderr = process.communicate(timeout=60)

    assert process.returncode == 0, f"sauberes Herunterfahren erwartet:\n{stderr}"

    delivered = [record_id for record_id, _ in _published(output)]
    # Vollstaendige Batches: die Zahl der Zustellungen ist ein Vielfaches der
    # Seitengroesse. Ein abgeschnittener Batch waere ein Teilvielfaches.
    assert len(delivered) % PAGE == 0, (
        f"{len(delivered)} Zustellungen sind kein Vielfaches der Seitengroesse "
        f"{PAGE} - der Batch wurde abgeschnitten"
    )
    bronze_files = list((Path(env["BRONZE_DIR"])).rglob("*.jsonl"))
    assert bronze_files, "der Bronze-Puffer muss beim Herunterfahren geschrieben werden"
