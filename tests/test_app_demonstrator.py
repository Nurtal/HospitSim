"""Smoke test du démonstrateur (logique importable sans Streamlit)."""

from hospital_simulator import HospitalGraph, run_scenario
from app.hdts_app import load_dataset, scenario_from_ui


def test_load_synthetic_and_build_scenario():
    dataset, label = load_dataset("synthetic", patients=150)
    assert label == "synthétique"
    from hospital_simulator import build_hospital_graph
    graph = build_hospital_graph(dataset)
    assert isinstance(graph, HospitalGraph)

    scenario = scenario_from_ui(
        graph, seed=1, days=30, warmup_days=5,
        admission_multiplier=1.5, capacity_service=graph.entry_service,
        capacity_factor=0.8, los_multiplier=1.2,
    )
    assert scenario.admission_multiplier == 1.5
    # La what-if capacité et DMS sont appliquées.
    assert scenario.effective_capacity(graph.entry_service) >= 1
    run_scenario(scenario)  # doit tourner sans erreur


def test_scenario_from_ui_defaults_are_neutral():
    dataset, _ = load_dataset("synthetic", patients=120)
    from hospital_simulator import build_hospital_graph
    graph = build_hospital_graph(dataset)
    sc = scenario_from_ui(graph)
    assert sc.admission_multiplier == 1.0
    assert sc.mean_los_days == {s: v["mean_los"] for s, v in graph.services.items()}
