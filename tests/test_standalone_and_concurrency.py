"""Tests : peak_concurrency et smoke du standalone hdts.py."""

import importlib.util
from pathlib import Path

from hospital_simulator import peak_concurrency

_HDTS = Path(__file__).resolve().parents[1] / "hdts.py"


def test_peak_concurrency_counts_overlaps():
    stays = [
        {"service": "ICU", "start": "2023-01-01", "end": "2023-01-05"},
        {"service": "ICU", "start": "2023-01-02", "end": "2023-01-06"},  # chevauche
        {"service": "ICU", "start": "2023-01-07", "end": "2023-01-09"},  # disjoint
        {"service": "ED", "start": "2023-01-01", "end": "2023-01-02"},
    ]
    peaks = peak_concurrency(stays)
    assert peaks["ICU"] == 2
    assert peaks["ED"] == 1


def test_peak_concurrency_adjacent_intervals_do_not_stack():
    stays = [
        {"service": "ED", "start": "2023-01-01", "end": "2023-01-05"},
        {"service": "ED", "start": "2023-01-05", "end": "2023-01-08"},  # départ = arrivée
    ]
    assert peak_concurrency(stays)["ED"] == 1


def _load_hdts():
    spec = importlib.util.spec_from_file_location("hdts", _HDTS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_standalone_runs_synthetic_and_writes_report(tmp_path):
    hdts = _load_hdts()
    rc = hdts.main([
        "--no-synthea", "--patients", "150", "--replications", "4",
        "--output", str(tmp_path),
    ])
    assert rc == 0
    report = tmp_path / "report.txt"
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "HDTS" in text
    assert "Validation séjour exponentiel" in text
    assert "WHAT-IF" in text


def test_standalone_validate_writes_validation_report(tmp_path):
    hdts = _load_hdts()
    rc = hdts.main([
        "--no-synthea", "--patients", "200", "--replications", "5",
        "--validate", "--output", str(tmp_path),
    ])
    assert rc == 0
    vreport = tmp_path / "validation_report.txt"
    assert vreport.exists()
    text = vreport.read_text(encoding="utf-8")
    assert "rapport de VALIDATION" in text
    assert "Couverture d'IC" in text
    assert "dispersion de Poisson" in text
    assert "markovienne" in text
