"""Deterministische Idempotenzschluessel."""

from __future__ import annotations

import pytest

from argus_connector.dedupe import DedupeKeyBuilder


class TestDedupeKeyBuilder:
    def test_same_input_same_key(self):
        builder = DedupeKeyBuilder("aisstream", ("mmsi", "timestamp"))
        record = {"mmsi": 211234560, "timestamp": "2026-08-28T09:14:03Z", "lat": 25.9}
        assert builder.build(record) == builder.build(dict(record))

    def test_key_is_stable_across_key_order(self):
        """Zwei Prozesse duerfen nicht wegen der Reihenfolge im Dict
        unterschiedliche Schluessel erzeugen."""
        builder = DedupeKeyBuilder("s", ("a", "b"))
        assert builder.build({"a": 1, "b": 2}) == builder.build({"b": 2, "a": 1})

    def test_irrelevant_fields_do_not_change_the_key(self):
        """Genau der Sinn der Feldauswahl: ein wechselndes Empfangsfeld darf
        nicht zu einer neuen Nachricht fuehren."""
        builder = DedupeKeyBuilder("s", ("mmsi", "timestamp"))
        base = {"mmsi": 1, "timestamp": "t"}
        assert builder.build(base) == builder.build({**base, "received_by": "station-7"})

    def test_relevant_change_changes_the_key(self):
        builder = DedupeKeyBuilder("s", ("mmsi", "timestamp"))
        assert builder.build({"mmsi": 1, "timestamp": "t1"}) != builder.build(
            {"mmsi": 1, "timestamp": "t2"}
        )

    def test_prefix_is_visible(self):
        builder = DedupeKeyBuilder("gdelt", ("id",))
        assert builder.build({"id": 5}).startswith("gdelt:")

    def test_nested_paths(self):
        builder = DedupeKeyBuilder("s", ("meta.id", "position.lat"))
        key = builder.build({"meta": {"id": "x"}, "position": {"lat": 1.5}})
        assert key == builder.build({"meta": {"id": "x"}, "position": {"lat": 1.5, "lon": 9}})

    def test_list_index_paths(self):
        builder = DedupeKeyBuilder("s", ("items.0.id",))
        assert builder.build({"items": [{"id": "a"}, {"id": "b"}]}).startswith("s:")

    def test_missing_field_is_an_error_by_default(self):
        builder = DedupeKeyBuilder("s", ("mmsi", "timestamp"))
        with pytest.raises(KeyError, match="timestamp"):
            builder.build({"mmsi": 1})

    def test_missing_field_allowed_explicitly(self):
        builder = DedupeKeyBuilder("s", ("a", "b"), allow_missing=True)
        assert builder.build({"a": 1}).startswith("s:")

    def test_missing_fields_collide_when_allowed(self):
        """Der Preis von allow_missing, ausdruecklich festgehalten."""
        builder = DedupeKeyBuilder("s", ("a", "b"), allow_missing=True)
        assert builder.build({"a": 1}) == builder.build({"a": 1, "c": 2})

    def test_requires_at_least_one_field(self):
        with pytest.raises(ValueError, match="Feld"):
            DedupeKeyBuilder("s", ())

    def test_distinct_values_stay_distinct(self):
        """Ein Kollisionstest im Kleinen: 5000 Datensaetze, 5000 Schluessel."""
        builder = DedupeKeyBuilder("s", ("id",))
        keys = {builder.build({"id": i}) for i in range(5000)}
        assert len(keys) == 5000

    def test_type_difference_is_reflected(self):
        builder = DedupeKeyBuilder("s", ("id",))
        assert builder.build({"id": 1}) != builder.build({"id": "1"})

    def test_build_many(self):
        builder = DedupeKeyBuilder("s", ("id",))
        assert len(builder.build_many([{"id": 1}, {"id": 2}])) == 2
