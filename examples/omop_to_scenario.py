"""Exemple end-to-end : OMOP synthétique -> calibration -> scénario répliqué.

Ce script est **auto-contenu et reproductible** (aucun téléchargement) : il
génère un jeu de données OMOP synthétique à partir d'une vérité-terrain connue,
montre que les estimateurs de calibration la retrouvent, puis paramètre et
exécute un scénario « what-if » avec réplications et intervalles de confiance.

Pour un article, la même chaîne s'applique telle quelle à des données réelles
(extrait OMOP d'un entrepôt, ou données Synthea converties en OMOP).

Lancement :

    python examples/omop_to_scenario.py
"""

from __future__ import annotations

import random

from hospital_simulator import (
    OmopDataset,
    estimate_length_of_stay,
    estimate_transition_probabilities,
    patients_from_omop,
    run_replications,
    stays_from_omop,
    Scenario,
)

# Vérité-terrain : transitions inter-services (le devenir "Discharge" n'est pas
# une visite OMOP ; il est déduit de la fin de trajectoire par l'estimateur).
GROUND_TRUTH_TRANSITIONS = {
    "ED": {"Ward": 0.60, "ICU": 0.25, "Discharge": 0.15},
    "Ward": {"ICU": 0.10, "Discharge": 0.90},
    "ICU": {"Ward": 0.80, "Discharge": 0.20},
}
GROUND_TRUTH_LOS = {"ED": 1.0, "ICU": 4.0, "Ward": 5.0}
_REAL_SERVICES = ("ED", "ICU", "Ward")


def _weighted_choice(rng: random.Random, row: dict[str, float]) -> str:
    return rng.choices(list(row), weights=list(row.values()), k=1)[0]


def build_synthetic_omop(n_patients: int = 300, seed: int = 0) -> OmopDataset:
    """Génère un OmopDataset synthétique suivant la vérité-terrain."""
    rng = random.Random(seed)
    person, conditions, visits = [], [], []

    for pid in range(1, n_patients + 1):
        person.append(
            {
                "person_id": str(pid),
                "gender_concept_id": rng.choice(["8507", "8532"]),
                "year_of_birth": str(rng.randint(1935, 1995)),
            }
        )
        conditions.append(
            {
                "person_id": str(pid),
                "condition_source_value": "J18.9",
                "condition_status_source_value": "primary",
                "condition_start_date": "2023-01-01",
            }
        )

        # Trajectoire : ED -> ... -> sortie, avec dates cohérentes.
        current = "ED"
        day = 0
        for _ in range(6):  # borne pour éviter les boucles ICU<->Ward infinies
            los = max(1, round(rng.expovariate(1.0 / GROUND_TRUTH_LOS[current])))
            start = f"2023-01-{day + 1:02d}"
            end = f"2023-01-{min(31, day + 1 + los):02d}"
            visits.append(
                {
                    "person_id": str(pid),
                    "visit_source_value": current,
                    "visit_start_date": start,
                    "visit_end_date": end,
                }
            )
            day += los
            nxt = _weighted_choice(rng, GROUND_TRUTH_TRANSITIONS[current])
            if nxt not in _REAL_SERVICES:
                break
            current = nxt

    return OmopDataset(person=person, condition_occurrence=conditions, visit_occurrence=visits)


def calibrate(dataset: OmopDataset):
    """Retourne (patients, routing estimé, DMS moyennes) à partir de l'OMOP."""
    patients = patients_from_omop(dataset, reference_year=2024)
    stays = stays_from_omop(dataset)
    routing = estimate_transition_probabilities(stays)
    los = estimate_length_of_stay(stays)
    mean_los = {svc: stats["mean"] for svc, stats in los.items()}
    return patients, routing, mean_los


def build_scenario(routing, mean_los, *, seed: int = 2026) -> Scenario:
    """Construit un scénario calibré depuis les estimations OMOP."""
    return Scenario(
        name="pneumonia_calibrated",
        days=120,
        warmup_days=20,
        arrival_rate_per_day=10.0,
        entry_service="ED",
        service_capacities={"ED": 30, "ICU": 18, "Ward": 60},
        routing=routing,
        mean_los_days=mean_los,
        seed=seed,
    )


def main() -> None:
    dataset = build_synthetic_omop(n_patients=400, seed=0)
    patients, routing, mean_los = calibrate(dataset)

    print(f"Patients générés depuis OMOP : {len(patients)}")
    print(f"Exemple : {patients[0].id} dx={patients[0].diagnostic_principal}\n")

    print("Calibration des transitions depuis ED (vérité-terrain vs estimé) :")
    for dest, p in sorted(GROUND_TRUTH_TRANSITIONS["ED"].items()):
        print(f"  {dest:<10} vrai={p:.2f}  estimé={routing['ED'].get(dest, 0):.2f}")
    print(f"\nDMS estimées (jours) : "
          f"{ {k: round(v, 2) for k, v in mean_los.items()} }\n")

    scenario = build_scenario(routing, mean_los)
    rep = run_replications(scenario, 40)
    print(rep.render_summary(
        metrics=["admissions", "blocked_transfers",
                 "ICU.mean_occupancy_rate", "ICU.saturation_days"]
    ))


if __name__ == "__main__":
    main()
