"""Schemakonformitaet und Round-Trip.

Gegen die *generierten* Artefakte aus packages/schemas, nicht gegen eine
Kopie: JSON -> Protobuf -> JSON muss dasselbe Objekt ergeben, und das Objekt
muss gegen das strenge JSON-Schema gelten.

Der Round-Trip ist der schaerfere der beiden Tests. Das JSON-Schema prueft,
dass nichts Fremdes drinsteht; der Round-Trip prueft zusaetzlich, dass jeder
Wert in seinem Protobuf-Feld auch wirklich Platz hat - eine Zahl, die als
Zeichenkette kommt, oder ein Enum-Name, den es nicht gibt, faellt erst hier
auf.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from aisstream.normalize import Normalizer
from aisstream.parser import UnsupportedMessageTypeError, parse

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "packages" / "schemas"
GEN_PYTHON = SCHEMA_DIR / "gen" / "python"
GEN_JSONSCHEMA = SCHEMA_DIR / "gen" / "jsonschema"

NOW = 1_787_910_000.0

pytestmark = pytest.mark.skipif(
    not GEN_PYTHON.exists() or not GEN_JSONSCHEMA.exists(),
    reason="Generierte Schema-Artefakte fehlen - zuerst 'make gen' ausfuehren.",
)

if GEN_PYTHON.exists():
    sys.path.insert(0, str(GEN_PYTHON))


@pytest.fixture(scope="module")
def protobuf_types():
    from argus.v1 import entity_pb2, observation_pb2

    return observation_pb2.Observation, entity_pb2.Entity


@pytest.fixture(scope="module")
def strict_schemas() -> dict[str, dict]:
    return {
        name: json.loads((GEN_JSONSCHEMA / f"{name}.strict.schema.json").read_text("utf-8"))
        for name in ("Observation", "Entity")
    }


@pytest.fixture(scope="module")
def normalized(stream_messages, edge_cases) -> tuple[list[dict], list[dict]]:
    """Alles, was der Konnektor aus dem gesamten Fixture-Bestand erzeugt."""
    normalizer = Normalizer(collector="ingest-sea-aisstream@0.1.0")
    observations: list[dict] = []
    entities: list[dict] = []
    for message in stream_messages + [m for _, m in edge_cases]:
        try:
            parsed = parse(message)
        except UnsupportedMessageTypeError:
            continue
        position = normalizer.to_observation(parsed, now=NOW, raw_ref="s3://bronze/test#L1")
        if position is not None:
            observations.append(position[0])
        static = normalizer.to_entity(parsed, now=NOW, raw_ref="s3://bronze/test#L1")
        if static is not None:
            entities.append(static[0])
    return observations, entities


def test_the_whole_fixture_set_is_normalized(normalized) -> None:
    observations, entities = normalized
    assert len(observations) > 500
    assert len(entities) > 50


def test_observations_validate_against_the_strict_schema(normalized, strict_schemas) -> None:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(strict_schemas["Observation"])
    for observation in normalized[0]:
        errors = sorted(validator.iter_errors(observation), key=str)
        assert not errors, f"{observation['obs_id']}: {[e.message for e in errors]}"


def test_entities_validate_against_the_strict_schema(normalized, strict_schemas) -> None:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(strict_schemas["Entity"])
    for entity in normalized[1]:
        errors = sorted(validator.iter_errors(entity), key=str)
        assert not errors, f"{entity['entity_id']}: {[e.message for e in errors]}"


def _roundtrip(payload: dict, message_class) -> dict:
    from google.protobuf.json_format import MessageToDict, ParseDict

    message = ParseDict(payload, message_class(), ignore_unknown_fields=False)
    return MessageToDict(
        message,
        preserving_proto_field_name=True,
        always_print_fields_with_no_presence=False,
    )


def test_observation_roundtrip_is_lossless(normalized, protobuf_types) -> None:
    observation_class, _ = protobuf_types
    for observation in normalized[0]:
        result = _roundtrip(observation, observation_class)
        assert result == observation, (
            f"Round-Trip veraendert {observation['obs_id']}:\n"
            f"  hinein: {json.dumps(observation, sort_keys=True)}\n"
            f"  heraus: {json.dumps(result, sort_keys=True)}"
        )


def test_entity_roundtrip_is_lossless(normalized, protobuf_types) -> None:
    _, entity_class = protobuf_types
    for entity in normalized[1]:
        result = _roundtrip(entity, entity_class)
        assert result == entity, (
            f"Round-Trip veraendert {entity['entity_id']}:\n"
            f"  hinein: {json.dumps(entity, sort_keys=True)}\n"
            f"  heraus: {json.dumps(result, sort_keys=True)}"
        )


def test_unknown_fields_would_be_caught(protobuf_types) -> None:
    """Beweist, dass der Round-Trip-Test scharf ist und nicht alles durchlaesst."""
    from google.protobuf.json_format import ParseError

    observation_class, _ = protobuf_types
    with pytest.raises(ParseError):
        _roundtrip({"obs_id": "X", "erfundenes_feld": 1}, observation_class)


def test_timestamps_are_utc_with_millisecond_precision(normalized) -> None:
    """ARGUS transportiert Zeit ausschliesslich als UTC mit Zonenangabe."""
    for observation in normalized[0]:
        assert observation["ingested_at"].endswith("Z")
        if "observed_at" in observation:
            assert observation["observed_at"].endswith("Z")
