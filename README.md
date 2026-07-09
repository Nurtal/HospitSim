# Hospital Digital Twin Simulator (HDTS)

**A lightweight, data-driven hospital flow simulation framework based on clinical standards (CIM-10, CCAM, OMOP).**

## 🚀 Overview

Hospital systems are complex dynamic environments where patient flows, clinical decisions, resource constraints and adverse events interact continuously.

This project aims to build a **minimal, reproducible and extensible hospital simulation framework** allowing researchers and healthcare professionals to explore "what-if" scenarios:

* What happens if emergency department admissions increase by 30%?
* What is the impact of reduced ICU capacity?
* How does an epidemic wave affect hospital resources?
* How do patient characteristics and comorbidities influence care pathways?

The objective is not to reproduce the entire complexity of a hospital, but to provide a **simple and transparent simulation engine** that can be progressively enriched with real-world healthcare data.

---

# ⚡ Installation & Quickstart

## Installation

```bash
pip install -e ".[dev]"   # core + viz (matplotlib) + test extras
# core only (stdlib + pyyaml): pip install -e .
```

## Run a simulation and print a dashboard

```python
from hospital_simulator import Scenario, run_scenario, print_dashboard

result = run_scenario(Scenario(name="baseline", days=60, arrival_rate_per_day=12.0, seed=2026))
print_dashboard(result)
```

## What-if analysis with confidence intervals

```python
from hospital_simulator import Scenario, run_replications

base = Scenario(days=90, warmup_days=15, arrival_rate_per_day=12.0, seed=2026)
icu_cut = base.with_capacity_change("ICU", 0.8, name="-20% ICU beds")   # remove 20% of ICU beds

rep = run_replications(icu_cut, n_replications=40)   # 40 reproducible replications
print(rep.render_summary(metrics=["blocked_transfers", "ICU.saturation_days"]))
```

## Sensitivity sweep (dose–response with CIs)

```python
from hospital_simulator import Scenario, sensitivity_sweep

sweep = sensitivity_sweep(
    Scenario(days=90, warmup_days=15, seed=2026),
    parameter="capacity:ICU", values=[6, 8, 10, 12, 16, 20],
    metrics=["blocked_transfers", "ICU.saturation_days"], n_replications=40,
)
print(sweep.render())
# Figures (requires the `viz` extra):
# from hospital_simulator.plotting import plot_sensitivity
# plot_sensitivity(sweep, "blocked_transfers", save_path="sensitivity.png")
```

## Patient with a CIM-10 diagnosis and comorbidities

```python
from hospital_simulator import Patient

p = Patient(age=78, sexe="F", diagnostic_principal="J18.9")
p.add_comorbidity("I50.0")
p.add_comorbidity("E11.9")
```

## Calibrate from OMOP data

See the end-to-end, reproducible example at
[`examples/omop_to_scenario.py`](examples/omop_to_scenario.py): it builds a
synthetic OMOP dataset, recovers the transition/length-of-stay parameters via
`estimate_transition_probabilities` / `estimate_length_of_stay`, and runs a
calibrated, replicated what-if scenario.

---

# 🎯 Objectives

The project aims to provide:

* A patient-centered simulation model
* A hospital pathway engine based on clinical rules
* Integration with healthcare data standards
* Scenario-based simulation capabilities
* Reproducible hospital modeling

The framework is designed to bridge:

* Clinical data warehouses
* OMOP-based observational data
* French healthcare coding standards
* Discrete Event Simulation approaches

---

# 🏥 Core concepts

## Patient model

Patients are represented as digital entities with:

* Demographics
* Primary diagnosis
* Secondary diagnoses / comorbidities
* Clinical severity
* Current location in the hospital pathway
* Performed procedures
* Clinical events

Example:

```python
Patient(
    age=78,
    sexe="F",
    diagnostic_principal="J18.9",
    diagnostics_secondaires=["I50.0", "E11.9"],
)
```

Diagnoses are represented using:

* **CIM-10** coding system

---

# 🩺 Clinical pathways

Patient trajectories are described through clinical pathways.

Example:

```
Emergency Department

        |
        |
    Diagnosis

        |
 -----------------
 |       |        |
Ward   ICU    Discharge
```

Each pathway may define:

* Required procedures
* Possible transitions
* Length of stay distributions
* Adverse event probabilities

