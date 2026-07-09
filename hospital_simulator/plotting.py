"""Figures matplotlib pour l'analyse et les articles (extra optionnel ``viz``).

Ce module n'est **pas** importé au chargement du package afin que le cœur reste
sans dépendance lourde. Il faut l'importer explicitement ::

    from hospital_simulator.plotting import plot_sensitivity

et installer l'extra ``viz`` (``pip install 'hospital_simulator[viz]'``).

Toutes les fonctions renvoient une figure matplotlib et, si ``save_path`` est
fourni, l'enregistrent (utile en environnement sans affichage / CI).
"""

from __future__ import annotations

try:
    import matplotlib.pyplot as plt
except ImportError as exc:  # pragma: no cover - dépend de l'environnement
    raise ImportError(
        "Le rendu graphique nécessite matplotlib : "
        "pip install 'hospital_simulator[viz]'."
    ) from exc

from hospital_simulator.scenario import SensitivitySweepResult, SimulationResult


def _finish(fig, save_path):
    """Enregistre la figure si un chemin est donné, puis la renvoie."""
    if save_path is not None:
        fig.savefig(save_path, bbox_inches="tight", dpi=150)
    return fig


def plot_sensitivity(
    sweep: SensitivitySweepResult,
    metric: str,
    *,
    ax=None,
    save_path=None,
):
    """Trace une métrique en fonction du paramètre balayé, avec bande d'IC.

    Args:
        sweep: Résultat de :func:`~hospital_simulator.scenario.sensitivity_sweep`.
        metric: Métrique à tracer (doit figurer dans ``sweep.metrics``).
        ax: Axe matplotlib existant (optionnel).
        save_path: Si fourni, enregistre la figure.
    """
    points = sweep.points(metric)
    xs = [p["value"] for p in points]
    means = [p["mean"] for p in points]
    lows = [p["ci_low"] for p in points]
    highs = [p["ci_high"] for p in points]

    if ax is None:
        fig, ax = plt.subplots(figsize=(7, 4))
    else:
        fig = ax.figure

    ax.plot(xs, means, marker="o", color="#1f77b4", label=metric)
    ax.fill_between(xs, lows, highs, color="#1f77b4", alpha=0.2,
                    label=f"IC {int(sweep.confidence * 100)}%")
    ax.set_xlabel(sweep.parameter)
    ax.set_ylabel(metric)
    ax.set_title(f"Sensibilité de « {metric} » à « {sweep.parameter} »")
    ax.legend()
    ax.grid(True, alpha=0.3)
    return _finish(fig, save_path)


def plot_occupancy(
    result: SimulationResult,
    *,
    services: list[str] | None = None,
    show_capacity: bool = True,
    save_path=None,
):
    """Trace l'occupation de chaque service au cours du temps (un run).

    Args:
        result: Résultat d'une simulation.
        services: Sous-ensemble de services à tracer (par défaut : tous).
        show_capacity: Ajoute une ligne de capacité (effective) par service.
        save_path: Si fourni, enregistre la figure.
    """
    records = result.daily_records
    days = [rec["day"] for rec in records]
    scenario = result.scenario
    services = services or list(scenario.service_capacities)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for i, svc in enumerate(services):
        color = f"C{i}"
        occ = [rec["occupancy"].get(svc, 0) for rec in records]
        ax.plot(days, occ, color=color, label=svc)
        if show_capacity:
            cap = scenario.effective_capacity(svc)
            ax.axhline(cap, color=color, linestyle="--", alpha=0.4)

    if scenario.warmup_days > 0:
        ax.axvspan(0, scenario.warmup_days, color="grey", alpha=0.12, label="warm-up")

    ax.set_xlabel("Jour")
    ax.set_ylabel("Lits occupés")
    ax.set_title(f"Occupation des services — scénario « {scenario.name} »")
    ax.legend(ncol=2, fontsize=8)
    ax.grid(True, alpha=0.3)
    return _finish(fig, save_path)


def plot_stress(result: SimulationResult, *, save_path=None):
    """Trace un bar chart des taux d'occupation moyen et pic par service."""
    ind = result.stress_indicators()
    services = list(ind["services"])
    means = [ind["services"][s]["mean_occupancy_rate"] for s in services]
    peaks = [ind["services"][s]["peak_occupancy_rate"] for s in services]

    x = range(len(services))
    width = 0.38
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar([i - width / 2 for i in x], means, width, label="moyenne", color="#4c72b0")
    ax.bar([i + width / 2 for i in x], peaks, width, label="pic", color="#dd8452")
    ax.axhline(100, color="red", linestyle="--", alpha=0.5, label="capacité")
    ax.set_xticks(list(x))
    ax.set_xticklabels(services)
    ax.set_ylabel("Taux d'occupation (%)")
    ax.set_title(f"Stress par service — scénario « {ind['scenario']} »")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    return _finish(fig, save_path)
