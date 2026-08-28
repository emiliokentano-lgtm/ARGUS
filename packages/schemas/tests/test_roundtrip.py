"""Vollstaendiger Round-Trip ueber alle Kernobjekte.

Die Fixtures decken realistische, aber unvollstaendige Nachrichten ab. Dieser
Test fuellt jedes Feld jedes Kernobjekts programmatisch aus dem Descriptor -
auch die, an die beim Schreiben der Beispiele niemand gedacht hat - und prueft
dann binaeren und JSON-Round-Trip sowie die Schema-Konformitaet.

Damit gilt die Zusicherung "serialisierbar, deserialisierbar, verlustfrei nach
JSON und zurueck" fuer das gesamte Schema und nicht nur fuer die Beispiele.
"""

from __future__ import annotations

import pytest
from google.protobuf import descriptor, json_format
from jsonschema import Draft202012Validator

from argus.v1 import (
    alert_pb2,
    aoi_pb2,
    assessment_pb2,
    case_pb2,
    entity_pb2,
    event_pb2,
    observation_pb2,
    relation_pb2,
    report_pb2,
    source_pb2,
    track_pb2,
    watchlist_pb2,
)
from conftest import load_schema

ROOTS = [
    ("Observation", observation_pb2.Observation),
    ("Event", event_pb2.Event),
    ("Entity", entity_pb2.Entity),
    ("Relation", relation_pb2.Relation),
    ("Report", report_pb2.Report),
    ("Track", track_pb2.Track),
    ("Assessment", assessment_pb2.Assessment),
    ("Source", source_pb2.Source),
    ("Aoi", aoi_pb2.Aoi),
    ("Watchlist", watchlist_pb2.Watchlist),
    ("Alert", alert_pb2.Alert),
    ("Case", case_pb2.Case),
]
IDS = [name for name, _ in ROOTS]

_SCALAR_VALUES = {
    descriptor.FieldDescriptor.TYPE_DOUBLE: 1.5,
    descriptor.FieldDescriptor.TYPE_FLOAT: 2.5,
    descriptor.FieldDescriptor.TYPE_INT64: -9007199254740993,
    descriptor.FieldDescriptor.TYPE_UINT64: 18446744073709551615,
    descriptor.FieldDescriptor.TYPE_INT32: -7,
    descriptor.FieldDescriptor.TYPE_FIXED64: 42,
    descriptor.FieldDescriptor.TYPE_FIXED32: 43,
    descriptor.FieldDescriptor.TYPE_BOOL: True,
    descriptor.FieldDescriptor.TYPE_STRING: "wert",
    descriptor.FieldDescriptor.TYPE_BYTES: b"\x00\x01\xfe",
    descriptor.FieldDescriptor.TYPE_UINT32: 44,
    descriptor.FieldDescriptor.TYPE_SFIXED32: -45,
    descriptor.FieldDescriptor.TYPE_SFIXED64: -46,
    descriptor.FieldDescriptor.TYPE_SINT32: -47,
    descriptor.FieldDescriptor.TYPE_SINT64: -48,
}

_MAX_DEPTH = 4


def _fill_well_known(msg) -> bool:
    """Well-Known-Types brauchen eine Sonderbehandlung, sonst wird die
    Struktur unendlich tief (Struct/Value verweisen auf sich selbst)."""
    full = msg.DESCRIPTOR.full_name
    if full == "google.protobuf.Timestamp":
        msg.FromJsonString("2026-08-28T09:14:03.221Z")
        return True
    if full == "google.protobuf.Duration":
        msg.FromJsonString("90.5s")
        return True
    if full == "google.protobuf.Struct":
        msg.update({"text": "wert", "zahl": 3, "flag": True, "liste": [1, "zwei"]})
        return True
    if full == "google.protobuf.Value":
        msg.string_value = "wert"
        return True
    if full == "google.protobuf.ListValue":
        msg.append("wert")
        return True
    return False


def _is_synthetic_oneof(oneof) -> bool:
    """proto3 `optional` wird intern als einelementiges oneof mit dem Namen
    "_<feld>" gefuehrt. Das ist kein echtes oneof und muss normal belegt
    werden. Die Protobuf-API stellt dafuer kein oeffentliches Merkmal bereit,
    deshalb die Namenskonvention."""
    return len(oneof.fields) == 1 and oneof.name == f"_{oneof.fields[0].name}"


def _is_map(field) -> bool:
    return (
        field.is_repeated
        and field.message_type is not None
        and field.message_type.GetOptions().map_entry
    )


