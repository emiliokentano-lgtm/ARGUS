"""Geteilte Geo-Helfer.

Klein gehalten und ohne Abhaengigkeiten: alles hier wird sowohl von den
Konnektoren als auch von der API und den Detektoren benutzt, und eine
Bibliothek, die an dieser Stelle eine schwere Abhaengigkeit zieht, zieht sie
ueberall hin.
"""

from argus_geo.bbox import BoundingBox, bbox_from_points, expand_bbox
from argus_geo.h3 import h3_to_int, int_to_h3, is_valid_h3
from argus_geo.units import (
    great_circle_distance_m,
    knots_to_m_per_s,
    m_per_s_to_knots,
    normalize_bearing,
)

__all__ = [
    "BoundingBox",
    "bbox_from_points",
    "expand_bbox",
    "great_circle_distance_m",
    "h3_to_int",
    "int_to_h3",
    "is_valid_h3",
    "knots_to_m_per_s",
    "m_per_s_to_knots",
    "normalize_bearing",
]

__version__ = "0.1.0"
