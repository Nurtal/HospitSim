"""Séries observées dérivées des séjours (pour la validation).

Fonctions descriptives qui transforment des séjours normalisés
(``{person_id, service, start, end}``, cf. :func:`hospital_simulator.omop.stays_from_omop`)
en séries temporelles observées : census journalier, arrivées journalières, et
découpage temporel train/test. Aucune dépendance externe.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from hospital_simulator.omop import parse_omop_date


def daily_census(stays: list[dict]) -> dict[str, dict[date, int]]:
    """Occupation journalière observée par service (nombre de patients présents/jour).

    Un patient occupe un service le jour ``d`` si ``start.date() <= d <= end.date()``.

    Returns:
        ``{service: {date: nombre_de_patients}}`` (jours contigus, zéros inclus).
    """
    # Incréments +1 à l'entrée, -1 au lendemain de la sortie, puis somme cumulée.
    deltas: dict[str, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    spans: dict[str, list[date]] = {}
    for stay in stays:
        service = stay.get("service")
        start = parse_omop_date(stay.get("start"))
        end = parse_omop_date(stay.get("end"))
        if not service or start is None or end is None:
            continue
        sd, ed = start.date(), end.date()
        if ed < sd:
            continue
        deltas[service][sd] += 1
        deltas[service][ed + timedelta(days=1)] -= 1
        lo, hi = spans.setdefault(service, [sd, ed])
        spans[service] = [min(lo, sd), max(hi, ed)]

    census: dict[str, dict[date, int]] = {}
    for service, day_deltas in deltas.items():
        lo, hi = spans[service]
        series: dict[date, int] = {}
        current = 0
        day = lo
        while day <= hi:
            current += day_deltas.get(day, 0)
            series[day] = current
            day += timedelta(days=1)
        census[service] = series
    return census


def census_sample(stays: list[dict]) -> dict[str, list[int]]:
    """Échantillon des valeurs de census journalier par service (pour la couverture)."""
    return {svc: list(series.values()) for svc, series in daily_census(stays).items()}


def daily_arrivals(stays: list[dict], entry_service: str) -> list[int]:
    """Nombre d'arrivées par jour dans le service d'entrée (pour tester la loi d'arrivée)."""
    counts: dict[date, int] = defaultdict(int)
    starts = []
    for stay in stays:
        if stay.get("service") != entry_service:
            continue
        start = parse_omop_date(stay.get("start"))
        if start is None:
            continue
        counts[start.date()] += 1
        starts.append(start.date())
    if not starts:
        return []
    lo, hi = min(starts), max(starts)
    series, day = [], lo
    while day <= hi:
        series.append(counts.get(day, 0))
        day += timedelta(days=1)
    return series


def temporal_split(stays: list[dict], split_date) -> tuple[list[dict], list[dict]]:
    """Sépare les séjours en (train, test) selon la date de début (< / >= split_date)."""
    split = parse_omop_date(split_date)
    train, test = [], []
    for stay in stays:
        start = parse_omop_date(stay.get("start"))
        if start is None:
            continue
        (train if start < split else test).append(stay)
    return train, test
