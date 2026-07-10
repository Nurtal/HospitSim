"""Dashboard démonstrateur HDTS (Streamlit — extra optionnel ``app``).

Câble l'existant : construit le graphe hospitalier depuis un jeu de données,
laisse l'utilisateur régler un scénario what-if, lance des réplications et affiche
les indicateurs de stress + figures.

Lancement :

    pip install -e ".[app]"
    streamlit run app/hdts_app.py

La logique réutilisable (``load_dataset`` / ``scenario_from_ui``) est importable
sans Streamlit (utilisée par les tests) ; ``streamlit`` n'est importé que dans
``main()``.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hospital_simulator import (
    OmopDataset,
    build_hospital_graph,
    omop_from_mimic,
    run_replications,
)


def load_dataset(source: str, *, patients: int = 500, path: str | None = None) -> tuple[OmopDataset, str]:
    """Charge un dataset selon la source choisie : 'synthetic', 'mimic', 'omop'."""
    if source == "mimic" and path:
        return omop_from_mimic(path), f"MIMIC-IV ({path})"
    if source == "omop" and path:
        return OmopDataset.from_dir(path), f"OMOP ({path})"
    from examples.synthea_omop_etl import generate_synthea_like_omop
    return generate_synthea_like_omop(n_patients=patients, seed=0), "synthétique"


def scenario_from_ui(
    graph,
    *,
    seed: int = 2026,
    days: int = 90,
    warmup_days: int = 15,
    admission_multiplier: float = 1.0,
    capacity_service: str | None = None,
    capacity_factor: float = 1.0,
    los_multiplier: float = 1.0,
):
    """Dérive un Scenario du graphe et applique les réglages what-if de l'UI."""
    scenario = graph.to_scenario(name="app", days=days, warmup_days=warmup_days, seed=seed)
    capacities = dict(scenario.service_capacities)
    if capacity_service in capacities and capacity_factor != 1.0:
        capacities[capacity_service] = max(1, int(round(capacities[capacity_service] * capacity_factor)))
    mean_los = {svc: los * los_multiplier for svc, los in scenario.mean_los_days.items()}
    return replace(
        scenario,
        admission_multiplier=admission_multiplier,
        service_capacities=capacities,
        mean_los_days=mean_los,
    )


def main() -> None:  # pragma: no cover - UI, non testée
    import streamlit as st
    from hospital_simulator.plotting import plot_occupancy, plot_stress
    from hospital_simulator import run_scenario

    st.set_page_config(page_title="HDTS — jumeau numérique hospitalier", layout="wide")
    st.title("🏥 HDTS — jumeau numérique hospitalier (démonstrateur)")

    with st.sidebar:
        st.header("Données")
        source = st.selectbox("Source", ["synthetic", "mimic", "omop"])
        patients = st.number_input("Patients (synthétique)", 100, 5000, 500, step=100)
        path = st.text_input("Dossier (MIMIC/OMOP)", "") or None
        st.header("Scénario what-if")
        admission = st.slider("Multiplicateur d'admissions", 0.5, 3.0, 1.0, 0.1)
        los_mult = st.slider("Multiplicateur de DMS", 0.5, 2.0, 1.0, 0.1)
        n_reps = st.slider("Réplications", 5, 60, 30, 5)

    dataset, label = load_dataset(source, patients=int(patients), path=path)
    graph = build_hospital_graph(dataset)
    st.caption(f"Source : {label} — service d'entrée : **{graph.entry_service}**")

    services = list(graph.services)
    cap_service = st.sidebar.selectbox("Service à ajuster", services) if services else None
    cap_factor = st.sidebar.slider("Facteur de capacité", 0.4, 2.0, 1.0, 0.1)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Graphe hospitalier auto-construit")
        st.json(graph.to_dict())
    scenario = scenario_from_ui(
        graph, admission_multiplier=admission, los_multiplier=los_mult,
        capacity_service=cap_service, capacity_factor=cap_factor,
    )
    rep = run_replications(scenario, int(n_reps))
    with col2:
        st.subheader("Indicateurs de stress (IC 95 %)")
        st.text(rep.render_summary(metrics=[
            "admissions", "blocked_transfers", "deaths", "mortality_rate",
        ] + [f"{s}.mean_occupancy_rate" for s in services]))

    result = run_scenario(scenario)
    st.subheader("Occupation & stress")
    c3, c4 = st.columns(2)
    c3.pyplot(plot_occupancy(result))
    c4.pyplot(plot_stress(result))


if __name__ == "__main__":
    main()
