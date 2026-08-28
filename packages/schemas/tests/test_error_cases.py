"""Die fuenf ausdruecklich modellierten Fehlerfaelle.

Diese Tests pruefen nicht, ob die Fixtures gueltig sind - das tut
test_examples.py. Sie pruefen, ob das Schema die *Unterscheidung* traegt, um
die es jeweils geht. Ein Schema, in dem "kein Zeitstempel" und "Zeitstempel
Epoche 0" gleich aussehen, hat den Fehlerfall nicht modelliert, sondern
verschluckt.
"""

from __future__ import annotations

from google.protobuf import json_format

from argus.v1 import common_pb2, event_pb2, observation_pb2
from conftest import load_fixture


def _obs(name: str) -> observation_pb2.Observation:
    return json_format.ParseDict(load_fixture(f"error-cases/{name}"), observation_pb2.Observation())


def _event(name: str) -> event_pb2.Event:
    return json_format.ParseDict(load_fixture(f"error-cases/{name}"), event_pb2.Event())


# --- 1. Unbekannte Entitaet -------------------------------------------------

def test_unknown_entity_keeps_raw_reference():
    obs = _obs("unknown-entity.observation.json")
    assert obs.entity_ref.id == "mmsi:970010101", "Rohbezug der Quelle muss erhalten bleiben"
    assert not obs.entity_ref.HasField("resolved_entity_id")
    assert obs.entity_ref.resolution_status == common_pb2.RESOLUTION_STATUS_UNRESOLVED


def test_unresolved_is_distinguishable_from_never_attempted():
    """UNRESOLVED (geprueft, nichts gefunden) und PENDING (noch nicht geprueft)
    sind verschiedene Zustaende. Wer sie zusammenwirft, kann die Review-Queue
    nicht befuellen."""
    assert common_pb2.RESOLUTION_STATUS_PENDING != common_pb2.RESOLUTION_STATUS_UNRESOLVED
    assert common_pb2.RESOLUTION_STATUS_UNSPECIFIED == 0
    # UNSPECIFIED ist der Defaultwert und darf nie eine Aussage bedeuten.
    assert common_pb2.ResolutionStatus.Name(0) == "RESOLUTION_STATUS_UNSPECIFIED"


# --- 2. Position ohne Zeitstempel -------------------------------------------

def test_missing_timestamp_is_absent_not_zero():
    obs = _obs("missing-timestamp.observation.json")
    assert not obs.HasField("observed_at"), "observed_at muss fehlen, nicht 1970 sein"
    assert obs.ingested_at.seconds > 0, "ingested_at wird immer vom System gesetzt"
    assert obs.quality.time_quality == common_pb2.TIME_QUALITY_INFERRED_FROM_INGEST


def test_epoch_zero_and_missing_are_different():
    """Der eigentliche Punkt: eine Quelle, die versehentlich 1970 meldet, darf
    nicht wie eine Quelle aussehen, die gar nichts meldet."""
    absent = observation_pb2.Observation()
    epoch = observation_pb2.Observation()
    epoch.observed_at.FromJsonString("1970-01-01T00:00:00Z")
    assert not absent.HasField("observed_at")
    assert epoch.HasField("observed_at")
    assert absent != epoch
    assert "observed_at" not in json_format.MessageToDict(absent, preserving_proto_field_name=True)
    assert "observed_at" in json_format.MessageToDict(epoch, preserving_proto_field_name=True)


def test_absent_heading_is_not_zero():
    """Derselbe Mechanismus fuer Kinematik: AIS liefert heading oft nicht, und
    0 Grad (Nord) ist ein gueltiger Wert."""
    k = observation_pb2.Kinematics()
    assert not k.HasField("heading_deg")
    k.heading_deg = 0.0
    assert k.HasField("heading_deg")
    assert json_format.MessageToDict(k, preserving_proto_field_name=True) == {"heading_deg": 0.0}


# --- 3. Ereignis ohne exakten Ort -------------------------------------------

def test_country_only_event_has_no_invented_point():
    ev = _event("country-only.event.json")
    assert not ev.geo.HasField("geometry"), "Kein erfundener Punkt in der Landesmitte"
    assert ev.geo.precision == common_pb2.GEO_PRECISION_COUNTRY
    assert ev.geo.place.country_iso3166_1 == "AR"
    assert not ev.geo.HasField("representative_point")
    assert ev.geo.uncertainty_radius_m > 0


def test_derived_representative_point_is_flagged():
    """Wenn die Karte doch einen Punkt braucht, muss er als abgeleitet
    gekennzeichnet sein."""
    geo = common_pb2.GeoLocation(precision=common_pb2.GEO_PRECISION_COUNTRY)
    geo.representative_point.lat = -38.4
    geo.representative_point.lon = -63.6
    geo.representative_point_is_derived = True
    as_dict = json_format.MessageToDict(geo, preserving_proto_field_name=True)
    assert as_dict["representative_point_is_derived"] is True


def test_unspecified_and_unknown_precision_differ():
    """UNSPECIFIED heisst 'nicht gesetzt', UNKNOWN heisst 'geprueft,
    unbestimmbar'. Nur so faellt eine Pipeline auf, die vergisst, die
    Praezision zu setzen."""
    assert common_pb2.GEO_PRECISION_UNSPECIFIED == 0
    assert common_pb2.GEO_PRECISION_UNKNOWN != common_pb2.GEO_PRECISION_UNSPECIFIED


# --- 4. Widerspruechliche Meldungen -----------------------------------------

def test_dispute_keeps_both_claims():
    ev = _event("disputed.event.json")
    assert ev.status == event_pb2.EVENT_STATUS_DISPUTED
    assert len(ev.contradictions) == 1
    contradiction = ev.contradictions[0]
    assert contradiction.field_path == "/magnitude/value"
    assert len(contradiction.claims) == 2, "Beide Behauptungen bleiben erhalten"
    values = [c.value.number_value for c in contradiction.claims]
    assert values == [4, 11]
    # Jede Behauptung traegt ihre eigene Quelle und Bewertung.
    assert contradiction.claims[0].source.id == "reliefweb"
    assert contradiction.claims[1].source.reliability == common_pb2.SOURCE_RELIABILITY_D
    # Solange kein Schiedsspruch gefaellt ist, gibt es keinen Sieger.
    assert not contradiction.HasField("preferred_claim_index")


def test_dispute_lowers_confidence_and_counts_contradicting_sources():
    ev = _event("disputed.event.json")
    assert ev.confidence < 0.5
    assert ev.corroboration.contradicting_sources == 2


# --- 5. Zurueckgezogene Meldung ---------------------------------------------

def test_retraction_preserves_the_record():
    ev = _event("retracted.event.json")
    assert ev.status == event_pb2.EVENT_STATUS_RETRACTED
    assert ev.HasField("retraction")
    assert ev.retraction.retracted_by_source == "wire-xyz"
    assert ev.retraction.inferred_by_system is False
    # Inhalt bleibt lesbar - der Datensatz wird nicht geleert.
    assert ev.title
    assert ev.reports


def test_retraction_is_traceable_through_versions():
    ev = _event("retracted.event.json")
    assert ev.version == 2
    assert [v.v for v in ev.versions] == [1, 2]
    assert "/status" in ev.versions[1].changed
    assert "/retraction" in ev.versions[1].changed


def test_system_inferred_retraction_is_marked_as_such():
    """Ein vom System abgeleiteter Rueckzug darf nicht wie ein Widerruf der
    Quelle aussehen."""
    r = common_pb2.Retraction(inferred_by_system=True, reason="4 Quellen widersprechen")
    assert r.inferred_by_system is True
