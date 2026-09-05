"""ARGUS — maritimer Echtzeit-Konnektor (AIS ueber AISStream.io).

Referenzimplementierung fuer Streaming-Quellen: was hier steht, ist die
Vorlage fuer jeden weiteren Konnektor, der einen dauerhaften Strom liest
statt in Abstaenden abzufragen.

    from aisstream import AisStreamConnector, AisStreamSettings

Der Prozess-Einstieg liegt in `aisstream.__main__` und wird ueber
`python -m aisstream` aufgerufen.
"""

from aisstream.config import POSITION_SUBJECT, STATIC_SUBJECT, AisStreamSettings
from aisstream.connector import AisStreamConnector
from aisstream.ids import deterministic_ulid, entity_ref_id, is_ulid
from aisstream.normalize import Normalizer
from aisstream.parser import (
    SUPPORTED_TYPES,
    MalformedMessageError,
    ParsedMessage,
    PositionFacts,
    StaticFacts,
    UnsupportedMessageTypeError,
    parse,
)
from aisstream.stream import AisStreamClient, FatalStreamError

__all__ = [
    "POSITION_SUBJECT",
    "STATIC_SUBJECT",
    "SUPPORTED_TYPES",
    "AisStreamClient",
    "AisStreamConnector",
    "AisStreamSettings",
    "FatalStreamError",
    "MalformedMessageError",
    "Normalizer",
    "ParsedMessage",
    "PositionFacts",
    "StaticFacts",
    "UnsupportedMessageTypeError",
    "deterministic_ulid",
    "entity_ref_id",
    "is_ulid",
    "parse",
]

__version__ = "0.1.0"