def populate(msg, depth: int = 0) -> None:
    """Belegt jedes Feld der Nachricht mit einem von Null verschiedenen Wert."""
    if _fill_well_known(msg):
        return
    if depth >= _MAX_DEPTH:
        return

    seen_oneofs: set[str] = set()
    for field in msg.DESCRIPTOR.fields:
        # Von jedem echten oneof nur ein Zweig - sonst ueberschreiben sie
        # einander und der Test prueft nur den letzten.
        oneof = field.containing_oneof
        if oneof is not None and not _is_synthetic_oneof(oneof):
            if oneof.name in seen_oneofs:
                continue
            seen_oneofs.add(oneof.name)

        if field.is_repeated:
            if _is_map(field):
                value_field = field.message_type.fields_by_name["value"]
                container = getattr(msg, field.name)
                if value_field.type == descriptor.FieldDescriptor.TYPE_MESSAGE:
                    populate(container["a"], depth + 1)
                else:
                    container["a"] = _SCALAR_VALUES[value_field.type]
                continue
            container = getattr(msg, field.name)
            for _ in range(2):
                if field.type == descriptor.FieldDescriptor.TYPE_MESSAGE:
                    populate(container.add(), depth + 1)
                elif field.type == descriptor.FieldDescriptor.TYPE_ENUM:
                    container.append(_enum_value(field))
                else:
                    container.append(_SCALAR_VALUES[field.type])
            continue

        if field.type == descriptor.FieldDescriptor.TYPE_MESSAGE:
            populate(getattr(msg, field.name), depth + 1)
        elif field.type == descriptor.FieldDescriptor.TYPE_ENUM:
            setattr(msg, field.name, _enum_value(field))
        else:
            setattr(msg, field.name, _SCALAR_VALUES[field.type])


def _enum_value(field) -> int:
    """Nimmt bewusst einen Wert ungleich 0: der Nullwert ist UNSPECIFIED und
    wuerde beim Serialisieren weggelassen, der Test also entwertet."""
    values = [v.number for v in field.enum_type.values if v.number != 0]
    return values[0] if values else 0


@pytest.fixture(scope="module", params=ROOTS, ids=IDS)
def populated(request):
    name, cls = request.param
    msg = cls()
    populate(msg)
    return name, cls, msg


def test_every_field_is_set(populated):
    """Der Fueller muss wirklich jedes Feld erreicht haben - sonst prueft der
    Round-Trip-Test weniger, als er vorgibt."""
    _, _, msg = populated
    missing = []
    for field in msg.DESCRIPTOR.fields:
        oneof = field.containing_oneof
        # Bei echten oneofs wird bewusst nur ein Zweig belegt.
        if oneof is not None and not _is_synthetic_oneof(oneof):
            if not msg.WhichOneof(oneof.name):
                missing.append(oneof.name)
            continue
        if field.is_repeated:
            if not getattr(msg, field.name):
                missing.append(field.name)
        elif field.has_presence:
            if not msg.HasField(field.name):
                missing.append(field.name)
        elif not getattr(msg, field.name):
            missing.append(field.name)
    assert not missing, f"nicht belegte Felder: {sorted(set(missing))}"


def test_binary_roundtrip(populated):
    _, cls, msg = populated
    clone = cls()
    clone.ParseFromString(msg.SerializeToString())
    assert clone == msg


def test_json_roundtrip_proto_names(populated):
    _, cls, msg = populated
    as_dict = json_format.MessageToDict(msg, preserving_proto_field_name=True)
    assert json_format.ParseDict(as_dict, cls()) == msg


def test_json_roundtrip_camel_names(populated):
    _, cls, msg = populated
    as_dict = json_format.MessageToDict(msg, preserving_proto_field_name=False)
    assert json_format.ParseDict(as_dict, cls()) == msg


def test_json_text_roundtrip(populated):
    """Auch ueber den Textweg, nicht nur ueber dict - dort schlagen
    Gleitkomma- und 64-Bit-Fehler zu."""
    _, cls, msg = populated
    text = json_format.MessageToJson(msg, preserving_proto_field_name=True)
    assert json_format.Parse(text, cls()) == msg


@pytest.mark.parametrize("preserve", [True, False], ids=["proto_names", "camel_names"])
def test_populated_message_validates_against_schema(populated, preserve):
    """Das generierte JSON Schema muss jedes Feld des Schemas kennen - inklusive
    64-Bit-Zahlen als String, Bytes als Base64 und Enums als Namen."""
    name, _, msg = populated
    as_dict = json_format.MessageToDict(msg, preserving_proto_field_name=preserve)
    validator = Draft202012Validator(load_schema(f"{name}.schema.json"))
    errors = sorted(validator.iter_errors(as_dict), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)


def test_populated_message_satisfies_strict_schema(populated):
    """Eine vollstaendig belegte Nachricht erfuellt zwangslaeufig auch alle
    Pflichtfelder - andernfalls verweist required.json auf ein Feld, das es
    nicht mehr gibt."""
    name, _, msg = populated
    as_dict = json_format.MessageToDict(msg, preserving_proto_field_name=True)
    validator = Draft202012Validator(load_schema(f"{name}.strict.schema.json"))
    errors = sorted(validator.iter_errors(as_dict), key=lambda e: list(e.path))
    assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)
