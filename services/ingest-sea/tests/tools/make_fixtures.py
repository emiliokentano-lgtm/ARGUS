"""Erzeugt die eingefrorenen AISStream-Fixtures.

HERKUNFT DER DATEN - BITTE LESEN
--------------------------------
Diese Nachrichten sind NICHT vom Live-Feed mitgeschnitten. Sie sind nach der
Drahtform von AISStream.io und nach ITU-R M.1371 erzeugt: Feldnamen,
Datentypen, Wertebereiche und Sentinelwerte entsprechen dem, was der Dienst
liefert; die Schiffe und ihre Fahrten sind erfunden.

Der Grund ist unspektakulaer: der Mitschnitt braucht einen API-Schluessel und
eine Verbindung zu aisstream.io, und beides gibt es in dieser Umgebung nicht.
Was daraus folgt, steht in der README neben den Fixtures - und zwar so, dass
niemand sie versehentlich fuer echte Beobachtungen haelt.

Deterministisch ueber einen festen Startwert: derselbe Aufruf erzeugt
dieselbe Datei. Sonst waere jeder Lauf ein Diff.

    python tests/tools/make_fixtures.py
"""

from __future__ import annotations

import json
import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "aisstream"
SEED = 20260829
# Fester Startzeitpunkt: die Fixtures duerfen nicht altern.
START = datetime(2026, 8, 28, 9, 0, 0, tzinfo=UTC)


def go_time(moment: datetime) -> str:
    """Zeitformat der Go-Standardbibliothek, wie AISStream es sendet."""
    return (
        moment.strftime("%Y-%m-%d %H:%M:%S.") + f"{moment.microsecond // 10000:02d}" + " +0000 UTC"
    )


class Vessel:
    """Ein erfundenes Schiff auf einer Grosskreisfahrt."""

    def __init__(
        self,
        *,
        mmsi: int,
        name: str,
        imo: int | None,
        call_sign: str,
        ship_type: int,
        lat: float,
        lon: float,
        course: float,
        speed_kn: float,
        length: int,
        beam: int,
        draught: float,
        destination: str,
        class_b: bool = False,
    ) -> None:
        self.mmsi = mmsi
        self.name = name
        self.imo = imo
        self.call_sign = call_sign
        self.ship_type = ship_type
        self.lat = lat
        self.lon = lon
        self.course = course
        self.speed_kn = speed_kn
        self.length = length
        self.beam = beam
        self.draught = draught
        self.destination = destination
        self.class_b = class_b

    def advance(self, seconds: float, rng: random.Random) -> None:
        """Bewegt das Schiff. Kurs und Fahrt schwanken leicht, wie im Leben."""
        self.course = (self.course + rng.uniform(-1.5, 1.5)) % 360.0
        self.speed_kn = max(0.0, self.speed_kn + rng.uniform(-0.3, 0.3))
        distance_nm = self.speed_kn * seconds / 3600.0
        bearing = math.radians(self.course)
        self.lat += (distance_nm / 60.0) * math.cos(bearing)
        self.lon += (
            (distance_nm / 60.0) * math.sin(bearing) / max(0.01, math.cos(math.radians(self.lat)))
        )
        self.lat = max(-89.9, min(89.9, self.lat))
        self.lon = ((self.lon + 180.0) % 360.0) - 180.0


