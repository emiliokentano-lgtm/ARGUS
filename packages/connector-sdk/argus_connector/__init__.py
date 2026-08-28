"""ARGUS Connector SDK.

Gemeinsame Grundlage aller Datenquellen-Konnektoren. Ziel aus Kapitel 5 des
Konzepts: eine neue Quelle anzubinden darf hoechstens einen halben Tag kosten.

Ein Konnektor beschreibt nur noch, *wie* er Daten holt und in das kanonische
Schema uebersetzt. Alles andere - Cursor-Persistenz, Rate-Limiting, Backoff,
Circuit Breaker, Bronze-Archivierung, Bus-Zustellung, Metriken,
Schema-Drift-Erkennung, Kill-Switch, sauberes Herunterfahren - kommt von hier.
"""

from argus_connector.base import (
    BaseConnector,
    CanonicalMessage,
    Connector,
    ConnectorMode,
    FetchResult,
    HealthStatus,
    RawRecord,
)
from argus_connector.bronze import BronzeWriter, FilesystemObjectStore, S3ObjectStore
from argus_connector.bus import MemoryPublisher, NatsPublisher, Publisher
from argus_connector.config import ConnectorSettings
from argus_connector.cursor import (
    ChainedCursorStore,
    Cursor,
    CursorStore,
    MemoryCursorStore,
    PostgresCursorStore,
    ValkeyCursorStore,
)
from argus_connector.dedupe import DedupeKeyBuilder
from argus_connector.drift import DriftReport, SchemaDriftDetector
from argus_connector.metrics import ConnectorMetrics
from argus_connector.ratelimit import AdaptiveRateLimiter, TokenBucket
from argus_connector.retry import CircuitBreaker, CircuitOpen, RetryPolicy, retry_async
from argus_connector.runner import ConnectorRunner, RunnerState

__all__ = [
    "AdaptiveRateLimiter",
    "BaseConnector",
    "BronzeWriter",
    "CanonicalMessage",
    "ChainedCursorStore",
    "CircuitBreaker",
    "CircuitOpen",
    "Connector",
    "ConnectorMetrics",
    "ConnectorMode",
    "ConnectorRunner",
    "ConnectorSettings",
    "Cursor",
    "CursorStore",
    "DedupeKeyBuilder",
    "DriftReport",
    "FetchResult",
    "FilesystemObjectStore",
    "HealthStatus",
    "MemoryCursorStore",
    "MemoryPublisher",
    "NatsPublisher",
    "PostgresCursorStore",
    "Publisher",
    "RawRecord",
    "RetryPolicy",
    "RunnerState",
    "S3ObjectStore",
    "SchemaDriftDetector",
    "TokenBucket",
    "ValkeyCursorStore",
    "retry_async",
]

__version__ = "0.1.0"
