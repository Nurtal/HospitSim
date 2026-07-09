"""Smoke test de l'ETL Synthea->OMOP->calibration->validation."""

import importlib.util
from pathlib import Path

_EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "synthea_omop_etl.py"


def _load():
    spec = importlib.util.spec_from_file_location("synthea_omop_etl", _EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_etl_recovers_ground_truth_and_validates_los():
    etl = _load()
    dataset, synthetic = etl.load_or_generate(None)
    assert synthetic is True

    patients, routing, mean_los, stays = etl.calibrate(dataset)
    assert len(patients) == 600
    assert len(stays) > len(patients)  # plusieurs séjours par patient

    # Récupération des transitions ED (± 0.06).
    for dest, truth in etl.GROUND_TRUTH_TRANSITIONS["ED"].items():
        assert abs(routing["ED"].get(dest, 0.0) - truth) < 0.06

    # La validation KS tourne et ne rejette pas l'hypothèse exponentielle
    # (vérité-terrain exponentielle) pour chaque service.
    report = etl.validate_length_of_stay(stays, mean_los)
    assert set(report) >= {"ED", "Ward", "ICU"}
    for svc, r in report.items():
        assert 0.0 <= r["p_value"] <= 1.0
        assert r["exponential_ok"] is True
