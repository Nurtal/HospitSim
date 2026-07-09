"""Tests Phase 2 : CIM-10, CCAM, parcours cliniques YAML, comorbidités."""

import random
from pathlib import Path

import pytest

from hospital_simulator import (
    CCAMValidator,
    CID10Validator,
    ClinicalPathway,
    Diagnosis,
    MedicalProcedure,
    Patient,
    load_pathways,
    load_pathways_from_string,
)


# ----- CIM-10 integration -----


class TestCID10Validator:
    @pytest.mark.parametrize("code", ["J18.9", "I50.0", "E11.9", "J189", "J18", "Z00"])
    def test_valid_codes(self, code):
        assert CID10Validator.is_valid(code) is True

    @pytest.mark.parametrize("code", ["", "J1", "123", "bad", "JJ18", None, 42])
    def test_invalid_codes(self, code):
        assert CID10Validator.is_valid(code) is False

    def test_normalize_strips_dot_and_uppercases(self):
        assert CID10Validator.normalize("j18.9") == "J189"

    def test_normalize_rejects_invalid(self):
        with pytest.raises(ValueError):
            CID10Validator.normalize("nope")


class TestDiagnosis:
    def test_dotted_code_normalized(self):
        d = Diagnosis("J18.9", description="Pneumonie")
        assert d.code == "J189"
        assert d.get_code() == "J189"

    def test_invalid_code_raises(self):
        with pytest.raises(ValueError, match="CIM-10 invalide"):
            Diagnosis("nope")

    def test_equality_by_code(self):
        assert Diagnosis("J18.9") == Diagnosis("J189")


# ----- CCAM procedures -----


class TestCCAM:
    @pytest.mark.parametrize("code", ["ZZLF900", "DZQM006"])
    def test_valid(self, code):
        assert CCAMValidator.is_valid(code) is True

    @pytest.mark.parametrize("code", ["ZZLF90", "zzlf9000", "1234567", ""])
    def test_invalid(self, code):
        assert CCAMValidator.is_valid(code) is False

    def test_procedure_with_code(self):
        proc = MedicalProcedure("Chest X-Ray", duration_minutes=15, code="zzlf900")
        assert proc.code == "ZZLF900"
        assert proc.name == "Chest X-Ray"

    def test_procedure_without_code(self):
        proc = MedicalProcedure("Blood test")
        assert proc.code is None
        assert proc.duration_minutes == 0

    def test_procedure_invalid_code_raises(self):
        with pytest.raises(ValueError, match="CCAM invalide"):
            MedicalProcedure("bad", code="XX")

    def test_procedure_negative_duration_raises(self):
        with pytest.raises(ValueError):
            MedicalProcedure("x", duration_minutes=-1)


# ----- Comorbidity handling -----


class TestComorbidities:
    def test_patient_with_valid_diagnoses(self):
        p = Patient(diagnostic_principal="J18.9", diagnostics_secondaires=["I50.0", "E11.9"])
        assert p.comorbidity_count == 2
        assert p.has_comorbidities is True

    def test_patient_invalid_primary_raises(self):
        with pytest.raises(ValueError, match="CIM-10 invalide"):
            Patient(diagnostic_principal="not_a_code")

    def test_patient_invalid_secondary_raises(self):
        with pytest.raises(ValueError, match="CIM-10 invalide"):
            Patient(diagnostics_secondaires=["bad"])

    def test_add_comorbidity_is_deduplicated(self):
        p = Patient(diagnostic_principal="J18.9")
        p.add_comorbidity("I50.0")
        p.add_comorbidity("I50.0")
        assert p.comorbidity_count == 1

    def test_add_invalid_comorbidity_raises(self):
        p = Patient()
        with pytest.raises(ValueError):
            p.add_comorbidity("xxx")

    def test_default_patient_has_no_comorbidities(self):
        assert Patient().has_comorbidities is False


# ----- Clinical pathway YAML -----

_PNEUMONIA_YAML = """
pneumonia:
  diagnosis:
    icd10: J18.9
  procedures:
    - chest_xray
    - blood_test
  transitions:
    ICU: 0.08
    Ward: 0.85
    Discharge: 0.07
"""


class TestClinicalPathways:
    def test_load_from_string(self):
        pathways = load_pathways_from_string(_PNEUMONIA_YAML)
        pw = pathways["pneumonia"]
        assert pw.diagnosis_code == "J18.9"
        assert "chest_xray" in pw.procedures
        assert pw.transitions["Ward"] == 0.85

    def test_load_bundled_example_file(self):
        path = Path(__file__).resolve().parents[1] / "hospital_simulator" / "data" / "pathways.yaml"
        pathways = load_pathways(path)
        assert "pneumonia" in pathways
        assert "heart_failure" in pathways

    def test_transitions_must_sum_to_one(self):
        with pytest.raises(ValueError, match="somme des transitions"):
            ClinicalPathway("bad", transitions={"Ward": 0.5, "ICU": 0.2})

    def test_probability_out_of_range_raises(self):
        with pytest.raises(ValueError, match="hors"):
            ClinicalPathway("bad", transitions={"Ward": 1.5})

    def test_invalid_diagnosis_code_raises(self):
        with pytest.raises(ValueError, match="CIM-10 invalide"):
            ClinicalPathway("bad", diagnosis_code="nope", transitions={"Ward": 1.0})

    def test_next_destination_is_reproducible(self):
        pw = load_pathways_from_string(_PNEUMONIA_YAML)["pneumonia"]
        seq1 = [pw.next_destination(random.Random(3)) for _ in range(5)]
        seq2 = [pw.next_destination(random.Random(3)) for _ in range(5)]
        assert seq1 == seq2
        assert all(dest in {"ICU", "Ward", "Discharge"} for dest in seq1)

    def test_next_destination_without_transitions_raises(self):
        with pytest.raises(ValueError, match="aucune transition"):
            ClinicalPathway("empty").next_destination()
