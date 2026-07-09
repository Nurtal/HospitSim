"""Import de données OMOP (Phase 3 — OMOP import).

Chargement léger et sans dépendance de tables OMOP CDM (person,
condition_occurrence, visit_occurrence, procedure_occurrence) et génération de
:class:`~hospital_simulator.patient.Patient` à partir de ces données.

Les tables sont manipulées comme des listes de dictionnaires (une ligne = un
dict), lisibles depuis des fichiers CSV ou fournies en mémoire. On reste
volontairement tolérant : les codes de diagnostic invalides sont ignorés plutôt
que de faire échouer tout l'import.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from hospital_simulator.patient import Patient
from hospital_simulator.models._cid_validator import CID10Validator

# Concepts OMOP standards utiles.
GENDER_CONCEPTS: dict[int, str] = {8507: "M", 8532: "F"}

# condition_type_concept_id marquant un diagnostic principal.
_PRIMARY_CONDITION_TYPE = 32902

# Correspondance par défaut visit_concept_id -> service simulé.
DEFAULT_VISIT_SERVICE_MAP: dict[int, str] = {
    9203: "ED",   # Emergency Room Visit
    262: "ED",    # Emergency Room and Inpatient Visit
    9201: "Ward",  # Inpatient Visit
    9202: "outpatient_clinic",  # Outpatient Visit
}

_OMOP_TABLES = (
    "person",
    "condition_occurrence",
    "visit_occurrence",
    "procedure_occurrence",
)


def _as_int(value: object) -> int | None:
    """Convertit prudemment une valeur en entier, sinon None."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_omop_date(value: object) -> datetime | None:
    """Parse une date OMOP (datetime, date ou chaîne ISO), sinon None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


@dataclass
class OmopDataset:
    """Ensemble de tables OMOP en mémoire."""

    person: list[dict] = field(default_factory=list)
    condition_occurrence: list[dict] = field(default_factory=list)
    visit_occurrence: list[dict] = field(default_factory=list)
    procedure_occurrence: list[dict] = field(default_factory=list)

    @classmethod
    def from_dir(cls, directory: str | Path) -> "OmopDataset":
        """Charge les tables OMOP depuis un dossier contenant des CSV.

        Chaque table ``{name}.csv`` présente est chargée ; les tables absentes
        restent vides.
        """
        directory = Path(directory)
        tables: dict[str, list[dict]] = {}
        for name in _OMOP_TABLES:
            csv_path = directory / f"{name}.csv"
            if csv_path.exists():
                with csv_path.open(newline="", encoding="utf-8") as handle:
                    tables[name] = list(csv.DictReader(handle))
            else:
                tables[name] = []
        return cls(**tables)


def _group_by(rows: list[dict], key: str) -> dict[str, list[dict]]:
    """Regroupe des lignes par la valeur (str) d'une colonne."""
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(str(row.get(key)), []).append(row)
    return groups


def _resolve_condition_code(row: dict, code_map: dict[int, str] | None) -> str | None:
    """Résout le code CIM-10 d'une condition OMOP (concept mappé ou source value)."""
    if code_map:
        concept_id = _as_int(row.get("condition_concept_id"))
        if concept_id is not None and concept_id in code_map:
            return code_map[concept_id]
    return row.get("condition_source_value")


def _is_primary(row: dict) -> bool:
    """Indique si une condition OMOP est marquée comme diagnostic principal."""
    status = str(row.get("condition_status_source_value", "")).strip().lower()
    if status in {"primary", "principal"}:
        return True
    return _as_int(row.get("condition_type_concept_id")) == _PRIMARY_CONDITION_TYPE


