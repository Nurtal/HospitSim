"""Tests Phase 2 : routage par diagnostic + HospitalGraph auto-construit."""

import random

import pytest

from hospital_simulator import (
    HospitalGraph,
    OmopDataset,
    Scenario,
    SimulationEngine,
    build_hospital_graph,
    diagnosis_group,
    estimate_diagnosis_mix,
    estimate_transitions_by_group,
    run_scenario,
)


# ----- Groupement de diagnostics -----


class TestDiagnosisGroup:
    def test_category_and_chapter(self):
        assert diagnosis_group("J18.9", level="category") == "J18"
        assert diagnosis_group("I21", level="category") == "I21"
        assert diagnosis_group("J18.9", level="chapter") == "J"

    def test_invalid_is_unknown(self):
        assert diagnosis_group(None) == "UNKNOWN"
        assert diagnosis_group("nope") == "UNKNOWN"


# ----- Calibration par groupe -----


def _stays_two_groups():
    # Groupe I21 -> ED->ICU ; groupe J18 -> ED->Ward.
    stays = []
    for pid in range(20):
        stays += [
            {"person_id": f"a{pid}", "service": "ED", "start": "2023-01-01", "end": "2023-01-01",
             "diagnosis": "I21"},
            {"person_id": f"a{pid}", "service": "ICU", "start": "2023-01-02", "end": "2023-01-05",
             "diagnosis": "I21"},
        ]
    for pid in range(20):
        stays += [
            {"person_id": f"b{pid}", "service": "ED", "start": "2023-01-01", "end": "2023-01-01",
             "diagnosis": "J18.9"},
            {"person_id": f"b{pid}", "service": "Ward", "start": "2023-01-02", "end": "2023-01-06",
             "diagnosis": "J18.9"},
        ]
    return stays


class TestGroupCalibration:
    def test_transitions_differ_by_group(self):
        by_group = estimate_transitions_by_group(_stays_two_groups())
        assert by_group["I21"]["ED"] == {"ICU": 1.0}
        assert by_group["J18"]["ED"] == {"Ward": 1.0}

    def test_diagnosis_mix_is_balanced(self):
        mix = estimate_diagnosis_mix(_stays_two_groups())
        assert mix["I21"] == pytest.approx(0.5)
        assert mix["J18"] == pytest.approx(0.5)


# ----- Moteur : routage conditionné + fallback + rétro-compat -----


class TestEngineGroupRouting:
    def test_group_routing_directs_by_diagnosis(self):
        sc = Scenario(
            name="grp", days=60, warmup_days=10, arrival_rate_per_day=8.0, seed=1,
            service_capacities={"ED": 50, "ICU": 50, "Ward": 50},
            routing={"ED": {"ICU": 0.5, "Ward": 0.5}, "ICU": {"Discharge": 1.0},
                     "Ward": {"Discharge": 1.0}},
            diagnosis_mix={"I21": 0.5, "J18": 0.5},
            routing_by_group={
                "I21": {"ED": {"ICU": 1.0}, "ICU": {"Discharge": 1.0}},
                "J18": {"ED": {"Ward": 1.0}, "Ward": {"Discharge": 1.0}},
            },
        )
        ind = run_scenario(sc).stress_indicators()
        # I21 -> ICU, J18 -> Ward : les deux services sont utilisés de façon marquée.
        assert ind["services"]["ICU"]["peak_occupancy"] > 0
        assert ind["services"]["Ward"]["peak_occupancy"] > 0

    def test_backward_compatible_without_groups(self):
        # Sans diagnosis_mix/routing_by_group : comportement inchangé (déterministe).
        base = dict(name="bc", days=40, arrival_rate_per_day=8.0, seed=3)
        r1 = run_scenario(Scenario(**base)).daily_records
        r2 = run_scenario(Scenario(**base)).daily_records
        assert r1 == r2

    def test_invalid_group_routing_sum_raises(self):
        sc = Scenario(
            routing_by_group={"I21": {"ED": {"ICU": 0.5, "Ward": 0.2}}},
        )
        with pytest.raises(ValueError, match="somme des probabilités"):
            SimulationEngine(sc)


# ----- HospitalGraph auto-construit -----


def _omop_two_pathways(n=40):
    from datetime import datetime, timedelta
    rng = random.Random(0)
    person, cond, visits = [], [], []
    for sid in range(1, n + 1):
        infarction = sid % 2 == 0
        code = "I21" if infarction else "J18.9"
        second = "ICU" if infarction else "Ward"
        person.append({"person_id": sid, "gender_concept_id": "8507", "year_of_birth": "1950"})
        cond.append({"person_id": sid, "condition_source_value": code,
                     "condition_status_source_value": "primary", "condition_start_date": "2023-01-01"})
        t = datetime(2023, 1, 1) + timedelta(days=rng.randint(0, 60))
        for svc, los in (("ED", 0.5), (second, 4.0)):
            end = t + timedelta(days=los)
            visits.append({"person_id": sid, "visit_source_value": svc,
                           "visit_start_date": t.isoformat(), "visit_end_date": end.isoformat()})
            t = end
    return OmopDataset(person=person, condition_occurrence=cond, visit_occurrence=visits)


class TestHospitalGraph:
    def test_build_graph_activates_diagnosis_routing(self):
        graph = build_hospital_graph(_omop_two_pathways())
        assert isinstance(graph, HospitalGraph)
        assert graph.entry_service == "ED"
        assert set(graph.diagnosis_mix) >= {"I21", "J18"}
        # I21 va en ICU, J18 va en Ward.
        assert graph.routing_by_group["I21"]["ED"].get("ICU", 0) > 0.5
        assert graph.routing_by_group["J18"]["ED"].get("Ward", 0) > 0.5

    def test_to_scenario_and_json_dot(self):
        graph = build_hospital_graph(_omop_two_pathways())
        sc = graph.to_scenario(seed=1)
        assert sc.diagnosis_mix == graph.diagnosis_mix
        assert "ED" in graph.to_json()
        assert "digraph hospital" in graph.to_dot()
        run_scenario(sc)  # doit tourner sans erreur
