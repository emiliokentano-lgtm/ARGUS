"""Konfiguration: die Fehler, die man erst im Betrieb bemerken wuerde.

Eine vertauschte Boundingbox liefert schweigend null Nachrichten. Ein
falscher Nachrichtentyp im Abonnement ebenso. Beides sieht aus wie "ruhige
See" und ist keine. Deshalb faellt es hier beim Start um und nicht dort.
"""

from __future__ import annotations

import pytest
from aisstream.config import POSITION_SUBJECT, STATIC_SUBJECT, AisStreamSettings
from pydantic import ValidationError


def test_subjects_are_constants_not_settings() -> None:
    """Eine Trennung, die sich per Umgebungsvariable aufheben laesst, ist keine."""
    assert POSITION_SUBJECT == "argus.canon.vessel.position"
    assert STATIC_SUBJECT == "argus.canon.vessel.static"
    assert "bounding_boxes" in AisStreamSettings.model_fields
    assert "position_subject" not in AisStreamSettings.model_fields


def test_api_key_never_appears_in_a_repr() -> None:
    settings = AisStreamSettings(api_key="geheim-123")
    assert "geheim-123" not in repr(settings)
    assert "geheim-123" not in str(settings)
    assert settings.api_key.get_secret_value() == "geheim-123"


def test_redacted_subscription_hides_the_key() -> None:
    settings = AisStreamSettings(api_key="geheim-123")
    assert settings.redacted_subscription()["APIKey"] == "***"
    assert settings.subscription()["APIKey"] == "geheim-123"


def test_empty_bounding_boxes_mean_worldwide() -> None:
    """AISStream verlangt das Feld auch dann, wenn alles abonniert wird."""
    subscription = AisStreamSettings(api_key="k").subscription()
    assert subscription["BoundingBoxes"] == [[[-90.0, -180.0], [90.0, 180.0]]]


def test_swapped_corners_are_rejected() -> None:
    """Der haeufigste Konfigurationsfehler - und der stillste."""
    with pytest.raises(ValidationError, match="suedwestliche"):
        AisStreamSettings(api_key="k", bounding_boxes=[[[55.0, 9.0], [53.0, 6.0]]])


@pytest.mark.parametrize(
    "boxes",
    [
        [[[53.0, 6.0]]],  # nur eine Ecke
        [[[53.0], [55.0, 9.0]]],  # Ecke ohne Laenge
        [[[95.0, 6.0], [96.0, 9.0]]],  # Breite ausserhalb
        [[[53.0, -200.0], [55.0, 9.0]]],  # Laenge ausserhalb
    ],
)
def test_malformed_bounding_boxes_are_rejected(boxes) -> None:
    with pytest.raises(ValidationError):
        AisStreamSettings(api_key="k", bounding_boxes=boxes)


def test_lists_come_from_the_environment_as_json(monkeypatch) -> None:
    monkeypatch.setenv("ARGUS_AIS_API_KEY", "k")
    monkeypatch.setenv("ARGUS_AIS_BOUNDING_BOXES", "[[[53.0, 6.0], [55.0, 9.0]]]")
    monkeypatch.setenv("ARGUS_AIS_MMSI_FILTER", "211331640,244660123")
    settings = AisStreamSettings()
    assert settings.bounding_boxes == [[[53.0, 6.0], [55.0, 9.0]]]
    assert settings.mmsi_filter == ["211331640", "244660123"]
    assert settings.subscription()["FiltersShipMMSI"] == ["211331640", "244660123"]


def test_broken_json_in_the_environment_is_named(monkeypatch) -> None:
    monkeypatch.setenv("ARGUS_AIS_API_KEY", "k")
    monkeypatch.setenv("ARGUS_AIS_BOUNDING_BOXES", "[[[53.0, 6.0], [55.0")
    with pytest.raises(ValidationError, match="JSON"):
        AisStreamSettings()


def test_unsupported_message_type_in_the_subscription_is_rejected() -> None:
    """Ein Typ, den der Parser nicht kennt, gehoert nicht ins Abonnement.

    Ihn zu abonnieren erzeugt Last, die sofort wieder verworfen wird - und
    verdeckt in der Metrik, welche Typen tatsaechlich unerwartet auftauchen.
    """
    with pytest.raises(ValidationError, match="Nicht unterstuetzte"):
        AisStreamSettings(api_key="k", message_types=["PositionReport", "BaseStationReport"])


def test_default_subscription_covers_exactly_what_the_parser_handles() -> None:
    from aisstream.parser import SUPPORTED_TYPES

    assert set(AisStreamSettings(api_key="k").message_types) == set(SUPPORTED_TYPES)
