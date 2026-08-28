"""Schema-Drift-Erkennung."""

from __future__ import annotations

from argus_connector.drift import DriftKind, SchemaDriftDetector


def _learn(detector: SchemaDriftDetector, record: dict, times: int) -> None:
    for _ in range(times):
        detector.inspect(dict(record))


class TestSchemaDriftDetector:
    def test_learning_phase_reports_nothing(self):
        detector = SchemaDriftDetector(learn_after=5)
        for i in range(5):
            assert not detector.inspect({"a": i, f"only_{i}": 1})

    def test_new_field_is_reported(self):
        detector = SchemaDriftDetector(learn_after=3)
        _learn(detector, {"a": 1}, 3)
        report = detector.inspect({"a": 1, "b": "neu"})
        assert DriftKind.NEW_FIELD in report.kinds
        assert "b" in report.summary()

    def test_type_change_is_reported(self):
        detector = SchemaDriftDetector(learn_after=3)
        _learn(detector, {"a": 1}, 3)
        report = detector.inspect({"a": "jetzt ein String"})
        assert DriftKind.TYPE_CHANGE in report.kinds

    def test_int_float_change_is_ignored(self):
        """1 und 1.0 sind fuer die Verarbeitung dasselbe."""
        detector = SchemaDriftDetector(learn_after=3)
        _learn(detector, {"a": 1}, 3)
        assert not detector.inspect({"a": 1.5})

    def test_null_is_not_a_type_change(self):
        """Fast jede Quelle liefert gelegentlich null fuer ein optionales Feld."""
        detector = SchemaDriftDetector(learn_after=3)
        _learn(detector, {"a": "x"}, 3)
        assert not detector.inspect({"a": None})

    def test_cardinality_change_is_distinguished(self):
        detector = SchemaDriftDetector(learn_after=3)
        _learn(detector, {"a": "x"}, 3)
        report = detector.inspect({"a": ["x", "y"]})
        assert DriftKind.CARDINALITY_CHANGE in report.kinds

    def test_missing_required_field_is_reported(self):
        detector = SchemaDriftDetector(learn_after=10)
        _learn(detector, {"a": 1, "b": 2}, 10)
        report = detector.inspect({"a": 1})
        assert DriftKind.MISSING_FIELD in report.kinds

    def test_optional_field_absence_is_not_reported(self):
        """Ein Feld, das schon beim Lernen oft fehlte, ist optional."""
        detector = SchemaDriftDetector(learn_after=10)
        for i in range(10):
            record = {"a": 1}
            if i < 3:
                record["sometimes"] = 1
            detector.inspect(record)
        assert not detector.inspect({"a": 1})

    def test_each_finding_is_reported_once(self):
        """Sonst erzeugt eine geaenderte Quelle eine Meldung je Datensatz."""
        detector = SchemaDriftDetector(learn_after=3)
        _learn(detector, {"a": 1}, 3)
        assert detector.inspect({"a": 1, "b": 2})
        assert not detector.inspect({"a": 1, "b": 3})
        assert not detector.inspect({"a": 1, "b": 4})

    def test_nested_fields_are_tracked(self):
        detector = SchemaDriftDetector(learn_after=3)
        _learn(detector, {"meta": {"id": "x"}}, 3)
        report = detector.inspect({"meta": {"id": "x", "extra": 1}})
        assert any("meta.extra" in f.path for f in report.findings)

    def test_state_round_trip_keeps_the_learned_shape(self):
        """Ein Neustart darf nicht neu lernen - sonst meldet der Konnektor nach
        jedem Deployment die halbe Quelle als Drift."""
        detector = SchemaDriftDetector(learn_after=3)
        _learn(detector, {"a": 1}, 3)
        restored = SchemaDriftDetector.from_state(detector.state(), learn_after=3)
        assert not restored.is_learning
        assert DriftKind.NEW_FIELD in restored.inspect({"a": 1, "b": 2}).kinds

    def test_deep_nesting_is_bounded(self):
        """Eine selbstaehnliche Struktur darf den Detektor nicht sprengen."""
        record: dict = {"level": 0}
        node = record
        for i in range(1, 30):
            node["child"] = {"level": i}
            node = node["child"]
        detector = SchemaDriftDetector(learn_after=1)
        detector.inspect(record)
        assert max(p.count(".") for p in detector.shape) < 10

    def test_non_mapping_records_are_skipped(self):
        """Ein blosser Wert oder eine Liste auf oberster Ebene hat keine
        Felder, die man vergleichen koennte - das ist keine Drift."""
        detector = SchemaDriftDetector(learn_after=1)
        assert not detector.inspect([1, 2, 3])
        assert not detector.inspect("text")
        assert not detector.inspect(None)
        # Die gelernte Form bleibt davon unberuehrt.
        detector.inspect({"a": 1})
        assert not detector.inspect({"a": 2})
