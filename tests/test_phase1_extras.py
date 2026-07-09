"""Tests Phase 1 : métriques d'orchestration, événements cliniques, visualisation."""

import pytest

from hospital_simulator import (
    ClinicalEvent,
    DispositionType,
    EventEngine,
    HospitalFlowSimulator,
    Patient,
    ServiceRegistry,
    render_registry,
)
from hospital_simulator.visualization import render_occupancy_bar


# ----- Orchestration metrics -----


class TestOrchestrationMetrics:
    def setup_method(self):
        self.simu = HospitalFlowSimulator()
        self.simu.configure_registry(3)  # ED, ICU, Ward

    def test_num_patients_counts_queue_and_admitted(self):
        self.simu.register_patient([Patient() for _ in range(3)])
        assert self.simu.num_patients_in_system == 3
        # Dispatch un patient vers ED : il quitte la file mais reste dans le système.
        self.simu.dispatch_next_if_any(next_service_name="ED")
        assert self.simu.num_patients_in_system == 3
        assert len(self.simu.incoming_queue_list) == 2

    def test_summarize_registry_status_reports_occupancy(self):
        self.simu.register_patient([Patient() for _ in range(2)])
        self.simu.dispatch_next_if_any(next_service_name="ED")
        summary = self.simu.summarize_registry_status()
        assert summary["ED"] == 1
        assert summary["ICU"] == 0
        assert summary["incoming_queue"] == 1

    def test_assert_registry_initialized_raises_on_empty(self):
        with pytest.raises(RuntimeError, match="pas initialisé"):
            HospitalFlowSimulator._assert_registry_is_initialized(ServiceRegistry())


# ----- Clinical events -----


class TestClinicalEvents:
    def test_probability_out_of_range_raises(self):
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            ClinicalEvent("sepsis", 1.5)

    def test_certain_event_always_triggers_and_is_reproducible(self):
        engine = EventEngine(seed=1)
        engine.register(ClinicalEvent("always", probability=1.0))
        p = Patient()
        triggered = engine.evaluate(p)
        assert [e.name for e in triggered] == ["always"]

    def test_impossible_event_never_triggers(self):
        engine = EventEngine(seed=1)
        engine.register(ClinicalEvent("never", probability=0.0))
        assert engine.evaluate(Patient()) == []

    def test_same_seed_gives_same_sequence(self):
        def run():
            eng = EventEngine(seed=99)
            eng.register(ClinicalEvent("e", probability=0.5))
            return [bool(eng.evaluate(Patient())) for _ in range(20)]

        assert run() == run()

    def test_disposition_death_discharges_patient(self):
        engine = EventEngine(seed=1)
        engine.register(
            ClinicalEvent("death", probability=1.0, disposition=DispositionType.DEATH)
        )
        p = Patient()
        engine.evaluate(p)
        assert p.status_admission == Patient.STATUS_DISCHARGED

    def test_disposition_transfer_icu_updates_service(self):
        engine = EventEngine(seed=1)
        engine.register(
            ClinicalEvent(
                "icu", probability=1.0, disposition=DispositionType.TRANSFER_TO_ICU
            )
        )
        p = Patient()
        engine.evaluate(p)
        assert p.status_admission == Patient.STATUS_TRANSFERRED_OUT
        assert p.current_admission_service_name == "ICU"


# ----- Visualization -----


class TestVisualization:
    def test_occupancy_bar_format(self):
        bar = render_occupancy_bar(5, 20, width=20)
        assert bar == "[#####---------------] 5/20 (25%)"

    def test_occupancy_bar_clamps_overflow(self):
        bar = render_occupancy_bar(30, 20, width=10)
        assert bar.startswith("[##########]")

    def test_occupancy_bar_zero_capacity_raises(self):
        with pytest.raises(ValueError):
            render_occupancy_bar(0, 0)

    def test_render_registry_lists_services(self):
        reg = ServiceRegistry()
        reg.register_service("ED", capacity=10)
        reg.admit(Patient(), service_name="ED")
        out = render_registry(reg)
        assert "ED" in out
        assert "1/10" in out

    def test_render_registry_empty(self):
        assert render_registry(ServiceRegistry()) == "(aucun service enregistré)"
