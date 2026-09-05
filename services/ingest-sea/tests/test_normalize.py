"""Vom AIS-Fakt zum kanonischen Objekt."""

from __future__ import annotations

import pytest
from aisstream.ids import is_ulid
from aisstream.normalize import Normalizer, subject_suffix_for
from aisstream.parser import UnsupportedMessageTypeError, parse

NOW = 1_787_910_000.0  # 2026-08-28, nach allen Fixture-Zeitstempeln


@pytest.fixture
def normalizer() -> Normalizer:
    return Normalizer(collector="ingest-sea-aisstream@0.1.0")


def _first(messages, message_type: str):
    return next(m for m in messages if m["MessageType"] == message_type)


# --- Trennung der beiden Ausgaenge -----------------------------------------


def test_subjects_are_the_promised_ones() -> None:
    assert subject_suffix_for("position", prefix="argus.canon") == "vessel.position"
    assert subject_suffix_for("static", prefix="argus.canon") == "vessel.static"


def test_wrong_prefix_fails_loudly_instead_of_publishing_elsewhere() -> None:
    """Ein falsches Praefix wuerde still auf ein anderes Subject schreiben.

    Der Stream bliebe leer, der Konnektor meldete Erfolg. Deshalb ein Fehler
    beim Start und keine Warnung im Betrieb.
    """
    with pytest.raises(ValueError, match=r"argus\.canon"):
        subject_suffix_for("position", prefix="argus.raw")


def test_position_report_yields_only_an_observation(normalizer, stream_messages) -> None:
    parsed = parse(_first(stream_messages, "PositionReport"))
    assert normalizer.to_observation(parsed, now=NOW) is not None
    assert normalizer.to_entity(parsed, now=NOW) is None


def test_ship_static_data_yields_only_an_entity(normalizer, stream_messages) -> None:
    parsed = parse(_first(stream_messages, "ShipStaticData"))
    assert normalizer.to_observation(parsed, now=NOW) is None
    assert normalizer.to_entity(parsed, now=NOW) is not None


def test_extended_class_b_yields_both(normalizer, stream_messages) -> None:
    parsed = parse(_first(stream_messages, "ExtendedClassBPositionReport"))
    assert normalizer.to_observation(parsed, now=NOW) is not None
    assert normalizer.to_entity(parsed, now=NOW) is not None


# --- Kennungen -------------------------------------------------------------


def test_entity_ref_uses_mmsi_when_no_imo_is_known(normalizer, stream_messages) -> None:
    """Ein Positionsbericht traegt nie eine IMO - dort kann nur die MMSI stehen."""
    parsed = parse(_first(stream_messages, "PositionReport"))
    observation, _, _ = normalizer.to_observation(parsed, now=NOW)
    assert observation["entity_ref"]["id"] == f"mmsi:{parsed.mmsi}"
    assert observation["entity_ref"]["resolution_status"] == "RESOLUTION_STATUS_PENDING"
    # Der Konnektor loest nicht auf und behauptet es auch nicht.
    assert "resolved_entity_id" not in observation["entity_ref"]


def test_imo_wins_over_mmsi_as_primary_identifier(normalizer, stream_messages) -> None:
    message = next(
        m
        for m in stream_messages
        if m["MessageType"] == "ShipStaticData" and m["Message"]["ShipStaticData"]["ImoNumber"]
    )
    entity, _, _ = normalizer.to_entity(parse(message), now=NOW)
    schemes = {i["scheme"]: i for i in entity["identifiers"]}
    assert schemes["imo"]["is_primary"] is True
    assert schemes["imo"]["stability"] == "IDENTIFIER_STABILITY_STABLE"
    # is_primary=False wird nicht geschrieben: proto3 kennt fuer diesen Bool
    # keine Praesenz, ein ausdrueckliches false ueberlebt den Round-Trip nicht.
    assert "is_primary" not in schemes["mmsi"]
    # Der ganze Punkt von ADR 0005: die MMSI ist als wechselnd gekennzeichnet.
    assert schemes["mmsi"]["stability"] == "IDENTIFIER_STABILITY_MUTABLE"


def test_mmsi_is_primary_only_without_imo(normalizer, edge_case) -> None:
    entity, _, _ = normalizer.to_entity(parse(edge_case("Teil A")), now=NOW)
    schemes = {i["scheme"]: i for i in entity["identifiers"]}
    assert "imo" not in schemes
    assert schemes["mmsi"]["is_primary"] is True


def test_entity_id_is_marked_provisional(normalizer, stream_messages) -> None:
    entity, _, _ = normalizer.to_entity(parse(_first(stream_messages, "ShipStaticData")), now=NOW)
    assert entity["attributes"]["entity_id_is_provisional"] is True
    assert "ADR 0005" in entity["resolution"]["note"]


