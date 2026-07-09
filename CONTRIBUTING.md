# Contributing to HospitSim

Thanks for your interest in contributing to the Hospital Digital Twin Simulator (HDTS).
The project is in early development; contributions, bug reports, and clinical use
cases are welcome.

## Getting started

```bash
git clone https://github.com/Nurtal/HospitSim
cd HospitSim
pip install -e ".[dev]"   # installs viz + test extras
pytest -q                 # run the test suite
```

## How to contribute

- **Bug reports / feature requests:** open a GitHub issue describing the problem,
  the expected behavior, and (for bugs) a minimal reproducible example.
- **Pull requests:**
  1. Fork the repository and create a topic branch.
  2. Add or update tests for any behavior change (the suite lives in `tests/`).
  3. Make sure `pytest -q` passes locally.
  4. Keep the core dependency-light: the simulation core relies only on the
     standard library and `pyyaml`. Heavy dependencies (matplotlib, numpy) stay
     behind the optional `viz` extra.
  5. Open a PR against `main` and describe the motivation and approach.

## Coding conventions

- Python ≥ 3.10, type hints on public functions.
- Deterministic, seed-driven randomness (no reliance on global RNG state in the
  simulation engine) so that results stay reproducible.
- Docstrings for public classes and functions.

## Scope

The goal is a **minimal, transparent, reproducible** hospital simulation engine
that bridges clinical coding standards (CIM-10, CCAM), OMOP observational data,
and discrete-event simulation. Please keep changes aligned with that scope.
