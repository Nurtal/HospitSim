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
import statistics
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
        warmup_days: Jours de chauffe (transitoire) exclus des indicateurs.
        routing_by_group: Routage optionnel conditionné au groupe de diagnostic
            ``{groupe: {service: {destination: proba}}}`` ; fallback sur ``routing``.
        diagnosis_mix: Distribution d'arrivée sur les groupes ``{groupe: proba}}``.
            Si vide, tous les patients partagent le routage global.
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
    warmup_days: int = 0
    routing_by_group: dict[str, dict[str, dict[str, float]]] = field(default_factory=dict)
    diagnosis_mix: dict[str, float] = field(default_factory=dict)
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
    group: str | None = None


@dataclass
class SimulationResult:
    """Résultat d'une simulation : trace journalière + indicateurs agrégés."""

    scenario: Scenario
    daily_records: list[dict] = field(default_factory=list)

    def analysis_records(self) -> list[dict]:
        """Enregistrements journaliers hors période de chauffe (warm-up)."""
        warmup = max(0, self.scenario.warmup_days)
        records = self.daily_records[warmup:]
        # Si la chauffe couvre toute la simulation, on retombe sur la trace complète.
        return records or self.daily_records

    def total(self, key: str) -> int:
        """Somme d'une métrique de flux (hors chauffe)."""
        return sum(record.get(key, 0) for record in self.analysis_records())

    def stress_indicators(self) -> dict:
        """Calcule les indicateurs de stress hospitalier de la simulation.

        Les indicateurs sont calculés sur la fenêtre d'analyse (période de chauffe
        ``warmup_days`` exclue).

        Returns:
            Un dict comprenant les totaux de flux, la mortalité, les files
            d'attente, et par service : occupation moyenne/pic (absolue et en %)
            ainsi que le nombre de jours de saturation.
        """
        records = self.analysis_records()
        services = list(self.scenario.service_capacities)
        per_service: dict[str, dict[str, float]] = {}
        for svc in services:
            capacity = self.scenario.effective_capacity(svc)
            occupancies = [rec["occupancy"].get(svc, 0) for rec in records] or [0]
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
        waitings = [rec["waiting"] for rec in records] or [0]

        return {
            "scenario": self.scenario.name,
            "days": len(records),
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
        def _check(row, label):
            total = sum(row.values())
            if row and abs(total - 1.0) > _ROUTING_SUM_TOLERANCE:
                raise ValueError(
                    f"Routage {label} : la somme des probabilités doit valoir 1.0 (reçu {total})."
                )

        for source, row in self.scenario.routing.items():
            _check(row, repr(source))
        for group, routing in self.scenario.routing_by_group.items():
            for source, row in routing.items():
                _check(row, f"{group!r}/{source!r}")

    def _sample_los(self, service: str) -> float:
        """Tire une durée de séjour (jours) selon une loi exponentielle."""
        mean = self.scenario.mean_los(service)
        if mean <= 0:
            return 0.0
        return self._rng.expovariate(1.0 / mean)

    def _sample_group(self) -> str | None:
        """Tire un groupe de diagnostic pour un patient à l'admission (ou None)."""
        mix = self.scenario.diagnosis_mix
        if not mix:
            return None
        return self._rng.choices(list(mix), weights=list(mix.values()), k=1)[0]

    def _next_destination(self, service: str, group: str | None = None) -> str:
        """Tire le devenir d'un patient quittant un service.

        Utilise le routage conditionné au groupe de diagnostic s'il est défini pour
        ``(group, service)``, sinon retombe sur le routage global (fallback pour les
        groupes absents ou creux). Défaut : sortie.
        """
        row = None
        if group is not None:
            row = self.scenario.routing_by_group.get(group, {}).get(service)
        if not row:
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
                dest = self._next_destination(pat.service, pat.group)
                if dest in TERMINALS:
                    occupancy[pat.service] -= 1
                    if dest == DEATH:
                        deaths += 1
                    else:
                        discharges += 1
                elif occupancy.get(dest, 0) < sc.effective_capacity(dest):
                    occupancy[pat.service] -= 1
                    occupancy[dest] += 1
                    active.append(_Active(dest, self._sample_los(dest), pat.group))
                else:
                    # Service cible plein : bed-blocking, nouvelle tentative demain.
                    blocked_transfer += 1
                    pat.remaining = 1.0
                    active.append(pat)

            # 3) Admissions depuis la file d'attente vers le service d'entrée.
            while waiting > 0 and occupancy[entry] < sc.effective_capacity(entry):
                occupancy[entry] += 1
                active.append(_Active(entry, self._sample_los(entry), self._sample_group()))
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


# --- Multi-réplications et intervalles de confiance (Phase 4 / rigueur stochastique) ---

# Métriques de flux agrégées reportées par réplication.
_FLOW_METRICS = (
    "arrivals",
    "admissions",
    "discharges",
    "deaths",
    "blocked_transfers",
    "mortality_rate",
    "peak_waiting",
    "mean_waiting",
)
# Métriques par service reportées par réplication.
_SERVICE_METRICS = (
    "mean_occupancy",
    "peak_occupancy",
    "mean_occupancy_rate",
    "peak_occupancy_rate",
    "saturation_days",
)


def _flatten_indicators(indicators: dict) -> dict[str, float]:
    """Aplati un dict d'indicateurs en un dict plat ``metric -> valeur``."""
    flat: dict[str, float] = {m: indicators[m] for m in _FLOW_METRICS}
    for service, stats in indicators["services"].items():
        for metric in _SERVICE_METRICS:
            flat[f"{service}.{metric}"] = stats[metric]
    return flat


@dataclass
class ReplicatedResult:
    """Résultats de plusieurs réplications indépendantes d'un même scénario."""

    scenario: Scenario
    runs: list[dict] = field(default_factory=list)

    @property
    def n_replications(self) -> int:
        return len(self.runs)

    def summary(self, confidence: float = 0.95) -> dict[str, dict[str, float]]:
        """Agrège les réplications : moyenne, écart-type et intervalle de confiance.

        L'intervalle de confiance utilise une approximation normale
        (``moyenne ± z · erreur-type``) ; prévoir n ≳ 30 réplications pour une
        bonne validité. Avec une seule réplication, l'IC se réduit à la moyenne.

        Args:
            confidence: Niveau de confiance de l'IC (défaut 0.95).

        Returns:
            Un dict ``metric -> {mean, std, sem, ci_low, ci_high, n, confidence}``.
        """
        if not 0.0 < confidence < 1.0:
            raise ValueError("confidence doit être dans ]0, 1[.")
        if not self.runs:
            return {}

        flats = [_flatten_indicators(run) for run in self.runs]
        z = statistics.NormalDist().inv_cdf(1.0 - (1.0 - confidence) / 2.0)

        summary: dict[str, dict[str, float]] = {}
        for metric in flats[0]:
            values = [flat[metric] for flat in flats]
            n = len(values)
            mean = statistics.fmean(values)
            std = statistics.stdev(values) if n > 1 else 0.0
            sem = std / math.sqrt(n) if n > 1 else 0.0
            margin = z * sem
            summary[metric] = {
                "mean": round(mean, 4),
                "std": round(std, 4),
                "sem": round(sem, 4),
                "ci_low": round(mean - margin, 4),
                "ci_high": round(mean + margin, 4),
                "n": n,
                "confidence": confidence,
            }
        return summary

    def render_summary(self, confidence: float = 0.95, metrics: list[str] | None = None) -> str:
        """Rend un tableau texte des métriques agrégées avec IC (pour un article)."""
        stats = self.summary(confidence=confidence)
        keys = metrics if metrics is not None else list(stats)
        header = (
            f"Scénario '{self.scenario.name}' — {self.n_replications} réplications "
            f"(IC {int(confidence * 100)}%)"
        )
        lines = [header, "-" * len(header)]
        width = max((len(k) for k in keys), default=0)
        for key in keys:
            s = stats[key]
            lines.append(
                f"  {key:>{width}} : {s['mean']:>10.3f}  [{s['ci_low']:.3f}, {s['ci_high']:.3f}]"
            )
        return "\n".join(lines)


def run_replications(
    scenario: Scenario,
    n_replications: int,
    *,
    base_seed: int | None = None,
) -> ReplicatedResult:
    """Exécute ``n_replications`` réplications indépendantes et reproductibles.

    Chaque réplication utilise une graine distincte dérivée de ``base_seed``
    (ou de ``scenario.seed``, ou 0), garantissant des résultats identiques d'un
    appel à l'autre pour un même ``base_seed``.

    Args:
        scenario: Le scénario à répliquer.
        n_replications: Nombre de réplications (>= 1).
        base_seed: Graine de base ; par défaut ``scenario.seed`` sinon 0.

    Returns:
        Un :class:`ReplicatedResult` rassemblant les indicateurs de chaque run.
    """
    if n_replications < 1:
        raise ValueError("n_replications doit être >= 1.")

    if base_seed is None:
        base_seed = scenario.seed if scenario.seed is not None else 0

    runs = [
        run_scenario(replace(scenario, seed=base_seed + i)).stress_indicators()
        for i in range(n_replications)
    ]
    return ReplicatedResult(scenario=scenario, runs=runs)


def replicated_census(
    scenario: Scenario,
    n_replications: int,
    *,
    base_seed: int | None = None,
) -> dict[str, list[list[int]]]:
    """Occupation journalière simulée par service sur ``n_replications`` réplications.

    Hors période de chauffe (``warmup_days``). Sert à construire la bande d'IC du
    census simulé pour la validation opérationnelle (couverture, cf.
    :func:`hospital_simulator.validation.ci_coverage`).

    Returns:
        ``{service: [[occ_rep0, occ_rep1, ...] pour le jour 0], [... jour 1], ...]}``.
    """
    if n_replications < 1:
        raise ValueError("n_replications doit être >= 1.")
    if base_seed is None:
        base_seed = scenario.seed if scenario.seed is not None else 0

    runs = [
        run_scenario(replace(scenario, seed=base_seed + i)).analysis_records()
        for i in range(n_replications)
    ]
    services = list(scenario.service_capacities)
    n_days = min((len(r) for r in runs), default=0)

    bands: dict[str, list[list[int]]] = {svc: [] for svc in services}
    for day in range(n_days):
        for svc in services:
            bands[svc].append([run[day]["occupancy"].get(svc, 0) for run in runs])
    return bands


# --- Analyse de sensibilité (balayage d'un paramètre) ---

# Champs scalaires du Scenario balayables directement par nom.
_SWEEPABLE_SCALARS = frozenset({
    "days",
    "arrival_rate_per_day",
    "admission_multiplier",
    "default_los_days",
    "warmup_days",
    "entry_service",
})


def _apply_parameter(scenario: Scenario, parameter: str, value) -> Scenario:
    """Renvoie une copie du scénario avec ``parameter`` fixé à ``value``.

    ``parameter`` accepte :
        * un champ scalaire du Scenario (ex: ``"arrival_rate_per_day"``) ;
        * ``"capacity:<service>"`` — capacité de base d'un service ;
        * ``"capacity_multiplier:<service>"`` — multiplicateur de capacité ;
        * ``"mean_los:<service>"`` — durée moyenne de séjour d'un service.
    """
    if parameter in _SWEEPABLE_SCALARS:
        return replace(scenario, **{parameter: value})

    if ":" in parameter:
        kind, service = parameter.split(":", 1)
        if kind == "capacity":
            new = dict(scenario.service_capacities)
            new[service] = value
            return replace(scenario, service_capacities=new)
        if kind == "capacity_multiplier":
            new = dict(scenario.capacity_multipliers)
            new[service] = value
            return replace(scenario, capacity_multipliers=new)
        if kind == "mean_los":
            new = dict(scenario.mean_los_days)
            new[service] = value
            return replace(scenario, mean_los_days=new)

    raise ValueError(
        f"Paramètre non balayable : {parameter!r}. Utilisez un champ scalaire "
        f"({sorted(_SWEEPABLE_SCALARS)}) ou 'capacity:<svc>' / "
        f"'capacity_multiplier:<svc>' / 'mean_los:<svc>'."
    )


@dataclass
class SensitivitySweepResult:
    """Résultat d'un balayage de sensibilité sur un paramètre.

    Attributs :
        scenario: Le scénario de base.
        parameter: Le paramètre balayé.
        values: Les valeurs testées (axe des abscisses).
        metrics: Les métriques suivies.
        confidence: Niveau de confiance des IC.
        n_replications: Réplications par valeur.
        data: ``{metric: [{value, mean, ci_low, ci_high, std, n}, ...]}`` — un
            point par valeur, prêt à tracer.
    """

    scenario: Scenario
    parameter: str
    values: list
    metrics: list[str]
    confidence: float
    n_replications: int
    data: dict[str, list[dict]] = field(default_factory=dict)

    def points(self, metric: str) -> list[dict]:
        """Renvoie la liste des points (value, mean, ci_low, ci_high) d'une métrique."""
        return self.data[metric]

    def render(self) -> str:
        """Rend un tableau texte du balayage (une section par métrique)."""
        lines = [
            f"Sensibilité '{self.parameter}' — scénario '{self.scenario.name}' "
            f"({self.n_replications} réplications, IC {int(self.confidence * 100)}%)"
        ]
        for metric in self.metrics:
            lines.append(f"  [{metric}]")
            for pt in self.data[metric]:
                lines.append(
                    f"    {self.parameter}={pt['value']!s:>8} : "
                    f"{pt['mean']:>10.3f}  [{pt['ci_low']:.3f}, {pt['ci_high']:.3f}]"
                )
        return "\n".join(lines)


def sensitivity_sweep(
    scenario: Scenario,
    parameter: str,
    values,
    metrics: list[str],
    *,
    n_replications: int = 30,
    base_seed: int | None = None,
    confidence: float = 0.95,
) -> SensitivitySweepResult:
    """Balaye un paramètre et mesure l'effet sur des indicateurs (avec IC).

    Pour chaque valeur de ``values``, exécute ``n_replications`` réplications du
    scénario modifié et récupère la moyenne et l'intervalle de confiance de
    chaque métrique demandée.

    Args:
        scenario: Scénario de base.
        parameter: Paramètre à balayer (cf. :func:`_apply_parameter`).
        values: Valeurs à tester.
        metrics: Clés d'indicateurs à suivre (plates, ex: ``"deaths"`` ou
            ``"ICU.mean_occupancy_rate"``).
        n_replications: Réplications par valeur.
        base_seed: Graine de base (partagée entre valeurs pour un contraste
            reproductible ; par défaut ``scenario.seed`` sinon 0).
        confidence: Niveau de confiance des IC.

    Returns:
        Un :class:`SensitivitySweepResult`.
    """
    values = list(values)
    if base_seed is None:
        base_seed = scenario.seed if scenario.seed is not None else 0

    data: dict[str, list[dict]] = {metric: [] for metric in metrics}
    for value in values:
        variant = _apply_parameter(scenario, parameter, value)
        summary = run_replications(
            variant, n_replications, base_seed=base_seed
        ).summary(confidence=confidence)
        for metric in metrics:
            if metric not in summary:
                raise KeyError(
                    f"Métrique inconnue : {metric!r}. Disponibles : {sorted(summary)}."
                )
            s = summary[metric]
            data[metric].append(
                {
                    "value": value,
                    "mean": s["mean"],
                    "ci_low": s["ci_low"],
                    "ci_high": s["ci_high"],
                    "std": s["std"],
                    "n": s["n"],
                }
            )

    return SensitivitySweepResult(
        scenario=scenario,
        parameter=parameter,
        values=values,
        metrics=list(metrics),
        confidence=confidence,
        n_replications=n_replications,
        data=data,
    )
