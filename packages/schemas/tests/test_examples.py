"""Die Beispiel-Payloads aus Kapitel 3.2 und die Fehlerfaelle.

Geprueft wird dreifach:
  1. Validierung gegen das generierte JSON Schema (lockere und strenge Fassung)
  2. Parsen in die generierten Protobuf-Klassen, ohne unbekannte Felder
  3. Round-Trip JSON -> Proto -> JSON -> Proto ohne Informationsverlust
"""

from __future__ import annotations

import json

import pytest
from google.protobuf import json_format
from jsonschema import Draft202012Validator

from argus.v1 import event_pb2, observation_pb2
from conftest import load_fixture, load_schema

CASES = [
    ("concept/observation.json", "Observation", observation_pb2.Observation),
    ("concept/event.json", "Event", event_pb2.Event),
    ("error-cases/unknown-entity.observation.json", "Observation", observation_pb2.Observation),
    ("error-cases/missing-timestamp.observation.json", "Observation", observation_pb2.Observation),
    ("error-cases/country-only.event.json", "Event", event_pb2.Event),
    ("error-cases/disputed.event.json", "Event", event_pb2.Event),
    ("error-cases/retracted.event.json", "Event", event_pb2.Event),
]

IDS = [c[0] for c in CASES]


@pytest.mark.parametrize(("path", "schema_name", "message_cls"), CASES, ids=IDS)
def test_validates_against_generated_schema(path, schema_name, message_cls):
    payload = load_fixture(path)
    validator = Draft202012Validator(load_schema(f"{schema_name}.schema.json"))
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)


@pytest.mark.parametrize(("path", "schema_name", "message_cls"), CASES, ids=IDS)
def test_validates_against_strict_schema(path, schema_name, message_cls):
    """Die strenge Fassung erzwingt die Pflichtfelder der Pipeline.

    Jedes mitgelieferte Beispiel muss auch die Pflichtfelder erfuellen -
    sonst waere es kein Beispiel, sondern ein Gegenbeispiel.
    """
    payload = load_fixture(path)
    validator = Draft202012Validator(load_schema(f"{schema_name}.strict.schema.json"))
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)


@pytest.mark.parametrize(("path", "schema_name", "message_cls"), CASES, ids=IDS)
def test_parses_without_unknown_fields(path, schema_name, message_cls):
    """Unbekannte Felder sind ein Fehler, kein stiller Verlust."""
    payload = load_fixture(path)
    msg = json_format.ParseDict(payload, message_cls(), ignore_unknown_fields=False)
    assert msg.ByteSize() > 0


@pytest.mark.parametrize(("path", "schema_name", "message_cls"), CASES, ids=IDS)
def test_json_roundtrip_is_lossless(path, schema_name, message_cls):
    """JSON -> Proto -> JSON -> Proto muss denselben Zustand ergeben.

    Verglichen werden die beiden Protobuf-Nachrichten, nicht die JSON-Texte:
    das Ausgangs-JSON darf Felder mit Standardwert enthalten, die Protobuf beim
    Serialisieren weglaesst. Semantisch ist das identisch.
    """
    payload = load_fixture(path)
    first = json_format.ParseDict(payload, message_cls())
    as_json = json_format.MessageToDict(first, preserving_proto_field_name=True)
    second = json_format.ParseDict(as_json, message_cls())
    assert first == second
    assert json_format.MessageToDict(second, preserving_proto_field_name=True) == as_json


@pytest.mark.parametrize(("path", "schema_name", "message_cls"), CASES, ids=IDS)
def test_binary_roundtrip_is_lossless(path, schema_name, message_cls):
    payload = load_fixture(path)
    msg = json_format.ParseDict(payload, message_cls())
    clone = message_cls()
    clone.ParseFromString(msg.SerializeToString())
    assert clone == msg


