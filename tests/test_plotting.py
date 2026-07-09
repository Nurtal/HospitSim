"""Tests des figures matplotlib (extra `viz`). Skippés si matplotlib absent."""

import pytest

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")  # backend headless avant tout import de pyplot

from hospital_simulator import Scenario, run_scenario, sensitivity_sweep  # noqa: E402
from hospital_simulator.plotting import (  # noqa: E402
    plot_occupancy,
    plot_sensitivity,
    plot_stress,
)


def _scenario() -> Scenario:
    return Scenario(name="fig", days=30, warmup_days=5, arrival_rate_per_day=10.0, seed=1)


def test_plot_occupancy_saves_file(tmp_path):
    result = run_scenario(_scenario())
    out = tmp_path / "occ.png"
    fig = plot_occupancy(result, save_path=out)
    assert out.exists() and out.stat().st_size > 0
    assert fig is not None


def test_plot_stress_saves_file(tmp_path):
    result = run_scenario(_scenario())
    out = tmp_path / "stress.png"
    plot_stress(result, save_path=out)
    assert out.exists() and out.stat().st_size > 0


def test_plot_sensitivity_saves_file(tmp_path):
    sweep = sensitivity_sweep(
        _scenario(), "arrival_rate_per_day", [6.0, 10.0, 14.0],
        metrics=["ICU.mean_occupancy_rate"], n_replications=6,
    )
    out = tmp_path / "sens.png"
    plot_sensitivity(sweep, "ICU.mean_occupancy_rate", save_path=out)
    assert out.exists() and out.stat().st_size > 0
