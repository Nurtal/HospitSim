"""Synthea -> OMOP -> calibration -> validation (Phase A, JMIR roadmap).

Chaîne complète et **reproductible** montrant comment calibrer et *valider* le
simulateur à partir de données OMOP.

Utilisation avec de vraies données Synthea
------------------------------------------
Synthea (https://github.com/synthetichealth/synthea) génère des patients
synthétiques exportables au format OMOP CDM :

    java -jar synthea-with-dependencies.jar -p 1000 \
        --exporter.omop.export=true

Placez les CSV OMOP produits (``person.csv``, ``condition_occurrence.csv``,
``visit_occurrence.csv``, ``procedure_occurrence.csv``) dans un dossier, puis :

    python examples/synthea_omop_etl.py /chemin/vers/omop_csv

Sans argument, le script génère un OMOP « Synthea-like » synthétique à
vérité-terrain connue, de sorte qu'il tourne hors-ligne et illustre la
méthodologie de validation.
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from hospital_simulator import (
    OmopDataset,
    estimate_length_of_stay,
    estimate_transition_probabilities,
    ks_exponential,
    length_of_stay_samples,
    patients_from_omop,
    stays_from_omop,
)

# Vérité-terrain du générateur synthétique (durées de séjour exponentielles).
GROUND_TRUTH_LOS = {"ED": 1.2, "Ward": 5.5, "ICU": 4.0}
GROUND_TRUTH_TRANSITIONS = {
    "ED": {"Ward": 0.60, "ICU": 0.25, "Discharge": 0.15},
    "Ward": {"ICU": 0.10, "Discharge": 0.90},
    "ICU": {"Ward": 0.80, "Discharge": 0.20},
}
_REAL_SERVICES = ("ED", "ICU", "Ward")


def _weighted_choice(rng: random.Random, row: dict[str, float]) -> str:
    return rng.choices(list(row), weights=list(row.values()), k=1)[0]


def generate_synthea_like_omop(n_patients: int = 600, seed: int = 0) -> OmopDataset:
    """Génère un OmopDataset synthétique de structure Synthea/OMOP.

    Les visites portent des horodatages continus (``visit_start_date`` /
    ``visit_end_date`` au format ISO datetime), donnant des durées de séjour
    continues — condition d'un test d'ajustement KS propre.
    """
    rng = random.Random(seed)
    base = datetime(2023, 1, 1)
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

        current = "ED"
        clock = base + timedelta(days=rng.randint(0, 300))
        for _ in range(6):  # borne anti-boucle ICU<->Ward
            los_days = rng.expovariate(1.0 / GROUND_TRUTH_LOS[current])
            end = clock + timedelta(days=los_days)
            visits.append(
                {
                    "person_id": str(pid),
                    "visit_source_value": current,
                    "visit_start_date": clock.isoformat(),
                    "visit_end_date": end.isoformat(),
                }
            )
            clock = end
            nxt = _weighted_choice(rng, GROUND_TRUTH_TRANSITIONS[current])
            if nxt not in _REAL_SERVICES:
                break
            current = nxt

    return OmopDataset(person=person, condition_occurrence=conditions, visit_occurrence=visits)


def load_or_generate(path: str | Path | None = None) -> tuple[OmopDataset, bool]:
    """Charge un OMOP depuis un dossier CSV, sinon en génère un synthétique.

    Returns:
        ``(dataset, is_synthetic)``.
    """
    if path is not None:
        return OmopDataset.from_dir(path), False
    return generate_synthea_like_omop(), True


def calibrate(dataset: OmopDataset):
    """Retourne (patients, routing, mean_los, stays) depuis l'OMOP."""
    patients = patients_from_omop(dataset, reference_year=2024)
    stays = stays_from_omop(dataset)
    routing = estimate_transition_probabilities(stays)
    los = estimate_length_of_stay(stays)
    mean_los = {svc: stats["mean"] for svc, stats in los.items()}
    return patients, routing, mean_los, stays


def validate_length_of_stay(stays, mean_los) -> dict[str, dict]:
    """Teste l'hypothèse de séjour exponentiel par service (KS à un échantillon).

    Returns:
        ``{service: {n, observed_mean, ks_D, p_value, exponential_ok}}``.
    """
    samples = length_of_stay_samples(stays)
    report: dict[str, dict] = {}
    for service, sample in samples.items():
        mean = mean_los.get(service)
        if not mean or len(sample) < 20:
            continue
        d, p = ks_exponential(sample, mean)
        report[service] = {
            "n": len(sample),
            "observed_mean": round(mean, 3),
            "ks_D": round(d, 4),
            "p_value": round(p, 4),
            "exponential_ok": p > 0.05,
        }
    return report


def main(path: str | None = None) -> None:
    dataset, synthetic = load_or_generate(path)
    kind = "synthétique (Synthea-like)" if synthetic else f"réel ({path})"
    patients, routing, mean_los, stays = calibrate(dataset)

    print(f"Source OMOP : {kind}")
    print(f"Patients : {len(patients)} | séjours : {len(stays)}\n")

    if synthetic:
        print("Récupération des transitions ED (vérité-terrain vs estimé) :")
        for dest, truth in sorted(GROUND_TRUTH_TRANSITIONS["ED"].items()):
            print(f"  {dest:<10} vrai={truth:.2f}  estimé={routing['ED'].get(dest, 0):.2f}")
        print()

    print("Validation de l'hypothèse de séjour exponentiel (KS) :")
    report = validate_length_of_stay(stays, mean_los)
    for service, r in report.items():
        verdict = "OK" if r["exponential_ok"] else "REJETÉ"
        print(f"  {service:<6} n={r['n']:>4}  DMS={r['observed_mean']:>5}j  "
              f"D={r['ks_D']:.3f}  p={r['p_value']:.3f}  -> exponentiel {verdict}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
