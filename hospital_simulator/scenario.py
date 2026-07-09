"""Moteur de scénarios « what-if » (Phase 4 — Digital twin experiments).

Simulation à événements discrets (pas de temps journalier) d'un flux hospitalier,
pilotée par une configuration :class:`Scenario`. Le moteur assemble les briques
des phases précédentes :

    * routage inter-services (probabilités de transition, cf. Phase 2/3),
    * capacités et occupation des services (Phase 1),
    * tirages stochastiques reproductibles via une seed unique.

Il permet d'explorer des questions du type « +40 % d'admissions respiratoires »
ou « -20 % de lits en réanimation », et produit des **indicateurs de stress**
hospitalier ainsi qu'un tableau de bord texte.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace

# Devenirs terminaux (le patient quitte l'hôpital).
DISCHARGE = "Discharge"
DEATH = "Death"
TERMINALS = frozenset({DISCHARGE, DEATH})

# Tolérance sur la somme des probabilités de routage.
_ROUTING_SUM_TOLERANCE = 1e-6


def _default_capacities() -> dict[str, int]:
    return {"ED": 40, "ICU": 10, "Ward": 80}


def _default_routing() -> dict[str, dict[str, float]]:
    return {
        "ED": {"Ward": 0.70, "ICU": 0.15, DISCHARGE: 0.15},
        "ICU": {"Ward": 0.60, DISCHARGE: 0.30, DEATH: 0.10},
        "Ward": {DISCHARGE: 0.90, "ICU": 0.05, DEATH: 0.05},
    }


def _default_mean_los() -> dict[str, float]:
    return {"ED": 0.5, "ICU": 5.0, "Ward": 4.0}


def _poisson(rng: random.Random, lam: float) -> int:
    """Tire un entier selon une loi de Poisson (algorithme de Knuth)."""
    if lam <= 0:
        return 0
    limit = math.exp(-lam)
    k = 0
    product = 1.0
    while True:
        k += 1
        product *= rng.random()
        if product <= limit:
            return k - 1


@dataclass
class Scenario:
    """Configuration d'un scénario de simulation.

    Attributs :
        name: Nom du scénario.
        days: Horizon de simulation (nombre de jours).
        entry_service: Service d'admission initial (ex: "ED").
        arrival_rate_per_day: Nombre moyen d'arrivées/jour (loi de Poisson).
        admission_multiplier: Facteur multiplicatif sur les arrivées (« what-if »).
        service_capacities: Capacité de base de chaque service.
        capacity_multipliers: Facteurs multiplicatifs de capacité par service.
        routing: Probabilités de transition ``{service: {destination: proba}}``.
        mean_los_days: Durée moyenne de séjour par service (jours).
        default_los_days: DMS par défaut pour un service non listé.
        seed: Graine du générateur aléatoire (reproductibilité).
    """

    name: str = "baseline"
    days: int = 30
    entry_service: str = "ED"
    arrival_rate_per_day: float = 10.0
    admission_multiplier: float = 1.0
    service_capacities: dict[str, int] = field(default_factory=_default_capacities)
    capacity_multipliers: dict[str, float] = field(default_factory=dict)
    routing: dict[str, dict[str, float]] = field(default_factory=_default_routing)
    mean_los_days: dict[str, float] = field(default_factory=_default_mean_los)
    default_los_days: float = 3.0
    seed: int | None = None

    def effective_capacity(self, service: str) -> int:
        """Capacité effective d'un service après application du multiplicateur."""
        base = self.service_capacities.get(service, 0)
        multiplier = self.capacity_multipliers.get(service, 1.0)
        return max(0, round(base * multiplier))

    def effective_arrival_rate(self) -> float:
        """Taux d'arrivée effectif après application du multiplicateur d'admissions."""
        return max(0.0, self.arrival_rate_per_day * self.admission_multiplier)

    def mean_los(self, service: str) -> float:
        """Durée moyenne de séjour d'un service (ou la valeur par défaut)."""
        return self.mean_los_days.get(service, self.default_los_days)

    # ---- Variantes « what-if » (retournent un nouveau Scenario) ----

    def with_admission_surge(self, factor: float, *, name: str | None = None) -> "Scenario":
        """Renvoie une variante avec une hausse d'admissions (ex: 1.4 = +40 %)."""
        return replace(
            self,
            admission_multiplier=self.admission_multiplier * factor,
            name=name or f"{self.name}+admissions x{factor:g}",
        )

    def with_capacity_change(
        self, service: str, factor: float, *, name: str | None = None
    ) -> "Scenario":
        """Renvoie une variante modifiant la capacité d'un service (ex: 0.8 = -20 %)."""
        new_multipliers = dict(self.capacity_multipliers)
        new_multipliers[service] = new_multipliers.get(service, 1.0) * factor
        return replace(
            self,
            capacity_multipliers=new_multipliers,
            name=name or f"{self.name}+{service} x{factor:g}",
        )


@dataclass
class _Active:
    """État interne d'un patient actif dans un service."""

    service: str
    remaining: float


