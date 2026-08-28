"""Einheiten und Winkel.

Einheitenfehler sind die teuerste Sorte stiller Fehler: nichts stuerzt ab, die
Zahlen sehen plausibel aus, und ein Schiff faehrt in der Auswertung doppelt so
schnell wie in Wirklichkeit. Deshalb genau eine Stelle, an der umgerechnet wird.
"""

from __future__ import annotations

import math

# Internationale Seemeile, exakt definiert.
_METERS_PER_NAUTICAL_MILE = 1852.0
_SECONDS_PER_HOUR = 3600.0

# Mittlerer Erdradius nach WGS84 (IUGG). Fuer Grosskreisdistanzen genau genug;
# fuer geodaetische Genauigkeit ist PostGIS zustaendig.
EARTH_RADIUS_M = 6_371_008.8


def knots_to_m_per_s(knots: float) -> float:
    return knots * _METERS_PER_NAUTICAL_MILE / _SECONDS_PER_HOUR


def m_per_s_to_knots(m_per_s: float) -> float:
    return m_per_s * _SECONDS_PER_HOUR / _METERS_PER_NAUTICAL_MILE


def normalize_bearing(degrees: float) -> float:
    """Bringt einen Kurs in [0, 360).

    AIS liefert 360 fuer "nicht verfuegbar" und 511 fuer "nicht gesetzt";
    beide muessen vor dem Speichern zu NULL werden, nicht zu 0 Grad. Diese
    Funktion normalisiert nur - das Erkennen der Sonderwerte gehoert in den
    jeweiligen Konnektor, weil die Werte je Quelle andere sind.
    """
    return degrees % 360.0


def great_circle_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Grosskreisdistanz in Metern (Haversine).

    Fuer Plausibilitaetspruefungen und Vorfilter gedacht: "kann ein Schiff in
    30 Sekunden dort gewesen sein". Exakte Entfernungen kommen aus PostGIS.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))
