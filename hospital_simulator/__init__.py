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
    omop_from_synthea_csv,
    omop_from_mimic,
)
from hospital_simulator.calibration import (
    estimate_transition_probabilities,
    estimate_length_of_stay,
    length_of_stay_samples,
    peak_concurrency,
    estimate_procedure_probabilities,
    build_pathway_from_transitions,
    diagnosis_group,
    estimate_transitions_by_group,
    estimate_diagnosis_mix,
)
from hospital_simulator.graph import HospitalGraph, build_hospital_graph
from hospital_simulator.validation import (
    describe,
    ks_two_sample,
    ks_one_sample,
    ks_exponential,
    ci_coverage,
    mae,
    mape,
    bias,
    wasserstein_1d,
    poisson_dispersion_test,
    markov_order_check,
)
from hospital_simulator.observed import (
    daily_census,
    census_sample,
    daily_arrivals,
    temporal_split,
)
from hospital_simulator.scenario import (
    Scenario,
    SimulationEngine,
    SimulationResult,
    ReplicatedResult,
    SensitivitySweepResult,
    run_scenario,
    run_replications,
    replicated_census,
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
    "omop_from_synthea_csv",
    "omop_from_mimic",
    "estimate_transition_probabilities",
    "estimate_length_of_stay",
    "length_of_stay_samples",
    "peak_concurrency",
    "estimate_procedure_probabilities",
    "build_pathway_from_transitions",
    "diagnosis_group",
    "estimate_transitions_by_group",
    "estimate_diagnosis_mix",
    "HospitalGraph",
    "build_hospital_graph",
    "describe",
    "ks_two_sample",
    "ks_one_sample",
    "ks_exponential",
    "ci_coverage",
    "mae",
    "mape",
    "bias",
    "wasserstein_1d",
    "poisson_dispersion_test",
    "markov_order_check",
    "daily_census",
    "census_sample",
    "daily_arrivals",
    "temporal_split",
    "Scenario",
    "SimulationEngine",
    "SimulationResult",
    "ReplicatedResult",
    "SensitivitySweepResult",
    "run_scenario",
    "run_replications",
    "replicated_census",
    "sensitivity_sweep",
]