def test_ids_are_ulids(normalizer, stream_messages) -> None:
    observation, _, _ = normalizer.to_observation(
        parse(_first(stream_messages, "PositionReport")), now=NOW
    )
    entity, _, _ = normalizer.to_entity(parse(_first(stream_messages, "ShipStaticData")), now=NOW)
    assert is_ulid(observation["obs_id"])
    assert is_ulid(entity["entity_id"])


def test_same_message_yields_the_same_id(stream_messages) -> None:
    """Die Zusage, auf der der Wiederanlauf aus Bronze beruht.

    Zwei getrennte Normalizer, verschiedene Systemzeiten, dieselbe
    Rohnachricht - dieselbe obs_id. Ohne das waere jeder Replay eine
    Verdopplung statt einer Wiederherstellung.
    """
    message = _first(stream_messages, "PositionReport")
    first, _, _ = Normalizer(collector="a@1").to_observation(parse(message), now=NOW)
    second, _, _ = Normalizer(collector="b@2").to_observation(parse(message), now=NOW + 86_400)
    assert first["obs_id"] == second["obs_id"]
    assert first["dedupe_key"] == second["dedupe_key"]


def test_different_messages_yield_different_ids(normalizer, stream_messages) -> None:
    ids = set()
    for message in stream_messages:
        try:
            parsed = parse(message)
        except UnsupportedMessageTypeError:
            continue
        result = normalizer.to_observation(parsed, now=NOW)
        if result is not None:
            ids.add(result[0]["obs_id"])
    positions = sum(
        1
        for m in stream_messages
        if m["MessageType"]
        in {
            "PositionReport",
            "StandardClassBPositionReport",
            "ExtendedClassBPositionReport",
            "AidsToNavigationReport",
        }
    )
    assert len(ids) == positions


# --- Typen -----------------------------------------------------------------


def test_aid_to_navigation_is_not_a_vessel(normalizer, edge_case) -> None:
    """Bojen fahren nicht. Sie als Schiff zu fuehren verdirbt jeden Detektor."""
    parsed = parse(edge_case("Navigationshilfe: kein Schiff"))
    observation, _, _ = normalizer.to_observation(parsed, now=NOW)
    entity, _, _ = normalizer.to_entity(parsed, now=NOW)
    assert observation["entity_ref"]["type"] == "ENTITY_TYPE_FACILITY"
    assert entity["type"] == "ENTITY_TYPE_FACILITY"


def test_sar_aircraft_is_an_aircraft(normalizer, edge_case) -> None:
    parsed = parse(edge_case("SAR-Flugzeug"))
    observation, _, _ = normalizer.to_observation(parsed, now=NOW)
    assert observation["entity_ref"]["type"] == "ENTITY_TYPE_AIRCRAFT"


def test_null_island_yields_no_geo_block(normalizer, edge_case) -> None:
    parsed = parse(edge_case("Null Island"))
    observation, _, _ = normalizer.to_observation(parsed, now=NOW)
    assert "geo" not in observation
    assert observation["kind"] == "OBSERVATION_KIND_STATUS"
    assert "null_island" in observation["quality"]["flags"]


def test_virtual_aton_is_marked_as_not_existing(normalizer, edge_case) -> None:
    parsed = parse(edge_case("Virtuelle Navigationshilfe"))
    observation, _, _ = normalizer.to_observation(parsed, now=NOW)
    assert observation["attributes"]["is_virtual_aton"] is True
    assert "virtual_aton" in observation["quality"]["flags"]


# --- Ungueltige Werte ------------------------------------------------------


def test_missing_position_becomes_a_status_not_a_zero_position(normalizer, edge_case) -> None:
    """Kein geo-Block statt 0/0 - und die Art der Beobachtung aendert sich mit."""
    parsed = parse(edge_case("Lat 91"))
    observation, _, _ = normalizer.to_observation(parsed, now=NOW)
    assert "geo" not in observation
    assert observation["kind"] == "OBSERVATION_KIND_STATUS"
    assert "invalid_position" in observation["quality"]["flags"]


def test_unavailable_kinematics_are_absent_not_zero(normalizer, edge_case) -> None:
    parsed = parse(edge_case("Heading 511"))
    observation, _, _ = normalizer.to_observation(parsed, now=NOW)
    kinematics = observation.get("kinematics", {})
    assert "heading_deg" not in kinematics
    assert "cog_deg" not in kinematics
    # Was verfuegbar ist, bleibt erhalten.
    assert kinematics["sog_kn"] == pytest.approx(11.2)


def test_h3_cells_are_computed_for_every_position(normalizer, stream_messages) -> None:
    parsed = parse(_first(stream_messages, "PositionReport"))
    observation, _, _ = normalizer.to_observation(parsed, now=NOW)
    geo = observation["geo"]
    assert geo["precision"] == "GEO_PRECISION_EXACT"
    for key in ("h3_r5", "h3_r7", "h3_r9"):
        assert len(geo[key]) == 15


