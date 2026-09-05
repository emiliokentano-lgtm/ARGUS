"""Die Sentinelwerte des AIS-Standards.

Der Kern dieser Datei ist eine einzige Zusicherung: jede clean_*-Funktion gibt
bei 'nicht verfuegbar' None zurueck und niemals 0. Ein Regressionstest dafuer
ist mehr wert als er aussieht - der Fehler ist still, und niemand bemerkt ihn,
bis eine Flotte vor Ghana liegt.
"""

from __future__ import annotations

import pytest
from aisstream import ais


@pytest.mark.parametrize(
    ("function", "sentinel"),
    [
        (ais.clean_latitude, 91.0),
        (ais.clean_longitude, 181.0),
        (ais.clean_sog, 102.3),
        (ais.clean_sog, 1023.0),
        (ais.clean_cog, 360.0),
        (ais.clean_cog, 3600.0),
        (ais.clean_heading, 511),
        (ais.clean_draught, 0.0),
    ],
)
def test_sentinels_become_none_never_zero(function, sentinel) -> None:
    assert function(sentinel) is None


@pytest.mark.parametrize(
    ("function", "value"),
    [
        (ais.clean_latitude, 0.0),
        (ais.clean_longitude, 0.0),
        (ais.clean_sog, 0.0),
        (ais.clean_cog, 0.0),
        (ais.clean_heading, 0),
    ],
)
def test_zero_is_a_real_value(function, value) -> None:
    """0 ist ein gueltiger Kurs, eine gueltige Fahrt und eine gueltige Position."""
    assert function(value) == 0.0


def test_out_of_range_coordinates_are_rejected() -> None:
    assert ais.clean_latitude(95.0) is None
    assert ais.clean_longitude(-200.0) is None
    assert ais.clean_latitude(-89.999) == pytest.approx(-89.999)


def test_sog_raw_tenths_are_recognised() -> None:
    # 234 in Zehnteln sind 23,4 kn - plausibel. 23,4 selbst ebenso; nur die
    # Rohform muss geteilt werden.
    assert ais.clean_sog(234.0) == pytest.approx(23.4)
    assert ais.clean_sog(23.4) == pytest.approx(23.4)


def test_cog_raw_tenths_are_recognised() -> None:
    assert ais.clean_cog(1184.0) == pytest.approx(118.4)
    assert ais.clean_cog(118.4) == pytest.approx(118.4)


def test_heading_has_no_tenths_form() -> None:
    """Anders als COG ist Heading immer ganzzahlig - 1184 ist Unsinn, nicht 118,4."""
    assert ais.clean_heading(1184) is None


def test_rate_of_turn_saturation_is_reported() -> None:
    assert ais.clean_rate_of_turn(-128) == (None, False)
    assert ais.clean_rate_of_turn(127) == (127.0, True)
    assert ais.clean_rate_of_turn(-127) == (-127.0, True)
    assert ais.clean_rate_of_turn(12) == (12.0, False)


def test_draught_raw_tenths() -> None:
    assert ais.clean_draught(121.0) == pytest.approx(12.1)
    assert ais.clean_draught(12.1) == pytest.approx(12.1)
    assert ais.clean_draught(0.0) is None


def test_at_sign_padding_is_not_a_name() -> None:
    assert ais.clean_text("@@@@@@@@@@") is None
    assert ais.clean_text("MUENSTERLAND@@@@@@@") == "MUENSTERLAND"
    assert ais.clean_text("   ") is None
    assert ais.clean_text(None) is None


def test_position_timestamp_semantics() -> None:
    assert ais.position_timestamp_quality(30) == (False, [])
    assert ais.position_timestamp_quality(62) == (True, ["dead_reckoned"])
    assert ais.position_timestamp_quality(61)[1] == ["manual_position_input"]
    assert ais.position_timestamp_quality(63)[1] == ["positioning_system_inoperative"]
    assert ais.position_timestamp_quality(60)[1] == ["position_time_not_available"]


def test_navigational_status_undefined_carries_no_information() -> None:
    assert ais.navigational_status(0) == "under_way_using_engine"
    assert ais.navigational_status(15) is None
    assert ais.navigational_status(None) is None


def test_ship_type_keeps_the_raw_code() -> None:
    assert ais.ship_type(70) == ("cargo", 70)
    assert ais.ship_type(80) == ("tanker", 80)
    assert ais.ship_type(30) == ("fishing", 30)
    assert ais.ship_type(52) == ("tug", 52)
    assert ais.ship_type(0) == (None, None)


def test_mmsi_category_separates_ships_from_everything_else() -> None:
    assert ais.mmsi_category(211331640) == "vessel"
    assert ais.mmsi_category(992111840) == "aid_to_navigation"
    assert ais.mmsi_category(111232500) == "sar_aircraft"
    assert ais.mmsi_category(2111234) == "coast_station"
    assert ais.mmsi_category(970010101) == "ais_sart"
    assert ais.mmsi_category(981234567) == "auxiliary_craft"


def test_mmsi_mid_only_where_it_is_defined() -> None:
    assert ais.mmsi_mid(211331640) == 211
    # Kuestenstation: die MID steht nach den zwei fuehrenden Nullen.
    assert ais.mmsi_mid(2111234) == 211
    # Fuer eine Navigationshilfe ist die MID nicht definiert - hier wird nichts
    # geraten.
    assert ais.mmsi_mid(992111840) is None


@pytest.mark.parametrize("imo", [9074729, 9811000, 9432268, 9285122, 9210945])
def test_valid_imo_numbers_pass_the_checksum(imo: int) -> None:
    assert ais.is_valid_imo(imo)


@pytest.mark.parametrize(
    "value",
    [
        1234568,  # Pruefziffer falsch
        0,  # 'nicht gemeldet'
        211331640,  # MMSI im IMO-Feld
        None,
        123,
    ],
)
def test_invalid_imo_numbers_are_rejected(value) -> None:
    assert not ais.is_valid_imo(value)


def test_dimensions_all_zero_means_not_reported() -> None:
    assert ais.dimensions({"A": 0, "B": 0, "C": 0, "D": 0}) is None
    assert ais.dimensions(None) is None
    dimension = ais.dimensions({"A": 135, "B": 45, "C": 14, "D": 14})
    assert dimension is not None
    assert dimension.length_m == 180.0
    assert dimension.beam_m == 28.0
