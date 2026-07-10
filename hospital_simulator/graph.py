"""Graphe hospitalier auto-construit depuis un EDS (OMOP).

Le :class:`HospitalGraph` est l'artefact central et **inspectable** du framework :
nœuds = services (capacité, durée moyenne de séjour), arêtes = transitions
(probabilités, globales et par groupe de diagnostic), plus la distribution
d'arrivée par diagnostic et le service d'entrée.

Il est reconstruit automatiquement à partir des traces patients (approche
**« process-mining-inspired »** : découverte d'un graphe dirigé par comptage de
transitions de 1er ordre + statistiques descriptives — aucune boîte noire), et
sert à dériver un :class:`~hospital_simulator.scenario.Scenario`.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime

from hospital_simulator.omop import OmopDataset, parse_omop_date, stays_from_omop
from hospital_simulator.calibration import (
    UNKNOWN_GROUP,
    estimate_diagnosis_mix,
    estimate_length_of_stay,
    estimate_transitions_by_group,
    estimate_transition_probabilities,
    peak_concurrency,
)
from hospital_simulator.scenario import DEATH, DISCHARGE, TERMINALS, Scenario


def _service_universe(routing: dict[str, dict[str, float]]) -> list[str]:
    """Services réels : sources + destinations non terminales, ordre déterministe."""
    services: dict[str, None] = {}
    for source, row in routing.items():
        services.setdefault(source, None)
        for dest in row:
            if dest not in TERMINALS:
                services.setdefault(dest, None)
    return list(services)


def _entry_service(stays: list[dict], services: list[str]) -> str:
    """Service d'entrée = service le plus fréquent en début de trajectoire."""
    by_person: dict[str, list[dict]] = {}
    for stay in stays:
        by_person.setdefault(str(stay.get("person_id")), []).append(stay)
    firsts: dict[str, int] = {}
    for seq in by_person.values():
        seq.sort(key=lambda s: parse_omop_date(s.get("start")) or datetime.max)
        for stay in seq:
            if stay.get("service") in services:
                firsts[stay["service"]] = firsts.get(stay["service"], 0) + 1
                break
    if not firsts:
        return services[0] if services else "ED"
    return max(firsts, key=firsts.get)


def _arrival_rate(stays: list[dict], entry: str) -> float:
    """Arrivées/jour = nb d'entrées dans le service d'entrée / durée observée."""
    starts = [parse_omop_date(s.get("start")) for s in stays if s.get("service") == entry]
    starts = [d for d in starts if d is not None]
    if len(starts) < 2:
        return max(1.0, float(len(starts)))
    span_days = (max(starts) - min(starts)).total_seconds() / 86400.0
    return len(starts) / span_days if span_days > 0 else float(len(starts))


@dataclass
class HospitalGraph:
    """Modèle hospitalier explicite auto-construit depuis un EDS."""

    services: dict[str, dict] = field(default_factory=dict)  # {svc: {capacity, mean_los}}
    routing: dict[str, dict[str, float]] = field(default_factory=dict)
    routing_by_group: dict[str, dict[str, dict[str, float]]] = field(default_factory=dict)
    diagnosis_mix: dict[str, float] = field(default_factory=dict)
    entry_service: str = "ED"
    arrival_rate_per_day: float = 10.0

    def to_scenario(self, *, name: str = "calibrated", days: int = 120,
                    warmup_days: int = 20, seed: int | None = None, **overrides) -> Scenario:
        """Dérive un :class:`Scenario` du graphe (paramètres surchargables)."""
        params = dict(
            name=name,
            days=days,
            warmup_days=warmup_days,
            entry_service=self.entry_service,
            arrival_rate_per_day=round(self.arrival_rate_per_day, 2),
            service_capacities={s: v["capacity"] for s, v in self.services.items()},
            mean_los_days={s: v["mean_los"] for s, v in self.services.items()},
            routing=self.routing,
            routing_by_group=self.routing_by_group,
            diagnosis_mix=self.diagnosis_mix,
            seed=seed,
        )
        params.update(overrides)
        return Scenario(**params)

    def to_dict(self) -> dict:
        return {
            "entry_service": self.entry_service,
            "arrival_rate_per_day": round(self.arrival_rate_per_day, 4),
            "services": self.services,
            "routing": self.routing,
            "routing_by_group": self.routing_by_group,
            "diagnosis_mix": self.diagnosis_mix,
        }

    def to_json(self, **kwargs) -> str:
        """Sérialise le graphe en JSON (inspectable, éditable)."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False, **kwargs)

    def to_dot(self) -> str:
        """Exporte le graphe global en DOT (Graphviz) pour visualisation."""
        lines = ["digraph hospital {", '  rankdir=LR;', '  node [shape=box];']
        for svc, meta in self.services.items():
            lines.append(f'  "{svc}" [label="{svc}\\ncap={meta["capacity"]} '
                         f'DMS={meta["mean_los"]:.1f}j"];')
        for terminal in (DISCHARGE, DEATH):
            lines.append(f'  "{terminal}" [shape=ellipse];')
        for source, row in self.routing.items():
            for dest, prob in row.items():
                lines.append(f'  "{source}" -> "{dest}" [label="{prob:.2f}"];')
        lines.append("}")
        return "\n".join(lines)


def build_hospital_graph(
    dataset: OmopDataset,
    *,
    level: str = "category",
    capacity_factor: float = 1.3,
    group_routing: bool = True,
) -> HospitalGraph:
    """Construit automatiquement un :class:`HospitalGraph` depuis un dataset OMOP.

    Args:
        dataset: Tables OMOP (ou issues d'un adaptateur EDS/MIMIC/Synthea).
        level: granularité des groupes de diagnostic (``"category"`` / ``"chapter"``).
        capacity_factor: capacité = ``ceil(factor × pic d'occupation observé)`` (min 5).
        group_routing: active le routage conditionné au diagnostic si les données le
            permettent (sinon fallback global).
    """
    return build_hospital_graph_from_stays(
        stays_from_omop(dataset), level=level,
        capacity_factor=capacity_factor, group_routing=group_routing,
    )


def build_hospital_graph_from_stays(
    stays: list[dict],
    *,
    level: str = "category",
    capacity_factor: float = 1.3,
    group_routing: bool = True,
) -> HospitalGraph:
    """Comme :func:`build_hospital_graph` mais à partir de séjours déjà normalisés.

    Utile pour calibrer sur un sous-ensemble temporel (hold-out, back-test COVID).
    """
    routing = estimate_transition_probabilities(stays)
    mean_los = {s: st["mean"] for s, st in estimate_length_of_stay(stays).items()}
    peaks = peak_concurrency(stays)

    services_list = _service_universe(routing)
    services = {
        svc: {
            "capacity": max(5, math.ceil(capacity_factor * peaks.get(svc, 0))),
            "mean_los": round(mean_los.get(svc, 3.0), 3),
        }
        for svc in services_list
    }

    entry = _entry_service(stays, services_list)
    arrival_rate = _arrival_rate(stays, entry)

    routing_by_group: dict = {}
    diagnosis_mix: dict = {}
    if group_routing:
        mix = estimate_diagnosis_mix(stays, level=level)
        # N'activer que si le diagnostic apporte de l'information (pas tout UNKNOWN).
        if set(mix) - {UNKNOWN_GROUP}:
            diagnosis_mix = mix
            routing_by_group = estimate_transitions_by_group(stays, level=level)

    return HospitalGraph(
        services=services,
        routing=routing,
        routing_by_group=routing_by_group,
        diagnosis_mix=diagnosis_mix,
        entry_service=entry,
        arrival_rate_per_day=arrival_rate,
    )