Example YAML definition:

```yaml
pneumonia:

  diagnosis:
    icd10: J18.9

  procedures:
    - chest_xray
    - blood_test
    - oxygen_therapy

  transitions:

    ICU: 0.08
    Ward: 0.85
    Discharge: 0.07
```

---

# 🏥 Hospital model

A hospital is represented as a network of services.

Examples:

* Emergency Department
* Medical wards
* Intensive Care Unit
* Radiology
* Operating rooms
* Outpatient clinics

Each service has:

* Capacity
* Waiting queue
* Average duration of stay
* Available procedures
* Routing rules

Example:

```python
registry = ServiceRegistry()
registry.register_service("ED", capacity=40)
```

---

# 🧪 Clinical procedures

Healthcare procedures are represented using:

* **CCAM** codes

Example:

```python
MedicalProcedure(name="Chest X-Ray", code="ZZLF900")
```

Procedures can depend on:

* Diagnosis
* Severity
* Clinical pathway
* Hospital protocols

---

# ⚠️ Clinical events

The simulation engine supports stochastic events:

Examples:

* ICU transfer
* Sepsis
* Acute deterioration
* Hospital-acquired infection
* Readmission
* Death

Example:

```yaml
event:

  name: sepsis

  probability: 0.04
```

---

# 🔄 Simulation engine

The simulator uses a **Discrete Event Simulation (DES)** approach.

A simulation consists of:

1. Patient generation
2. Patient arrival
3. Clinical pathway execution
4. Resource allocation
5. Event triggering
6. Patient outcome

Example:

```python
from hospital_simulator import Scenario, run_scenario

result = run_scenario(Scenario(days=30, seed=0))
```

---

# 🧬 Data integration

The framework is designed to work with healthcare data sources.

## OMOP compatibility

Patients can be generated from:

* OMOP Clinical Data Model
* Clinical Data Warehouses
* Synthetic datasets

Example workflow:

```
Hospital Data Warehouse

          |

        OMOP

          |

Patient generator

          |

Simulation engine

          |

Hospital scenario analysis
```

---

# 📊 Possible use cases

## Emergency department saturation

Scenario:

```
+40% respiratory infection admissions
```

Outputs:

* Waiting times
* Bed occupancy
* ICU pressure
* Patient outcomes

## ICU capacity planning

Scenario:

```
-20% ICU beds
```

Outputs:

* ICU overflow
* Delayed admissions
* Mortality impact

## Seasonal epidemic modeling

Scenario:

```
Influenza / COVID wave
```

Outputs:

* Resource consumption
* Hospital stress indicators

---

# 🧱 Project architecture (initial idea)

```
hdts/

├── patients/
│   ├── patient.py
│   └── generator.py

├── hospital/
│   ├── service.py
│   ├── pathway.py
│   └── resources.py

├── clinical/
│   ├── diagnosis.py
│   ├── procedure.py
│   └── events.py

├── simulation/
│   ├── engine.py
│   └── scheduler.py

├── data/
│   ├── omop/
│   └── examples/

├── scenarios/
│   └── pneumonia_wave.yaml

└── notebooks/
```

---

# 🛠 Roadmap

## Phase 1 — Minimal simulator

* [x] Patient object
* [x] Hospital services
* [x] Basic patient routing
* [x] Event simulation
* [x] Simple visualization

## Phase 2 — Clinical modeling

* [x] CIM-10 integration
* [x] CCAM procedures
* [x] Clinical pathway YAML files
* [x] Comorbidity handling

## Phase 3 — Data-driven calibration

* [x] OMOP import
* [x] Transition probability estimation
* [x] Length of stay estimation
* [x] Procedure probability estimation

## Phase 4 — Digital twin experiments

* [x] Scenario engine
* [x] Dashboard
* [x] Hospital stress indicators
* [x] Reproducible simulations

---

# 🔬 Scientific positioning

This project explores the concept of a lightweight healthcare digital twin based on:

* Discrete Event Simulation
* Clinical coding standards
* Real-world healthcare data
* Transparent and interpretable models

The goal is to create a practical bridge between clinical data warehouses and operational hospital modeling.

---

# 📜 License

Released under the [MIT License](LICENSE).

---

# 🤝 Contributions

Contributions, ideas and clinical use cases are welcome.

The project is currently in an early development phase.
