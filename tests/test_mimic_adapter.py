"""Tests de l'adaptateur MIMIC-IV -> OmopDataset."""

import csv
import gzip

from hospital_simulator import (
    estimate_transition_probabilities,
    omop_from_mimic,
    patients_from_omop,
    stays_from_omop,
)
from hospital_simulator.omop import classify_mimic_careunit


def test_careunit_classification():
    assert classify_mimic_careunit("Emergency Department") == "ED"
    assert classify_mimic_careunit("Medical Intensive Care Unit (MICU)") == "ICU"
    assert classify_mimic_careunit("Surgical Intensive Care Unit (SICU)") == "ICU"
    assert classify_mimic_careunit("Coronary Care Unit (CCU)") == "ICU"
    assert classify_mimic_careunit("Medicine") == "Ward"
    assert classify_mimic_careunit("Med/Surg") == "Ward"


def _write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _write_csv_gz(path, fieldnames, rows):
    with gzip.open(path, "wt", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _make_mimic(tmp_path):
    hosp = tmp_path / "hosp"
    hosp.mkdir()
    _write_csv(
        hosp / "patients.csv",
        ["subject_id", "gender", "anchor_age", "anchor_year"],
        [{"subject_id": "10", "gender": "F", "anchor_age": "70", "anchor_year": "2180"},
         {"subject_id": "20", "gender": "M", "anchor_age": "55", "anchor_year": "2150"}],
    )
    # transfers en .csv.gz pour exercer la lecture gzip
    _write_csv_gz(
        hosp / "transfers.csv.gz",
        ["subject_id", "hadm_id", "eventtype", "careunit", "intime", "outtime"],
        [
            {"subject_id": "10", "hadm_id": "100", "eventtype": "admit",
             "careunit": "Emergency Department",
             "intime": "2180-01-01 08:00:00", "outtime": "2180-01-01 12:00:00"},
            {"subject_id": "10", "hadm_id": "100", "eventtype": "transfer",
             "careunit": "Medical Intensive Care Unit (MICU)",
             "intime": "2180-01-01 12:00:00", "outtime": "2180-01-04 12:00:00"},
            {"subject_id": "10", "hadm_id": "100", "eventtype": "transfer",
             "careunit": "Medicine",
             "intime": "2180-01-04 12:00:00", "outtime": "2180-01-09 12:00:00"},
            {"subject_id": "10", "hadm_id": "100", "eventtype": "discharge",
             "careunit": "", "intime": "2180-01-09 12:00:00", "outtime": ""},
        ],
    )
    _write_csv(
        hosp / "diagnoses_icd.csv",
        ["subject_id", "hadm_id", "seq_num", "icd_code", "icd_version"],
        [
            {"subject_id": "10", "hadm_id": "100", "seq_num": "1", "icd_code": "J189", "icd_version": "10"},
            {"subject_id": "10", "hadm_id": "100", "seq_num": "2", "icd_code": "I509", "icd_version": "10"},
            {"subject_id": "10", "hadm_id": "100", "seq_num": "3", "icd_code": "486", "icd_version": "9"},
        ],
    )
    _write_csv(
        hosp / "admissions.csv",
        ["subject_id", "hadm_id", "hospital_expire_flag", "discharge_location", "deathtime"],
        [{"subject_id": "10", "hadm_id": "100", "hospital_expire_flag": "1",
          "discharge_location": "DIED", "deathtime": "2180-01-09 12:00:00"}],
    )
    return tmp_path


def test_mimic_intra_hospital_transitions(tmp_path):
    ds = omop_from_mimic(_make_mimic(tmp_path))
    stays = stays_from_omop(ds)
    # Séjours groupés par admission (subject_hadm).
    assert all(s["person_id"] == "10_100" for s in stays if s["person_id"].startswith("10"))
    # Discharge (careunit vide) exclu -> 3 séjours pour l'admission.
    assert len([s for s in stays if s["person_id"] == "10_100"]) == 3

    trans = estimate_transition_probabilities(stays)
    assert trans["ED"] == {"ICU": 1.0}       # ED -> MICU
    assert trans["ICU"] == {"Ward": 1.0}     # MICU -> Medicine
    # Décès hospitalier (admissions) -> dernier séjour (Ward) terminal en Death.
    assert trans["Ward"] == {"Death": 1.0}


def test_mimic_death_marked_on_last_stay(tmp_path):
    ds = omop_from_mimic(_make_mimic(tmp_path))
    stays = stays_from_omop(ds)
    ward = [s for s in stays if s["service"] == "Ward"][0]
    assert ward["disposition"] == "Death"


def test_mimic_diagnoses_icd10_only_and_primary(tmp_path):
    ds = omop_from_mimic(_make_mimic(tmp_path))
    patients = {p.id: p for p in patients_from_omop(ds, reference_year=2180)}
    p = patients["omop-10"]
    assert p.sexe == "F"
    assert p.age == 70  # yob = anchor_year 2180 - anchor_age 70 = 2110 ; 2180 - 2110 = 70
    assert p.diagnostic_principal == "J189"        # seq_num 1
    assert "I509" in p.diagnostics_secondaires     # seq_num 2
    # Le code CIM-9 "486" est ignoré.
    assert "486" not in p.diagnostics_secondaires


def test_mimic_length_of_stay(tmp_path):
    from hospital_simulator import length_of_stay_samples
    ds = omop_from_mimic(_make_mimic(tmp_path))
    los = length_of_stay_samples(stays_from_omop(ds))
    assert los["ICU"][0] == 3.0   # MICU 01->04 janvier
    assert los["Ward"][0] == 5.0  # Medicine 04->09 janvier