@dataclass
class SimulationResult:
    """Résultat d'une simulation : trace journalière + indicateurs agrégés."""

    scenario: Scenario
    daily_records: list[dict] = field(default_factory=list)

    def total(self, key: str) -> int:
        """Somme d'une métrique de flux sur toute la simulation."""
        return sum(record.get(key, 0) for record in self.daily_records)

    def stress_indicators(self) -> dict:
        """Calcule les indicateurs de stress hospitalier de la simulation.

        Returns:
            Un dict comprenant les totaux de flux, la mortalité, les files
            d'attente, et par service : occupation moyenne/pic (absolue et en %)
            ainsi que le nombre de jours de saturation.
        """
        services = list(self.scenario.service_capacities)
        per_service: dict[str, dict[str, float]] = {}
        for svc in services:
            capacity = self.scenario.effective_capacity(svc)
            occupancies = [rec["occupancy"].get(svc, 0) for rec in self.daily_records]
            occupancies = occupancies or [0]
            peak = max(occupancies)
            mean = sum(occupancies) / len(occupancies)
            saturation_days = sum(
                1 for o in occupancies if capacity > 0 and o >= capacity
            )
            per_service[svc] = {
                "capacity": capacity,
                "peak_occupancy": peak,
                "mean_occupancy": round(mean, 2),
                "peak_occupancy_rate": round(100 * peak / capacity, 1) if capacity else 0.0,
                "mean_occupancy_rate": round(100 * mean / capacity, 1) if capacity else 0.0,
                "saturation_days": saturation_days,
            }

        deaths = self.total("deaths")
        discharges = self.total("discharges")
        exits = deaths + discharges
        waitings = [rec["waiting"] for rec in self.daily_records] or [0]

        return {
            "scenario": self.scenario.name,
            "days": self.scenario.days,
            "arrivals": self.total("arrivals"),
            "admissions": self.total("admissions"),
            "discharges": discharges,
            "deaths": deaths,
            "blocked_transfers": self.total("blocked_transfer"),
            "mortality_rate": round(deaths / exits, 4) if exits else 0.0,
            "peak_waiting": max(waitings),
            "mean_waiting": round(sum(waitings) / len(waitings), 2),
            "services": per_service,
        }


class SimulationEngine:
    """Moteur de simulation à événements discrets d'un scénario hospitalier."""

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self._rng = random.Random(scenario.seed)
        self._validate_routing()

    def _validate_routing(self) -> None:
        for source, row in self.scenario.routing.items():
            total = sum(row.values())
            if row and abs(total - 1.0) > _ROUTING_SUM_TOLERANCE:
                raise ValueError(
                    f"Routage {source!r} : la somme des probabilités doit valoir 1.0 (reçu {total})."
                )

    def _sample_los(self, service: str) -> float:
        """Tire une durée de séjour (jours) selon une loi exponentielle."""
        mean = self.scenario.mean_los(service)
        if mean <= 0:
            return 0.0
        return self._rng.expovariate(1.0 / mean)

    def _next_destination(self, service: str) -> str:
        """Tire le devenir d'un patient quittant un service (défaut : sortie)."""
        row = self.scenario.routing.get(service)
        if not row:
            return DISCHARGE
        return self._rng.choices(list(row), weights=list(row.values()), k=1)[0]

    def run(self) -> SimulationResult:
        """Exécute la simulation et renvoie le résultat complet."""
        sc = self.scenario
        entry = sc.entry_service
        occupancy: dict[str, int] = {svc: 0 for svc in sc.service_capacities}
        active: list[_Active] = []
        waiting = 0
        rate = sc.effective_arrival_rate()
        result = SimulationResult(scenario=sc)

        for day in range(sc.days):
            arrivals = _poisson(self._rng, rate)
            waiting += arrivals
            discharges = deaths = blocked_transfer = admissions = 0

            # 1) Décrément des durées de séjour ; identifie les patients à faire transiter.
            still_active: list[_Active] = []
            transitioning: list[_Active] = []
            for pat in active:
                pat.remaining -= 1.0
                (transitioning if pat.remaining <= 0 else still_active).append(pat)
            active = still_active

            # 2) Transitions : le patient garde son lit tant qu'il ne peut pas bouger.
            for pat in transitioning:
                dest = self._next_destination(pat.service)
                if dest in TERMINALS:
                    occupancy[pat.service] -= 1
                    if dest == DEATH:
                        deaths += 1
                    else:
                        discharges += 1
                elif occupancy.get(dest, 0) < sc.effective_capacity(dest):
                    occupancy[pat.service] -= 1
                    occupancy[dest] += 1
                    active.append(_Active(dest, self._sample_los(dest)))
                else:
                    # Service cible plein : bed-blocking, nouvelle tentative demain.
                    blocked_transfer += 1
                    pat.remaining = 1.0
                    active.append(pat)

            # 3) Admissions depuis la file d'attente vers le service d'entrée.
            while waiting > 0 and occupancy[entry] < sc.effective_capacity(entry):
                occupancy[entry] += 1
                active.append(_Active(entry, self._sample_los(entry)))
                waiting -= 1
                admissions += 1

            result.daily_records.append(
                {
                    "day": day,
                    "arrivals": arrivals,
                    "admissions": admissions,
                    "discharges": discharges,
                    "deaths": deaths,
                    "blocked_transfer": blocked_transfer,
                    "waiting": waiting,
                    "occupancy": dict(occupancy),
                }
            )

        return result


def run_scenario(scenario: Scenario) -> SimulationResult:
    """Raccourci : instancie le moteur et exécute le scénario."""
    return SimulationEngine(scenario).run()
