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
import gzip
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
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
    text = str(value)
    if text.endswith("Z"):  # horodatages ISO type Synthea ("2020-01-01T10:00:00Z")
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
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


def _mark_last_visit_death(visits: list[dict], died_person_ids: set[str]) -> None:
    """Marque ``disposition="Death"`` sur le dernier séjour des personnes décédées.

    Le « dernier » séjour est celui de date de début la plus tardive. Modifie
    ``visits`` en place.
    """
    best: dict[str, tuple] = {}  # person_id -> (start, index)
    for i, visit in enumerate(visits):
        pid = str(visit.get("person_id"))
        if pid not in died_person_ids:
            continue
        start = parse_omop_date(visit.get("visit_start_date"))
        if pid not in best:
            best[pid] = (start, i)
            continue
        cur_start, _ = best[pid]
        if cur_start is None or (start is not None and start >= cur_start):
            best[pid] = (start, i)
    for _, index in best.values():
        visits[index]["disposition"] = "Death"


# Correspondance ENCOUNTERCLASS Synthea -> service simulé.
SYNTHEA_ENCOUNTER_SERVICE: dict[str, str] = {
    "emergency": "ED",
    "urgentcare": "ED",
    "inpatient": "Ward",
    "ambulatory": "outpatient_clinic",
    "outpatient": "outpatient_clinic",
    "wellness": "outpatient_clinic",
}
# Classes considérées comme relevant du flux hospitalier aigu.
SYNTHEA_HOSPITAL_CLASSES: frozenset = frozenset({"emergency", "urgentcare", "inpatient"})


def omop_from_synthea_csv(
    directory: str | Path,
    *,
    hospital_only: bool = True,
    service_map: dict[str, str] | None = None,
) -> OmopDataset:
    """Construit un OmopDataset à partir d'un export **CSV** de Synthea.

    L'export CSV de Synthea (``patients.csv``, ``encounters.csv``,
    ``conditions.csv``, ``procedures.csv``) est stable, contrairement à
    l'exportateur OMOP natif. Les ``ENCOUNTERCLASS`` sont mappées vers les
    services simulés.

    Note : Synthea modélise des parcours de soins sur toute une vie (nombreuses
    visites ambulatoires) et ne distingue pas les transferts intra-hospitaliers
    (ICU/ward). Avec ``hospital_only=True`` (défaut), seules les classes aiguës
    (urgences, hospitalisation) sont conservées ; la calibration des transitions
    reste donc grossière — MIMIC-IV convient mieux pour l'intra-hospitalier.

    Args:
        directory: Dossier contenant les CSV Synthea.
        hospital_only: Ne garder que les encounters aigus (cf.
            :data:`SYNTHEA_HOSPITAL_CLASSES`).
        service_map: Correspondance ``ENCOUNTERCLASS -> service`` (défaut :
            :data:`SYNTHEA_ENCOUNTER_SERVICE`).
    """
    directory = Path(directory)
    service_map = service_map if service_map is not None else SYNTHEA_ENCOUNTER_SERVICE

    def _read(name: str) -> list[dict]:
        path = directory / name
        if not path.exists():
            return []
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    patient_rows = _read("patients.csv")
    person = [
        {
            "person_id": row.get("Id"),
            "gender_concept_id": "8507" if row.get("GENDER") == "M" else "8532",
            "year_of_birth": (row.get("BIRTHDATE") or "")[:4],
        }
        for row in patient_rows
    ]
    death_date = {
        row.get("Id"): parse_omop_date((row.get("DEATHDATE") or "").strip())
        for row in patient_rows
        if (row.get("DEATHDATE") or "").strip()
    }

    visits = []
    for row in _read("encounters.csv"):
        cls = (row.get("ENCOUNTERCLASS") or "").lower()
        if hospital_only and cls not in SYNTHEA_HOSPITAL_CLASSES:
            continue
        service = service_map.get(cls)
        if service is None:
            continue
        visits.append(
            {
                "person_id": row.get("PATIENT"),
                "visit_source_value": service,
                "visit_start_date": row.get("START"),
                "visit_end_date": row.get("STOP"),
            }
        )

    condition_rows = _read("conditions.csv")
    conditions = [
        {
            "person_id": row.get("PATIENT"),
            "condition_source_value": row.get("CODE"),
            "condition_start_date": row.get("START"),
        }
        for row in condition_rows
    ]
    procedures = [
        {"person_id": row.get("PATIENT"), "procedure_source_value": row.get("CODE")}
        for row in _read("procedures.csv")
    ]

    # Diagnostic principal = 1er code CIM-10 valide du patient -> rattaché aux visites.
    primary_by_patient: dict[str, str] = {}
    for row in condition_rows:
        pid = row.get("PATIENT")
        code = row.get("CODE")
        if pid not in primary_by_patient and code and CID10Validator.is_valid(code):
            primary_by_patient[pid] = code
    for visit in visits:
        visit["diagnosis"] = primary_by_patient.get(str(visit.get("person_id")))

    # Décès intra-hospitalier : DEATHDATE tombant pendant le dernier séjour aigu.
    if death_date:
        last_visit: dict[str, tuple] = {}  # person_id -> (start, end, index)
        for i, visit in enumerate(visits):
            pid = visit["person_id"]
            start = parse_omop_date(visit.get("visit_start_date"))
            prev = last_visit.get(pid)
            if prev is None or (start is not None and (prev[0] is None or start >= prev[0])):
                last_visit[pid] = (start, parse_omop_date(visit.get("visit_end_date")), i)
        died = set()
        for pid, (start, end, index) in last_visit.items():
            dd = death_date.get(pid)
            if dd is None or start is None or end is None:
                continue
            if start.date() <= dd.date() <= end.date() + timedelta(days=1):
                died.add(pid)
                visits[index]["disposition"] = "Death"

    return OmopDataset(
        person=person,
        condition_occurrence=conditions,
        visit_occurrence=visits,
        procedure_occurrence=procedures,
    )


