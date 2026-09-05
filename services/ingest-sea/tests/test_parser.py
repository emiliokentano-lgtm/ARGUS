"""Die Uebersetzung der AISStream-Drahtform.

Laeuft ueber den gesamten Fixture-Bestand: jede Nachricht, die der Parser
annehmen soll, muss er annehmen - und jede, die er ablehnt, muss er aus einem
benannten Grund ablehnen.
"""

from __future__ import annotations

import pytest
from aisstream import ais
from aisstream.parser import (
    SUPPORTED_TYPES,
    MalformedMessageError,
    UnsupportedMessageTypeError,
    parse,
    parse_go_time,
)


def test_every_supported_type_appears_in_the_fixtures(stream_messages) -> None:
    """Ein Fixture-Bestand, der einen Typ nicht enthaelt, testet ihn nicht."""
    seen = {m["MessageType"] for m in stream_messages}
    missing = set(SUPPORTED_TYPES) - seen
    assert not missing, f"Diese Typen fehlen in den Fixtures: {sorted(missing)}"


def test_fixture_count_meets_the_requirement(stream_messages, edge_cases) -> None:
    assert len(stream_messages) + len(edge_cases) >= 500


def test_all_supported_fixtures_parse(stream_messages) -> None:
    parsed = skipped = 0
    for message in stream_messages:
        try:
            result = parse(message)
        except UnsupportedMessageTypeError:
            skipped += 1
            continue
        parsed += 1
        assert ais.is_valid_mmsi(result.mmsi)
        assert result.position is not None or result.static is not None
    assert parsed > 500
    assert skipped > 0, "Ohne nicht unterstuetzte Typen bleibt der Ueberspringpfad ungetestet"


def test_unsupported_type_names_itself() -> None:
    with pytest.raises(UnsupportedMessageTypeError) as excinfo:
        parse(
            {
                "MessageType": "BaseStationReport",
                "MetaData": {"MMSI": 2111234, "time_utc": "2026-08-28 09:00:00.0 +0000 UTC"},
                "Message": {"BaseStationReport": {"UserID": 2111234}},
            }
        )
    assert excinfo.value.message_type == "BaseStationReport"


@pytest.mark.parametrize(
    ("envelope", "reason"),
    [
        ({}, "MessageType"),
        ({"MessageType": "PositionReport"}, "MetaData"),
        ({"MessageType": "PositionReport", "MetaData": {}}, "Message"),
        (
            {
                "MessageType": "PositionReport",
                "MetaData": {"MMSI": 211331640},
                "Message": {"SomethingElse": {}},
            },
            "Message.PositionReport",
        ),
        (
            {
                "MessageType": "PositionReport",
                "MetaData": {"MMSI": 0},
                "Message": {"PositionReport": {"UserID": 0}},
            },
            "MMSI",
        ),
    ],
)
def test_malformed_envelopes_say_what_is_wrong(envelope, reason) -> None:
    with pytest.raises(MalformedMessageError) as excinfo:
        parse(envelope)
    assert reason in str(excinfo.value)


def test_mmsi_comes_from_the_ais_record_not_from_metadata() -> None:
    """MetaData ist der Rueckfall, nicht die Quelle.

    Widersprechen sich beide, gilt der AIS-Satz - MetaData ist die Sicht des
    Dienstes und kann aus einer frueheren Nachricht stammen.
    """
    parsed = parse(
        {
            "MessageType": "PositionReport",
            "MetaData": {"MMSI": 999999999, "time_utc": "2026-08-28 09:00:00.0 +0000 UTC"},
            "Message": {
                "PositionReport": {
                    "MessageID": 1,
                    "UserID": 211331640,
                    "Latitude": 53.5,
                    "Longitude": 8.1,
                    "Sog": 10.0,
                    "Cog": 90.0,
                    "TrueHeading": 90,
                    "Timestamp": 10,
                }
            },
        }
    )
    assert parsed.mmsi == 211331640


def test_mmsi_string_with_leading_zero_is_read() -> None:
    parsed = parse(
        {
            "MessageType": "PositionReport",
            "MetaData": {
                "MMSI_String": "002111234",
                "time_utc": "2026-08-28 09:00:00.0 +0000 UTC",
            },
            "Message": {"PositionReport": {"MessageID": 1, "Latitude": 53.5, "Longitude": 8.1}},
        }
    )
    assert parsed.mmsi == 2111234
    assert parsed.mmsi_category == "coast_station"


# --- Zeitformat ------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected_iso"),
    [
        ("2026-08-28 09:14:03.221 +0000 UTC", "2026-08-28T09:14:03.221000+00:00"),
        ("2026-08-28 09:14:03 +0000 UTC", "2026-08-28T09:14:03+00:00"),
        ("2026-08-28T09:14:03Z".replace("Z", " +0000 UTC"), "2026-08-28T09:14:03+00:00"),
        ("2026-08-28 11:14:03 +0200 CEST", "2026-08-28T09:14:03+00:00"),
    ],
)
def test_go_time_format(text: str, expected_iso: str) -> None:
    from datetime import UTC, datetime

    epoch = parse_go_time(text)
    assert epoch is not None
    assert datetime.fromtimestamp(epoch, tz=UTC).isoformat() == expected_iso


