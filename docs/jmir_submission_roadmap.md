# Roadmap — Submission to JMIR Medical Informatics

Target venue: **JMIR Medical Informatics** (open access, peer-reviewed,
health/medical informatics). Article type: **Original Paper** framed as a
*development-and-evaluation* study of a reproducible, OMOP-calibrated hospital
digital-twin simulator.

> Status of the software as of 2026-07: functional 4-phase framework, 114 tests,
> stochastic rigor (multi-replication CIs) in place, self-contained OMOP demo.
> The **software is ready**; the **manuscript and its evaluation are not yet done**.

---

## 1. Positioning / angle for JMIR MI

JMIR MI reviewers reward: a clear clinical-informatics problem, methodological
soundness, reproducibility, and demonstrated usefulness — **not** raw novelty or
a high-impact clinical outcome. Frame the paper as:

> "An open-source, transparent, OMOP-calibrated discrete-event digital twin of
> hospital patient flow, and its evaluation on \[dataset], enabling reproducible
> what-if analysis of capacity and admission scenarios."

Three pillars, matching JMIR's implicit **Develop → Demonstrate → Evaluate**:
1. **Develop** — the framework (patients, CIM-10/CCAM, pathways, DES engine).
2. **Demonstrate** — calibration from OMOP + reproducible what-if scenarios.
3. **Evaluate** — face/empirical validity + reproducibility + (light) usability.

---

## 2. Gap analysis (what's missing beyond the current code)

| Need | Current state | Required for JMIR |
|------|---------------|-------------------|
| Real / realistic data | synthetic only | ≥1 dataset run (Synthea→OMOP, or MIMIC-IV/eICU) |
| Empirical validation | none | compare simulated LOS/occupancy vs data or literature |
| Statistical rigor | ✅ multi-replication CIs | keep; add sensitivity analysis |
| Reproducibility artifacts | ✅ CI, tests, example | + Zenodo DOI, pinned versions, data/code availability statement |
| Manuscript | none | full IMRaD + structured abstract |
| Reporting standard | n/a | follow modeling best practice (e.g., STRESS-DES / ISPOR-SMDM) |
| Usability signal | none | light expert feedback on the dashboard/indicators |
| Docs polish | README API examples stale | fix API examples, add tutorial notebook |

---

## 3. Phased work plan

### Phase A — Data & validation (highest priority, ~2–3 weeks)
- [ ] Pick the demonstration dataset. Recommended: **Synthea → OMOP** (fully
      open, no IRB/GDPR friction). Fallback: MIMIC-IV (needs credentialing).
- [ ] Build a reproducible ETL notebook: dataset → OMOP tables → `patients_from_omop`,
      `stays_from_omop`, `estimate_*`.
- [ ] **Validation**: compare simulated vs observed distributions of
      length-of-stay and service occupancy (KS test / mean-absolute-error), and
      cross-check transition probabilities vs the data. Report figures + metrics.
- [ ] **Sensitivity analysis**: one-parameter sweeps (arrival rate, ICU capacity,
      mean LOS) reporting an indicator vs parameter, with CIs. (Needs a small
      `sensitivity_sweep` helper — not yet built.)

### Phase B — Experiments / results (~1–2 weeks)
- [ ] Define 2–3 what-if scenarios mirroring the README use cases
      (+X% respiratory admissions; −Y% ICU beds; epidemic wave).
- [ ] Run each with `run_replications` (n ≥ 30), report stress indicators with
      95% CIs; highlight non-overlapping CIs as the key finding.
- [ ] Produce publication-quality figures (occupancy time series with CI bands,
      indicator-vs-parameter curves). Add a `matplotlib` renderer behind the
      existing `viz` extra.

### Phase C — Reproducibility & artifacts (~few days)
- [ ] Tag a release; mint a **Zenodo DOI**; add "Data and Code Availability".
- [ ] Convert `examples/omop_to_scenario.py` into a runnable **tutorial notebook**
      under `notebooks/`.
- [ ] Fix stale README API examples (`sexe`, `diagnostic_principal`,
      `diagnostics_secondaires`) and add a Quickstart.
- [ ] Freeze environment (pin versions / ship `uv.lock`), ensure CI green.

