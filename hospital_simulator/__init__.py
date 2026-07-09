"""Hospital Digital Twin Simulator (HDTS) — API publique du package."""

from hospital_simulator.patient import Patient
from hospital_simulator.constants import ServiceType, DispositionType
from hospital_simulator.services.service_manager import ServiceManager
from hospital_simulator.services.service_registry import ServiceRegistry
from hospital_simulator.orchestration import HospitalFlowSimulator
from hospital_simulator.events import ClinicalEvent, EventEngine
from hospital_simulator.visualization import (
    render_registry,
    print_registry,
    render_dashboard,
    print_dashboard,
)
from hospital_simulator.models.data_structure import (
    Diagnosis,
    DiagnosisLocal,
    MedicalProcedure,
)
from hospital_simulator.models._cid_validator import CID10Validator
from hospital_simulator.models._ccam_validator import CCAMValidator
from hospital_simulator.pathways import (
    ClinicalPathway,
    load_pathways,
    load_pathways_from_dict,
    load_pathways_from_string,
)
from hospital_simulator.omop import (
    OmopDataset,
    patients_from_omop,
    stays_from_omop,
    conditions_from_omop,
    procedures_from_omop,
)
from hospital_simulator.calibration import (
    estimate_transition_probabilities,
    estimate_length_of_stay,
    estimate_procedure_probabilities,
    build_pathway_from_transitions,
)
from hospital_simulator.scenario import (
    Scenario,
    SimulationEngine,
    SimulationResult,
    ReplicatedResult,
    SensitivitySweepResult,
    run_scenario,
    run_replications,
    sensitivity_sweep,
)

__all__ = [
    "Patient",
    "ServiceType",
    "DispositionType",
    "ServiceManager",
    "ServiceRegistry",
    "HospitalFlowSimulator",
    "ClinicalEvent",
    "EventEngine",
    "render_registry",
    "print_registry",
    "render_dashboard",
    "print_dashboard",
    "Diagnosis",
    "DiagnosisLocal",
    "MedicalProcedure",
    "CID10Validator",
    "CCAMValidator",
    "ClinicalPathway",
    "load_pathways",
    "load_pathways_from_dict",
    "load_pathways_from_string",
    "OmopDataset",
    "patients_from_omop",
    "stays_from_omop",
    "conditions_from_omop",
    "procedures_from_omop",
    "estimate_transition_probabilities",
    "estimate_length_of_stay",
    "estimate_procedure_probabilities",
    "build_pathway_from_transitions",
    "Scenario",
    "SimulationEngine",
    "SimulationResult",
    "ReplicatedResult",
    "SensitivitySweepResult",
    "run_scenario",
    "run_replications",
    "sensitivity_sweep",
]
