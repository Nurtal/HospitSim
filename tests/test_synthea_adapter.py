"""Tests de l'adaptateur Synthea CSV -> OmopDataset."""

import csv

from hospital_simulator import omop_from_synthea_csv, patients_from_omop, stays_from_omop


def _write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _make_synthea_dir(tmp_path):
    _write_csv(
        tmp_path / "patients.csv",
        ["Id", "BIRTHDATE", "GENDER"],
        [{"Id": "p1", "BIRTHDATE": "1950-06-01", "GENDER": "F"},
         {"Id": "p2", "BIRTHDATE": "1980-01-01", "GENDER": "M"}],
    )
    _write_csv(
        tmp_path / "encounters.csv",
        ["Id", "START", "STOP", "PATIENT", "ENCOUNTERCLASS", "CODE"],
        [
            {"Id": "e1", "START": "2020-01-01T08:00:00Z", "STOP": "2020-01-01T12:00:00Z",
             "PATIENT": "p1", "ENCOUNTERCLASS": "emergency", "CODE": "50849002"},
            {"Id": "e2", "START": "2020-01-01T12:00:00Z", "STOP": "2020-01-06T12:00:00Z",
             "PATIENT": "p1", "ENCOUNTERCLASS": "inpatient", "CODE": "1505002"},
            {"Id": "e3", "START": "2019-05-01T09:00:00Z", "STOP": "2019-05-01T09:20:00Z",
             "PATIENT": "p2", "ENCOUNTERCLASS": "wellness", "CODE": "162673000"},
        ],
    )
    return tmp_path


def test_hospital_only_filters_and_maps_services(tmp_path):
    ds = omop_from_synthea_csv(_make_synthea_dir(tmp_path))  # hospital_only=True
    services = {v["service"] for v in stays_from_omop(ds)}
    assert services == {"ED", "Ward"}   # emergency->ED, inpatient->Ward ; wellness exclu
    assert len(ds.person) == 2


def test_include_ambulatory_when_not_hospital_only(tmp_path):
    ds = omop_from_synthea_csv(_make_synthea_dir(tmp_path), hospital_only=False)
    services = {v["service"] for v in stays_from_omop(ds)}
    assert "outpatient_clinic" in services  # wellness -> outpatient_clinic

def test_demographics_mapped(tmp_path):
    ds = omop_from_synthea_csv(_make_synthea_dir(tmp_path))
    patients = {p.id: p for p in patients_from_omop(ds, reference_year=2020)}
    assert patients["omop-p1"].sexe == "F"
    assert patients["omop-p1"].age == 70  # 2020 - 1950


def test_iso_z_timestamps_give_positive_los(tmp_path):
    from hospital_simulator import length_of_stay_samples
    ds = omop_from_synthea_csv(_make_synthea_dir(tmp_path))
    los = length_of_stay_samples(stays_from_omop(ds))
    assert los["Ward"][0] > 4.9  # séjour inpatient ~5 jours
