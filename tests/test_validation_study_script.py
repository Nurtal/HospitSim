"""Smoke test du script d'étude de validation (opérationnel + hold-out + COVID)."""

import importlib.util
from pathlib import Path

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validation_study.py"


def _load():
    spec = importlib.util.spec_from_file_location("validation_study", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validation_study_runs_and_writes_figures(tmp_path):
    study = _load()
    rc = study.main([
        "--synthetic", "--patients", "300", "--replications", "5",
        "--holdout-date", "2023-06-01", "--covid-split", "2023-04-01",
        "--output", str(tmp_path),
    ])
    assert rc == 0
    report = tmp_path / "validation_report.txt"
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "Validation opérationnelle" in text
    assert "Hold-out temporel" in text
    assert "Back-test expérience naturelle" in text
    # Figures phares présentes.
    pngs = list(tmp_path.glob("*.png"))
    names = {p.name for p in pngs}
    assert any(n.startswith("census_coverage_") for n in names)
    assert any(n.startswith("los_fit_") for n in names)
    assert "arrivals.png" in names
    assert "covid_backtest.png" in names
