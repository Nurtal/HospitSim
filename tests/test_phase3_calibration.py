"""Tests Phase 3 : import OMOP et estimateurs de calibration."""

import csv

import pytest

from hospital_simulator import (
    OmopDataset,
    Patient,
    build_pathway_from_transitions,
    conditions_from_omop,
    estimate_length_of_stay,
    estimate_procedure_probabilities,
    estimate_transition_probabilities,
    patients_from_omop,
    procedures_from_omop,
    stays_from_omop,
)


def _sample_dataset() -> OmopDataset:
    return OmopDataset(
        person=[
            {"person_id": "1", "gender_concept_id": "8532", "year_of_birth": "1945"},
            {"person_id": "2", "gender_concept_id": "8507", "year_of_birth": "1980"},
        ],
        condition_occurrence=[
            # Patient 1 : pneumonie (principale) + insuffisance cardiaque (comorbidité)
            {"person_id": "1", "condition_source_value": "J18.9",
             "condition_status_source_value": "primary", "condition_start_date": "2020-01-01"},
            {"person_id": "1", "condition_source_value": "I50.0",
             "condition_start_date": "2020-01-02"},
            # Patient 2 : pneumonie, code invalide ignoré
            {"person_id": "2", "condition_source_value": "J18.9",
             "condition_start_date": "2021-03-01"},
            {"person_id": "2", "condition_source_value": "NOT_A_CODE",
             "condition_start_date": "2021-03-01"},
        ],
        visit_occurrence=[
            {"person_id": "1", "visit_source_value": "ED",
             "visit_start_date": "2020-01-01", "visit_end_date": "2020-01-01"},
            {"person_id": "1", "visit_source_value": "Ward",
             "visit_start_date": "2020-01-02", "visit_end_date": "2020-01-07"},
            {"person_id": "2", "visit_source_value": "ED",
             "visit_start_date": "2021-03-01", "visit_end_date": "2021-03-01"},
            {"person_id": "2", "visit_source_value": "ICU",
             "visit_start_date": "2021-03-02", "visit_end_date": "2021-03-06"},
        ],
        procedure_occurrence=[
            {"person_id": "1", "procedure_source_value": "chest_xray"},
            {"person_id": "2", "procedure_source_value": "chest_xray"},
            {"person_id": "2", "procedure_source_value": "intubation"},
        ],
    )


# ----- OMOP import -----


class TestOmopImport:
    def test_patients_generated_with_demographics(self):
        patients = patients_from_omop(_sample_dataset(), reference_year=2025)
        assert len(patients) == 2
        by_id = {p.id: p for p in patients}
        p1 = by_id["omop-1"]
        assert p1.sexe == "F"
        assert p1.age == 2025 - 1945
        assert isinstance(p1, Patient)

    def test_primary_and_comorbidities_resolved(self):
        p1 = {p.id: p for p in patients_from_omop(_sample_dataset())}["omop-1"]
        assert p1.diagnostic_principal == "J189"  # normalisé (sans point)
        assert p1.diagnostics_secondaires == ["I500"]

    def test_invalid_codes_are_skipped(self):
        p2 = {p.id: p for p in patients_from_omop(_sample_dataset())}["omop-2"]
        assert p2.diagnostic_principal == "J189"
        assert p2.diagnostics_secondaires == []  # "NOT_A_CODE" ignoré

    def test_code_map_translates_concept_ids(self):
        ds = OmopDataset(
            person=[{"person_id": "9", "gender_concept_id": "8507", "year_of_birth": "1970"}],
            condition_occurrence=[{"person_id": "9", "condition_concept_id": "255848"}],
        )
        patients = patients_from_omop(ds, code_map={255848: "J18.9"})
        assert patients[0].diagnostic_principal == "J189"

    def test_load_from_csv_dir(self, tmp_path):
        ds = _sample_dataset()
        with (tmp_path / "person.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["person_id", "gender_concept_id", "year_of_birth"])
            w.writeheader()
            w.writerows(ds.person)
        loaded = OmopDataset.from_dir(tmp_path)
        assert len(loaded.person) == 2
        assert loaded.visit_occurrence == []  # table absente -> vide


# ----- Transition probability estimation -----


class TestTransitionEstimation:
    def test_transitions_normalized_and_terminal_added(self):
        stays = stays_from_omop(_sample_dataset())
        probs = estimate_transition_probabilities(stays)
        # Patient 1: ED->Ward, Patient 2: ED->ICU  => depuis ED : 50% Ward, 50% ICU
        assert probs["ED"] == {"Ward": 0.5, "ICU": 0.5}
        # Ward et ICU sont terminaux -> Discharge à 100%
        assert probs["Ward"] == {"Discharge": 1.0}
        assert probs["ICU"] == {"Discharge": 1.0}

    def test_no_terminal_when_disabled(self):
        stays = stays_from_omop(_sample_dataset())
        probs = estimate_transition_probabilities(stays, terminal=None)
        assert "Ward" not in probs  # aucune transition sortante observée

    def test_build_pathway_from_estimated_transitions(self):
        stays = stays_from_omop(_sample_dataset())
        probs = estimate_transition_probabilities(stays)
        pw = build_pathway_from_transitions("from_ed", probs["ED"], diagnosis_code="J18.9")
        assert abs(sum(pw.transitions.values()) - 1.0) < 1e-9
        assert pw.diagnosis_code == "J18.9"


# ----- Length of stay estimation -----


class TestLengthOfStay:
    def test_los_per_service(self):
        stays = stays_from_omop(_sample_dataset())
        los = estimate_length_of_stay(stays)
        assert los["Ward"]["mean"] == pytest.approx(5.0)  # 01->07 janvier
        assert los["ICU"]["mean"] == pytest.approx(4.0)   # 02->06 mars
        assert los["ED"]["n"] == 2
        assert los["ED"]["mean"] == pytest.approx(0.0)

    def test_missing_end_date_ignored(self):
        stays = [{"person_id": "1", "service": "ED", "start": "2020-01-01", "end": None}]
        assert estimate_length_of_stay(stays) == {}


# ----- Procedure probability estimation -----


class TestProcedureEstimation:
    def test_probabilities_conditioned_on_diagnosis(self):
        ds = _sample_dataset()
        conditions = conditions_from_omop(ds)
        procedures = procedures_from_omop(ds)
        probs = estimate_procedure_probabilities(conditions, procedures)
        # 2 patients avec J189, tous deux ont eu chest_xray -> 1.0
        assert probs["J189"]["chest_xray"] == pytest.approx(1.0)
        # 1 des 2 a eu intubation -> 0.5
        assert probs["J189"]["intubation"] == pytest.approx(0.5)
        # I500 : 1 patient (le n°1), pas d'intubation
        assert "intubation" not in probs["I500"]