def classify_mimic_careunit(careunit: str) -> str:
    """Classe une unité de soins MIMIC-IV en service simulé (ED / ICU / Ward)."""
    name = (careunit or "").lower()
    if "emergency" in name:
        return "ED"
    if "intensive care" in name or "icu" in name or "ccu" in name:
        return "ICU"
    return "Ward"


def _read_mimic_table(directory: Path, base: str) -> list[dict]:
    """Lit une table MIMIC (``{base}.csv`` ou ``{base}.csv.gz``, cherchée récursivement)."""
    for pattern in (f"{base}.csv", f"{base}.csv.gz"):
        for path in sorted(directory.rglob(pattern)):
            if path.suffix == ".gz":
                with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
                    return list(csv.DictReader(handle))
            with path.open(newline="", encoding="utf-8") as handle:
                return list(csv.DictReader(handle))
    return []


def omop_from_mimic(
    directory: str | Path,
    *,
    episode_level: bool = True,
    careunit_classifier=classify_mimic_careunit,
) -> OmopDataset:
    """Construit un OmopDataset à partir d'un extrait **MIMIC-IV** (CSV ou CSV.gz).

    MIMIC-IV décrit les transferts intra-hospitaliers (table ``transfers`` :
    ``careunit`` + ``intime``/``outtime``), ce qui permet de calibrer de vraies
    transitions ED → ICU → ward, et fournit des diagnostics en **CIM-10**
    (``diagnoses_icd``, ``icd_version == 10``).

    Tables attendues (dans le dossier ou un sous-dossier ``hosp/`` / ``icu/``) :
    ``patients``, ``transfers``, ``diagnoses_icd``, ``procedures_icd``.

    Args:
        directory: Racine de l'extrait MIMIC-IV.
        episode_level: si True (défaut), chaque **admission** (``hadm_id``) est
            traitée comme une trajectoire distincte — ``person_id`` des séjours =
            ``"{subject_id}_{hadm_id}"`` — afin d'obtenir des transitions
            intra-hospitalières propres (plutôt que de chaîner des séjours de
            différentes hospitalisations).
        careunit_classifier: fonction ``careunit -> service``.
    """
    directory = Path(directory)

    person = []
    for row in _read_mimic_table(directory, "patients"):
        yob = None
        anchor_age = _as_int(row.get("anchor_age"))
        anchor_year = _as_int(row.get("anchor_year"))
        if anchor_age is not None and anchor_year is not None:
            yob = anchor_year - anchor_age
        person.append(
            {
                "person_id": row.get("subject_id"),
                "gender_concept_id": "8507" if row.get("gender") == "M" else "8532",
                "year_of_birth": str(yob) if yob is not None else "",
            }
        )

    visits = []
    for row in _read_mimic_table(directory, "transfers"):
        careunit = row.get("careunit")
        if not careunit or (row.get("eventtype") or "").lower() == "discharge":
            continue
        subject = row.get("subject_id")
        hadm = row.get("hadm_id")
        person_id = f"{subject}_{hadm}" if episode_level and hadm else subject
        visits.append(
            {
                "person_id": person_id,
                "visit_source_value": careunit_classifier(careunit),
                "visit_start_date": row.get("intime"),
                "visit_end_date": row.get("outtime"),
            }
        )

    conditions = []
    primary_by_episode: dict[str, str] = {}
    for row in _read_mimic_table(directory, "diagnoses_icd"):
        if str(row.get("icd_version")) != "10":  # on ne garde que la CIM-10
            continue
        subject = row.get("subject_id")
        hadm = row.get("hadm_id")
        is_primary = str(row.get("seq_num")) == "1"
        conditions.append(
            {
                "person_id": subject,
                "condition_source_value": row.get("icd_code"),
                "condition_status_source_value": "primary" if is_primary else "",
            }
        )
        if is_primary:
            episode = f"{subject}_{hadm}" if episode_level and hadm else str(subject)
            primary_by_episode.setdefault(episode, row.get("icd_code"))

    # Diagnostic principal rattaché à chaque visite de l'épisode (routage par diagnostic).
    for visit in visits:
        visit["diagnosis"] = primary_by_episode.get(str(visit.get("person_id")))

    procedures = []
    for row in _read_mimic_table(directory, "procedures_icd"):
        procedures.append(
            {"person_id": row.get("subject_id"), "procedure_source_value": row.get("icd_code")}
        )

    # Décès hospitaliers (table admissions) -> disposition "Death" du dernier séjour.
    died: set[str] = set()
    for row in _read_mimic_table(directory, "admissions"):
        subject = row.get("subject_id")
        hadm = row.get("hadm_id")
        pid = f"{subject}_{hadm}" if episode_level and hadm else str(subject)
        flag = str(row.get("hospital_expire_flag") or "").strip()
        discharge = (row.get("discharge_location") or "").strip().upper()
        deathtime = (row.get("deathtime") or "").strip()
        if flag == "1" or discharge == "DIED" or deathtime:
            died.add(pid)
    if died:
        _mark_last_visit_death(visits, died)

    return OmopDataset(
        person=person,
        condition_occurrence=conditions,
        visit_occurrence=visits,
        procedure_occurrence=procedures,
    )


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


