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


def plot_census_coverage(
    observed_census: list,
    simulated_bands: list,
    service: str,
    *,
    save_path=None,
):
    """Figure phare de validation : census observé vs bande d'IC 95 % simulée.

    Args:
        observed_census: valeurs de census journalier observées pour le service.
        simulated_bands: sortie de ``replicated_census`` pour ce service
            (``[[occ_rep, ...] par jour]``).
        service: nom du service.
        save_path: si fourni, enregistre la figure.
    """
    import statistics

    days = list(range(len(simulated_bands)))
    low = [_pctl(sorted(reps), 2.5) for reps in simulated_bands]
    high = [_pctl(sorted(reps), 97.5) for reps in simulated_bands]
    med = [statistics.median(reps) for reps in simulated_bands]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.fill_between(days, low, high, color="#1f77b4", alpha=0.2, label="IC 95 % simulé")
    ax.plot(days, med, color="#1f77b4", label="médiane simulée")
    # Census observé : histogramme horizontal en marge (distribution).
    ax.axhline(statistics.median(observed_census), color="#d62728", linestyle="--",
               label="médiane observée")
    obs_sorted = sorted(observed_census)
    ax.axhspan(_pctl(obs_sorted, 2.5), _pctl(obs_sorted, 97.5), color="#d62728", alpha=0.10,
               label="IC 95 % observé")
    ax.set_xlabel("Jour de simulation")
    ax.set_ylabel(f"Census — {service}")
    ax.set_title(f"Validation du census — {service}")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    return _finish(fig, save_path)


def _pctl(sorted_values, pct):
    """Percentile par interpolation (échantillon trié)."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    import math
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lo = int(math.floor(rank))
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = rank - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def plot_los_fit(observed, mean: float, service: str, *, ks_d=None, wasserstein=None, save_path=None):
    """Validation de la LOS : ECDF observée vs CDF exponentielle ajustée (moyenne)."""
    import math

    s = sorted(observed)
    n = len(s)
    ecdf_y = [(i + 1) / n for i in range(n)]
    xmax = max(s) if s else 1.0
    grid = [xmax * t / 200.0 for t in range(201)]
    exp_y = [1.0 - math.exp(-x / mean) for x in grid] if mean > 0 else [0] * len(grid)

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.step(s, ecdf_y, where="post", color="#d62728", label="ECDF observée")
    ax.plot(grid, exp_y, color="#1f77b4", label=f"exponentielle (moy={mean:.2f}j)")
    ann = []
    if ks_d is not None:
        ann.append(f"KS D={ks_d:.3f}")
    if wasserstein is not None:
        ann.append(f"W1={wasserstein:.2f}j")
    if ann:
        ax.text(0.97, 0.05, "  ".join(ann), transform=ax.transAxes, ha="right",
                fontsize=9, bbox=dict(boxstyle="round", fc="white", alpha=0.7))
    ax.set_xlabel("Durée de séjour (jours)")
    ax.set_ylabel("F(x)")
    ax.set_title(f"Ajustement de la durée de séjour — {service}")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    return _finish(fig, save_path)


def plot_arrival_fit(daily_counts, *, save_path=None):
    """Validation du processus d'arrivée : histogramme observé vs pmf de Poisson."""
    import math
    import statistics
    from collections import Counter

    counts = list(daily_counts)
    n = len(counts)
    lam = statistics.fmean(counts) if counts else 0.0
    kmax = max(counts) if counts else 0
    freq = Counter(counts)
    ks = list(range(kmax + 1))
    obs = [freq.get(k, 0) / n for k in ks]
    pois = [math.exp(-lam) * lam ** k / math.factorial(k) for k in ks]
    index = (statistics.variance(counts) / lam) if (n > 1 and lam) else float("nan")

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(ks, obs, width=0.6, color="#4c72b0", alpha=0.7, label="observé")
    ax.plot(ks, pois, "o-", color="#dd8452", label=f"Poisson (λ={lam:.2f})")
    ax.text(0.97, 0.9, f"dispersion={index:.2f}", transform=ax.transAxes, ha="right",
            fontsize=9, bbox=dict(boxstyle="round", fc="white", alpha=0.7))
    ax.set_xlabel("Arrivées par jour")
    ax.set_ylabel("Fréquence")
    ax.set_title("Processus d'arrivée : observé vs Poisson")
    ax.legend(fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)
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