def test_h3_cells_survive_the_bigint_conversion(normalizer, stream_messages) -> None:
    """Die Zellen gehen als bigint in die Datenbank (ADR 0003)."""
    from argus_geo import h3_to_int, int_to_h3

    parsed = parse(_first(stream_messages, "PositionReport"))
    observation, _, _ = normalizer.to_observation(parsed, now=NOW)
    for key in ("h3_r5", "h3_r7", "h3_r9"):
        assert int_to_h3(h3_to_int(observation["geo"][key])) == observation["geo"][key]


# --- Zeit ------------------------------------------------------------------


def test_future_timestamp_is_marked_not_corrected(normalizer, edge_case) -> None:
    """Den Fehler der Quelle zu korrigieren hiesse, ihn zu unserem zu machen."""
    parsed = parse(edge_case("Zukunft"))
    observation, _, observed_at = normalizer.to_observation(parsed, now=NOW)
    assert observation["quality"]["time_quality"] == "TIME_QUALITY_IMPLAUSIBLE"
    assert "future_timestamp" in observation["quality"]["flags"]
    assert observed_at == parsed.received_at  # unveraendert
    assert observation["observed_at"].startswith("2027-")


def test_unreadable_timestamp_leaves_observed_at_absent(normalizer, edge_case) -> None:
    parsed = parse(edge_case("Zeitstempel unlesbar"))
    observation, _, observed_at = normalizer.to_observation(parsed, now=NOW)
    assert observed_at is None
    assert "observed_at" not in observation
    assert observation["quality"]["time_quality"] == "TIME_QUALITY_MISSING"
    assert "no_source_timestamp" in observation["quality"]["flags"]


# --- Positionssprung -------------------------------------------------------


def test_position_jump_is_flagged(normalizer, edge_case) -> None:
    normalizer.to_observation(parse(edge_case("Heading 511")), now=NOW)
    parsed = parse(edge_case("Positionssprung"))
    observation, _, _ = normalizer.to_observation(parsed, now=NOW)
    assert "impossible_speed" in observation["quality"]["flags"]


def test_normal_movement_is_not_flagged(normalizer, stream_messages) -> None:
    positions = [m for m in stream_messages if m["MessageType"] == "PositionReport"]
    flagged = 0
    for message in positions:
        result = normalizer.to_observation(parse(message), now=NOW)
        if result and "impossible_speed" in result[0]["quality"].get("flags", []):
            flagged += 1
    assert flagged == 0, "Regulaere Fahrt darf keinen Sprungverdacht ausloesen"


def test_seconds_since_previous_is_recorded(normalizer, stream_messages) -> None:
    positions = [m for m in stream_messages if m["MessageType"] == "PositionReport"][:40]
    with_gap = 0
    for message in positions:
        observation, _, _ = normalizer.to_observation(parse(message), now=NOW)
        if "seconds_since_previous" in observation["quality"]:
            with_gap += 1
    assert with_gap > 0


def test_position_history_is_bounded(stream_messages) -> None:
    """Ein 24-Stunden-Lauf darf nicht an einer wachsenden Landkarte scheitern."""
    normalizer = Normalizer(collector="test@1", position_history_size=5)
    for message in stream_messages:
        try:
            parsed = parse(message)
        except UnsupportedMessageTypeError:
            continue
        normalizer.to_observation(parsed, now=NOW)
    assert len(normalizer._last_position) <= 5


# --- Stammdaten ------------------------------------------------------------


def test_missing_name_becomes_a_marked_placeholder(normalizer, edge_case) -> None:
    parsed = parse(edge_case("Teil B"))
    entity, _, _ = normalizer.to_entity(parsed, now=NOW)
    assert entity["display_name"] == f"MMSI {parsed.mmsi}"
    assert entity["attributes"]["display_name_is_placeholder"] is True


def test_conflicting_names_keep_the_old_one_as_alias(normalizer, edge_case) -> None:
    parsed = parse(edge_case("anderen Namen"))
    entity, _, _ = normalizer.to_entity(parsed, now=NOW)
    assert entity["display_name"] == "EASTERN GLORY"
    assert entity["aliases"][0]["name"] == "PACIFIC GLORY"
    assert entity["aliases"][0]["kind"] == "ALIAS_KIND_FORMER_NAME"


def test_dimensions_are_carried_over(normalizer, stream_messages) -> None:
    entity, _, _ = normalizer.to_entity(parse(_first(stream_messages, "ShipStaticData")), now=NOW)
    dimensions = entity["attributes"]["dimensions"]
    assert dimensions["length_m"] > 0
    assert dimensions["beam_m"] > 0


def test_provenance_names_source_collector_and_licence(normalizer, stream_messages) -> None:
    observation, _, _ = normalizer.to_observation(
        parse(_first(stream_messages, "PositionReport")), now=NOW
    )
    source = observation["source"]
    assert source["id"] == "aisstream"
    # Admiralty B, nicht A: AIS ist unauthentifiziert.
    assert source["reliability"] == "SOURCE_RELIABILITY_B"
    assert source["collector"] == "ingest-sea-aisstream@0.1.0"
    assert source["license_id"] == "aisstream-tos"