@pytest.mark.parametrize(("path", "schema_name", "message_cls"), CASES, ids=IDS)
def test_camel_case_output_also_validates(path, schema_name, message_cls):
    """Protobuf-JSON kennt beide Schreibweisen; das Schema muss beide kennen."""
    payload = load_fixture(path)
    msg = json_format.ParseDict(payload, message_cls())
    camel = json_format.MessageToDict(msg, preserving_proto_field_name=False)
    validator = Draft202012Validator(load_schema(f"{schema_name}.schema.json"))
    errors = list(validator.iter_errors(camel))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)


def test_schema_rejects_mixed_field_name_styles():
    """Dasselbe Feld darf nicht in beiden Schreibweisen zugleich auftreten.

    Die Protobuf-JSON-Spezifikation verbietet das. Die Python-Implementierung
    (protobuf 7.x) erzwingt es nicht, sondern uebernimmt stillschweigend den
    zuletzt gelesenen Wert - stiller Datenverlust genau der Sorte, die ARGUS
    nicht haben darf. Deshalb faengt das generierte JSON Schema den Fall ab,
    und dieser Test haelt beide Verhaltensweisen fest: bricht die
    Parser-Toleranz irgendwann weg, faellt es hier auf.
    """
    payload = load_fixture("concept/observation.json")
    payload["obsId"] = "01HZX8QK3M4N5P6R7S8T9V0W99"
    validator = Draft202012Validator(load_schema("Observation.schema.json"))
    assert list(validator.iter_errors(payload)), "Schema muss doppelte Schreibweise ablehnen"

    parsed = json_format.ParseDict(payload, observation_pb2.Observation())
    assert parsed.obs_id in {payload["obs_id"], payload["obsId"]}


def test_schema_rejects_unknown_field():
    """Tippfehler in Feldnamen fallen im Schema auf, nicht erst im Betrieb."""
    payload = load_fixture("concept/observation.json")
    payload["kinematiks"] = {}
    validator = Draft202012Validator(load_schema("Observation.schema.json"))
    assert list(validator.iter_errors(payload))


def test_concept_observation_keeps_documented_values():
    """Die Werte aus Kapitel 3.2 duerfen sich beim Parsen nicht veraendern."""
    obs = json_format.ParseDict(load_fixture("concept/observation.json"), observation_pb2.Observation())
    assert obs.entity_ref.id == "imo:9284435"
    assert obs.geo.h3_r7 == "871f0d4c2ffffff"
    assert obs.kinematics.sog_kn == pytest.approx(11.2)
    assert obs.kinematics.draft_m == pytest.approx(12.1)
    assert obs.attributes["nav_status"] == "under_way"
    assert obs.attributes["destination"] == "JEA"
    assert obs.quality.position_accuracy_m == pytest.approx(20.0)
    assert obs.quality.is_interpolated is False
    assert obs.raw_ref.endswith("part-0012.jsonl#L4471")


def test_concept_event_keeps_documented_values():
    ev = json_format.ParseDict(load_fixture("concept/event.json"), event_pb2.Event())
    assert ev.type == "economic.rate_decision"
    assert ev.severity == pytest.approx(0.72)
    assert ev.confidence == pytest.approx(0.95)
    assert ev.corroboration.independent_sources == 6
    assert ev.corroboration.first_seen_source == "reuters"
    assert ev.scores.priority == pytest.approx(88.4)
    assert ev.status == event_pb2.EVENT_STATUS_CONFIRMED
    assert ev.versions[0].v == 1
    assert list(ev.versions[0].changed) == ["severity"]
    # occurred_at.end ist im Beispiel null - das muss als "nicht gesetzt"
    # ankommen und nicht als Epoche 0.
    assert not ev.occurred_at.HasField("end")
    # Die Erklaerung des Scores muss vollstaendig erhalten bleiben.
    assert [f.factor for f in ev.scores.explanation][:2] == ["watchlist", "proximity"]
    assert ev.scores.explanation[0].contribution == pytest.approx(0.25)
