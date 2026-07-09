"""Smoke test de l'exemple end-to-end OMOP -> calibration -> scénario."""

import importlib.util
from pathlib import Path

_EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "omop_to_scenario.py"


def _load_example():
    spec = importlib.util.spec_from_file_location("omop_to_scenario", _EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pipeline_recovers_ground_truth_and_runs():
    ex = _load_example()
    dataset = ex.build_synthetic_omop(n_patients=400, seed=0)
    patients, routing, mean_los = ex.calibrate(dataset)

    assert len(patients) == 400
    # La calibration doit retrouver la vérité-terrain des transitions ED (± 0.08).
    for dest, truth in ex.GROUND_TRUTH_TRANSITIONS["ED"].items():
        assert abs(routing["ED"].get(dest, 0.0) - truth) < 0.08

    scenario = ex.build_scenario(routing, mean_los, seed=1)
    summary = ex.run_replications(scenario, 5).summary()
    assert "ICU.mean_occupancy_rate" in summary
    assert summary["admissions"]["ci_low"] <= summary["admissions"]["ci_high"]
