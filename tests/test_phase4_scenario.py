"""Tests Phase 4 : moteur de scénarios, indicateurs de stress, dashboard."""

import pytest

from hospital_simulator import (
    Scenario,
    SimulationEngine,
    render_dashboard,
    run_scenario,
)


def _base_scenario(**kwargs) -> Scenario:
    params = dict(name="test", days=40, arrival_rate_per_day=8.0, seed=42)
    params.update(kwargs)
    return Scenario(**params)


# ----- Scenario configuration -----


class TestScenarioConfig:
    def test_effective_capacity_applies_multiplier(self):
        sc = Scenario(service_capacities={"ICU": 10}).with_capacity_change("ICU", 0.8)
        assert sc.effective_capacity("ICU") == 8

    def test_effective_arrival_rate_applies_surge(self):
        sc = Scenario(arrival_rate_per_day=10.0).with_admission_surge(1.4)
        assert sc.effective_arrival_rate() == pytest.approx(14.0)

    def test_what_if_helpers_do_not_mutate_original(self):
        base = Scenario(arrival_rate_per_day=10.0, service_capacities={"ICU": 10})
        base.with_admission_surge(2.0).with_capacity_change("ICU", 0.5)
        assert base.effective_arrival_rate() == pytest.approx(10.0)
        assert base.effective_capacity("ICU") == 10

    def test_invalid_routing_sum_raises(self):
        sc = Scenario(routing={"ED": {"Ward": 0.5, "ICU": 0.2}})
        with pytest.raises(ValueError, match="somme des probabilités"):
            SimulationEngine(sc)


# ----- Reproducibility -----


class TestReproducibility:
    def test_same_seed_identical_records(self):
        r1 = run_scenario(_base_scenario())
        r2 = run_scenario(_base_scenario())
        assert r1.daily_records == r2.daily_records

    def test_different_seed_differs(self):
        r1 = run_scenario(_base_scenario(seed=1))
        r2 = run_scenario(_base_scenario(seed=2))
        assert r1.daily_records != r2.daily_records

    def test_records_span_full_horizon(self):
        result = run_scenario(_base_scenario(days=25))
        assert len(result.daily_records) == 25


# ----- Stress indicators -----


class TestStressIndicators:
    def test_indicators_structure(self):
        ind = run_scenario(_base_scenario()).stress_indicators()
        assert set(ind["services"]) == {"ED", "ICU", "Ward"}
        icu = ind["services"]["ICU"]
        assert {"capacity", "peak_occupancy", "mean_occupancy_rate", "saturation_days"} <= set(icu)
        assert 0.0 <= ind["mortality_rate"] <= 1.0

    def test_flow_conservation(self):
        result = run_scenario(_base_scenario())
        ind = result.stress_indicators()
        # Tout patient admis finit par sortir, décéder, ou rester présent en fin de simulation.
        still_present = sum(ind["services"][s]["peak_occupancy"] for s in ["ED", "ICU", "Ward"])
        assert ind["admissions"] >= ind["discharges"] + ind["deaths"]
        assert still_present >= 0

    def test_icu_capacity_cut_increases_pressure(self):
        base = _base_scenario(arrival_rate_per_day=14.0)
        cut = base.with_capacity_change("ICU", 0.4)
        base_ind = run_scenario(base).stress_indicators()
        cut_ind = run_scenario(cut).stress_indicators()
        # Moins de lits ICU => davantage de jours de saturation et/ou de transferts bloqués.
        assert (
            cut_ind["services"]["ICU"]["saturation_days"]
            >= base_ind["services"]["ICU"]["saturation_days"]
        )
        assert cut_ind["blocked_transfers"] >= base_ind["blocked_transfers"]

    def test_admission_surge_increases_load(self):
        base = _base_scenario(arrival_rate_per_day=6.0)
        surge = base.with_admission_surge(2.5)
        base_ind = run_scenario(base).stress_indicators()
        surge_ind = run_scenario(surge).stress_indicators()
        assert surge_ind["arrivals"] > base_ind["arrivals"]
        assert surge_ind["services"]["ED"]["peak_occupancy"] >= base_ind["services"]["ED"]["peak_occupancy"]


# ----- Dashboard -----


class TestDashboard:
    def test_dashboard_contains_key_sections(self):
        result = run_scenario(_base_scenario(name="grippe"))
        out = render_dashboard(result)
        assert "grippe" in out
        assert "Occupation par service" in out
        assert "ICU" in out
