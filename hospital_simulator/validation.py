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