def _fleet() -> list[Vessel]:
    """Gemischte Flotte: Deutsche Bucht, Elbe, Strasse von Hormus.

    Die IMO-Nummern sind so gewaehlt, dass ihre Pruefziffer stimmt - sonst
    laeuft der Konnektor beim Test ueber jedes Schiff in den Zweig
    'invalid_imo_checksum' und der Testfall dafuer waere wertlos.
    """
    return [
        Vessel(
            mmsi=211331640,
            name="MUENSTERLAND",
            imo=9074729,
            call_sign="DHBQ",
            ship_type=70,
            lat=53.9012,
            lon=8.1043,
            course=118.0,
            speed_kn=12.4,
            length=180,
            beam=28,
            draught=8.6,
            destination="DEHAM",
        ),
        Vessel(
            mmsi=244660123,
            name="STAD AMSTERDAM",
            imo=9811000,
            call_sign="PBSA",
            ship_type=37,
            lat=53.6440,
            lon=6.9210,
            course=270.0,
            speed_kn=8.1,
            length=78,
            beam=11,
            draught=4.9,
            destination="NLRTM",
        ),
        Vessel(
            mmsi=636019234,
            name="ATLANTIC PIONEER",
            imo=9432268,
            call_sign="A8XY4",
            ship_type=80,
            lat=26.4531,
            lon=56.3902,
            course=145.0,
            speed_kn=13.8,
            length=333,
            beam=60,
            draught=20.4,
            destination="AEJEA",
        ),
        Vessel(
            mmsi=477553000,
            name="EASTERN GLORY",
            imo=9285122,
            call_sign="VRQF7",
            ship_type=71,
            lat=25.9412,
            lon=56.2603,
            course=310.0,
            speed_kn=11.2,
            length=294,
            beam=32,
            draught=12.1,
            destination="SGSIN",
        ),
        Vessel(
            mmsi=265512340,
            name="NORDIC TRADER",
            imo=9210945,
            call_sign="SLMK",
            ship_type=79,
            lat=54.1877,
            lon=7.8801,
            course=45.0,
            speed_kn=9.6,
            length=142,
            beam=21,
            draught=6.8,
            destination="SEGOT",
        ),
        Vessel(
            mmsi=232009876,
            name="AURORA STAR",
            imo=9166962,
            call_sign="MDPQ3",
            ship_type=60,
            lat=53.5307,
            lon=8.5710,
            course=200.0,
            speed_kn=17.3,
            length=195,
            beam=27,
            draught=6.2,
            destination="GBHUL",
        ),
        Vessel(
            mmsi=211778990,
            name="ELBE 3",
            imo=None,
            call_sign="DFAQ",
            ship_type=52,
            lat=53.8720,
            lon=8.7104,
            course=95.0,
            speed_kn=6.4,
            length=32,
            beam=10,
            draught=3.9,
            destination="DEBRV",
        ),
        Vessel(
            mmsi=246330111,
            name="ZEEHOND",
            imo=None,
            call_sign="PCXY",
            ship_type=30,
            lat=53.4401,
            lon=6.2007,
            course=15.0,
            speed_kn=4.2,
            length=24,
            beam=7,
            draught=2.4,
            destination="FISHING",
            class_b=True,
        ),
        Vessel(
            mmsi=211220334,
            name="SEEBAER",
            imo=None,
            call_sign="DGAX",
            ship_type=36,
            lat=54.0210,
            lon=8.3390,
            course=180.0,
            speed_kn=5.5,
            length=14,
            beam=4,
            draught=1.8,
            destination="",
            class_b=True,
        ),
        Vessel(
            mmsi=470119988,
            name="GULF FALCON",
            imo=9407598,
            call_sign="A6EQ2",
            ship_type=89,
            lat=26.1120,
            lon=56.1440,
            course=330.0,
            speed_kn=10.9,
            length=110,
            beam=18,
            draught=7.1,
            destination="AEDXB",
        ),
        Vessel(
            mmsi=311043900,
            name="ISLAND MERCHANT",
            imo=9337729,
            call_sign="C6BQ8",
            ship_type=70,
            lat=53.7011,
            lon=7.4508,
            course=88.0,
            speed_kn=14.7,
            length=225,
            beam=32,
            draught=11.3,
            destination="DEWVN",
        ),
        Vessel(
            mmsi=257889012,
            name="FJORD LINK",
            imo=9243069,
            call_sign="LADG5",
            ship_type=61,
            lat=54.3312,
            lon=8.0022,
            course=355.0,
            speed_kn=15.9,
            length=163,
            beam=25,
            draught=5.7,
            destination="NOOSL",
        ),
    ]