@pytest.mark.parametrize("text", ["", None, "nicht-ein-zeitstempel", "2026-13-45 99:99:99"])
def test_unreadable_time_is_none_not_now(text) -> None:
    """Ein unlesbarer Zeitstempel darf nicht still zu 'jetzt' werden."""
    assert parse_go_time(text) is None


# --- Sonderfaelle ----------------------------------------------------------


def test_invalid_position_is_dropped_not_mapped_to_zero(edge_case) -> None:
    parsed = parse(edge_case("Lat 91"))
    assert parsed.position is not None
    assert parsed.position.lat is None
    assert parsed.position.lon is None
    assert not parsed.position.has_position
    assert "invalid_position" in parsed.position.quality_flags


def test_heading_511_and_cog_360_become_none(edge_case) -> None:
    parsed = parse(edge_case("Heading 511"))
    assert parsed.position is not None
    assert parsed.position.heading_deg is None
    assert parsed.position.cog_deg is None


def test_cog_3600_is_the_same_sentinel(edge_case) -> None:
    parsed = parse(edge_case("COG in Rohform"))
    assert parsed.position is not None
    assert parsed.position.cog_deg is None


def test_dead_reckoning_is_recognised(edge_case) -> None:
    parsed = parse(edge_case("Timestamp 62"))
    assert parsed.position is not None
    assert parsed.position.is_dead_reckoned


def test_null_island_is_flagged_and_dropped(edge_case) -> None:
    """0/0 ist im Schema nicht von 'keine Position' zu unterscheiden.

    Begruendung im Parser: GeoPoint.lat/.lon sind proto3-double ohne Praesenz.
    Die Marke bleibt erhalten, damit der Fall im Quellen-Panel sichtbar ist.
    """
    parsed = parse(edge_case("Null Island"))
    assert parsed.position is not None
    assert not parsed.position.has_position
    assert "null_island" in parsed.position.quality_flags


def test_bad_imo_checksum_is_not_adopted(edge_case) -> None:
    parsed = parse(edge_case("falscher Pruefziffer"))
    assert parsed.static is not None
    assert parsed.static.imo is None
    assert "invalid_imo_checksum" in parsed.static.quality_flags


def test_mmsi_in_the_imo_field_is_not_adopted(edge_case) -> None:
    parsed = parse(edge_case("IMO-Feld traegt die MMSI"))
    assert parsed.static is not None
    assert parsed.static.imo is None


def test_at_padded_static_data_yields_nothing(edge_case) -> None:
    parsed = parse(edge_case("Leere Textfelder"))
    assert parsed.static is not None
    assert parsed.static.name is None
    assert parsed.static.call_sign is None
    assert parsed.static.destination is None
    assert parsed.static.eta is None


def test_extended_class_b_carries_position_and_static(stream_messages) -> None:
    """Typ 19 ist der einzige Satz mit beidem."""
    message = next(m for m in stream_messages if m["MessageType"] == "ExtendedClassBPositionReport")
    parsed = parse(message)
    assert parsed.position is not None
    assert parsed.static is not None
    assert parsed.static.name


def test_static_data_report_parts_are_kept_apart(edge_case) -> None:
    part_a = parse(edge_case("Teil A"))
    part_b = parse(edge_case("Teil B"))
    assert part_a.static is not None and part_a.static.part == "A"
    assert part_a.static.name == "ZEEHOND"
    assert part_a.static.call_sign is None
    assert part_b.static is not None and part_b.static.part == "B"
    assert part_b.static.call_sign == "PCXY"
    assert part_b.static.name is None


def test_aton_is_not_a_vessel(edge_case) -> None:
    parsed = parse(edge_case("Navigationshilfe: kein Schiff"))
    assert parsed.mmsi_category == "aid_to_navigation"
    assert parsed.static is not None
    assert parsed.static.aton_type == "special_mark"


def test_virtual_aton_is_marked(edge_case) -> None:
    parsed = parse(edge_case("Virtuelle Navigationshilfe"))
    assert parsed.static is not None
    assert parsed.static.is_virtual_aton


def test_eta_stays_a_string_without_a_year(edge_cases) -> None:
    """Das Jahr zu raten hiesse, ein Feld zu erfinden, das AIS nicht hat."""
    message = next(
        m
        for _, m in edge_cases
        if m["MessageType"] == "ShipStaticData"
        and m["Message"]["ShipStaticData"].get("Eta", {}).get("Month")
    )
    parsed = parse(message)
    assert parsed.static is not None
    assert parsed.static.eta is not None
    assert parsed.static.eta.startswith("--")


def test_raw_draught_in_tenths(edge_case) -> None:
    parsed = parse(edge_case("Tiefgang in Rohform"))
    assert parsed.static is not None
    assert parsed.static.max_draught_m == pytest.approx(12.1)
