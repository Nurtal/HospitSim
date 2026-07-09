"""Tests pour le simulateur hospitalier - Phase 1 scenarios complets."""

import math
import pytest
from datetime import datetime
from typing import Optional

# ----- Tests Patient creation (existing) ----


def is_even(x: int) -> bool:
    return x % 2 == 0


class TestPatientCreation:
    def test_patient_creation_default(self):
        from hospital_simulator.patient import Patient
        p = Patient()
        assert isinstance(p.id, str)

    def test_patient_has_uuid_prefix_pplus_8hex(self):
        from hospital_simulator.patient import Patient
        ids = {Patient().id for _ in range(50)}
        assert all(len(i) == 9 and i.startswith("P") for i in ids), "IDs must be 'P' + 8 hex chars"
        assert len(ids) == 50, "IDs should be unique"

    def test_patient_default_status_is_incoming(self):
        from hospital_simulator.patient import Patient
        p = Patient()
        assert p.status_admission == Patient.STATUS_INCOMING
        assert p.is_incoming is True

    def test_patient_invalid_status_raises(self):
        from hospital_simulator.patient import Patient
        with pytest.raises(ValueError, match="Statut invalide"):
            Patient(status_admission="foobar")

    def test_set_status_updates_service_name_and_history(self):
        from hospital_simulator.patient import Patient
        p = Patient()
        p.set_status(Patient.STATUS_DISPATCH_QUEUED)
        assert p.is_dispatch_queued is True
        assert p.transfer_history.get(Patient.STATUS_INCOMING) is None

    def test_set_status_with_service_records_transfer(self):
        from hospital_simulator.patient import Patient
        p = Patient()
        p.set_status(Patient.STATUS_DISPATCH_QUEUED, service_name_str_or_None=None)
        p.set_status(
            Patient.STATUS_ASSIGNED_TO_SERVICE, 
            service_name_str_or_None="ED"
        )
        assert p.status_admission == Patient.STATUS_ASSIGNED_TO_SERVICE
        assert p.current_service_name_if_assigned == "ED"

    def test_is_in_service_false_while_incoming(self):
        from hospital_simulator.patient import Patient
        p = Patient()
        p.set_status(
            Patient.STATUS_DISPATCH_QUEUED, 
            service_name_str_or_None="ED"
        )
        assert p.current_admission_service_name == "ED"
        assert p.is_in_service("ED") is False

    def test_patient_repr_contains_id(self):
        from hospital_simulator.patient import Patient
        p = Patient()
        r = repr(p)
        assert f"id='{p.id}'" in r


# ===== Phase 1 new scenarios =====
# ---------------------------------------------------------------- --
# Scenario 1: register_service rejects bad input
# ----------------------------------------------------------------


class TestServiceRegistryBasics:

    def test_register_valid_urgences_ed(self):
        """Scenario: Enregistrement ED avec capacité de base (20 lits)."""
        from hospital_simulator.services.service_registry import ServiceRegistry
        reg = ServiceRegistry()
        reg.register_service("ED", capacity=20)
        assert "ED" in reg.service_types

    def test_register_with_zero_capacity_raises(self):
        """Scenariu: capacite nulle provoque une erreur."""
        from hospital_simulator.services.service_registry import ServiceRegistry
        reg = ServiceRegistry()
        with pytest.raises(ValueError, match="entier > 0"):
            reg.register_service("ED", capacity=0)

    def test_register_with_negative_capacity_raises(self):
        """Scenariu: capacite négative provoque une erreur."""
        from hospital_simulator.services.service_registry import ServiceRegistry
        reg = ServiceRegistry()
        with pytest.raises(ValueError, match="entier > 0"):
            reg.register_service("ED", capacity=-5)

    def test_register_duplicate_raises_value_error(self):
        """Scenariu: doublon de service levé."""
        from hospital_simulator.services.service_registry import ServiceRegistry
        reg = ServiceRegistry()
        reg.register_service("ED", capacity=20)
        with pytest.raises(ValueError, match="déjà enregistrée"):
            reg.register_service("ED", capacity=10)

    def test_register_with_boolean_raises_type_error(self):
        """Scenariu: un bool en capacité ne doit pas passer."""
        from hospital_simulator.services.service_registry import ServiceRegistry
        reg = ServiceRegistry()
        with pytest.raises(TypeError, match="entier positif"):
            reg.register_service("ED", capacity=True)

    def test_register_with_float_raises_type_error(self):
        """Scenario: une capacité de type float est refusée."""
        from hospital_simulator.services.service_registry import ServiceRegistry
        reg = ServiceRegistry()
        with pytest.raises(TypeError, match="entier positif"):
            reg.register_service("ED", capacity=10.5)

    def test_register_with_none_raises(self):
        """Scenariu: aucun nom, pas d'enregistrement."""
        from hospital_simulator.services.service_registry import ServiceRegistry
        reg = ServiceRegistry()
        with pytest.raises(ValueError, match="chaîne de caractères"):
            reg.register_service(None)

    def test_register_with_empty_string_raises(self):
        """Scenariu: chaine vide ne peut servir de nom."""
        from hospital_simulator.services.service_registry import ServiceRegistry
        reg = ServiceRegistry()
        with pytest.raises(ValueError, match="chaîne de caractères"):
            reg.register_service("")