def _aids() -> list[dict[str, Any]]:
    """Navigationshilfen (Typ 21). Eine davon virtuell, eine off position."""
    return [
        {
            "mmsi": 992111840,
            "name": "ELBE APPROACH",
            "type": 30,
            "lat": 53.9950,
            "lon": 8.1080,
            "virtual": False,
            "off": False,
        },
        {
            "mmsi": 992111841,
            "name": "GB 1",
            "type": 24,
            "lat": 53.9101,
            "lon": 8.2240,
            "virtual": False,
            "off": True,
        },
        {
            "mmsi": 992476015,
            "name": "HORMUZ TSS WEST",
            "type": 31,
            "lat": 26.5501,
            "lon": 56.4402,
            "virtual": True,
            "off": False,
        },
        {
            "mmsi": 992351099,
            "name": "WRECK SEEADLER",
            "type": 4,
            "lat": 54.0455,
            "lon": 7.9912,
            "virtual": False,
            "off": False,
        },
    ]


def _metadata(vessel_mmsi: int, name: str, lat: float, lon: float, moment: datetime) -> dict:
    return {
        "MMSI": vessel_mmsi,
        "MMSI_String": vessel_mmsi,
        "ShipName": name,
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "time_utc": go_time(moment),
    }


def position_report(vessel: Vessel, moment: datetime, rng: random.Random) -> dict:
    """Typ 1/2/3. Enthaelt mit Absicht gelegentlich Sentinelwerte."""
    heading = 511 if rng.random() < 0.12 else int(vessel.course) % 360
    cog = 360.0 if rng.random() < 0.04 else round(vessel.course, 1)
    sog = 102.3 if rng.random() < 0.02 else round(vessel.speed_kn, 1)
    return {
        "MessageType": "PositionReport",
        "MetaData": _metadata(vessel.mmsi, vessel.name, vessel.lat, vessel.lon, moment),
        "Message": {
            "PositionReport": {
                "MessageID": rng.choice([1, 1, 1, 2, 3]),
                "RepeatIndicator": 0,
                "UserID": vessel.mmsi,
                "Valid": True,
                "NavigationalStatus": 0 if vessel.speed_kn > 0.5 else rng.choice([1, 5]),
                "RateOfTurn": rng.choice([0, 0, 0, -128, 12, -9, 127]),
                "Sog": sog,
                "PositionAccuracy": rng.random() < 0.7,
                "Longitude": round(vessel.lon, 6),
                "Latitude": round(vessel.lat, 6),
                "Cog": cog,
                "TrueHeading": heading,
                "Timestamp": rng.choice([*range(60), 60, 61, 62, 63]),
                "SpecialManoeuvreIndicator": 0,
                "Spare": 0,
                "Raim": False,
                "CommunicationState": rng.randrange(0, 524288),
            }
        },
    }


def ship_static_data(vessel: Vessel, moment: datetime, rng: random.Random) -> dict:
    """Typ 5. Bei Schiffen ohne IMO steht dort eine 0 - wie im echten Feed."""
    eta = moment + timedelta(hours=rng.randrange(4, 72))
    return {
        "MessageType": "ShipStaticData",
        "MetaData": _metadata(vessel.mmsi, vessel.name, vessel.lat, vessel.lon, moment),
        "Message": {
            "ShipStaticData": {
                "MessageID": 5,
                "RepeatIndicator": 0,
                "UserID": vessel.mmsi,
                "Valid": True,
                "AisVersion": 2,
                "ImoNumber": vessel.imo or 0,
                "CallSign": vessel.call_sign,
                "Name": vessel.name,
                "Type": vessel.ship_type,
                "Dimension": {
                    "A": vessel.length - vessel.length // 4,
                    "B": vessel.length // 4,
                    "C": vessel.beam // 2,
                    "D": vessel.beam - vessel.beam // 2,
                },
                "FixType": 1,
                "Eta": {"Month": eta.month, "Day": eta.day, "Hour": eta.hour, "Minute": eta.minute},
                "MaximumStaticDraught": vessel.draught,
                "Destination": vessel.destination,
                "Dte": False,
                "Spare": False,
            }
        },
    }


