#!/usr/bin/env python3
"""Étude de validation HDTS — génère le rapport et les figures du papier.

Orchestre le protocole de validation (cf. README « Validation & publication
roadmap ») sur un jeu de données et écrit un rapport texte + des figures PNG
prêtes pour l'article :

    1. Validation opérationnelle : couverture d'IC du census, ajustement de la
       durée de séjour (KS + Wasserstein), processus d'arrivée (Poisson), audit
       markovien d'ordre 1.
    2. Hold-out temporel : calibrer avant une date, valider après (--holdout-date).
    3. Back-test « expérience naturelle » COVID : calibrer avant --covid-split,
       propager la surcharge observée, comparer prédit vs observé (census + mortalité).

Exemples :

    python scripts/validation_study.py --mimic-dir /data/mimiciv --output figures/
    python scripts/validation_study.py --mimic-dir /data/mimiciv \
        --holdout-date 2150-06-01 --covid-split 2150-03-01
    python scripts/validation_study.py --synthetic --patients 800   # démo hors-ligne

Nécessite l'extra ``viz`` (matplotlib).
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from hospital_simulator import (  # noqa: E402
    OmopDataset,
    build_hospital_graph,
    build_hospital_graph_from_stays,
    census_sample,
    ci_coverage,
    daily_arrivals,
    ks_exponential,
    length_of_stay_samples,
    markov_order_check,
    omop_from_flat_csv,
    omop_from_mimic,
    poisson_dispersion_test,
    replicated_census,
    run_replications,
    stays_from_omop,
    wasserstein_1d,
)
from hospital_simulator.omop import parse_omop_date  # noqa: E402
from hospital_simulator.observed import temporal_split  # noqa: E402


def _log(msg: str) -> None:
    print(f"[validation] {msg}")


def load_dataset(args) -> tuple[OmopDataset, str]:
    if args.flat_csv:
        return omop_from_flat_csv(args.flat_csv), f"CSV plat ({args.flat_csv})"
    if args.mimic_dir:
        return omop_from_mimic(args.mimic_dir), f"MIMIC-IV ({args.mimic_dir})"
    if args.omop_dir:
        return OmopDataset.from_dir(args.omop_dir), f"OMOP ({args.omop_dir})"
    from examples.synthea_omop_etl import generate_synthea_like_omop
    return generate_synthea_like_omop(n_patients=args.patients, seed=args.seed), "synthétique"


def _pooled(bands: dict) -> dict:
    return {svc: [v for day in days for v in day] for svc, days in bands.items()}


def _observed_mortality(stays: list[dict]) -> float:
    by_person: dict[str, list[dict]] = {}
    for stay in stays:
        if stay.get("service"):
            by_person.setdefault(str(stay["person_id"]), []).append(stay)
    total = died = 0
    for seq in by_person.values():
        seq.sort(key=lambda s: parse_omop_date(s.get("start")) or datetime.max)
        total += 1
        if seq[-1].get("disposition") == "Death":
            died += 1
    return died / total if total else 0.0


def _arrival_rate(stays: list[dict], entry: str) -> float:
    starts = [parse_omop_date(s.get("start")) for s in stays if s.get("service") == entry]
    starts = [d for d in starts if d is not None]
    if len(starts) < 2:
        return max(1.0, float(len(starts)))
    span = (max(starts) - min(starts)).total_seconds() / 86400.0
    return len(starts) / span if span > 0 else float(len(starts))


# --------------------------------------------------------------------------- #

def run_operational(scenario, stays, graph, n_reps, seed, outdir, plotting) -> list[str]:
    from hospital_simulator import mae  # noqa: F401  (dispo si besoin)

    lines = ["## Validation opérationnelle", ""]
    obs = census_sample(stays)
    bands = replicated_census(scenario, n_reps, base_seed=seed)
    sim = _pooled(bands)

    lines.append("Couverture d'IC 95 % du census :")
    for svc in scenario.service_capacities:
        if obs.get(svc) and sim.get(svc):
            cov = ci_coverage(obs[svc], sim[svc])
            lines.append(f"    {svc:<8} couverture={cov['coverage'] * 100:5.1f}%  "
                         f"IC_sim=[{cov['ci_low']:.0f}, {cov['ci_high']:.0f}]")
            plotting.plot_census_coverage(obs[svc], bands[svc], svc,
                                          save_path=outdir / f"census_coverage_{svc}.png")

    lines += ["", "Durée de séjour (exponentielle : KS + Wasserstein) :"]
    rng = random.Random(seed)
    for svc, sample in length_of_stay_samples(stays).items():
        mean = graph.services.get(svc, {}).get("mean_los")
        if not mean or len(sample) < 20:
            continue
        d, p = ks_exponential(sample, mean)
        w = wasserstein_1d(sample, [rng.expovariate(1.0 / mean) for _ in range(2000)])
        lines.append(f"    {svc:<8} n={len(sample):>4}  D={d:.3f} p={p:.3f}  W1={w:.2f}j  "
                     f"-> {'OK' if p > 0.05 else 'REJETÉ'}")
        plotting.plot_los_fit(sample, mean, svc, ks_d=d, wasserstein=w,
                              save_path=outdir / f"los_fit_{svc}.png")

    arrivals = daily_arrivals(stays, graph.entry_service)
    lines += ["", "Processus d'arrivée (Poisson) :"]
    if len(arrivals) >= 2:
        disp = poisson_dispersion_test(arrivals)
        lines.append(f"    {graph.entry_service}: indice={disp['dispersion_index']:.2f}  "
                     f"p={disp['p_value']:.3f}  -> Poisson {'OK' if disp['is_poisson'] else 'REJETÉ'}")
        plotting.plot_arrival_fit(arrivals, save_path=outdir / "arrivals.png")

    mk = markov_order_check(stays)
    lines += ["", "Hypothèse markovienne ordre-1 :",
              f"    TV moyenne={mk['mean_tv']:.3f}  TV max={mk['max_tv']:.3f}  "
              f"contextes={mk['n_contexts']}", ""]
    return lines


def run_holdout(stays, holdout_date, n_reps, seed, plotting, outdir) -> list[str]:
    train, test = temporal_split(stays, holdout_date)
    lines = ["## Hold-out temporel", "",
             f"Split : {holdout_date}  (train={len(train)} séjours, test={len(test)} séjours)"]
    if len(train) < 30 or len(test) < 30:
        return lines + ["    (pas assez de données de part et d'autre)", ""]
    graph = build_hospital_graph_from_stays(train)
    scenario = graph.to_scenario(seed=seed)
    bands = replicated_census(scenario, n_reps, base_seed=seed)
    sim = _pooled(bands)
    obs_test = census_sample(test)
    lines.append("Couverture d'IC 95 % du census sur la fenêtre TEST :")
    for svc in scenario.service_capacities:
        if obs_test.get(svc) and sim.get(svc):
            cov = ci_coverage(obs_test[svc], sim[svc])
            lines.append(f"    {svc:<8} couverture_test={cov['coverage'] * 100:5.1f}%")
            plotting.plot_census_coverage(obs_test[svc], bands[svc], svc,
                                          save_path=outdir / f"holdout_coverage_{svc}.png")
    return lines + [""]


def run_covid(stays, split, n_reps, seed, plotting, outdir) -> list[str]:
    pre, post = temporal_split(stays, split)
    lines = ["## Back-test expérience naturelle (COVID)", "",
             f"Split : {split}  (pré={len(pre)} séjours, post={len(post)} séjours)"]
    if len(pre) < 30 or len(post) < 30:
        return lines + ["    (pas assez de données pré/post)", ""]

    graph_pre = build_hospital_graph_from_stays(pre)
    entry = graph_pre.entry_service
    pre_rate = graph_pre.arrival_rate_per_day
    post_rate = _arrival_rate(post, entry)
    surge = post_rate / pre_rate if pre_rate > 0 else 1.0
    lines.append(f"Surcharge observée des arrivées : x{surge:.2f} "
                 f"(pré={pre_rate:.2f}/j, post={post_rate:.2f}/j)")

    scenario = graph_pre.to_scenario(seed=seed).with_admission_surge(surge, name="covid_surge")
    rep = run_replications(scenario, n_reps, base_seed=seed)
    mort = rep.summary()["mortality_rate"]
    obs_mort = _observed_mortality(post)
    inside = mort["ci_low"] <= obs_mort <= mort["ci_high"]
    verdict = "DANS l'IC" if inside else "HORS IC"
    lines.append(f"Mortalité prédite={mort['mean']:.3f} [IC {mort['ci_low']:.3f}, {mort['ci_high']:.3f}]  "
                 f"observée={obs_mort:.3f}  -> {verdict}")

    bands = replicated_census(scenario, n_reps, base_seed=seed)
    sim = _pooled(bands)
    obs_post = census_sample(post)
    lines.append("Couverture du census POST par la prédiction surge :")
    for svc in scenario.service_capacities:
        if obs_post.get(svc) and sim.get(svc):
            cov = ci_coverage(obs_post[svc], sim[svc])
            lines.append(f"    {svc:<8} couverture={cov['coverage'] * 100:5.1f}%")
    # Figure phare : service le plus contraint.
    target = min(scenario.service_capacities, key=lambda s: scenario.effective_capacity(s))
    if obs_post.get(target) and bands.get(target):
        plotting.plot_census_coverage(obs_post[target], bands[target], f"{target} (COVID back-test)",
                                      save_path=outdir / "covid_backtest.png")
    return lines + [""]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="HDTS — étude de validation (figures du papier).")
    parser.add_argument("--mimic-dir", type=str, default=None)
    parser.add_argument("--omop-dir", type=str, default=None, help="Dossier de CSV OMOP CDM.")
    parser.add_argument("--flat-csv", type=str, default=None,
                        help="Un seul CSV plat (un séjour par ligne : person_id, service, start, end, ...).")
    parser.add_argument("--synthetic", action="store_true", help="Force les données synthétiques.")
    parser.add_argument("--patients", type=int, default=800)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--replications", type=int, default=40)
    parser.add_argument("--holdout-date", type=str, default=None)
    parser.add_argument("--covid-split", type=str, default=None)
    parser.add_argument("--output", type=Path, default=Path("validation_figures"))
    args = parser.parse_args(argv)

    try:
        from hospital_simulator import plotting
    except ImportError:
        _log("matplotlib requis : pip install -e '.[viz]'.")
        return 1

    args.output.mkdir(parents=True, exist_ok=True)
    dataset, label = load_dataset(args)

    from hospital_simulator import validate_omop_dataset
    check = validate_omop_dataset(dataset)
    mortality = "oui" if (check["has_disposition"] or check["n_deaths"]) else "non"
    _log(f"Dataset : {check['n_visits']} visites, {check['n_stays']} séjours, "
         f"services={check['services']}, mortalité={mortality}")
    for msg in check["messages"]:
        _log(msg)
    if not check["ok"]:
        _log("Dataset inexploitable — arrêt.")
        return 1

    stays = stays_from_omop(dataset)
    graph = build_hospital_graph(dataset)
    scenario = graph.to_scenario(seed=args.seed, days=args.days, warmup_days=args.warmup)

    _log(f"Source : {label}  ({len(stays)} séjours, entrée={graph.entry_service})")

    report = [f"# Étude de validation HDTS — source : {label}",
              f"# Réplications : {args.replications} | seed : {args.seed}", ""]
    report += run_operational(scenario, stays, graph, args.replications, args.seed, args.output, plotting)
    if args.holdout_date:
        report += run_holdout(stays, args.holdout_date, args.replications, args.seed, plotting, args.output)
    if args.covid_split:
        report += run_covid(stays, args.covid_split, args.replications, args.seed, plotting, args.output)

    text = "\n".join(report)
    print(text)
    (args.output / "validation_report.txt").write_text(text + "\n", encoding="utf-8")
    _log(f"Rapport + figures écrits dans {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
