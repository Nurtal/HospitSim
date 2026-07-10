"""Calibration data-driven du simulateur (Phase 3).

Estimateurs statistiques élémentaires, sans dépendance externe, permettant de
paramétrer les parcours cliniques et les services à partir de séjours et de
procédures observés (typiquement issus d'un entrepôt OMOP) :

    * :func:`estimate_transition_probabilities` — probabilités de transition
      entre services.
    * :func:`estimate_length_of_stay` — durées de séjour par service.
    * :func:`estimate_procedure_probabilities` — probabilité d'une procédure
      sachant un diagnostic.

Les séjours ("stays") sont des dicts normalisés ``{person_id, service, start, end}``
tels que produits par :func:`hospital_simulator.omop.stays_from_omop`.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime

from hospital_simulator.omop import parse_omop_date
from hospital_simulator.pathways import ClinicalPathway
from hospital_simulator.models._cid_validator import CID10Validator

# Devenir terminal implicite en fin de trajectoire patient.
DEFAULT_TERMINAL = "Discharge"

# Groupe de diagnostic par défaut quand le code est absent/invalide.
UNKNOWN_GROUP = "UNKNOWN"


def diagnosis_group(code: str | None, level: str = "category") -> str:
    """Regroupe un code CIM-10 en cohorte explicable.

    Args:
        code: code CIM-10 (ex: "J18.9").
        level: ``"category"`` (lettre + 2 chiffres, ex: "J18") ou ``"chapter"``
            (lettre, ex: "J").

    Returns:
        Le groupe, ou :data:`UNKNOWN_GROUP` si le code est absent/invalide.
    """
    if not code or not CID10Validator.is_valid(code):
        return UNKNOWN_GROUP
    normalized = CID10Validator.normalize(code)  # ex: "J189"
    if level == "chapter":
        return normalized[0]
    if level == "category":
        return normalized[:3]
    raise ValueError("level doit être 'category' ou 'chapter'.")


def _group_of_person(stays: list[dict], level: str) -> dict[str, str]:
    """Associe chaque patient à son groupe de diagnostic (via le champ ``diagnosis``)."""
    groups: dict[str, str] = {}
    for stay in stays:
        pid = str(stay.get("person_id"))
        if pid not in groups:
            groups[pid] = diagnosis_group(stay.get("diagnosis"), level=level)
    return groups


def estimate_transitions_by_group(
    stays: list[dict],
    *,
    level: str = "category",
    terminal: str | None = DEFAULT_TERMINAL,
) -> dict[str, dict[str, dict[str, float]]]:
    """Estime une matrice de transition **par groupe de diagnostic**.

    Chaque patient est affecté à un groupe (via le champ ``diagnosis`` de ses
    séjours) ; les transitions sont estimées séparément par groupe.

    Returns:
        ``{groupe: {service_source: {destination: probabilité}}}``.
    """
    groups = _group_of_person(stays, level)
    by_group: dict[str, list[dict]] = defaultdict(list)
    for stay in stays:
        by_group[groups[str(stay.get("person_id"))]].append(stay)
    return {
        group: estimate_transition_probabilities(group_stays, terminal=terminal)
        for group, group_stays in by_group.items()
    }


def estimate_diagnosis_mix(stays: list[dict], *, level: str = "category") -> dict[str, float]:
    """Distribution d'arrivée sur les groupes de diagnostic (un patient = un tirage)."""
    groups = _group_of_person(stays, level)
    counts: dict[str, int] = defaultdict(int)
    for group in groups.values():
        counts[group] += 1
    total = sum(counts.values())
    return {g: n / total for g, n in counts.items()} if total else {}