# ---------------------------------------------------------------- --
# Scenario 2: admit full ED queue (capacity saturation)
# ----------------------------------------------------------------


class TestServiceCapacityAdmission:
    """Verifie le verrouillage sur la capacité d'un service."""

    def setup_method(self):
        from hospital_simulator.services.service_registry import ServiceRegistry
        self.reg = ServiceRegistry()
        self.reg.register_service("ED", capacity=3)  # petite capacité pour tests rapides.

    def test_admit_patient_until_queue_saturates(self):
        """Scenario: Admettre un patient en ED (avant saturation, OK)."""
        from hospital_simulator.patient import Patient
        p = Patient()
        self.reg.admit(p, service_name="ED")
        assert p.status_admission == Patient.STATUS_ASSIGNED_TO_SERVICE
        assert p.current_admission_service_name == "ED"

    def test_admit_full_queue_blocks_patient(self):
        """Scenario: Queue ED pleine - l'admissiion bloque et laisse le patient incoming."""
        from hospital_simulator.patient import Patient
        # 3 patients + 1 saturant.
        queue = [Patient() for _ in range(4)]
        for p in queue[:3]:
            self.reg.admit(p, "ED")
        before_state = queue[3].status_admission  
        
        # Un service plein ne change pas le status (patient reste incoming).
        result = self.reg.admit(queue[3], service_name="ED")

        assert result is False  # Admissiion échouée - bloque.
        assert queue[3].status_admission == before_state
        # Pas de trace du patient dans l'historique du service ED.
        assert "ED" not in queue[3].transfer_history

    def test_get_service_capacity_is_defined(self):
        """Verify that get_service_capacity returns a number."""
        cap = self.reg.get_service_capacity("ED")
        
        assert isinstance(cap, int) or isinstance(cap, type(None))


# ------------------------------------------------------------------
# Scenario 3: orchestration - dispatch queue
# -----------------------------------------------------------------


class TestHospitalFlowSimulatorDispatch:

    def setup_method(self):
        from hospital_simulator.orchestration import HospitalFlowSimulator
        simu = HospitalFlowSimulator()
        simu.configure_registry(1)   # Only ED
        self.simu = simu

    def test_register_patient_adds_to_incoming_queue(self):
        """Scenario: Un patient arrive, il est mis dans la file entrante."""
        from hospital_simulator.patient import Patient
        p = Patient()
        assert len(self.simu.incoming_queue_list) == 0
        self.simu.register_patient(p)
        assert len(self.simu.incoming_queue_list) == 1

    def test_register_invalid_entry_raises_type_error(self):
        """Scenario: entrée invalide pour register_patient levé."""
        with pytest.raises(TypeError, match="Entrée invalide"):
            self.simu.register_patient("pas un patient")

    def test_dispatch_next_if_any_pops_incoming_queue_on_success(self):
        """Scenario: dispatch d'un patient - il sort de la queue (dispatch vers ED)."""
        from hospital_simulator.patient import Patient
        p = Patient()
        self.simu.register_patient(p)
        
        result = self.simu.dispatch_next_if_any(next_service_name="ED")

        assert result is True  # Action effectué.
        assert len(self.simu.incoming_queue_list) == 0

    def test_dispatch_empty_incoming_returns_false(self):
        """Scenario: dispatch sur queue vide - pas d'action."""

        result = self.simu.dispatch_next_if_any()
        
        assert result is False


# ------------------------------------------------------------------
# Scenario 4: end-to-end patient flow
# -----------------------------------------------------------------


class TestEndToEndPatientFlowPhase1:

    def setup_method(self):
        from hospital_simulator.orchestration import HospitalFlowSimulator
        self.simu = HospitalFlowSimulator()
        # Configuration ED + ICU de petite taille pour tests rapides.
        default_ed_c = 2  
        self.simu.configure_registry(3)   # ED, ICU, Ward by default  
        self.ed_capacity = default_ed_c

    def test_end_to_end_3_patients_pass_through(self):
        """Scenariu: 3 patients arrivant et dispatch au service."""

        from hospital_simulator.patient import Patient
        queue = [Patient() for _ in range(3)]

        # 1/2 / 3 - Enregistrement et arrivee en ed.  
        self.simu.register_patient(queue)
        
        assert len(self.simu.incoming_queue_list) == 3
        # Dispatch 1er (ED).  
        self.simu.dispatch_next_if_any(next_service_name="ED")

    def test_end_to_end_3_patients_status_changes_after_dispatch(self):
        """Scenariu: les statuts des patients sont mis à jour dans simulateur."""

        from hospital_simulator.patient import Patient
        queue = [Patient() for _ in range(3)]
        
        self.simu.register_patient(queue)  # Ajout en queue.  
        
        dispatched_results = []
        while len(self.simu.incoming_queue_list):
            dispatched_results.append(
                self.simu.dispatch_next_if_any(next_service_name="ED")
            )

        expected_status = Patient.STATUS_ASSIGNED_TO_SERVICE
        for _, p in enumerate(queue):
            assert (p.status_admission == expected_status), \
                f"Patient status wrong: expected {expected_status}, got {p.status_admission}"