def patients_from_omop(
    dataset: OmopDataset,
    *,
    code_map: dict[int, str] | None = None,
    reference_year: int | None = None,
) -> list[Patient]:
    """Génère des patients à partir d'un dataset OMOP.

    Pour chaque personne, le diagnostic principal est la condition marquée
    ``primary`` (ou, à défaut, la plus précoce). Les autres conditions valides
    deviennent des comorbidités. Les codes CIM-10 invalides sont ignorés.

    Args:
        dataset: Les tables OMOP.
        code_map: Correspondance optionnelle ``condition_concept_id -> code CIM-10``.
        reference_year: Année de référence pour calculer l'âge (défaut : année courante).

    Returns:
        La liste des patients générés (un par personne).
    """
    reference_year = reference_year or datetime.now().year
    conditions_by_person = _group_by(dataset.condition_occurrence, "person_id")

    patients: list[Patient] = []
    for person in dataset.person:
        person_id = str(person.get("person_id"))

        sexe = GENDER_CONCEPTS.get(_as_int(person.get("gender_concept_id")))
        yob = _as_int(person.get("year_of_birth"))
        age = reference_year - yob if yob is not None else None

        # Ordonne les conditions : principales d'abord, puis par date de début.
        conditions = conditions_by_person.get(person_id, [])
        conditions = sorted(
            conditions,
            key=lambda r: (
                not _is_primary(r),
                parse_omop_date(r.get("condition_start_date")) or datetime.max,
            ),
        )

        codes: list[str] = []
        for row in conditions:
            code = _resolve_condition_code(row, code_map)
            if code and CID10Validator.is_valid(code):
                normalized = CID10Validator.normalize(code)
                if normalized not in codes:
                    codes.append(normalized)

        primary = codes[0] if codes else ""
        secondaries = codes[1:]

        patients.append(
            Patient(
                id=f"omop-{person_id}",
                age=age,
                sexe=sexe,
                diagnostic_principal=primary,
                diagnostics_secondaires=secondaries,
            )
        )

    return patients


def stays_from_omop(
    dataset: OmopDataset,
    *,
    service_map: dict[int, str] | None = None,
    use_source_value: bool = True,
) -> list[dict]:
    """Extrait des séjours normalisés (pour la calibration) depuis les visites OMOP.

    Args:
        dataset: Les tables OMOP.
        service_map: Correspondance ``visit_concept_id -> service`` (défaut :
            :data:`DEFAULT_VISIT_SERVICE_MAP`).
        use_source_value: si True, ``visit_source_value`` prime lorsqu'il est
            renseigné (utile pour distinguer ICU/Ward que le concept ne capture pas).

    Returns:
        Une liste de dicts ``{person_id, service, start, end}``.
    """
    service_map = service_map if service_map is not None else DEFAULT_VISIT_SERVICE_MAP
    stays: list[dict] = []
    for visit in dataset.visit_occurrence:
        service = None
        if use_source_value:
            source = str(visit.get("visit_source_value", "")).strip()
            service = source or None
        if service is None:
            service = service_map.get(_as_int(visit.get("visit_concept_id")))
        if service is None:
            continue
        stays.append(
            {
                "person_id": str(visit.get("person_id")),
                "service": service,
                "start": parse_omop_date(visit.get("visit_start_date")),
                "end": parse_omop_date(visit.get("visit_end_date")),
            }
        )
    return stays


def conditions_from_omop(
    dataset: OmopDataset,
    *,
    code_map: dict[int, str] | None = None,
) -> list[dict]:
    """Extrait des conditions normalisées ``{person_id, code}`` (codes CIM-10 valides)."""
    out: list[dict] = []
    for row in dataset.condition_occurrence:
        code = _resolve_condition_code(row, code_map)
        if code and CID10Validator.is_valid(code):
            out.append({"person_id": str(row.get("person_id")), "code": CID10Validator.normalize(code)})
    return out


def procedures_from_omop(dataset: OmopDataset) -> list[dict]:
    """Extrait des procédures normalisées ``{person_id, procedure}`` depuis OMOP."""
    out: list[dict] = []
    for row in dataset.procedure_occurrence:
        proc = row.get("procedure_source_value") or _as_int(row.get("procedure_concept_id"))
        if proc is not None and proc != "":
            out.append({"person_id": str(row.get("person_id")), "procedure": str(proc)})
    return out