def _sequences_by_person(stays: list[dict]) -> dict[str, list[dict]]:
    """Regroupe les séjours par patient, triés chronologiquement."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for stay in stays:
        grouped[str(stay.get("person_id"))].append(stay)

    for person_id, seq in grouped.items():
        seq.sort(key=lambda s: parse_omop_date(s.get("start")) or datetime.max)
    return grouped


def estimate_transition_probabilities(
    stays: list[dict],
    *,
    terminal: str | None = DEFAULT_TERMINAL,
) -> dict[str, dict[str, float]]:
    """Estime les probabilités de transition entre services.

    Pour chaque patient, on parcourt ses séjours dans l'ordre chronologique et
    on compte les transitions ``service_courant -> service_suivant``. Si
    ``terminal`` est fourni, le dernier séjour de chaque patient compte une
    transition vers un devenir terminal : la valeur ``disposition`` portée par
    ce dernier séjour (ex: ``"Death"``) si elle existe, sinon ``terminal``
    (typiquement ``"Discharge"``).

    Args:
        stays: Séjours normalisés ``{person_id, service, start, end[, disposition]}``.
        terminal: Devenir terminal par défaut ajouté en fin de trajectoire, ou
            None pour ne compter que les transitions observées entre services.

    Returns:
        Un dict ``{service_source: {destination: probabilité}}`` normalisé (chaque
        ligne somme à 1.0).
    """
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for seq in _sequences_by_person(stays).values():
        with_service = [s for s in seq if s.get("service")]
        services = [s["service"] for s in with_service]
        if not services:
            continue
        for current, nxt in zip(services, services[1:]):
            counts[current][nxt] += 1
        if terminal is not None:
            disposition = with_service[-1].get("disposition") or terminal
            counts[services[-1]][disposition] += 1

    probabilities: dict[str, dict[str, float]] = {}
    for source, dest_counts in counts.items():
        total = sum(dest_counts.values())
        probabilities[source] = {
            dest: n / total for dest, n in dest_counts.items()
        }
    return probabilities


def length_of_stay_samples(stays: list[dict]) -> dict[str, list[float]]:
    """Extrait les durées de séjour (jours) observées par service.

    Les séjours sans date de début/fin exploitable ou de durée négative sont
    ignorés. Utile pour la validation distributionnelle (cf.
    :mod:`hospital_simulator.validation`).

    Returns:
        Un dict ``{service: [durée_en_jours, ...]}``.
    """
    durations: dict[str, list[float]] = defaultdict(list)
    for stay in stays:
        service = stay.get("service")
        start = parse_omop_date(stay.get("start"))
        end = parse_omop_date(stay.get("end"))
        if not service or start is None or end is None:
            continue
        days = (end - start).total_seconds() / 86400.0
        if days < 0:
            continue
        durations[service].append(days)
    return dict(durations)


def peak_concurrency(stays: list[dict]) -> dict[str, int]:
    """Occupation simultanée maximale observée par service (balayage d'intervalles).

    Utile pour dimensionner les capacités d'un scénario à partir des données.

    Returns:
        Un dict ``{service: nombre_max_de_patients_simultanés}``.
    """
    events: dict[str, list[tuple]] = defaultdict(list)
    for stay in stays:
        service = stay.get("service")
        start = parse_omop_date(stay.get("start"))
        end = parse_omop_date(stay.get("end"))
        if not service or start is None or end is None or end < start:
            continue
        events[service].append((start, 1))
        events[service].append((end, -1))

    peaks: dict[str, int] = {}
    for service, evs in events.items():
        # À temps égal, traiter les sorties (-1) avant les entrées (+1).
        evs.sort(key=lambda e: (e[0], e[1]))
        current = peak = 0
        for _, delta in evs:
            current += delta
            peak = max(peak, current)
        peaks[service] = peak
    return peaks


def estimate_length_of_stay(stays: list[dict]) -> dict[str, dict[str, float]]:
    """Estime la durée de séjour (en jours) par service.

    Returns:
        Un dict ``{service: {"mean": ..., "median": ..., "n": ...}}``.
    """
    result: dict[str, dict[str, float]] = {}
    for service, values in length_of_stay_samples(stays).items():
        result[service] = {
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "n": len(values),
        }
    return result


def estimate_procedure_probabilities(
    conditions: list[dict],
    procedures: list[dict],
) -> dict[str, dict[str, float]]:
    """Estime P(procédure | diagnostic) à partir de données par patient.

    Pour chaque diagnostic, le dénominateur est le nombre de patients porteurs
    de ce diagnostic ; le numérateur, le nombre d'entre eux ayant subi la
    procédure. Une probabilité est donc dans [0, 1] et les procédures ne somment
    pas nécessairement à 1 (elles ne sont pas mutuellement exclusives).

    Args:
        conditions: Dicts ``{person_id, code}``.
        procedures: Dicts ``{person_id, procedure}``.

    Returns:
        Un dict ``{code_diagnostic: {procedure: probabilité}}``.
    """
    persons_by_diagnosis: dict[str, set[str]] = defaultdict(set)
    for row in conditions:
        persons_by_diagnosis[str(row["code"])].add(str(row["person_id"]))

    procedures_by_person: dict[str, set[str]] = defaultdict(set)
    for row in procedures:
        procedures_by_person[str(row["person_id"])].add(str(row["procedure"]))

    result: dict[str, dict[str, float]] = {}
    for code, persons in persons_by_diagnosis.items():
        denom = len(persons)
        if denom == 0:
            continue
        proc_counts: dict[str, int] = defaultdict(int)
        for person_id in persons:
            for proc in procedures_by_person.get(person_id, ()):
                proc_counts[proc] += 1
        result[code] = {proc: n / denom for proc, n in proc_counts.items()}
    return result


def build_pathway_from_transitions(
    name: str,
    transitions_row: dict[str, float],
    *,
    diagnosis_code: str | None = None,
    procedures: list[str] | None = None,
) -> ClinicalPathway:
    """Construit un :class:`ClinicalPathway` à partir de transitions estimées.

    Les probabilités estimées somment déjà à 1.0 (aux erreurs d'arrondi près),
    ce qui satisfait la validation de :class:`ClinicalPathway`.

    Args:
        name: Nom du parcours.
        transitions_row: Une ligne ``{destination: probabilité}`` telle que
            renvoyée par :func:`estimate_transition_probabilities`.
        diagnosis_code: Code CIM-10 associé (optionnel).
        procedures: Procédures attendues (optionnel).
    """
    return ClinicalPathway(
        name=name,
        diagnosis_code=diagnosis_code,
        procedures=list(procedures or []),
        transitions=dict(transitions_row),
    )