def class_b_position(vessel: Vessel, moment: datetime, rng: random.Random) -> dict:
    """Typ 18. Kein Navigationsstatus - Klasse B kennt ihn nicht."""
    return {
        "MessageType": "StandardClassBPositionReport",
        "MetaData": _metadata(vessel.mmsi, vessel.name, vessel.lat, vessel.lon, moment),
        "Message": {
            "StandardClassBPositionReport": {
                "MessageID": 18,
                "RepeatIndicator": 0,
                "UserID": vessel.mmsi,
                "Valid": True,
                "Spare1": 0,
                "Sog": round(vessel.speed_kn, 1),
                "PositionAccuracy": rng.random() < 0.5,
                "Longitude": round(vessel.lon, 6),
                "Latitude": round(vessel.lat, 6),
                "Cog": round(vessel.course, 1),
                "TrueHeading": 511,
                "Timestamp": rng.randrange(0, 60),
                "Spare2": 0,
                "ClassBUnit": True,
                "ClassBDisplay": False,
                "ClassBDsc": True,
                "ClassBBand": True,
                "ClassBMsg22": True,
                "AssignedMode": False,
                "Raim": True,
                "CommunicationStateIsItdma": True,
                "CommunicationState": 393222,
            }
        },
    }


def extended_class_b(vessel: Vessel, moment: datetime, rng: random.Random) -> dict:
    """Typ 19: Position UND Stammdaten in einer Nachricht."""
    return {
        "MessageType": "ExtendedClassBPositionReport",
        "MetaData": _metadata(vessel.mmsi, vessel.name, vessel.lat, vessel.lon, moment),
        "Message": {
            "ExtendedClassBPositionReport": {
                "MessageID": 19,
                "RepeatIndicator": 0,
                "UserID": vessel.mmsi,
                "Valid": True,
                "Spare1": 0,
                "Sog": round(vessel.speed_kn, 1),
                "PositionAccuracy": True,
                "Longitude": round(vessel.lon, 6),
                "Latitude": round(vessel.lat, 6),
                "Cog": round(vessel.course, 1),
                "TrueHeading": int(vessel.course) % 360,
                "Timestamp": rng.randrange(0, 60),
                "Spare2": 0,
                "Name": vessel.name,
                "Type": vessel.ship_type,
                "Dimension": {
                    "A": vessel.length // 2,
                    "B": vessel.length // 2,
                    "C": vessel.beam // 2,
                    "D": vessel.beam // 2,
                },
                "FixType": 1,
                "Raim": False,
                "Dte": False,
                "AssignedMode": False,
                "Spare3": 0,
            }
        },
    }


def static_data_report(vessel: Vessel, moment: datetime, part: int) -> dict:
    """Typ 24. Zwei Haelften, die getrennt gesendet werden."""
    if part == 0:
        report = {
            "PartNumber": 0,
            "ReportA": {"Valid": True, "Name": vessel.name},
            "ReportB": {"Valid": False},
        }
    else:
        report = {
            "PartNumber": 1,
            "ReportA": {"Valid": False},
            "ReportB": {
                "Valid": True,
                "ShipType": vessel.ship_type,
                "VendorIDName": "SRT",
                "VendorIDModel": 3,
                "VendorIDSerial": 148021,
                "CallSign": vessel.call_sign,
                "Dimension": {
                    "A": vessel.length // 2,
                    "B": vessel.length // 2,
                    "C": vessel.beam // 2,
                    "D": vessel.beam // 2,
                },
                "FixType": 1,
                "Spare": 0,
            },
        }
    return {
        "MessageType": "StaticDataReport",
        "MetaData": _metadata(vessel.mmsi, vessel.name, vessel.lat, vessel.lon, moment),
        "Message": {
            "StaticDataReport": {
                "MessageID": 24,
                "RepeatIndicator": 0,
                "UserID": vessel.mmsi,
                "Valid": True,
                "Spare1": 0,
                **report,
            }
        },
    }


