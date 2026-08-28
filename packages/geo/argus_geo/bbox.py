"""Huellrechtecke fuer Viewport-Abfragen."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Achsenparalleles Huellrechteck in WGS84.

    `crosses_antimeridian` ist der Fall, den fast jede Kartenanwendung zuerst
    falsch macht: bei einem Ausschnitt ueber dem Pazifik ist `west` groesser als
    `east`. Wer das ignoriert, bekommt bei jedem Schwenk ueber die Datumsgrenze
    ein leeres Ergebnis - und merkt es nie, weil dort selten jemand hinsieht.
    """

    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        if not -90.0 <= self.south <= 90.0 or not -90.0 <= self.north <= 90.0:
            raise ValueError(f"Breitengrad ausserhalb [-90, 90]: {self.south}, {self.north}")
        if self.south > self.north:
            raise ValueError(f"south ({self.south}) liegt noerdlich von north ({self.north})")
        if not -180.0 <= self.west <= 180.0 or not -180.0 <= self.east <= 180.0:
            raise ValueError(f"Laengengrad ausserhalb [-180, 180]: {self.west}, {self.east}")

    @property
    def crosses_antimeridian(self) -> bool:
        return self.west > self.east

    def contains(self, lon: float, lat: float) -> bool:
        if not self.south <= lat <= self.north:
            return False
        if self.crosses_antimeridian:
            return lon >= self.west or lon <= self.east
        return self.west <= lon <= self.east

    def split_at_antimeridian(self) -> tuple[BoundingBox, ...]:
        """Zerlegt einen Ausschnitt ueber der Datumsgrenze in zwei.

        PostGIS und die meisten Kachelserver rechnen mit einfachen Rechtecken.
        Statt ueberall Sonderfaelle zu verteilen, wird hier einmal zerlegt.
        """
        if not self.crosses_antimeridian:
            return (self,)
        return (
            BoundingBox(self.west, self.south, 180.0, self.north),
            BoundingBox(-180.0, self.south, self.east, self.north),
        )

    def as_wkt(self) -> str:
        """WKT-Polygon fuer PostGIS-Abfragen."""
        return (
            "POLYGON(("
            f"{self.west} {self.south}, {self.east} {self.south}, "
            f"{self.east} {self.north}, {self.west} {self.north}, "
            f"{self.west} {self.south}))"
        )


def bbox_from_points(points: Iterable[tuple[float, float]]) -> BoundingBox:
    """Huellrechteck einer Punktmenge, als (lon, lat)."""
    coordinates = list(points)
    if not coordinates:
        raise ValueError("Ein Huellrechteck braucht mindestens einen Punkt")
    lons = [lon for lon, _ in coordinates]
    lats = [lat for _, lat in coordinates]
    return BoundingBox(min(lons), min(lats), max(lons), max(lats))


def expand_bbox(bbox: BoundingBox, degrees: float) -> BoundingBox:
    """Vergroessert ein Huellrechteck, ohne die Gradgrenzen zu verletzen."""
    if degrees < 0:
        raise ValueError("degrees muss nicht-negativ sein")
    return BoundingBox(
        west=max(-180.0, bbox.west - degrees),
        south=max(-90.0, bbox.south - degrees),
        east=min(180.0, bbox.east + degrees),
        north=min(90.0, bbox.north + degrees),
    )
