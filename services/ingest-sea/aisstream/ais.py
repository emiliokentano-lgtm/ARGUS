"""AIS-Fachwissen: Sentinelwerte, Kennungen, Entschluesselung.

Dieses Modul kennt den AIS-Standard (ITU-R M.1371), aber nicht AISStream und
nicht ARGUS. Es ist die Stelle, an der "1023 bedeutet nicht verfuegbar" steht -
einmal, nicht verstreut in drei Parsern.

DER WICHTIGSTE PUNKT DER GANZEN DATEI
-------------------------------------
AIS hat keine Nullwerte. Jede Groesse hat stattdessen einen Sentinelwert im
gueltigen Wertebereich des Feldes, der "nicht verfuegbar" bedeutet:

    Breite     91      Laenge      181
    SOG        102.3   COG         360.0 (roh 3600)
    Heading    511     Rate of Turn -128

Wer diese Werte nicht abfaengt, bekommt eine Flotte vor der Kueste Ghanas,
Schiffe mit 102 Knoten und einen Bugkurs von 511 Grad. Und wer sie auf 0
abbildet, macht es schlimmer: 0 ist ein gueltiger Kurs, eine gueltige
Geschwindigkeit und - vor Westafrika - eine gueltige Position. Aus "unbekannt"
wird dann "praezise bekannt und falsch".

Deshalb gibt jede clean_*-Funktion hier `None` zurueck und niemals 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# --- Sentinelwerte ---------------------------------------------------------

# Position. AISStream liefert bereits Dezimalgrad; die Sentinelwerte kommen
# unveraendert durch.
LAT_UNAVAILABLE = 91.0
LON_UNAVAILABLE = 181.0

# Speed over ground in Knoten. Roh in 1/10 kn, also 1023; AISStream teilt durch
# zehn. Beide Formen werden abgefangen, weil eine Aenderung an der
# Quellenbibliothek sonst still 102 Knoten schnelle Schiffe erzeugt.
SOG_UNAVAILABLE = 102.3
SOG_UNAVAILABLE_RAW = 1023.0
# Alles ab hier ist fuer ein Schiff physikalisch unmoeglich. Der schnellste
# Serienbau liegt unter 60 kn; Tragflaechenboote erreichen 50.
SOG_MAX_PLAUSIBLE_KN = 80.0

# Course over ground in Grad. Roh in 1/10 Grad, also 3600.
COG_UNAVAILABLE = 360.0
COG_UNAVAILABLE_RAW = 3600.0

# True heading in ganzen Grad. 511 = nicht verfuegbar.
HEADING_UNAVAILABLE = 511

# Rate of turn. -128 = nicht verfuegbar. +-127 = "dreht schneller als
# 5 Grad/30 s", also eine Untergrenze und kein Messwert.
ROT_UNAVAILABLE = -128
ROT_SATURATED = 127

# Tiefgang in 1/10 m, 0 = nicht verfuegbar.
DRAUGHT_UNAVAILABLE = 0.0

# --- AIS-Zeitstempelfeld (Sekunde der UTC-Minute) --------------------------
#
# Das Feld `Timestamp` in den Positionsberichten ist kein Zeitstempel, sondern
# die Sekunde innerhalb der UTC-Minute - mit vier Sonderwerten, die etwas ueber
# die Qualitaet der Position aussagen und nicht ueber ihre Zeit.
TIMESTAMP_NOT_AVAILABLE = 60
TIMESTAMP_MANUAL_INPUT = 61
TIMESTAMP_DEAD_RECKONING = 62
TIMESTAMP_INOPERATIVE = 63


def clean_latitude(value: float | int | None) -> float | None:
    """Breite in Dezimalgrad, oder None.

    Wirft nichts weg ausser dem, was nachweislich keine Position ist: den
    Sentinelwert und alles ausserhalb des gueltigen Bereichs.
    """
    if value is None:
        return None
    lat = float(value)
    if lat == LAT_UNAVAILABLE or not -90.0 <= lat <= 90.0:
        return None
    return lat


def clean_longitude(value: float | int | None) -> float | None:
    if value is None:
        return None
    lon = float(value)
    if lon == LON_UNAVAILABLE or not -180.0 <= lon <= 180.0:
        return None
    return lon


def clean_sog(value: float | int | None) -> float | None:
    """Geschwindigkeit ueber Grund in Knoten, oder None."""
    if value is None:
        return None
    sog = float(value)
    if sog in (SOG_UNAVAILABLE, SOG_UNAVAILABLE_RAW) or sog < 0:
        return None
    # Rohform in 1/10 kn: alles oberhalb des plausiblen Bereichs, das durch
    # zehn geteilt plausibel wird, war eine Zehntelangabe.
    if sog > SOG_MAX_PLAUSIBLE_KN and sog / 10.0 <= SOG_MAX_PLAUSIBLE_KN:
        return sog / 10.0
    return sog


def clean_cog(value: float | int | None) -> float | None:
    """Kurs ueber Grund in Grad, oder None."""
    if value is None:
        return None
    cog = float(value)
    if cog in (COG_UNAVAILABLE, COG_UNAVAILABLE_RAW):
        return None
    # Rohform in 1/10 Grad.
    if cog > 360.0:
        cog = cog / 10.0
        if cog >= 360.0:
            return None
    if not 0.0 <= cog < 360.0:
        return None
    return cog


def clean_heading(value: float | int | None) -> float | None:
    """Bugrichtung in Grad, oder None.

    Anders als COG ist Heading immer ganzzahlig; es gibt keine Zehntelform.
    """
    if value is None:
        return None
    heading = float(value)
    if heading == HEADING_UNAVAILABLE or not 0.0 <= heading < 360.0:
        return None
    return heading


def clean_rate_of_turn(value: float | int | None) -> tuple[float | None, bool]:
    """Drehrate in Grad/Minute und ob der Wert an der Bereichsgrenze klebt.

    Gibt (Wert, gesaettigt) zurueck. Bei +-127 ist die tatsaechliche Drehrate
    hoeher als der gemeldete Wert - das ist eine Untergrenze, keine Messung,
    und die Unterscheidung gehoert in die Qualitaetsangabe.
    """
    if value is None:
        return None, False
    rot = float(value)
    if rot == ROT_UNAVAILABLE:
        return None, False
    if abs(rot) >= ROT_SATURATED:
        return float(ROT_SATURATED if rot > 0 else -ROT_SATURATED), True
    return rot, False


def clean_draught(value: float | int | None) -> float | None:
    """Tiefgang in Metern, oder None. 0 bedeutet 'nicht gemeldet'."""
    if value is None:
        return None
    draught = float(value)
    if draught <= DRAUGHT_UNAVAILABLE:
        return None
    # Rohform in 1/10 m: kein Schiff hat 25 m Tiefgang, aber 25.5 in Zehnteln
    # waeren 2,55 m. Die Grenze liegt beim tiefsten je gebauten Schiff (~25 m).
    if draught > 25.5:
        return draught / 10.0
    return draught


def clean_text(value: str | None) -> str | None:
    """AIS-Text: 6-Bit-ASCII, mit '@' aufgefuellt.

    '@@@@@@@@' ist ein leeres Feld, kein Schiffsname. Auch Felder aus lauter
    Leerzeichen sind leer.
    """
    if value is None:
        return None
    cleaned = value.replace("@", " ").strip()
    return cleaned or None


def position_timestamp_quality(value: int | None) -> tuple[bool, list[str]]:
    """Wertet das AIS-Feld `Timestamp` aus.

    Gibt (ist_koppelnavigation, Qualitaetsmarken) zurueck. Der Wert 62 sagt
    ausdruecklich, dass die Position gerechnet und nicht gemessen ist - eine
    Angabe, fuer die ObservationQuality ein eigenes Feld hat und die man nicht
    verschenken sollte.
    """
    if value is None:
        return False, []
    if value == TIMESTAMP_DEAD_RECKONING:
        return True, ["dead_reckoned"]
    if value == TIMESTAMP_MANUAL_INPUT:
        return False, ["manual_position_input"]
    if value == TIMESTAMP_INOPERATIVE:
        return False, ["positioning_system_inoperative"]
    if value == TIMESTAMP_NOT_AVAILABLE:
        return False, ["position_time_not_available"]
    return False, []


# --- Navigationsstatus (Feld 'NavigationalStatus', Typ 1/2/3) ---------------

NAVIGATIONAL_STATUS: dict[int, str] = {
    0: "under_way_using_engine",
    1: "at_anchor",
    2: "not_under_command",
    3: "restricted_manoeuverability",
    4: "constrained_by_draught",
    5: "moored",
    6: "aground",
    7: "engaged_in_fishing",
    8: "under_way_sailing",
    9: "reserved_hsc",
    10: "reserved_wig",
    11: "power_driven_vessel_towing_astern",
    12: "power_driven_vessel_pushing_ahead",
    13: "reserved",
    14: "ais_sart_mob_epirb",
    15: "undefined",
}


def navigational_status(value: int | None) -> str | None:
    """Klartextname des Navigationsstatus.

    15 ('undefined') ist der Standardwert vieler Transponder und wird wie
    'nicht gemeldet' behandelt - er traegt keine Information.
    """
    if value is None or value == 15:
        return None
    return NAVIGATIONAL_STATUS.get(value)


# --- Schiffstyp (Feld 'Type', Typ 5/19/24B) --------------------------------

_SHIP_TYPE_GROUPS: dict[int, str] = {
    2: "wing_in_ground",
    3: "special",  # 30 Fischerei, 31/32 Schlepper, 33 Baggerarbeiten, ...
    4: "high_speed_craft",
    5: "special",  # 50 Lotse, 51 SAR, 52 Schlepper, 53 Hafentender, ...
    6: "passenger",
    7: "cargo",
    8: "tanker",
    9: "other",
}

# Einzelcodes, die aus ihrer Zehnergruppe herausfallen und im Lagebild
# tatsaechlich unterschieden werden muessen.
_SHIP_TYPE_SPECIFIC: dict[int, str] = {
    30: "fishing",
    31: "towing",
    32: "towing_long",
    33: "dredging",
    34: "diving_ops",
    35: "military_ops",
    36: "sailing",
    37: "pleasure_craft",
    50: "pilot_vessel",
    51: "search_and_rescue",
    52: "tug",
    53: "port_tender",
    54: "anti_pollution",
    55: "law_enforcement",
    58: "medical_transport",
    59: "non_combatant",
}


def ship_type(value: int | None) -> tuple[str | None, int | None]:
    """Schiffstyp als (Gruppe, Rohcode).

    Der Rohcode bleibt erhalten: die Gruppierung ist eine Vereinfachung fuer
    die Darstellung, und ein Konnektor darf Information nicht wegwerfen, nur
    weil er sie gerade nicht braucht.
    """
    if value is None or not 0 < value < 100:
        return None, None
    specific = _SHIP_TYPE_SPECIFIC.get(value)
    if specific:
        return specific, value
    return _SHIP_TYPE_GROUPS.get(value // 10), value


# --- Navigationshilfen (Feld 'Type', Typ 21) -------------------------------

_ATON_TYPES: dict[int, str] = {
    0: "not_specified",
    1: "reference_point",
    2: "racon",
    3: "fixed_structure",
    4: "emergency_wreck_marking_buoy",
    5: "light_without_sectors",
    6: "light_with_sectors",
    9: "beacon_cardinal_n",
    14: "beacon_port_hand",
    15: "beacon_starboard_hand",
    20: "cardinal_mark_n",
    21: "cardinal_mark_e",
    22: "cardinal_mark_s",
    23: "cardinal_mark_w",
    24: "port_hand_mark",
    25: "starboard_hand_mark",
    26: "preferred_channel_port_hand",
    27: "preferred_channel_starboard_hand",
    28: "isolated_danger",
    29: "safe_water",
    30: "special_mark",
    31: "light_vessel_lanby_rigs",
}


def aton_type(value: int | None) -> tuple[str | None, int | None]:
    if value is None:
        return None, None
    return _ATON_TYPES.get(value, "other"), value


# --- Abmessungen -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Dimensions:
    """Schiffsabmessungen aus den vier AIS-Referenzabstaenden.

    A/B sind die Abstaende der Antenne nach vorn und achtern, C/D nach
    backbord und steuerbord. Laenge und Breite ergeben sich daraus; die
    Antennenposition selbst ist die Grundlage fuer den Versatz zwischen
    gemeldeter Position und Schiffsmittelpunkt.
    """

    length_m: float | None
    beam_m: float | None
    to_bow_m: int | None
    to_stern_m: int | None
    to_port_m: int | None
    to_starboard_m: int | None


def dimensions(raw: dict[str, Any] | None) -> Dimensions | None:
    """Liest den Dimension-Block. Alles 0 bedeutet 'nicht gemeldet'."""
    if not isinstance(raw, dict):
        return None
    a, b, c, d = (raw.get(k) for k in ("A", "B", "C", "D"))
    values = [v for v in (a, b, c, d) if isinstance(v, int | float)]
    if not values or all(v == 0 for v in values):
        return None
    length = (a + b) if isinstance(a, int | float) and isinstance(b, int | float) else None
    beam = (c + d) if isinstance(c, int | float) and isinstance(d, int | float) else None
    return Dimensions(
        length_m=float(length) if length else None,
        beam_m=float(beam) if beam else None,
        to_bow_m=int(a) if isinstance(a, int | float) else None,
        to_stern_m=int(b) if isinstance(b, int | float) else None,
        to_port_m=int(c) if isinstance(c, int | float) else None,
        to_starboard_m=int(d) if isinstance(d, int | float) else None,
    )


# --- Kennungen -------------------------------------------------------------


def is_valid_mmsi(value: int | None) -> bool:
    """Neunstellige MMSI. Fuehrende Null ist zulaessig (Kuestenstationen)."""
    return isinstance(value, int) and 0 < value <= 999_999_999


def mmsi_category(mmsi: int) -> str:
    """Was fuer ein Sender ist das?

    Die MMSI kodiert ihre eigene Art in den fuehrenden Ziffern. Das ist
    wichtig, weil eine Navigationshilfe (99...) und ein Suchflugzeug (111...)
    keine Schiffe sind und im Lagebild nicht als solche erscheinen duerfen -
    auch dann nicht, wenn sie ueber dieselbe Leitung kommen.
    """
    text = f"{mmsi:09d}"
    if text.startswith("00"):
        return "coast_station"
    if text.startswith("0"):
        return "group"
    if text.startswith("111"):
        return "sar_aircraft"
    if text.startswith("99"):
        return "aid_to_navigation"
    if text.startswith("98"):
        return "auxiliary_craft"
    if text.startswith("970"):
        return "ais_sart"
    if text.startswith("972"):
        return "man_overboard"
    if text.startswith("974"):
        return "epirb"
    return "vessel"


def mmsi_mid(mmsi: int) -> int | None:
    """Maritime Identification Digits - die drei Ziffern der Flaggenzuordnung.

    Bewusst ohne Landkarte: eine unvollstaendige MID-Tabelle liefert fuer nicht
    gelistete Flaggen still das Falsche. Die Zuordnung MID -> Land gehoert in
    ein gepflegtes Register, nicht in einen Konnektor.
    """
    text = f"{mmsi:09d}"
    category = mmsi_category(mmsi)
    if category in ("coast_station", "group"):
        offset = 2 if category == "coast_station" else 1
        return int(text[offset : offset + 3])
    if category == "vessel":
        return int(text[:3])
    return None


def is_valid_imo(value: int | None) -> bool:
    """IMO-Nummer mit Pruefziffer.

    Der Grund fuer diese Funktion steht in ADR 0005: eine IMO-Nummer kann in
    einer Quelle schlicht falsch sein. Sieben Stellen, die letzte ist die
    Pruefziffer: Summe aus Ziffer_i * (8 - i) fuer i = 1..6, modulo 10.

    AIS-Typ 5 liefert haeufig 0 (nicht gemeldet) oder die MMSI im IMO-Feld -
    beides scheitert an der Pruefung, und genau dafuer ist sie da.
    """
    if not isinstance(value, int) or not 1_000_000 <= value <= 9_999_999:
        return False
    digits = [int(c) for c in str(value)]
    checksum = sum(digit * (7 - index) for index, digit in enumerate(digits[:6]))
    return checksum % 10 == digits[6]