def _primary_diagnosis_by_person(
    dataset: OmopDataset, code_map: dict[int, str] | None = None
) -> dict[str, str]:
    """Diagnostic principal CIM-10 valide par personne (primary, sinon le plus précoce)."""
    by_person = _group_by(dataset.condition_occurrence, "person_id")
    result: dict[str, str] = {}
    for person_id, conditions in by_person.items():
        ordered = sorted(
            conditions,
            key=lambda r: (
                not _is_primary(r),
                parse_omop_date(r.get("condition_start_date")) or datetime.max,
            ),
        )
        for row in ordered:
            code = _resolve_condition_code(row, code_map)
            if code and CID10Validator.is_valid(code):
                result[person_id] = code
                break
    return result


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
        Une liste de dicts ``{person_id, service, start, end, disposition}``
        (``disposition`` renseignée pour le dernier séjour d'un décès, sinon None).
    """
    service_map = service_map if service_map is not None else DEFAULT_VISIT_SERVICE_MAP
    # Diagnostic principal par personne (fallback quand la visite n'en porte pas —
    # cas d'un OMOP générique où le diagnostic est dans condition_occurrence).
    primary = _primary_diagnosis_by_person(dataset)
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
        person_id = str(visit.get("person_id"))
        stays.append(
            {
                "person_id": person_id,
                "service": service,
                "start": parse_omop_date(visit.get("visit_start_date")),
                "end": parse_omop_date(visit.get("visit_end_date")),
                "disposition": visit.get("disposition"),
                "diagnosis": visit.get("diagnosis") or primary.get(person_id),
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