def aton_report(aid: dict[str, Any], moment: datetime, rng: random.Random) -> dict:
    return {
        "MessageType": "AidsToNavigationReport",
        "MetaData": _metadata(aid["mmsi"], aid["name"], aid["lat"], aid["lon"], moment),
        "Message": {
            "AidsToNavigationReport": {
                "MessageID": 21,
                "RepeatIndicator": 0,
                "UserID": aid["mmsi"],
                "Valid": True,
                "Type": aid["type"],
                "Name": aid["name"],
                "PositionAccuracy": True,
                "Longitude": round(aid["lon"], 6),
                "Latitude": round(aid["lat"], 6),
                "Dimension": {"A": 4, "B": 4, "C": 4, "D": 4},
                "Fixtype": 7 if aid["virtual"] else 1,
                "Timestamp": rng.randrange(0, 60),
                "OffPosition": aid["off"],
                "AtonStatus": 0,
                "Raim": False,
                "VirtualAtoN": aid["virtual"],
                "AssignedMode": False,
                "Spare": 0,
                "NameExtension": "",
            }
        },
    }


def unsupported(moment: datetime, rng: random.Random) -> dict:
    """Typen, die AISStream liefert und dieser Konnektor nicht uebersetzt.

    Sie gehoeren in die Fixtures, weil der Ueberspringpfad sonst nie mit
    echten Daten laeuft - und weil sie im Feed tatsaechlich vorkommen.
    """
    message_type = rng.choice(
        [
            "BaseStationReport",
            "BinaryBroadcastMessage",
            "SafetyBroadcastMessage",
            "DataLinkManagementMessage",
            "LongRangeAisBroadcastMessage",
        ]
    )
    mmsi = rng.choice([2111234, 992111840, 211331640])
    return {
        "MessageType": message_type,
        "MetaData": _metadata(mmsi, "", 53.5, 8.1, moment),
        "Message": {message_type: {"MessageID": 4, "UserID": mmsi, "Valid": True}},
    }


def build_stream() -> list[dict[str, Any]]:
    """Der Hauptbestand: eine gemischte Viertelstunde ueber drei Seegebiete.

    Die Uhr und die Bewegung muessen zusammenpassen: wer die Schiffe um 20
    Sekunden Fahrt versetzt, die Zeitstempel aber nur um Millisekunden
    weiterdreht, erzeugt eine Flotte, die sich mit dem Zehnfachen ihrer
    gemeldeten Fahrt bewegt - und einen Sprungtest, der bei jedem zweiten
    Schiff anschlaegt. Deshalb ist ROUND_INTERVAL_S die einzige Quelle fuer
    beides.
    """
    round_interval_s = 10.0
    rng = random.Random(SEED)
    fleet = _fleet()
    aids = _aids()
    messages: list[dict[str, Any]] = []

    for round_index in range(46):
        round_start = START + timedelta(seconds=round_index * round_interval_s)
        offset_ms = 0

        # round_start als Vorgabewert gebunden: eine Closure ueber die
        # Schleifenvariable wuerde beim naechsten Durchlauf mitwandern.
        def stamp(round_start: datetime = round_start) -> datetime:
            # Die Nachrichten einer Runde verteilen sich ueber die Runde,
            # ueberholen sie aber nicht.
            nonlocal offset_ms
            offset_ms += rng.randrange(40, 180)
            return round_start + timedelta(milliseconds=min(offset_ms, 9_500))

        for vessel in fleet:
            vessel.advance(round_interval_s, rng)
            moment = stamp()
            if vessel.class_b:
                messages.append(
                    extended_class_b(vessel, moment, rng)
                    if round_index % 9 == 4
                    else class_b_position(vessel, moment, rng)
                )
            else:
                messages.append(position_report(vessel, moment, rng))

        if round_index % 6 == 2:
            for vessel in fleet[: 4 if round_index % 12 == 2 else 2]:
                messages.append(ship_static_data(vessel, stamp(), rng))

        if round_index % 7 == 3:
            for vessel in (v for v in fleet if v.class_b):
                for part in (0, 1):
                    messages.append(static_data_report(vessel, stamp(), part))

        if round_index % 5 == 1:
            for aid in aids:
                messages.append(aton_report(aid, stamp(), rng))

        if round_index % 4 == 0:
            messages.append(unsupported(stamp(), rng))

    return messages


