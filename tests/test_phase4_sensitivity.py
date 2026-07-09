"""Tests : analyse de sensibilité (balayage de paramètre)."""

import pytest

from hospital_simulator import Scenario, sensitivity_sweep
from hospital_simulator.scenario import _apply_parameter


def _scenario(**kwargs) -> Scenario:
    params = dict(name="sens", days=40, warmup_days=5, arrival_rate_per_day=8.0, seed=3)
    params.update(kwargs)
    return Scenario(**params)


class TestApplyParameter:
    def test_scalar_field(self):
        sc = _apply_parameter(_scenario(), "arrival_rate_per_day", 20.0)
        assert sc.arrival_rate_per_day == 20.0

    def test_capacity_entry(self):
        sc = _apply_parameter(_scenario(), "capacity:ICU", 3)
        assert sc.service_capacities["ICU"] == 3

    def test_mean_los_entry(self):
        sc = _apply_parameter(_scenario(), "mean_los:ICU", 9.0)
        assert sc.mean_los_days["ICU"] == 9.0

    def test_does_not_mutate_original(self):
        base = _scenario()
        _apply_parameter(base, "capacity:ICU", 1)
        assert base.service_capacities["ICU"] == 10  # défaut inchangé

    def test_unknown_parameter_raises(self):
        with pytest.raises(ValueError, match="non balayable"):
            _apply_parameter(_scenario(), "nope", 1)


class TestSensitivitySweep:
    def test_structure_and_points(self):
        sweep = sensitivity_sweep(
            _scenario(), "arrival_rate_per_day", [4.0, 8.0, 12.0],
            metrics=["arrivals", "ICU.mean_occupancy_rate"],
            n_replications=8,
        )
        assert sweep.parameter == "arrival_rate_per_day"
        assert len(sweep.points("arrivals")) == 3
        for pt in sweep.points("arrivals"):
            assert pt["ci_low"] <= pt["mean"] <= pt["ci_high"]

    def test_arrivals_increase_with_rate(self):
        sweep = sensitivity_sweep(
            _scenario(), "arrival_rate_per_day", [4.0, 10.0, 20.0],
            metrics=["arrivals"], n_replications=12,
        )
        means = [p["mean"] for p in sweep.points("arrivals")]
        assert means[0] < means[1] < means[2]

    def test_icu_capacity_cut_raises_saturation(self):
        sweep = sensitivity_sweep(
            _scenario(arrival_rate_per_day=14.0), "capacity:ICU", [20, 10, 5],
            metrics=["ICU.saturation_days"], n_replications=12,
        )
        sat = [p["mean"] for p in sweep.points("ICU.saturation_days")]
        assert sat[-1] >= sat[0]  # moins de lits -> plus de saturation

    def test_reproducible(self):
        kw = dict(metrics=["deaths"], n_replications=6)
        s1 = sensitivity_sweep(_scenario(), "arrival_rate_per_day", [6.0, 12.0], **kw)
        s2 = sensitivity_sweep(_scenario(), "arrival_rate_per_day", [6.0, 12.0], **kw)
        assert s1.data == s2.data

    def test_unknown_metric_raises(self):
        with pytest.raises(KeyError, match="Métrique inconnue"):
            sensitivity_sweep(_scenario(), "arrival_rate_per_day", [8.0],
                              metrics=["not_a_metric"], n_replications=3)

    def test_render_contains_parameter(self):
        sweep = sensitivity_sweep(_scenario(), "arrival_rate_per_day", [8.0],
                                  metrics=["deaths"], n_replications=3)
        assert "arrival_rate_per_day" in sweep.render()
