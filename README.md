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

## One-command standalone

`hdts.py` runs the whole pipeline end to end — it generates data with
**Synthea** (downloading the jar and exporting to OMOP if Java is available,
otherwise falling back to a synthetic dataset), calibrates transitions and
length of stay, validates the length-of-stay assumption, sizes service
capacities from the observed peak occupancy, and simulates a baseline + a
what-if scenario with confidence intervals — writing a report (and optional
figures):

```bash
python hdts.py                        # Synthea if available, else synthetic fallback
python hdts.py --patients 2000 --figures
python hdts.py --omop-dir /data/omop  # start from existing OMOP CSVs
python hdts.py --mimic-dir /data/mimiciv  # calibrate from MIMIC-IV (real ICU/ward transfers)
python hdts.py --mimic-dir /data/mimiciv --validate --figures  # + validation report & coverage figure
python hdts.py --no-synthea           # force the synthetic generator
```

It auto-builds an **explainable hospital graph** (services + per-diagnosis
routing), exports it to `hospital_graph.json` / `.dot`, and — with `--validate`
— writes a validation report (census CI-coverage, arrival Poisson test, LOS
KS/Wasserstein, Markov order-1 audit).

## Explainable model & diagnosis-conditioned routing

```python
from hospital_simulator import build_hospital_graph, OmopDataset, run_replications

graph = build_hospital_graph(OmopDataset.from_dir("/data/omop"))
print(graph.to_dict()["routing_by_group"])   # e.g. I21: ED->ICU, J18: ED->Ward
scenario = graph.to_scenario(seed=2026)       # diagnosis routing activated if data allows
print(run_replications(scenario, 40).render_summary(metrics=["deaths", "mortality_rate"]))
```

## Validation study (paper figures)

One script runs the whole validation protocol and writes the report + figures:

```bash
python scripts/validation_study.py --mimic-dir /data/mimiciv --output figures/
python scripts/validation_study.py --mimic-dir /data/mimiciv \
    --holdout-date 2150-06-01 --covid-split 2150-03-01   # + temporal hold-out & COVID back-test
python scripts/validation_study.py --synthetic --patients 800   # offline demo
```

It produces: census CI-coverage per service, LOS goodness-of-fit (KS + Wasserstein),
arrival-process Poisson check, Markov order-1 audit, temporal hold-out, and — with
`--covid-split` — a predictive **COVID natural-experiment back-test** (calibrate
pre-period, propagate the observed surge, compare predicted vs observed census and
mortality).

## Interactive demonstrator (optional)

```bash
pip install -e ".[app]"
streamlit run app/hdts_app.py    # tweak a what-if scenario, run, see indicators + figures
```

**Data sources.** Synthea is convenient but models lifelong care and no
intra-hospital ICU/ward transfers, so its transitions are coarse. **MIMIC-IV**
(`--mimic-dir`, credentialed access via PhysioNet) has real per-unit stays
(`transfers` table) and ICD-10 diagnoses, and is the recommended source for
intra-hospital transition/length-of-stay calibration; admissions are treated as
episodes (`hadm_id`) to recover clean ED → ICU → ward pathways.

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

# 🔬 Validation & publication roadmap (JMIR Medical Informatics)

**Target:** JMIR Medical Informatics — an Original Paper framed as a
**development-and-validation study** of a minimal, reproducible, OMOP-fed
hospital digital twin.

**Story.** A small, turnkey tool that plugs into a hospital **clinical data
warehouse (EDS)**, calibrates itself from routine data, and simulates "what-if"
scenarios from a set of initial conditions and simple rules. The study answers a
concrete capacity question on a **real EDS**, validates the tool against observed
reality, and is fully reproducible on the open **MIMIC-IV** dataset.

**Framing (fit-for-purpose).** The model is *deliberately* simple (Poisson
arrivals, exponential length of stay, Markov transitions, bed-blocking). It is
validated as **decision-support for directional capacity questions with
quantified uncertainty — not as a high-fidelity point predictor.** Validation
follows recognized frameworks: **Sargent** (V&V), **ISPOR-SMDM** (modeling good
research practices), reported per **STRESS-DES**.

## Validation ladder