def build_edge_cases() -> list[dict[str, Any]]:
    """Die Faelle, auf die es ankommt - jeder mit einer Beschreibung.

    Der Schluessel `_case` ist Dokumentation und nicht Teil der Drahtform; die
    Tests entfernen ihn, bevor sie parsen.
    """
    moment = datetime(2026, 8, 28, 9, 30, 0, tzinfo=UTC)
    base_meta = _metadata(211331640, "MUENSTERLAND", 53.9, 8.1, moment)

    def envelope(case: str, message_type: str, body: dict, meta: dict | None = None) -> dict:
        return {
            "_case": case,
            "MessageType": message_type,
            "MetaData": meta or dict(base_meta),
            "Message": {message_type: body},
        }

    position_base = {
        "MessageID": 1,
        "RepeatIndicator": 0,
        "UserID": 211331640,
        "Valid": True,
        "NavigationalStatus": 0,
        "RateOfTurn": 0,
        "Sog": 11.2,
        "PositionAccuracy": True,
        "Longitude": 8.1,
        "Latitude": 53.9,
        "Cog": 118.4,
        "TrueHeading": 121,
        "Timestamp": 30,
        "SpecialManoeuvreIndicator": 0,
        "Spare": 0,
        "Raim": False,
        "CommunicationState": 2148,
    }

    cases: list[dict[str, Any]] = [
        envelope(
            "Position nicht verfuegbar: Lat 91 / Lon 181 sind AIS-Sentinelwerte "
            "und duerfen nicht als 0/0 erscheinen.",
            "PositionReport",
            {**position_base, "Latitude": 91.0, "Longitude": 181.0},
        ),
        envelope(
            "Heading 511 und COG 360 bedeuten 'nicht verfuegbar' - beide muessen "
            "zu null werden, nicht zu 0 Grad.",
            "PositionReport",
            {**position_base, "TrueHeading": 511, "Cog": 360.0},
        ),
        envelope(
            "COG in Rohform (1/10 Grad): 3600 ist derselbe Sentinelwert wie 360.",
            "PositionReport",
            {**position_base, "Cog": 3600.0},
        ),
        envelope(
            "SOG 102.3 = nicht verfuegbar.",
            "PositionReport",
            {**position_base, "Sog": 102.3},
        ),
        envelope(
            "Rate of Turn -128 = nicht verfuegbar, +127 = gesaettigt (Untergrenze).",
            "PositionReport",
            {**position_base, "RateOfTurn": -128},
        ),
        envelope(
            "Rate of Turn am Anschlag: der wahre Wert ist hoeher als gemeldet.",
            "PositionReport",
            {**position_base, "RateOfTurn": 127},
        ),
        envelope(
            "Timestamp 62: die Position ist gekoppelt, nicht gemessen.",
            "PositionReport",
            {**position_base, "Timestamp": 62},
        ),
        envelope(
            "Timestamp 63: Positionssystem ausser Betrieb.",
            "PositionReport",
            {**position_base, "Timestamp": 63},
        ),
        envelope(
            "Null Island: formal gueltig, praktisch immer ein Transponder ohne Fix.",
            "PositionReport",
            {**position_base, "Latitude": 0.0, "Longitude": 0.0},
        ),
        envelope(
            "Zeitstempel in der Zukunft. Wird markiert, nicht korrigiert.",
            "PositionReport",
            position_base,
            {**base_meta, "time_utc": go_time(moment + timedelta(days=400))},
        ),
        envelope(
            "Zeitstempel unlesbar. Die Position bleibt trotzdem etwas wert.",
            "PositionReport",
            position_base,
            {**base_meta, "time_utc": "nicht-ein-zeitstempel"},
        ),
        envelope(
            "Positionssprung: dasselbe Schiff 2000 Seemeilen weiter, eine Sekunde "
            "spaeter. Zwei Sender mit derselben MMSI oder ein Bitfehler.",
            "PositionReport",
            {**position_base, "Latitude": 25.9, "Longitude": 56.2},
            {**base_meta, "time_utc": go_time(moment + timedelta(seconds=1))},
        ),
        envelope(
            "IMO-Nummer mit falscher Pruefziffer. Wird nicht als Kennung uebernommen.",
            "ShipStaticData",
            {
                "MessageID": 5,
                "RepeatIndicator": 0,
                "UserID": 211331640,
                "Valid": True,
                "AisVersion": 2,
                "ImoNumber": 1234568,
                "CallSign": "DHBQ",
                "Name": "MUENSTERLAND",
                "Type": 70,
                "Dimension": {"A": 135, "B": 45, "C": 14, "D": 14},
                "FixType": 1,
                "Eta": {"Month": 8, "Day": 29, "Hour": 6, "Minute": 30},
                "MaximumStaticDraught": 8.6,
                "Destination": "DEHAM",
                "Dte": False,
                "Spare": False,
            },
        ),
        envelope(
            "IMO-Feld traegt die MMSI - haeufiger Konfigurationsfehler an Bord.",
            "ShipStaticData",
            {
                "MessageID": 5,
                "RepeatIndicator": 0,
                "UserID": 211331640,
                "Valid": True,
                "AisVersion": 2,
                "ImoNumber": 211331640,
                "CallSign": "DHBQ",
                "Name": "MUENSTERLAND",
                "Type": 70,
                "Dimension": {"A": 135, "B": 45, "C": 14, "D": 14},
                "FixType": 1,
                "Eta": {"Month": 8, "Day": 29, "Hour": 6, "Minute": 30},
                "MaximumStaticDraught": 8.6,
                "Destination": "DEHAM",
                "Dte": False,
                "Spare": False,
            },
        ),
        envelope(
            "Leere Textfelder: AIS fuellt mit '@' auf. '@@@@@@@' ist kein Name.",
            "ShipStaticData",
            {
                "MessageID": 5,
                "RepeatIndicator": 0,
                "UserID": 211331640,
                "Valid": True,
                "AisVersion": 2,
                "ImoNumber": 0,
                "CallSign": "@@@@@@@",
                "Name": "@@@@@@@@@@@@@@@@@@@@",
                "Type": 0,
                "Dimension": {"A": 0, "B": 0, "C": 0, "D": 0},
                "FixType": 0,
                "Eta": {"Month": 0, "Day": 0, "Hour": 24, "Minute": 60},
                "MaximumStaticDraught": 0.0,
                "Destination": "@@@@@@@@@@@@@@@@@@@@",
                "Dte": True,
                "Spare": False,
            },
        ),
        envelope(
            "Navigationshilfe: kein Schiff. Muss als FACILITY erscheinen.",
            "AidsToNavigationReport",
            {
                "MessageID": 21,
                "RepeatIndicator": 0,
                "UserID": 992111840,
                "Valid": True,
                "Type": 30,
                "Name": "ELBE APPROACH",
                "PositionAccuracy": True,
                "Longitude": 8.108,
                "Latitude": 53.995,
                "Dimension": {"A": 4, "B": 4, "C": 4, "D": 4},
                "Fixtype": 1,
                "Timestamp": 30,
                "OffPosition": False,
                "AtonStatus": 0,
                "Raim": False,
                "VirtualAtoN": False,
                "AssignedMode": False,
                "Spare": 0,
                "NameExtension": "",
            },
            _metadata(992111840, "ELBE APPROACH", 53.995, 8.108, moment),
        ),
        envelope(
            "Virtuelle Navigationshilfe: existiert physisch nicht.",
            "AidsToNavigationReport",
            {
                "MessageID": 21,
                "RepeatIndicator": 0,
                "UserID": 992476015,
                "Valid": True,
                "Type": 31,
                "Name": "HORMUZ TSS WEST",
                "PositionAccuracy": True,
                "Longitude": 56.4402,
                "Latitude": 26.5501,
                "Dimension": {"A": 0, "B": 0, "C": 0, "D": 0},
                "Fixtype": 7,
                "Timestamp": 30,
                "OffPosition": False,
                "AtonStatus": 0,
                "Raim": False,
                "VirtualAtoN": True,
                "AssignedMode": False,
                "Spare": 0,
                "NameExtension": "",
            },
            _metadata(992476015, "HORMUZ TSS WEST", 26.5501, 56.4402, moment),
        ),
        envelope(
            "SAR-Flugzeug (MMSI 111...): kein Schiff, sondern ein Luftfahrzeug.",
            "PositionReport",
            {**position_base, "UserID": 111232500, "Sog": 96.0},
            _metadata(111232500, "RESCUE 51", 54.1, 7.9, moment),
        ),
        envelope(
            "Typ 24 Teil A: nur der Name, sonst nichts.",
            "StaticDataReport",
            {
                "MessageID": 24,
                "RepeatIndicator": 0,
                "UserID": 246330111,
                "Valid": True,
                "Spare1": 0,
                "PartNumber": 0,
                "ReportA": {"Valid": True, "Name": "ZEEHOND"},
                "ReportB": {"Valid": False},
            },
            _metadata(246330111, "ZEEHOND", 53.44, 6.2, moment),
        ),
        envelope(
            "Typ 24 Teil B: Rufzeichen und Typ, aber kein Name.",
            "StaticDataReport",
            {
                "MessageID": 24,
                "RepeatIndicator": 0,
                "UserID": 246330111,
                "Valid": True,
                "Spare1": 0,
                "PartNumber": 1,
                "ReportA": {"Valid": False},
                "ReportB": {
                    "Valid": True,
                    "ShipType": 30,
                    "VendorIDName": "SRT",
                    "VendorIDModel": 3,
                    "VendorIDSerial": 148021,
                    "CallSign": "PCXY",
                    "Dimension": {"A": 12, "B": 12, "C": 3, "D": 4},
                    "FixType": 1,
                    "Spare": 0,
                },
            },
            _metadata(246330111, "", 53.44, 6.2, moment),
        ),
        envelope(
            "MetaData nennt einen anderen Namen als der AIS-Satz. Der Satz gewinnt, "
            "der andere bleibt als frueherer Name erhalten.",
            "ShipStaticData",
            {
                "MessageID": 5,
                "RepeatIndicator": 0,
                "UserID": 477553000,
                "Valid": True,
                "AisVersion": 2,
                "ImoNumber": 9285122,
                "CallSign": "VRQF7",
                "Name": "EASTERN GLORY",
                "Type": 71,
                "Dimension": {"A": 220, "B": 74, "C": 16, "D": 16},
                "FixType": 1,
                "Eta": {"Month": 9, "Day": 2, "Hour": 14, "Minute": 0},
                "MaximumStaticDraught": 12.1,
                "Destination": "SGSIN",
                "Dte": False,
                "Spare": False,
            },
            _metadata(477553000, "PACIFIC GLORY", 25.94, 56.26, moment),
        ),
        envelope(
            "Tiefgang in Rohform (1/10 m): 121 sind 12,1 m, nicht 121 m.",
            "ShipStaticData",
            {
                "MessageID": 5,
                "RepeatIndicator": 0,
                "UserID": 477553000,
                "Valid": True,
                "AisVersion": 2,
                "ImoNumber": 9285122,
                "CallSign": "VRQF7",
                "Name": "EASTERN GLORY",
                "Type": 71,
                "Dimension": {"A": 220, "B": 74, "C": 16, "D": 16},
                "FixType": 1,
                "Eta": {"Month": 9, "Day": 2, "Hour": 14, "Minute": 0},
                "MaximumStaticDraught": 121.0,
                "Destination": "SGSIN",
                "Dte": False,
                "Spare": False,
            },
        ),
    ]
    return cases


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    stream = build_stream()
    stream_path = FIXTURE_DIR / "stream-sample.jsonl"
    stream_path.write_text(
        "".join(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n" for m in stream),
        encoding="utf-8",
    )

    edge = build_edge_cases()
    edge_path = FIXTURE_DIR / "edge-cases.jsonl"
    edge_path.write_text(
        "".join(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n" for m in edge),
        encoding="utf-8",
    )

    counts: dict[str, int] = {}
    for message in stream + edge:
        counts[message["MessageType"]] = counts.get(message["MessageType"], 0) + 1
    print(f"{stream_path.name}: {len(stream)} Nachrichten")
    print(f"{edge_path.name}: {len(edge)} Nachrichten")
    for name, count in sorted(counts.items(), key=lambda item: -item[1]):
        print(f"  {name:32s} {count:5d}")
    print(f"  {'GESAMT':32s} {len(stream) + len(edge):5d}")


if __name__ == "__main__":
    main()