### Phase D — Manuscript (~2–3 weeks, overlaps C)
- [ ] Draft IMRaD (see §4).
- [ ] Write the **structured abstract** (Background/Objective/Methods/Results/Conclusions).
- [ ] Optional but valuable: short **expert evaluation** — 2–3 clinicians or bed
      managers rate the dashboard/indicators (usefulness, interpretability),
      report qualitatively.
- [ ] Internal review pass; language polish.

### Phase E — Submission (~1 week)
- [ ] Prepare JMIR submission package (see §6).
- [ ] Submit; plan for one major-revision cycle.

---

## 4. Manuscript structure (IMRaD, JMIR)

- **Structured abstract** (required):
  - *Background* — hospital flow complexity, need for transparent, reproducible
    what-if tools; gap between clinical data warehouses (OMOP) and operational
    simulation.
  - *Objective* — develop and evaluate an open-source, OMOP-calibrated hospital
    DES digital twin.
  - *Methods* — patient/clinical model (CIM-10, CCAM), pathway/routing model, DES
    engine, OMOP calibration, replication/CI methodology, validation approach.
  - *Results* — validation metrics; what-if scenario results with CIs.
  - *Conclusions* — usefulness, limitations, availability.
- **Introduction** — problem, related work (SimPy/AnyLogic hospital DES, digital
  twins in health, OHDSI/OMOP), contribution.
- **Methods** — architecture; formal model (Poisson arrivals, LOS distribution,
  bed-blocking, transition matrix); calibration estimators; experimental design
  (replications, warm-up, CIs); validation design.
- **Results** — calibration recovery, validation vs data/literature, sensitivity
  analysis, what-if outcomes.
- **Discussion** — interpretation, comparison to prior tools, limitations
  (synthetic vs real, no death table in visit-only calibration, single-site),
  future work.
- **Conclusion**, **Availability** (GitHub + Zenodo DOI + license).

---

## 5. Reproducibility checklist (JMIR values this heavily)
- [ ] Public repo, OSI license (✅ MIT), tagged release + Zenodo DOI.
- [ ] Pinned dependencies; CI badge (✅ workflow added).
- [ ] All figures/tables regenerable from a single scripted pipeline.
- [ ] Seeds reported; number of replications and CI method stated.
- [ ] Data availability statement (Synthea generation params or MIMIC access note).
- [ ] Report following a DES reporting guideline (STRESS-DES).

---

## 6. JMIR submission logistics checklist
- [ ] Confirm article type = Original Paper and current **APC** (budget ~US$2–3k;
      check waiver/discount eligibility).
- [ ] Structured abstract within JMIR word limits.
- [ ] Authorship, ORCID, contributions, conflicts of interest, funding.
- [ ] Multimedia appendix for code/figures; cite the Zenodo DOI.
- [ ] Cover letter stating fit (reproducible informatics tool + evaluation).
- [ ] Suggested reviewers (health-DES / OHDSI community).
- [ ] Verify no PHI; ethics statement (Synthea = synthetic → typically exempt;
      MIMIC → cite data use agreement / IRB exemption).

---

## 7. Indicative timeline
~6–9 weeks of focused work: A (2–3w) → B (1–2w) → C (few days, parallel) →
D (2–3w) → E (1w). Plan for one revision round after submission.

---

## 8. Anticipated reviewer objections & mitigations
- *"Only synthetic data."* → Run on Synthea→OMOP (and ideally MIMIC-IV);
  present validation metrics; state synthetic-data rationale (privacy, repro).
- *"Single-run / anecdotal numbers."* → ✅ already fixed: multi-replication CIs;
  add sensitivity analysis.
- *"Yet another hospital DES."* → Emphasize the differentiator: **automatic
  calibration from standard OMOP CDM** + full reproducibility + clinical coding
  (CIM-10/CCAM) integration.
- *"No clinical impact."* → Reframe as an informatics *methods/tool* paper with
  demonstrated validity and usefulness, not a clinical outcomes study.
- *"Model realism (exponential LOS, memoryless transitions)."* → Justify as a
  transparent baseline; show sensitivity; note pluggable distributions as future
  work.

---

## 9. Immediate next actions (this repo)
1. `sensitivity_sweep()` helper in `scenario.py` (vary one parameter, return
   indicator + CI per value).
2. Optional `matplotlib` figure renderer behind the `viz` extra.
3. Synthea→OMOP ETL notebook under `notebooks/`.
4. Fix stale README API examples + add Quickstart.
5. Tag release + Zenodo DOI once Phase A/B results exist.
