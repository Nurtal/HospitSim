"""Tests : multi-réplications, intervalles de confiance, warm-up."""

import pytest

from hospital_simulator import Scenario, run_replications, run_scenario


def _scenario(**kwargs) -> Scenario:
    params = dict(name="rep", days=40, arrival_rate_per_day=8.0, seed=7)
    params.update(kwargs)
    return Scenario(**params)


# ----- Warm-up -----


class TestWarmup:
    def test_warmup_shrinks_analysis_window(self):
        ind = run_scenario(_scenario(days=40, warmup_days=10)).stress_indicators()
        assert ind["days"] == 30  # 40 - 10 jours de chauffe

    def test_warmup_covering_all_falls_back_to_full(self):
        ind = run_scenario(_scenario(days=20, warmup_days=50)).stress_indicators()
        assert ind["days"] == 20

    def test_warmup_changes_flow_totals(self):
        full = run_scenario(_scenario(days=40, warmup_days=0)).stress_indicators()
        warm = run_scenario(_scenario(days=40, warmup_days=10)).stress_indicators()
        # La fenêtre plus courte compte moins d'arrivées.
        assert warm["arrivals"] <= full["arrivals"]


# ----- Replications & confidence intervals -----


class TestReplications:
    def test_reproducible_for_same_base_seed(self):
        r1 = run_replications(_scenario(), 5, base_seed=100)
        r2 = run_replications(_scenario(), 5, base_seed=100)
        assert r1.runs == r2.runs

    def test_replications_differ_across_runs(self):
        rep = run_replications(_scenario(), 5, base_seed=100)
        # Les réplications utilisent des graines distinctes -> pas toutes identiques.
        arrivals = [run["arrivals"] for run in rep.runs]
        assert len(set(arrivals)) > 1

    def test_count_and_invalid_n(self):
        assert run_replications(_scenario(), 3).n_replications == 3
        with pytest.raises(ValueError):
            run_replications(_scenario(), 0)

    def test_summary_has_ci_bracketing_mean(self):
        rep = run_replications(_scenario(), 30, base_seed=1)
        summary = rep.summary(confidence=0.95)
        assert "arrivals" in summary
        assert "ICU.mean_occupancy_rate" in summary
        for metric in summary.values():
            assert metric["ci_low"] <= metric["mean"] <= metric["ci_high"]
            assert metric["n"] == 30

    def test_single_replication_ci_collapses_to_mean(self):
        rep = run_replications(_scenario(), 1, base_seed=1)
        s = rep.summary()["arrivals"]
        assert s["ci_low"] == s["mean"] == s["ci_high"]
        assert s["std"] == 0.0

    def test_invalid_confidence_raises(self):
        rep = run_replications(_scenario(), 3)
        with pytest.raises(ValueError):
            rep.summary(confidence=1.5)

    def test_render_summary_contains_scenario_and_ci(self):
        rep = run_replications(_scenario(name="grippe"), 10, base_seed=2)
        out = rep.render_summary(metrics=["arrivals", "deaths"])
        assert "grippe" in out
        assert "10 réplications" in out
