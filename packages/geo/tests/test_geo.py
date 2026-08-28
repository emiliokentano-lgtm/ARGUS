"""Geo-Helfer."""

from __future__ import annotations

import pytest

from argus_geo import (
    BoundingBox,
    bbox_from_points,
    expand_bbox,
    great_circle_distance_m,
    h3_to_int,
    int_to_h3,
    is_valid_h3,
    knots_to_m_per_s,
    m_per_s_to_knots,
    normalize_bearing,
)
from argus_geo.h3 import InvalidH3IndexError


class TestH3:
    def test_round_trip(self) -> None:
        index = "871f0d4c2ffffff"
        assert int_to_h3(h3_to_int(index)) == index

    def test_fits_into_a_signed_bigint(self) -> None:
        """Die Zusicherung, auf der das Datenbankschema aufbaut.

        Ein H3-Zellindex belegt genau 15 Hexstellen: Bit 63 ist reserviert und
        0, die Bits 62-59 tragen den Modus. Der groesstmoegliche Wert liegt
        damit unter 2^60 und passt bequem in ein vorzeichenbehaftetes bigint.
        """
        largest = "f" * 15
        assert h3_to_int(largest) == 2**60 - 1
        assert h3_to_int(largest) < 2**63

    def test_uppercase_is_accepted(self) -> None:
        assert h3_to_int("871F0D4C2FFFFFF") == h3_to_int("871f0d4c2ffffff")

    @pytest.mark.parametrize("value", ["", "zzz", "871f0d4c2fffff", "871f0d4c2ffffff0"])
    def test_invalid_input_is_rejected(self, value: str) -> None:
        assert not is_valid_h3(value)
        with pytest.raises(InvalidH3IndexError):
            h3_to_int(value)

    def test_negative_int_is_rejected(self) -> None:
        """Ein negativer Wert bedeutet, dass beim Speichern etwas ueberlaufen
        ist - das darf nicht stillschweigend zurueckgerechnet werden."""
        with pytest.raises(InvalidH3IndexError, match="Ueberlauf"):
            int_to_h3(-1)

    def test_error_message_names_the_problem(self) -> None:
        with pytest.raises(InvalidH3IndexError, match="15 Hexstellen"):
            h3_to_int("abc")


class TestBoundingBox:
    def test_contains(self) -> None:
        box = BoundingBox(west=54.0, south=24.0, east=58.0, north=27.0)
        assert box.contains(56.26, 25.94)
        assert not box.contains(60.0, 25.94)
        assert not box.contains(56.26, 30.0)

    def test_antimeridian_is_detected(self) -> None:
        box = BoundingBox(west=170.0, south=-10.0, east=-170.0, north=10.0)
        assert box.crosses_antimeridian

    def test_contains_across_the_antimeridian(self) -> None:
        """Der Fall, den fast jede Kartenanwendung zuerst falsch macht."""
        box = BoundingBox(west=170.0, south=-10.0, east=-170.0, north=10.0)
        assert box.contains(175.0, 0.0)
        assert box.contains(-175.0, 0.0)
        assert not box.contains(0.0, 0.0)

    def test_split_at_antimeridian(self) -> None:
        box = BoundingBox(west=170.0, south=-10.0, east=-170.0, north=10.0)
        parts = box.split_at_antimeridian()
        assert len(parts) == 2
        assert parts[0].east == 180.0
        assert parts[1].west == -180.0

    def test_normal_box_is_not_split(self) -> None:
        box = BoundingBox(west=0.0, south=0.0, east=10.0, north=10.0)
        assert box.split_at_antimeridian() == (box,)

    def test_invalid_latitude_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Breitengrad"):
            BoundingBox(west=0.0, south=-91.0, east=1.0, north=0.0)

    def test_inverted_latitude_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="noerdlich"):
            BoundingBox(west=0.0, south=10.0, east=1.0, north=0.0)

    def test_from_points(self) -> None:
        box = bbox_from_points([(1.0, 2.0), (5.0, -3.0), (-1.0, 4.0)])
        assert (box.west, box.south, box.east, box.north) == (-1.0, -3.0, 5.0, 4.0)

    def test_from_points_needs_at_least_one(self) -> None:
        with pytest.raises(ValueError, match="mindestens einen Punkt"):
            bbox_from_points([])

    def test_expand_is_clamped_at_the_poles(self) -> None:
        box = expand_bbox(BoundingBox(0.0, 88.0, 1.0, 89.0), 5.0)
        assert box.north == 90.0

    def test_expand_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="nicht-negativ"):
            expand_bbox(BoundingBox(0.0, 0.0, 1.0, 1.0), -1.0)

    def test_wkt_is_closed(self) -> None:
        wkt = BoundingBox(0.0, 0.0, 1.0, 1.0).as_wkt()
        assert wkt.startswith("POLYGON((") and wkt.endswith("))")
        points = wkt[9:-2].split(", ")
        assert points[0] == points[-1], "ein Polygon muss geschlossen sein"


class TestUnits:
    def test_knots_round_trip(self) -> None:
        assert m_per_s_to_knots(knots_to_m_per_s(11.2)) == pytest.approx(11.2)

    def test_one_knot_is_one_nautical_mile_per_hour(self) -> None:
        assert knots_to_m_per_s(1.0) == pytest.approx(1852.0 / 3600.0)

    @pytest.mark.parametrize(
        ("value", "expected"), [(0.0, 0.0), (360.0, 0.0), (370.0, 10.0), (-10.0, 350.0)]
    )
    def test_normalize_bearing(self, value: float, expected: float) -> None:
        assert normalize_bearing(value) == pytest.approx(expected)

    def test_distance_between_identical_points_is_zero(self) -> None:
        assert great_circle_distance_m(8.0, 50.0, 8.0, 50.0) == pytest.approx(0.0)

    def test_known_distance(self) -> None:
        """Frankfurt - Rotterdam, rund 370 km."""
        distance = great_circle_distance_m(8.6742, 50.1092, 4.4013, 51.9244)
        assert 360_000 < distance < 380_000

    def test_distance_is_symmetric(self) -> None:
        forward = great_circle_distance_m(8.0, 50.0, 4.0, 52.0)
        backward = great_circle_distance_m(4.0, 52.0, 8.0, 50.0)
        assert forward == pytest.approx(backward)
