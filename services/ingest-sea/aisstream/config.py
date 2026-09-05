"""Konfiguration des AIS-Konnektors.

Ergaenzt die allgemeinen ConnectorSettings aus dem SDK um das, was nur
AISStream betrifft. Getrennt gehalten, weil das SDK nichts ueber Boundingboxen
wissen muss und der Konnektor nichts ueber Bronze-Spool-Verzeichnisse.

Namensschema wie im SDK: ARGUS_AIS_<FELD>.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Die Subjects sind in der Aufgabenstellung festgeschrieben. Sie stehen hier
# als Konstanten und nicht als Vorgabewert eines Konfigurationsfeldes: eine
# Trennung von Position und Stammdaten, die sich per Umgebungsvariable
# aufheben laesst, ist keine Trennung.
POSITION_SUBJECT = "argus.canon.vessel.position"
STATIC_SUBJECT = "argus.canon.vessel.static"


class AisStreamSettings(BaseSettings):
    """Alles, was AISStream betrifft."""

    model_config = SettingsConfigDict(
        env_prefix="ARGUS_AIS_",
        extra="ignore",
        case_sensitive=False,
    )

    # SecretStr: der Schluessel darf weder in einem Log noch in einem
    # Fehlerbericht auftauchen. pydantic zeigt beim Ausgeben '**********'.
    api_key: SecretStr = SecretStr("")
    url: str = "wss://stream.aisstream.io/v0/stream"

    # Boundingboxen im Format von AISStream: [[[lat_min, lon_min],
    # [lat_max, lon_max]], ...]. Leer bedeutet weltweit - was zulaessig ist,
    # aber die volle Last bedeutet und deshalb eine bewusste Entscheidung
    # sein sollte.
    #
    # NoDecode: pydantic-settings wuerde diese Felder selbst als JSON lesen,
    # BEVOR ein Validator sie sieht - und bei einem Tippfehler einen
    # SettingsError werfen, der nur den Feldnamen nennt. Mit NoDecode kommt
    # die Zeichenkette roh bei `_parse_json` an, und die Fehlermeldung sagt,
    # was an der Eingabe kaputt ist.
    bounding_boxes: Annotated[list[list[list[float]]], NoDecode] = Field(default_factory=list)
    # MMSI-Filter. Leer bedeutet: alle Sender im Ausschnitt. Auch als
    # kommagetrennte Liste zulaessig - eine Handvoll MMSI als JSON-Array in
    # eine Umgebungsvariable zu schreiben ist eine Zumutung.
    mmsi_filter: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # Nachrichtentypen, die abonniert werden. Leer bedeutet alle - dann
    # kommen auch die Typen, die dieser Konnektor nicht uebersetzt, und
    # werden gezaehlt und verworfen. Die Vorgabe ist deshalb die Liste, die
    # der Parser tatsaechlich beherrscht.
    message_types: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "PositionReport",
            "ShipStaticData",
            "StandardClassBPositionReport",
            "ExtendedClassBPositionReport",
            "AidsToNavigationReport",
            "StaticDataReport",
        ]
    )

    # --- Verbindung ---------------------------------------------------
    connect_timeout_s: float = 10.0
    # Kommt ueber diese Zeit keine einzige Nachricht, gilt die Verbindung als
    # tot. AISStream sendet im Weltausschnitt mehrere hundert Nachrichten pro
    # Sekunde; eine Minute Stille ist bereits ein starkes Signal. Bei engen
    # Boundingboxen muss der Wert hoch gesetzt werden - sonst baut der
    # Konnektor die Verbindung ab, weil in seinem Ausschnitt nachts nichts
    # faehrt.
    idle_timeout_s: float = 60.0
    # WebSocket-Ping. Haelt Zwischenknoten davon ab, die Leitung als untaetig
    # zu schliessen, und erkennt einen Abbruch ohne Close-Frame.
    ping_interval_s: float = 20.0
    ping_timeout_s: float = 20.0

    # Wiederverbindung: exponentiell mit Vollem Jitter, gedeckelt.
    reconnect_base_delay_s: float = 0.5
    reconnect_max_delay_s: float = 30.0
    # Akzeptanzkriterium der Aufgabenstellung: Wiederherstellung in unter
    # 30 Sekunden. Der Deckel oben ist deshalb kein Zufallswert.
    reconnect_max_attempts: int = -1  # unbegrenzt

    # --- Puffer und Stapel --------------------------------------------
    # Warteschlange zwischen WebSocket-Leser und Verarbeitung. Der Leser darf
    # nie blockieren: blockiert er, wachsen die Puffer im Kernel und in der
    # Bibliothek, und aus Rueckstau wird ein Speicherleck. Ist die
    # Warteschlange voll, wird das AELTESTE verworfen und gezaehlt.
    queue_size: int = 20_000
    # Hoechstzahl Nachrichten je Stapel. Groesser = weniger Overhead pro
    # Nachricht, aber mehr Doppelzustellung nach einem Absturz.
    max_batch_size: int = 2_000
    # Laengste Wartezeit auf einen vollen Stapel. Bei ruhiger Quelle
    # entscheidet dieser Wert ueber die Latenz, nicht der Durchsatz.
    max_batch_wait_s: float = 1.0

    # --- Plausibilitaet ------------------------------------------------
    # Implizite Geschwindigkeit zwischen zwei Positionen derselben MMSI,
    # oberhalb derer ein Sprung angenommen wird. 100 kn liegt weit ueber
    # jedem Schiff und unter dem, was ein vertauschter Sender erzeugt.
    max_implied_speed_kn: float = 100.0
    # Zahl der MMSI, fuer die die letzte Position vorgehalten wird. Begrenzt,
    # weil dieser Speicher sonst in einem 24-Stunden-Lauf mitwaechst - der
    # klassische Weg, wie ein Konnektor sein Speicherbudget verliert.
    position_history_size: int = 100_000

    @field_validator("bounding_boxes", "mmsi_filter", "message_types", mode="before")
    @classmethod
    def _parse_json(cls, value: Any) -> Any:
        """Listen kommen aus der Umgebung als JSON-Zeichenkette.

        pydantic-settings macht das fuer verschachtelte Modelle von selbst,
        fuer einfache Listen aber nicht zuverlaessig - und eine Boundingbox,
        die still als einelementige Liste mit einer Zeichenkette ankommt,
        faellt erst beim Abonnieren auf.
        """
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith(("[", "{")):
                try:
                    return json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Kein gueltiges JSON: {exc}") from exc
            return [part.strip() for part in text.split(",") if part.strip()]
        return value

    @field_validator("bounding_boxes")
    @classmethod
    def _check_boxes(cls, boxes: list[list[list[float]]]) -> list[list[list[float]]]:
        for index, box in enumerate(boxes):
            if len(box) != 2 or any(len(corner) != 2 for corner in box):
                raise ValueError(
                    f"Boundingbox {index} hat nicht die Form "
                    "[[lat_min, lon_min], [lat_max, lon_max]]"
                )
            (lat1, lon1), (lat2, lon2) = box
            if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90):
                raise ValueError(f"Boundingbox {index}: Breite ausserhalb -90..90")
            if not (-180 <= lon1 <= 180 and -180 <= lon2 <= 180):
                raise ValueError(f"Boundingbox {index}: Laenge ausserhalb -180..180")
            if lat1 >= lat2:
                # Vertauschte Ecken sind der haeufigste Konfigurationsfehler
                # und liefern schweigend null Nachrichten.
                raise ValueError(
                    f"Boundingbox {index}: erste Ecke muss die suedwestliche sein "
                    f"(lat {lat1} >= lat {lat2})"
                )
        return boxes

    @model_validator(mode="after")
    def _check_types(self) -> AisStreamSettings:
        from aisstream.parser import SUPPORTED_TYPES

        unknown = [t for t in self.message_types if t not in SUPPORTED_TYPES]
        if unknown:
            raise ValueError(
                f"Nicht unterstuetzte Nachrichtentypen im Abonnement: {', '.join(unknown)}. "
                f"Unterstuetzt: {', '.join(sorted(SUPPORTED_TYPES))}"
            )
        return self

    def subscription(self) -> dict[str, Any]:
        """Die Abonnementnachricht, wie AISStream sie erwartet.

        Wird nach JEDER Verbindung neu gesendet - AISStream haelt kein
        Abonnement ueber einen Verbindungsabbruch hinweg, und eine
        wiederhergestellte Verbindung ohne Abonnement ist eine Leitung, ueber
        die nie wieder etwas kommt. Der Fehler sieht aus wie eine stille
        Quelle und ist keiner.
        """
        message: dict[str, Any] = {"APIKey": self.api_key.get_secret_value()}
        # AISStream verlangt das Feld auch dann, wenn weltweit abonniert wird.
        message["BoundingBoxes"] = self.bounding_boxes or [[[-90.0, -180.0], [90.0, 180.0]]]
        if self.mmsi_filter:
            message["FiltersShipMMSI"] = self.mmsi_filter
        if self.message_types:
            message["FilterMessageTypes"] = self.message_types
        return message

    def redacted_subscription(self) -> dict[str, Any]:
        """Dieselbe Nachricht fuer das Protokoll, ohne Schluessel."""
        message = self.subscription()
        message["APIKey"] = "***"
        return message