| Level | Question | Status |
|---|---|---|
| Verification | Does the code implement the equations? | ✅ 153 tests, deterministic seeds |
| Recovery | Does calibration recover known parameters? | ✅ synthetic ground truth |
| Input validity | Do estimated params match the data (train/test)? | ⏳ V1/V2 |
| Assumption audit | Do Poisson / exponential / Markov hold? | ◐ KS on LOS done; extend |
| Operational validity | Does the simulated system reproduce observed outputs? | ⏳ V2 (core) |
| Predictive validity | Does it predict a *real* change (natural experiment)? | ⏳ V4 (COVID) |
| Sensitivity / cross-model | Robust? Consistent with an M/M/c queue? | ◐ sweeps done; add M/M/c |

## Phases

### Phase V0 — Foundations ✅
- [x] Simulation engine, OMOP calibration, Synthea/MIMIC-IV adapters, death
      modeling, multi-replication confidence intervals, sensitivity sweeps,
      figures, standalone `hdts.py`, 153 tests.

### Phase V1 — Validation tooling ✅
- [x] `validation.ci_coverage`: **CI-coverage** of observed census vs simulated 95% band
      (+ `scenario.replicated_census`, `plotting.plot_census_coverage`, `hdts.py --validate`).
- [x] Point-error metrics: `mae` / `mape` / `bias`.
- [x] Distributional: `ks_exponential` + `wasserstein_1d` on per-unit LOS.
- [x] **Arrival process test** (`poisson_dispersion_test`, index var/mean ≈ 1).
- [x] **Markov order-1 check** (`markov_order_check`, order-1 vs order-2 TV).
- [x] Temporal **hold-out** helper (`observed.temporal_split`) + observed series
      (`observed.daily_census` / `daily_arrivals`).

### Phase V1b — Explainable auto-construction ✅ (bonus)
- [x] First-class `HospitalGraph` auto-built from OMOP (`build_hospital_graph`,
      `to_scenario` / `to_json` / `to_dot`); **diagnosis-conditioned routing**
      (CIM-10 → parcours) wired into the engine with fallback for rare groups.
- [x] Lightweight Streamlit demonstrator (`app/hdts_app.py`, extra `app`).

### Phase V2 — Operational validation on MIMIC-IV (reproducible backbone)
- [ ] Calibrate on a training window; simulate; compare simulated vs observed:
      census/occupancy (CI coverage), LOS (KS/Wasserstein), bed-days, mortality.
- [ ] Report in-sample and out-of-sample (temporal hold-out) results.
- [ ] Public, re-runnable notebook so third parties reproduce the numbers.

### Phase V3 — Real EDS case study
- [ ] Extract an OMOP cohort from the EDS (chosen units, time window).
- [ ] Frame a concrete operational question (e.g., ICU/ward capacity, surge).
- [ ] Calibrate + validate outputs against the EDS (same metrics as V2).

### Phase V4 — Predictive validation: COVID-19 natural experiment (the headline)
- [ ] Calibrate on the **pre-COVID** period.
- [ ] Run the surge what-if corresponding to the observed 2020–2022 wave.
- [ ] Compare **predicted vs observed** stress (peak occupancy, saturation days,
      mortality) — observed values within the model's CI = predictive validation
      of the what-if capability.

### Phase V5 — Assumption audit, sensitivity, face validity
- [ ] Assumption audit section (arrivals/LOS/Markov) → documents the operating
      envelope and motivates future extensions (log-normal / phase-type LOS).
- [ ] Sensitivity analysis of conclusions (parameter sweeps with CIs).
- [ ] **Face validity**: 2–3 clinicians / bed managers rate plausibility and
      usefulness of the dashboard/indicators (short Likert + qualitative).

### Phase V6 — Manuscript & submission
- [ ] IMRaD + structured abstract; report per STRESS-DES.
- [ ] Tag release + **Zenodo DOI**; data/code availability statement.
- [ ] Submit to JMIR Medical Informatics (budget the APC; ethics note: EDS
      governance / MIMIC-IV DUA).

## Key validation metrics
Census **CI-coverage %**, LOS **KS D / p** and **Wasserstein**, arrival
**dispersion index**, occupancy/bed-days/mortality **MAE·MAPE·bias**,
temporal-holdout error, what-if **non-overlapping CIs**, COVID back-test
**predicted-vs-observed within CI**.

## Headline figures
1. Observed daily census overlaid on the simulated 95% CI band (coverage %).
2. COVID back-test: predicted vs observed surge stress indicators.
3. Sensitivity dose–response curves (e.g. ICU beds → blocked transfers) with CIs.

> A more detailed working plan lives in
> [`docs/jmir_submission_roadmap.md`](docs/jmir_submission_roadmap.md).

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
