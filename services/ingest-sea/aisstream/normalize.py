"""Vom AIS-Fakt zum kanonischen ARGUS-Objekt.

Zwei Ausgaenge, bewusst getrennt (Aufgabenstellung, Constraint 2):

    argus.canon.vessel.position   Observation, Sekunden bis Minuten gueltig
    argus.canon.vessel.static     Entity,      Monate bis Jahre gueltig

Der Grund fuer die Trennung ist nicht Ordnungsliebe, sondern Lebensdauer: eine
Position ist nach fuenf Minuten historisch, ein Schiffsname nach fuenf Jahren
noch aktuell. Beides ueber dasselbe Subject zu schicken hiesse, entweder die
Positionen zu lange oder die Stammdaten zu kurz vorzuhalten.

WAS HIER NICHT PASSIERT
-----------------------
Entity Resolution. Dieser Code weiss nicht, welches Schiff hinter einer MMSI
steckt, und behauptet es auch nicht: `EntityRef.resolution_status` bleibt
PENDING, `resolved_entity_id` leer. Die Regel aus ADR 0005 gilt hier woertlich -
die MMSI wandert als quellnativer Bezeichner mit, nicht als Schluessel.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import h3

from aisstream import ais
from aisstream.config import POSITION_SUBJECT, STATIC_SUBJECT
from aisstream.ids import deterministic_ulid, entity_ref_id, identity_seed
from aisstream.parser import ParsedMessage
from argus_geo import great_circle_distance_m, m_per_s_to_knots

# Die drei Aufloesungen aus Kapitel 3.5 und ADR 0003: r5 Region, r7
# Ereignis-Bucket, r9 Feinabgleich.
H3_RESOLUTIONS = (5, 7, 9)

# Admiralty-Bewertung der Quelle (Kapitel 7.2). B statt A, und das mit Absicht:
# AISStream buendelt Empfaenger unbekannter Guete, und AIS selbst ist
# unauthentifiziert - ein Sender kann melden, was er will. "Meist zuverlaessig"
# ist die ehrlichste Einstufung, die sich belegen laesst.
SOURCE_RELIABILITY = "SOURCE_RELIABILITY_B"
SOURCE_ID = "aisstream"
LICENSE_ID = "aisstream-tos"


def _iso(epoch: float) -> str:
    """UTC-Zeitstempel in der kanonischen Protobuf-JSON-Form.

    google.protobuf.Timestamp gibt beim Serialisieren null, drei, sechs oder
    neun Nachkommastellen aus - nie ein '.000'. Wer hier fest auf
    Millisekunden formatiert, erzeugt eine Zeichenkette, die durch einen
    Protobuf-Round-Trip veraendert wird. Das faellt in keinem Test auf, der
    nur validiert, und in jedem, der vergleicht.
    """
    moment = datetime.fromtimestamp(epoch, tz=UTC)
    timespec = "seconds" if moment.microsecond == 0 else "milliseconds"
    return moment.isoformat(timespec=timespec).replace("+00:00", "Z")


def _code(value: int | None) -> str | None:
    """Zahlencode fuer den Struct-Bereich: als Zeichenkette, siehe unten."""
    return None if value is None else str(value)


def _h3_cells(lat: float, lon: float) -> dict[str, str]:
    return {f"h3_r{res}": h3.latlng_to_cell(lat, lon, res) for res in H3_RESOLUTIONS}


def _entity_type_for(category: str) -> str:
    """Was fuer eine Entitaet steckt hinter dieser MMSI.

    Eine Navigationshilfe als Schiff zu fuehren waere ein Fehler, der sich
    durch das ganze Lagebild zieht: Bojen fahren nicht, und ein Detektor, der
    stillstehende Schiffe sucht, faende nichts anderes mehr.
    """
    return {
        "aid_to_navigation": "ENTITY_TYPE_FACILITY",
        "sar_aircraft": "ENTITY_TYPE_AIRCRAFT",
        "coast_station": "ENTITY_TYPE_FACILITY",
    }.get(category, "ENTITY_TYPE_VESSEL")


def _provenance(retrieved_at: float, clock_skew_ms: int | None, collector: str) -> dict[str, Any]:
    provenance: dict[str, Any] = {
        "id": SOURCE_ID,
        "reliability": SOURCE_RELIABILITY,
        "collector": collector,
        "license_id": LICENSE_ID,
        "retrieved_at": _iso(retrieved_at),
    }
    if clock_skew_ms is not None:
        provenance["clock_skew_ms"] = clock_skew_ms
    return provenance


class Normalizer:
    """Erzeugt kanonische Objekte aus uebersetzten AIS-Nachrichten.

    Zustandsbehaftet, aber nur in einer Hinsicht: er merkt sich die letzte
    Position je MMSI, um Positionsspruenge zu erkennen. Der Speicher ist hart
    begrenzt (siehe `_remember_position`) - ein Konnektor, der 24 Stunden ohne
    Speicherwachstum laufen soll, darf keine unbegrenzte Landkarte fuehren.
    """

    def __init__(
        self,
        *,
        collector: str,
        schema_version: str = "1.0.0",
        max_implied_speed_kn: float = 100.0,
        max_future_skew_s: float = 300.0,
        position_history_size: int = 100_000,
    ) -> None:
        self.collector = collector
        self.schema_version = schema_version
        self.max_implied_speed_kn = max_implied_speed_kn
        self.max_future_skew_s = max_future_skew_s
        self.position_history_size = position_history_size
        # MMSI -> (Zeit, Breite, Laenge). Einfaches dict statt LRU: Python
        # haelt die Einfuegereihenfolge, und beim Ueberlauf faellt der aelteste
        # Eintrag heraus. Das ist keine echte LRU, reicht aber fuer den Zweck -
        # ein Sender, der laenger nichts gemeldet hat, ist als Vergleichspunkt
        # ohnehin wertlos.
        self._last_position: dict[int, tuple[float, float, float]] = {}

    # -- Zeit ------------------------------------------------------------

    def _time_quality(self, observed_at: float | None, now: float) -> tuple[float | None, str, str]:
        """Bewertet den Quellzeitstempel.

        Gibt (verwendeter Zeitstempel, TimeQuality, Marke) zurueck. Ein
        Zeitstempel aus der Zukunft wird NICHT korrigiert: er bleibt stehen und
        wird als unplausibel gekennzeichnet. Ihn auf 'jetzt' zu ziehen wuerde
        den Fehler der Quelle in eine Aussage von ARGUS verwandeln.
        """
        if observed_at is None:
            return None, "TIME_QUALITY_MISSING", "no_source_timestamp"
        if observed_at > now + self.max_future_skew_s:
            return observed_at, "TIME_QUALITY_IMPLAUSIBLE", "future_timestamp"
        if observed_at <= 0:
            return observed_at, "TIME_QUALITY_IMPLAUSIBLE", "epoch_zero_timestamp"
        return observed_at, "TIME_QUALITY_SOURCE_PROVIDED", ""

    # -- Positionsspruenge -----------------------------------------------

    def _check_jump(
        self, mmsi: int, lat: float, lon: float, when: float
    ) -> tuple[list[str], float | None]:
        """Vergleicht mit der letzten Position derselben MMSI.

        Erkennt zwei Faelle, die im AIS haeufig sind und verschiedene Ursachen
        haben: einen Sprung (zwei Schiffe senden dieselbe MMSI, oder ein
        Bitfehler kippt eine Koordinate) und eine Meldung, die aelter ist als
        die vorherige (Umordnung auf dem Weg).

        Markiert, verwirft nicht. Ob ein Sprung Manipulation ist, entscheidet
        die Anomalieerkennung mit mehr Kontext - hier ist nur bekannt, dass
        die beiden Punkte nicht zusammenpassen.
        """
        flags: list[str] = []
        previous = self._last_position.get(mmsi)
        seconds_since: float | None = None

        if previous is not None:
            previous_time, previous_lat, previous_lon = previous
            delta_t = when - previous_time
            if delta_t < 0:
                flags.append("out_of_order_timestamp")
            elif delta_t > 0:
                seconds_since = delta_t
                # Reihenfolge der Argumente: LAENGE zuerst. argus_geo dreht
                # sie bewusst um, damit die Verwechslung beim Lesen auffaellt
                # und nicht erst an einem Schiff mitten in der Sahara.
                distance_m = great_circle_distance_m(previous_lon, previous_lat, lon, lat)
                implied_kn = m_per_s_to_knots(distance_m / delta_t)
                if implied_kn > self.max_implied_speed_kn:
                    flags.append("impossible_speed")
            else:
                seconds_since = 0.0

        self._remember_position(mmsi, when, lat, lon)
        return flags, seconds_since

    def _remember_position(self, mmsi: int, when: float, lat: float, lon: float) -> None:
        if mmsi in self._last_position:
            del self._last_position[mmsi]  # ans Ende schieben
        elif len(self._last_position) >= self.position_history_size:
            # Aeltesten Eintrag entfernen. Das Speicherbudget ist eine harte
            # Zusage, kein Richtwert.
            self._last_position.pop(next(iter(self._last_position)))
        self._last_position[mmsi] = (when, lat, lon)

    # -- Observation ------------------------------------------------------

    def to_observation(
        self,
        message: ParsedMessage,
        *,
        now: float,
        raw_ref: str | None = None,
        clock_skew_ms: int | None = None,
    ) -> tuple[dict[str, Any], str, float | None] | None:
        """Positionsmeldung -> Observation.

        Rueckgabe: (Objekt, dedupe_key, observed_at) oder None, wenn die
        Nachricht keinen Positionsteil hat.
        """
        position = message.position
        if position is None:
            return None

        observed_at, time_quality, time_flag = self._time_quality(message.received_at, now)
        effective_time = observed_at if observed_at is not None else now

        flags = list(position.quality_flags)
        if time_flag:
            flags.append(time_flag)

        seconds_since: float | None = None
        geo: dict[str, Any] | None = None
        if position.has_position:
            assert position.lat is not None and position.lon is not None  # noqa: S101
            jump_flags, seconds_since = self._check_jump(
                message.mmsi, position.lat, position.lon, effective_time
            )
            flags.extend(jump_flags)
            geo = {
                "lat": position.lat,
                "lon": position.lon,
                **_h3_cells(position.lat, position.lon),
                "precision": "GEO_PRECISION_EXACT",
            }

        kinematics = {
            key: value
            for key, value in (
                ("sog_kn", position.sog_kn),
                ("cog_deg", position.cog_deg),
                ("heading_deg", position.heading_deg),
                ("rate_of_turn_deg_min", position.rate_of_turn_deg_min),
                ("draft_m", position.draft_m),
            )
            if value is not None
        }

        # Codes stehen als Zeichenketten im Struct. Grund: Struct kennt fuer
        # Zahlen nur double. Eine 21 kommt aus einem Protobuf-Round-Trip als
        # 21.0 zurueck - bei einem Nachrichtentyp oder einer Kennung ist das
        # keine Rundung, sondern ein Typwechsel. Messwerte bleiben Zahlen,
        # weil sie welche sind.
        attributes: dict[str, Any] = {
            "ais_message_type": str(message.ais_type),
            "mmsi": str(message.mmsi),
            "mmsi_category": message.mmsi_category,
        }
        if position.nav_status:
            attributes["nav_status"] = position.nav_status
        if message.static is not None and message.static.aton_type:
            attributes["aton_type"] = message.static.aton_type
        if message.static is not None and message.static.is_virtual_aton:
            # Eine virtuelle Navigationshilfe existiert physisch nicht. Sie
            # ungekennzeichnet auf die Karte zu setzen waere eine Erfindung.
            attributes["is_virtual_aton"] = True
            flags.append("virtual_aton")
        if message.static is not None and message.static.is_off_position:
            attributes["aton_off_position"] = True

        # Nur setzen, was wahr ist: proto3 kennt fuer diese Bools keine
        # Praesenz, ein ausdrueckliches false ist vom Fehlen ununterscheidbar.
        # Es hinzuschreiben taeuscht eine Aussage vor, die das Schema nicht
        # transportieren kann.
        quality: dict[str, Any] = {"time_quality": time_quality}
        if position.is_dead_reckoned:
            quality["is_dead_reckoned"] = True
        if position.position_accuracy_high is not None:
            # Das AIS-Bit sagt nur "besser oder schlechter als 10 m". Genau so
            # wird es uebersetzt: 10 bzw. 100 Meter, nicht eine erfundene Zahl
            # dazwischen.
            quality["position_accuracy_m"] = 10.0 if position.position_accuracy_high else 100.0
        if seconds_since is not None:
            quality["seconds_since_previous"] = round(seconds_since, 3)
        if flags:
            quality["flags"] = flags

        seed = identity_seed(
            SOURCE_ID,
            {
                "mmsi": message.mmsi,
                "type": message.ais_type,
                "t": message.received_at,
                "lat": position.lat,
                "lon": position.lon,
                "sog": position.sog_kn,
                "cog": position.cog_deg,
            },
        )
        dedupe_key = f"{SOURCE_ID}:pos:{deterministic_ulid(timestamp_s=effective_time, seed=seed)}"

        observation: dict[str, Any] = {
            "obs_id": deterministic_ulid(timestamp_s=effective_time, seed=seed),
            "schema_version": self.schema_version,
            "ingested_at": _iso(now),
            "source": _provenance(now, clock_skew_ms, self.collector),
            "entity_ref": {
                "type": _entity_type_for(message.mmsi_category),
                "id": entity_ref_id(imo=None, mmsi=message.mmsi),
                "resolution_status": "RESOLUTION_STATUS_PENDING",
            },
            "kind": (
                "OBSERVATION_KIND_POSITION" if position.has_position else "OBSERVATION_KIND_STATUS"
            ),
            "attributes": attributes,
            "quality": quality,
            "dedupe_key": dedupe_key,
        }
        if observed_at is not None:
            observation["observed_at"] = _iso(observed_at)
        if geo is not None:
            observation["geo"] = geo
        if kinematics:
            observation["kinematics"] = kinematics
        if raw_ref:
            observation["raw_ref"] = raw_ref

        return observation, dedupe_key, observed_at

    # -- Entity -----------------------------------------------------------

    def to_entity(
        self,
        message: ParsedMessage,
        *,
        now: float,
        raw_ref: str | None = None,
        clock_skew_ms: int | None = None,
    ) -> tuple[dict[str, Any], str, float | None] | None:
        """Stammdatenmeldung -> Entity (Kandidat, nicht kanonischer Satz).

        `entity_id` ist provisorisch. Ein stabiler Schluessel je Schiff waere
        nur ueber die MMSI zu bilden - und genau das verbietet ADR 0005, weil
        eine MMSI bei Flaggenwechsel neu vergeben wird und zwei Schiffe sich
        dann eine Zeile teilen wuerden, die niemand mehr trennen kann. Der
        Resolver fuehrt die Kandidaten ueber `identifiers` zusammen.
        """
        static = message.static
        if static is None:
            return None

        observed_at, time_quality, time_flag = self._time_quality(message.received_at, now)
        effective_time = observed_at if observed_at is not None else now

        name = static.name or message.metadata_name
        display_name = name or f"MMSI {message.mmsi}"

        mmsi_identifier: dict[str, Any] = {
            "scheme": "mmsi",
            "value": str(message.mmsi),
            # MUTABLE ist der ganze Punkt: der Resolver muss wissen, dass
            # dieser Bezeichner ein schwaches Indiz ist.
            "stability": "IDENTIFIER_STABILITY_MUTABLE",
        }
        if static.imo is None:
            mmsi_identifier["is_primary"] = True
        identifiers: list[dict[str, Any]] = [mmsi_identifier]
        if static.imo is not None:
            identifiers.insert(
                0,
                {
                    "scheme": "imo",
                    "value": str(static.imo),
                    "stability": "IDENTIFIER_STABILITY_STABLE",
                    "is_primary": True,
                },
            )
        if static.call_sign:
            identifiers.append(
                {
                    "scheme": "callsign",
                    "value": static.call_sign,
                    "stability": "IDENTIFIER_STABILITY_EPHEMERAL",
                }
            )

        attributes: dict[str, Any] = {
            "ais_message_type": str(message.ais_type),
            "mmsi": str(message.mmsi),
            "mmsi_category": message.mmsi_category,
            # Ausdruecklich vermerkt, damit ein Konsument nicht auf die Idee
            # kommt, diese ID sei kanonisch.
            "entity_id_is_provisional": True,
        }
        mid = ais.mmsi_mid(message.mmsi)
        if mid is not None:
            # Nur die Ziffern, keine Landzuordnung - siehe ais.mmsi_mid.
            attributes["mmsi_mid"] = f"{mid:03d}"
        if name is None:
            attributes["display_name_is_placeholder"] = True
        for key, value in (
            ("ship_type", static.ship_type),
            ("ship_type_code", _code(static.ship_type_code)),
            ("destination", static.destination),
            ("eta", static.eta),
            ("max_draught_m", static.max_draught_m),
            ("aton_type", static.aton_type),
            ("aton_type_code", _code(static.aton_type_code)),
            ("fix_type", _code(static.fix_type)),
            ("ais_static_part", static.part),
        ):
            if value is not None:
                attributes[key] = value
        if static.is_virtual_aton:
            attributes["is_virtual_aton"] = True
        if static.dimensions is not None:
            dimension = static.dimensions
            # Abmessungen sind Messwerte und bleiben Zahlen - ausdruecklich
            # als float, damit sie den double-Round-Trip unveraendert
            # ueberstehen.
            attributes["dimensions"] = {
                key: float(value)
                for key, value in (
                    ("length_m", dimension.length_m),
                    ("beam_m", dimension.beam_m),
                    ("to_bow_m", dimension.to_bow_m),
                    ("to_stern_m", dimension.to_stern_m),
                    ("to_port_m", dimension.to_port_m),
                    ("to_starboard_m", dimension.to_starboard_m),
                )
                if value is not None
            }
        flags = list(static.quality_flags)
        if time_flag:
            flags.append(time_flag)
        if flags:
            attributes["quality_flags"] = flags
        attributes["time_quality"] = time_quality

        seed = identity_seed(
            SOURCE_ID,
            {
                "mmsi": message.mmsi,
                "type": message.ais_type,
                "t": message.received_at,
                "name": name,
                "imo": static.imo,
                "callsign": static.call_sign,
                "dest": static.destination,
                "part": static.part,
            },
        )
        entity_id = deterministic_ulid(timestamp_s=effective_time, seed=seed)

        entity: dict[str, Any] = {
            "entity_id": entity_id,
            "schema_version": self.schema_version,
            "ingested_at": _iso(now),
            "source": _provenance(now, clock_skew_ms, self.collector),
            "type": _entity_type_for(message.mmsi_category),
            "display_name": display_name,
            "identifiers": identifiers,
            "attributes": attributes,
            "resolution": {
                "decided_by": self.collector,
                "note": (
                    "Kandidat aus einer AIS-Stammdatenmeldung. entity_id ist "
                    "provisorisch; die Zusammenfuehrung erfolgt ueber identifiers "
                    "im Resolver (siehe ADR 0005)."
                ),
            },
        }
        if observed_at is not None:
            entity["observed_at"] = _iso(observed_at)
        if raw_ref:
            entity["raw_ref"] = raw_ref
        if name and static.name and message.metadata_name and static.name != message.metadata_name:
            # Zwei Namen fuer dieselbe MMSI. Der AIS-Satz gewinnt, der andere
            # bleibt als frueherer Name erhalten - genau der Fall, fuer den
            # AliasKind FORMER_NAME da ist.
            entity["aliases"] = [
                {
                    "name": message.metadata_name,
                    "kind": "ALIAS_KIND_FORMER_NAME",
                    "lang": "und",
                    "script": "Latn",
                }
            ]

        dedupe_key = f"{SOURCE_ID}:static:{entity_id}"
        return entity, dedupe_key, observed_at


def subject_suffix_for(kind: str, *, prefix: str) -> str:
    """Suffix, das zusammen mit `prefix` das zugesagte Subject ergibt.

    Der Runner setzt das Subject als `prefix + "." + suffix` zusammen. Ein
    falsch gesetztes Praefix wuerde damit stillschweigend auf ein anderes
    Subject veroeffentlichen - der Stream bliebe leer, der Konnektor meldete
    Erfolg. Deshalb wird hier gerechnet und nicht geraten.
    """
    subject = {"position": POSITION_SUBJECT, "static": STATIC_SUBJECT}[kind]
    if not subject.startswith(f"{prefix}."):
        raise ValueError(
            f"Subject-Praefix {prefix!r} passt nicht zum zugesagten Subject "
            f"{subject!r}. Erwartet wird ARGUS_NATS__SUBJECT_PREFIX=argus.canon."
        )
    return subject[len(prefix) + 1 :]
