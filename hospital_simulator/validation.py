"""Validation statistique légère (Phase A — validation empirique).

Tests de Kolmogorov–Smirnov et statistiques descriptives sans dépendance
externe, pour comparer les distributions **simulées** aux distributions
**observées** (ex: durées de séjour) et pour tester les hypothèses
distributionnelles du modèle (ex: séjour exponentiel).

La p-value KS utilise la forme asymptotique (distribution de Kolmogorov avec la
correction de Stephens) ; prévoir des échantillons suffisants (n ≳ 20).
"""

from __future__ import annotations

import bisect
import math
import statistics
from typing import Callable, Sequence


def _kolmogorov_q(t: float) -> float:
    """Fonction de survie de la distribution de Kolmogorov Q(t) = P(K > t)."""
    if t <= 0.0:
        return 1.0
    total = 0.0
    for k in range(1, 101):
        term = ((-1) ** (k - 1)) * math.exp(-2.0 * k * k * t * t)
        total += term
        if abs(term) < 1e-12:
            break
    return max(0.0, min(1.0, 2.0 * total))


def describe(sample: Sequence[float]) -> dict:
    """Statistiques descriptives d'un échantillon."""
    values = list(sample)
    n = len(values)
    if n == 0:
        return {"n": 0}
    return {
        "n": n,
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "std": statistics.stdev(values) if n > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def _ecdf(sorted_sample: list[float], x: float) -> float:
    """Fonction de répartition empirique évaluée en x (fraction <= x)."""
    return bisect.bisect_right(sorted_sample, x) / len(sorted_sample)


def ks_two_sample(a: Sequence[float], b: Sequence[float]) -> tuple[float, float]:
    """Test de Kolmogorov–Smirnov à deux échantillons.

    Returns:
        ``(D, p_value)`` — statistique KS et p-value asymptotique. Une p-value
        élevée indique qu'on ne peut pas rejeter l'égalité des distributions.
    """
    sa, sb = sorted(a), sorted(b)
    n, m = len(sa), len(sb)
    if n == 0 or m == 0:
        raise ValueError("Les deux échantillons doivent être non vides.")

    d = 0.0
    for x in sorted(set(sa) | set(sb)):
        d = max(d, abs(_ecdf(sa, x) - _ecdf(sb, x)))

    en = math.sqrt(n * m / (n + m))
    p = _kolmogorov_q((en + 0.12 + 0.11 / en) * d)
    return d, p


def ks_one_sample(sample: Sequence[float], cdf: Callable[[float], float]) -> tuple[float, float]:
    """Test KS à un échantillon contre une fonction de répartition théorique ``cdf``."""
    s = sorted(sample)
    n = len(s)
    if n == 0:
        raise ValueError("L'échantillon doit être non vide.")

    d = 0.0
    for i, x in enumerate(s):
        fx = cdf(x)
        d = max(d, (i + 1) / n - fx, fx - i / n)

    en = math.sqrt(n)
    p = _kolmogorov_q((en + 0.12 + 0.11 / en) * d)
    return d, p


def ks_exponential(sample: Sequence[float], mean: float) -> tuple[float, float]:
    """Teste si ``sample`` suit une loi exponentielle de moyenne ``mean``.

    Utile pour vérifier l'hypothèse de durée de séjour exponentielle du moteur
    de simulation face aux durées réellement observées.
    """
    if mean <= 0:
        raise ValueError("mean doit être > 0.")
    lam = 1.0 / mean
    return ks_one_sample(sample, lambda x: 1.0 - math.exp(-lam * x) if x >= 0 else 0.0)


# --------------------------------------------------------------------------- #
# Métriques de validation opérationnelle (simulé vs observé)
# --------------------------------------------------------------------------- #

def _percentile(sorted_values: list[float], pct: float) -> float:
    """Percentile (interpolation linéaire) d'un échantillon déjà trié."""
    if not sorted_values:
        raise ValueError("échantillon vide")
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lo = int(math.floor(rank))
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = rank - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def ci_coverage(
    observed: Sequence[float],
    simulated: Sequence[float],
    *,
    lower_pct: float = 2.5,
    upper_pct: float = 97.5,
) -> dict:
    """Couverture des valeurs observées par l'intervalle central du simulé.

    Métrique phare de validation opérationnelle : la fraction des valeurs
    **observées** (ex: census journalier) tombant dans l'intervalle
    ``[q_lower, q_upper]`` de la distribution **simulée**. Une couverture proche
    du niveau nominal (95 %) indique que le modèle reproduit l'observé, incertitude
    comprise.

    Returns:
        ``{coverage, ci_low, ci_high, n_observed, nominal}``.
    """
    obs = list(observed)
    sim = sorted(simulated)
    if not obs or not sim:
        raise ValueError("les deux échantillons doivent être non vides.")
    low = _percentile(sim, lower_pct)
    high = _percentile(sim, upper_pct)
    inside = sum(1 for v in obs if low <= v <= high)
    return {
        "coverage": inside / len(obs),
        "ci_low": low,
        "ci_high": high,
        "n_observed": len(obs),
        "nominal": (upper_pct - lower_pct) / 100.0,
    }


def _paired(a: Sequence[float], b: Sequence[float]) -> tuple[list[float], list[float]]:
    a, b = list(a), list(b)
    if len(a) != len(b):
        raise ValueError("les séquences appariées doivent avoir la même longueur.")
    if not a:
        raise ValueError("séquences vides.")
    return a, b


def mae(observed: Sequence[float], predicted: Sequence[float]) -> float:
    """Erreur absolue moyenne entre deux séries appariées."""
    o, p = _paired(observed, predicted)
    return statistics.fmean(abs(x - y) for x, y in zip(o, p))


def mape(observed: Sequence[float], predicted: Sequence[float]) -> float:
    """Erreur absolue moyenne en pourcentage (points où l'observé est non nul)."""
    o, p = _paired(observed, predicted)
    terms = [abs(x - y) / abs(x) for x, y in zip(o, p) if x != 0]
    if not terms:
        raise ValueError("aucune valeur observée non nulle pour le MAPE.")
    return 100.0 * statistics.fmean(terms)


def bias(observed: Sequence[float], predicted: Sequence[float]) -> float:
    """Biais moyen (prédit - observé) ; >0 = surestimation."""
    o, p = _paired(observed, predicted)
    return statistics.fmean(y - x for x, y in zip(o, p))


def wasserstein_1d(a: Sequence[float], b: Sequence[float]) -> float:
    """Distance de Wasserstein-1 entre deux échantillons 1D (aire entre les ECDF).

    Nulle si les distributions sont identiques ; homogène à l'unité des données.
    """
    sa, sb = sorted(a), sorted(b)
    if not sa or not sb:
        raise ValueError("les deux échantillons doivent être non vides.")
    points = sorted(set(sa) | set(sb))
    distance = 0.0
    for x0, x1 in zip(points, points[1:]):
        fa = _ecdf(sa, x0)
        fb = _ecdf(sb, x0)
        distance += abs(fa - fb) * (x1 - x0)
    return distance


def poisson_dispersion_test(daily_counts: Sequence[int]) -> dict:
    """Teste si des comptages journaliers suivent une loi de Poisson.

    Sous Poisson, l'indice de dispersion variance/moyenne vaut 1. On l'évalue via
    une approximation normale : ``index ~ N(1, 2/(n-1))``.

    Returns:
        ``{dispersion_index, z, p_value, n, is_poisson}`` (is_poisson = p > 0.05).
    """
    counts = [c for c in daily_counts]
    n = len(counts)
    if n < 2:
        raise ValueError("il faut au moins 2 jours.")
    mean = statistics.fmean(counts)
    if mean == 0:
        raise ValueError("moyenne nulle : indice de dispersion indéfini.")
    var = statistics.variance(counts)
    index = var / mean
    z = (index - 1.0) / math.sqrt(2.0 / (n - 1))
    p = 2.0 * (1.0 - statistics.NormalDist().cdf(abs(z)))
    return {
        "dispersion_index": index,
        "z": z,
        "p_value": p,
        "n": n,
        "is_poisson": p > 0.05,
    }


def markov_order_check(stays: list[dict], *, min_context: int = 20) -> dict:
    """Audit de l'hypothèse markovienne d'ordre 1 sur les transitions de services.

    Compare, pour chaque contexte ``(précédent, courant)`` suffisamment fréquent,
    la distribution du service suivant à la distribution d'ordre 1
    ``P(suivant | courant)``. Une distance de variation totale (TV) élevée suggère
    que l'ordre 1 est insuffisant.

    Returns:
        ``{mean_tv, max_tv, n_contexts}`` (0 contexte => tv = 0).
    """
    by_person: dict[str, list[dict]] = {}
    for stay in stays:
        by_person.setdefault(str(stay.get("person_id")), []).append(stay)

    order1: dict[str, dict[str, int]] = {}
    order2: dict[tuple, dict[str, int]] = {}
    for seq in by_person.values():
        services = [s["service"] for s in sorted(seq, key=lambda s: s.get("start") or 0)
                    if s.get("service")]
        for cur, nxt in zip(services, services[1:]):
            order1.setdefault(cur, {}).setdefault(nxt, 0)
            order1[cur][nxt] += 1
        for prev, cur, nxt in zip(services, services[1:], services[2:]):
            order2.setdefault((prev, cur), {}).setdefault(nxt, 0)
            order2[(prev, cur)][nxt] += 1

    def _normalize(counts: dict[str, int]) -> dict[str, float]:
        total = sum(counts.values())
        return {k: v / total for k, v in counts.items()} if total else {}

    tvs = []
    for (prev, cur), counts in order2.items():
        if sum(counts.values()) < min_context or cur not in order1:
            continue
        d2 = _normalize(counts)
        d1 = _normalize(order1[cur])
        keys = set(d1) | set(d2)
        tv = 0.5 * sum(abs(d2.get(k, 0.0) - d1.get(k, 0.0)) for k in keys)
        tvs.append(tv)

    if not tvs:
        return {"mean_tv": 0.0, "max_tv": 0.0, "n_contexts": 0}
    return {"mean_tv": statistics.fmean(tvs), "max_tv": max(tvs), "n_contexts": len(tvs)}
