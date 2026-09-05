"""AISStream-Nachrichten in typisierte Fakten uebersetzen.

Die Drahtform von AISStream.io ist ein Umschlag mit drei Teilen:

    {
      "MessageType": "PositionReport",
      "MetaData":  {"MMSI": 211331640, "ShipName": "...", "time_utc": "..."},
      "Message":   {"PositionReport": { ...Felder des AIS-Satzes... }}
    }

`MetaData` ist die Sicht des Dienstes auf die Nachricht (Empfangszeit,
zuletzt bekannter Schiffsname), `Message` der entschluesselte AIS-Satz.
Beide widersprechen sich gelegentlich - MetaData.ShipName stammt aus einem
frueheren Typ-5-Satz und kann aelter sein als der aktuelle. Wo beides
vorliegt, gewinnt der AIS-Satz; MetaData ist der Rueckfall.

Dieses Modul entscheidet nichts ueber ARGUS. Es liefert Fakten und Marken;
was daraus wird, steht in normalize.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from aisstream import ais

# AISStream-Nachrichtentyp -> AIS-Nachrichtentypen nach ITU-R M.1371.
# Ein Eintrag hier ist die einzige Stelle, an der ein Typ unterstuetzt wird.
SUPPORTED_TYPES: dict[str, tuple[int, ...]] = {
    "PositionReport": (1, 2, 3),
    "ShipStaticData": (5,),
    "StandardClassBPositionReport": (18,),
    "ExtendedClassBPositionReport": (19,),
    "AidsToNavigationReport": (21,),
    "StaticDataReport": (24,),
}

# Go formatiert Zeiten als "2026-08-28 09:14:03.221 +0000 UTC". Das ist weder
# RFC 3339 noch ISO 8601, und datetime.fromisoformat kommt damit nicht zurecht.
_GO_TIME = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[ T]"
    r"(?P<time>\d{2}:\d{2}:\d{2}(?:\.\d+)?)"
    r"\s*(?P<offset>[+-]\d{4})?"
    r"(?:\s+\w+)?$"
)


class MalformedMessageError(ValueError):
    """Der Umschlag ist nicht das, was AISStream zusagt."""


class UnsupportedMessageTypeError(ValueError):
    """Ein Typ, den dieser Konnektor nicht uebersetzt.

    Kein Fehler im engeren Sinn: AISStream liefert ueber zwanzig Typen, und
    wir haben uns fuer sechs entschieden. Der Aufrufer zaehlt sie und geht
    weiter.
    """

    def __init__(self, message_type: str) -> None:
        super().__init__(f"Nachrichtentyp {message_type!r} wird nicht uebersetzt")
        self.message_type = message_type


@dataclass(slots=True)
class PositionFacts:
    """Was eine Positionsmeldung ueber Ort und Bewegung sagt."""

    lat: float | None
    lon: float | None
    sog_kn: float | None = None
    cog_deg: float | None = None
    heading_deg: float | None = None
    rate_of_turn_deg_min: float | None = None
    draft_m: float | None = None
    nav_status: str | None = None
    position_accuracy_high: bool | None = None
    is_dead_reckoned: bool = False
    quality_flags: list[str] = field(default_factory=list)

    @property
    def has_position(self) -> bool:
        return self.lat is not None and self.lon is not None


@dataclass(slots=True)
class StaticFacts:
    """Was eine Stammdatenmeldung ueber das Schiff sagt."""

    name: str | None = None
    call_sign: str | None = None
    imo: int | None = None
    ship_type: str | None = None
    ship_type_code: int | None = None
    destination: str | None = None
    eta: str | None = None
    dimensions: ais.Dimensions | None = None
    max_draught_m: float | None = None
    fix_type: int | None = None
    # Nur bei Typ 21 belegt: eine Navigationshilfe ist kein Schiff.
    aton_type: str | None = None
    aton_type_code: int | None = None
    is_virtual_aton: bool = False
    is_off_position: bool | None = None
    # Typ 24 kommt in zwei Haelften: A traegt den Namen, B den Rest. Welche
    # Haelfte vorlag, entscheidet, was fehlen darf.
    part: str | None = None
    quality_flags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedMessage:
    """Eine uebersetzte AISStream-Nachricht.

    Position und Stammdaten sind getrennt und beide optional. Typ 19 belegt
    ausnahmsweise beide - ein Klasse-B-Sender, der seinen Namen zusammen mit
    der Position schickt.
    """

    message_type: str
    ais_types: tuple[int, ...]
    mmsi: int
    mmsi_category: str
    received_at: float | None
    metadata_name: str | None
    position: PositionFacts | None = None
    static: StaticFacts | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def ais_type(self) -> int:
        """Der konkrete AIS-Typ, sofern die Nachricht ihn nennt."""
        reported = self.raw.get("_message_id")
        if isinstance(reported, int) and reported in self.ais_types:
            return reported
        return self.ais_types[0]


def parse_go_time(value: str | None) -> float | None:
    """Wandelt AISStreams Zeitangabe in Unix-Sekunden.

    Gibt None zurueck, wenn das Format nicht passt. Ein nicht lesbarer
    Zeitstempel ist kein Grund, die Nachricht zu verwerfen - die Position ist
    trotzdem etwas wert, und `TimeQuality` haelt fest, was fehlt.
    """
    if not value or not isinstance(value, str):
        return None
    match = _GO_TIME.match(value.strip())
    if not match:
        return None
    offset = match.group("offset") or "+0000"
    text = f"{match.group('date')}T{match.group('time')}{offset[:3]}:{offset[3:]}"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _as_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _body(envelope: dict[str, Any], message_type: str) -> dict[str, Any]:
    message = envelope.get("Message")
    if not isinstance(message, dict):
        raise MalformedMessageError("Feld 'Message' fehlt oder ist kein Objekt")
    body = message.get(message_type)
    if not isinstance(body, dict):
        raise MalformedMessageError(
            f"Feld 'Message.{message_type}' fehlt. AISStream sagt zu, dass der "
            f"Rumpf unter dem Namen aus MessageType liegt."
        )
    return body


def _position_from(body: dict[str, Any], *, with_nav_status: bool) -> PositionFacts:
    lat = ais.clean_latitude(body.get("Latitude"))
    lon = ais.clean_longitude(body.get("Longitude"))

    flags: list[str] = []
    if lat is None or lon is None:
        # Ausdruecklich vermerkt statt still weggelassen: eine Positionsmeldung
        # ohne Position ist ein Betriebszustand, ueber den das Quellen-Panel
        # Bescheid wissen will.
        flags.append("invalid_position")
    elif lat == 0.0 and lon == 0.0:
        # Null Island: praktisch immer ein Transponder ohne GPS-Fix.
        #
        # Sie wird verworfen, und der Grund ist nicht die Unwahrscheinlichkeit,
        # sondern das Schema: GeoPoint.lat und .lon sind proto3-double ohne
        # Praesenz. Ein Punkt bei 0/0 ist nach einem Protobuf-Round-Trip nicht
        # mehr von einer fehlenden Position zu unterscheiden - die Nachricht
        # wuerde ihre Bedeutung unterwegs aendern. Eine Beobachtung, deren Sinn
        # vom Transportweg abhaengt, gehoert nicht in den Bus.
        #
        # Die Marke bleibt: der Fall verschwindet nicht, er wird sichtbar.
        flags.append("null_island")
        lat = lon = None

    dead_reckoned, timestamp_flags = ais.position_timestamp_quality(_as_int(body.get("Timestamp")))
    flags.extend(timestamp_flags)

    rate_of_turn, saturated = ais.clean_rate_of_turn(body.get("RateOfTurn"))
    if saturated:
        flags.append("rate_of_turn_saturated")

    accuracy = body.get("PositionAccuracy")
    return PositionFacts(
        lat=lat,
        lon=lon,
        sog_kn=ais.clean_sog(body.get("Sog")),
        cog_deg=ais.clean_cog(body.get("Cog")),
        heading_deg=ais.clean_heading(body.get("TrueHeading")),
        rate_of_turn_deg_min=rate_of_turn,
        nav_status=(
            ais.navigational_status(_as_int(body.get("NavigationalStatus")))
            if with_nav_status
            else None
        ),
        position_accuracy_high=accuracy if isinstance(accuracy, bool) else None,
        is_dead_reckoned=dead_reckoned,
        quality_flags=flags,
    )


def _eta_from(raw: Any) -> str | None:
    """AIS-ETA: Monat, Tag, Stunde, Minute - ohne Jahr.

    Deshalb bleibt sie eine Zeichenkette und wird nicht zu einem Zeitstempel
    gerechnet. Das Jahr zu raten hiesse, aus einer Angabe mit vier Feldern
    eine mit fuenf zu machen und das fuenfte zu erfinden; bei einer ETA im
    Januar, gemeldet im Dezember, geht das reproduzierbar schief.
    """
    if not isinstance(raw, dict):
        return None
    month, day = _as_int(raw.get("Month")), _as_int(raw.get("Day"))
    hour, minute = _as_int(raw.get("Hour")), _as_int(raw.get("Minute"))
    if not month or not day:
        return None  # 0 bedeutet in beiden Feldern "nicht verfuegbar"
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    if hour is None or hour > 23 or minute is None or minute > 59:
        hour, minute = 24, 60  # AIS-Sentinel fuer "Zeit unbekannt"
    return f"--{month:02d}-{day:02d}T{hour:02d}:{minute:02d}Z"


def _static_from_ship_static(body: dict[str, Any]) -> StaticFacts:
    imo_raw = _as_int(body.get("ImoNumber"))
    flags: list[str] = []
    imo = imo_raw if ais.is_valid_imo(imo_raw) else None
    if imo_raw and imo is None:
        # Der Fall aus ADR 0005: die Quelle liefert eine IMO, die keine ist.
        # Haeufig steht dort die MMSI oder eine Null. Wir uebernehmen sie
        # nicht als Kennung, verschweigen den Vorgang aber nicht.
        flags.append("invalid_imo_checksum")
    group, code = ais.ship_type(_as_int(body.get("Type")))
    return StaticFacts(
        name=ais.clean_text(body.get("Name")),
        call_sign=ais.clean_text(body.get("CallSign")),
        imo=imo,
        ship_type=group,
        ship_type_code=code,
        destination=ais.clean_text(body.get("Destination")),
        eta=_eta_from(body.get("Eta")),
        dimensions=ais.dimensions(body.get("Dimension")),
        max_draught_m=ais.clean_draught(body.get("MaximumStaticDraught")),
        fix_type=_as_int(body.get("FixType")),
        quality_flags=flags,
    )


def _static_from_static_data_report(body: dict[str, Any]) -> StaticFacts:
    """Typ 24: zwei Haelften, die getrennt gesendet werden.

    Teil A traegt nur den Namen, Teil B Rufzeichen, Typ und Abmessungen. Ein
    Sender schickt beide, aber nicht zwingend nacheinander und nicht zwingend
    beide innerhalb eines Empfangsfensters. Sie hier zusammenzufuehren waere
    Zustandshaltung ueber Nachrichtengrenzen hinweg - das ist Aufgabe des
    Resolvers, nicht des Parsers. Wir melden, was in dieser Haelfte steht.
    """
    part_number = _as_int(body.get("PartNumber"))
    report_a = body.get("ReportA") if isinstance(body.get("ReportA"), dict) else None
    report_b = body.get("ReportB") if isinstance(body.get("ReportB"), dict) else None

    if part_number == 0 or (report_a and report_a.get("Valid")):
        return StaticFacts(
            name=ais.clean_text((report_a or {}).get("Name")),
            part="A",
        )
    body_b = report_b or {}
    group, code = ais.ship_type(_as_int(body_b.get("ShipType")))
    vendor = ais.clean_text(body_b.get("VendorIDName"))
    return StaticFacts(
        call_sign=ais.clean_text(body_b.get("CallSign")),
        ship_type=group,
        ship_type_code=code,
        dimensions=ais.dimensions(body_b.get("Dimension")),
        fix_type=_as_int(body_b.get("FixType")),
        part="B",
        quality_flags=[] if vendor is None else [f"vendor:{vendor}"],
    )


def _static_from_aton(body: dict[str, Any]) -> StaticFacts:
    aton_group, aton_code = ais.aton_type(_as_int(body.get("Type")))
    name = ais.clean_text(body.get("Name"))
    extension = ais.clean_text(body.get("NameExtension"))
    if name and extension:
        name = f"{name}{extension}"
    off_position = body.get("OffPosition")
    return StaticFacts(
        name=name,
        aton_type=aton_group,
        aton_type_code=aton_code,
        is_virtual_aton=bool(body.get("VirtualAtoN")),
        is_off_position=off_position if isinstance(off_position, bool) else None,
        dimensions=ais.dimensions(body.get("Dimension")),
        fix_type=_as_int(body.get("Fixtype") or body.get("FixType")),
    )


def parse(envelope: dict[str, Any]) -> ParsedMessage:
    """Uebersetzt einen AISStream-Umschlag.

    Wirft `UnsupportedMessageTypeError` fuer Typen ausserhalb von
    SUPPORTED_TYPES und `MalformedMessageError`, wenn der Umschlag seine
    eigene Zusage bricht.
    """
    if not isinstance(envelope, dict):
        raise MalformedMessageError("Umschlag ist kein Objekt")

    message_type = envelope.get("MessageType")
    if not isinstance(message_type, str) or not message_type:
        raise MalformedMessageError("Feld 'MessageType' fehlt")
    if message_type not in SUPPORTED_TYPES:
        raise UnsupportedMessageTypeError(message_type)

    metadata = envelope.get("MetaData")
    if not isinstance(metadata, dict):
        raise MalformedMessageError("Feld 'MetaData' fehlt oder ist kein Objekt")

    body = _body(envelope, message_type)

    # Die MMSI steht an zwei Stellen. Der AIS-Satz ist die Quelle, MetaData
    # der Rueckfall - dort heisst dasselbe Feld je nach Version MMSI oder
    # MMSI_String, und der String kann fuehrende Nullen tragen.
    mmsi = _as_int(body.get("UserID")) or _as_int(metadata.get("MMSI"))
    if mmsi is None:
        raw_string = metadata.get("MMSI_String")
        if isinstance(raw_string, str) and raw_string.strip().isdigit():
            mmsi = int(raw_string.strip())
    if not ais.is_valid_mmsi(mmsi):
        raise MalformedMessageError(
            f"Keine gueltige MMSI in der Nachricht (gefunden: {mmsi!r}). Ohne "
            "Absenderkennung ist die Meldung nicht zuordenbar."
        )
    assert mmsi is not None  # noqa: S101 - von is_valid_mmsi bereits geprueft

    position: PositionFacts | None = None
    static: StaticFacts | None = None

    if message_type == "PositionReport":
        position = _position_from(body, with_nav_status=True)
    elif message_type == "StandardClassBPositionReport":
        position = _position_from(body, with_nav_status=False)
    elif message_type == "ExtendedClassBPositionReport":
        # Der einzige Typ, der beides in einer Nachricht liefert.
        position = _position_from(body, with_nav_status=False)
        group, code = ais.ship_type(_as_int(body.get("Type")))
        static = StaticFacts(
            name=ais.clean_text(body.get("Name")),
            ship_type=group,
            ship_type_code=code,
            dimensions=ais.dimensions(body.get("Dimension")),
            fix_type=_as_int(body.get("FixType")),
        )
    elif message_type == "AidsToNavigationReport":
        position = _position_from(body, with_nav_status=False)
        static = _static_from_aton(body)
    elif message_type == "ShipStaticData":
        static = _static_from_ship_static(body)
    elif message_type == "StaticDataReport":
        static = _static_from_static_data_report(body)

    raw = dict(body)
    raw["_message_id"] = _as_int(body.get("MessageID"))

    return ParsedMessage(
        message_type=message_type,
        ais_types=SUPPORTED_TYPES[message_type],
        mmsi=mmsi,
        mmsi_category=ais.mmsi_category(mmsi),
        received_at=parse_go_time(metadata.get("time_utc")),
        metadata_name=ais.clean_text(metadata.get("ShipName")),
        position=position,
        static=static,
        raw=raw,
    )
