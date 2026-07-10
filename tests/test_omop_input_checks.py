"""Tests d'import : tables OMOP requises, table death, CSV plat, validateur."""

import csv

import pytest

from hospital_simulator import (
    OmopDataset,
    estimate_transition_probabilities,
    omop_from_flat_csv,
    stays_from_omop,
    validate_omop_dataset,
)


def _write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _make_omop_dir(tmp_path, with_death=True):
    _write_csv(tmp_path / "person.csv",
               ["person_id", "gender_concept_id", "year_of_birth"],
               [{"person_id": "1", "gender_concept_id": "8532", "year_of_birth": "1950"}])
    _write_csv(tmp_path / "visit_occurrence.csv",
               ["person_id", "visit_source_value", "visit_start_date", "visit_end_date"],
               [{"person_id": "1", "visit_source_value": "ED",
                 "visit_start_date": "2020-01-01", "visit_end_date": "2020-01-01"},
                {"person_id": "1", "visit_source_value": "ICU",
                 "visit_start_date": "2020-01-02", "visit_end_date": "2020-01-06"}])
    _write_csv(tmp_path / "condition_occurrence.csv",
               ["person_id", "condition_source_value", "condition_status_source_value",
                "condition_start_date"],
               [{"person_id": "1", "condition_source_value": "I21",
                 "condition_status_source_value": "primary", "condition_start_date": "2020-01-01"}])
    if with_death:
        _write_csv(tmp_path / "death.csv", ["person_id", "death_date"],
                   [{"person_id": "1", "death_date": "2020-01-06"}])
    return tmp_path


class TestOmopDirImport:
    def test_from_dir_loads_required_tables(self, tmp_path):
        ds = OmopDataset.from_dir(_make_omop_dir(tmp_path))
        assert len(ds.person) == 1
        assert len(ds.visit_occurrence) == 2
        assert len(ds.condition_occurrence) == 1
        assert len(ds.death) == 1

    def test_stays_carry_diagnosis_and_death(self, tmp_path):
        ds = OmopDataset.from_dir(_make_omop_dir(tmp_path))
        stays = stays_from_omop(ds)
        assert all(s["diagnosis"] == "I21" for s in stays)  # depuis condition_occurrence
        # Décès (table death) marqué sur le dernier séjour (ICU).
        icu = [s for s in stays if s["service"] == "ICU"][0]
        assert icu["disposition"] == "Death"
        assert estimate_transition_probabilities(stays)["ICU"] == {"Death": 1.0}

    def test_missing_death_means_no_mortality(self, tmp_path):
        ds = OmopDataset.from_dir(_make_omop_dir(tmp_path, with_death=False))
        assert all(s.get("disposition") != "Death" for s in stays_from_omop(ds))


class TestFlatCsv:
    def test_single_flat_csv_input(self, tmp_path):
        path = tmp_path / "stays.csv"
        _write_csv(path,
                   ["person_id", "service", "start", "end", "diagnosis", "disposition", "sex", "age"],
                   [{"person_id": "p1", "service": "ED", "start": "2023-01-01", "end": "2023-01-01",
                     "diagnosis": "I21", "disposition": "", "sex": "M", "age": "70"},
                    {"person_id": "p1", "service": "ICU", "start": "2023-01-02", "end": "2023-01-06",
                     "diagnosis": "I21", "disposition": "Death", "sex": "M", "age": "70"}])
        ds = omop_from_flat_csv(path)
        stays = stays_from_omop(ds)
        assert {s["service"] for s in stays} == {"ED", "ICU"}
        assert estimate_transition_probabilities(stays)["ED"] == {"ICU": 1.0}
        assert estimate_transition_probabilities(stays)["ICU"] == {"Death": 1.0}
        assert ds.person[0]["gender_concept_id"] == "8507"


class TestValidator:
    def test_validator_ok_and_flags(self, tmp_path):
        ds = OmopDataset.from_dir(_make_omop_dir(tmp_path))
        report = validate_omop_dataset(ds)
        assert report["ok"] is True
        assert report["n_stays"] == 2
        assert set(report["services"]) == {"ED", "ICU"}
        assert report["has_diagnosis"] is True
        assert report["has_disposition"] is True

    def test_validator_rejects_empty(self):
        report = validate_omop_dataset(OmopDataset())
        assert report["ok"] is False
        assert any("aucune visite" in m for m in report["messages"])
