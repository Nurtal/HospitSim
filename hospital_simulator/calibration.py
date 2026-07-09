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

# Devenir terminal implicite en fin de trajectoire patient.
DEFAULT_TERMINAL = "Discharge"


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
    transition vers ce devenir terminal (ex: sortie).

    Args:
        stays: Séjours normalisés ``{person_id, service, start, end}``.
        terminal: Nom du devenir terminal ajouté en fin de trajectoire, ou None
            pour ne compter que les transitions observées entre services.

    Returns:
        Un dict ``{service_source: {destination: probabilité}}`` normalisé (chaque
        ligne somme à 1.0).
    """
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for seq in _sequences_by_person(stays).values():
        services = [s.get("service") for s in seq if s.get("service")]
        if not services:
            continue
        for current, nxt in zip(services, services[1:]):
            counts[current][nxt] += 1
        if terminal is not None:
            counts[services[-1]][terminal] += 1

    probabilities: dict[str, dict[str, float]] = {}
    for source, dest_counts in counts.items():
        total = sum(dest_counts.values())
        probabilities[source] = {
            dest: n / total for dest, n in dest_counts.items()
        }
    return probabilities


def estimate_length_of_stay(stays: list[dict]) -> dict[str, dict[str, float]]:
    """Estime la durée de séjour (en jours) par service.

    Les séjours sans date de début ou de fin exploitable sont ignorés. Une durée
    négative (fin avant début) est également écartée.

    Returns:
        Un dict ``{service: {"mean": ..., "median": ..., "n": ...}}``.
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

    result: dict[str, dict[str, float]] = {}
    for service, values in durations.items():
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
