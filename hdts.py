#!/usr/bin/env python3
"""HDTS standalone — génère les données, calibre, valide et simule, tout en un.

Ce script autonome enchaîne toute la chaîne du jumeau numérique hospitalier :

    1. Données  : exécute Synthea (téléchargé si besoin) et exporte en OMOP,
                  OU, à défaut de Java/réseau, génère un OMOP synthétique.
    2. Calibration : transitions inter-services + durées de séjour depuis l'OMOP.
    3. Validation  : test de Kolmogorov–Smirnov de l'hypothèse de séjour exponentiel.
    4. Simulation  : scénario calibré + variante « what-if » avec réplications et
                     intervalles de confiance ; capacités dimensionnées sur les données.
    5. Sortie   : un rapport texte (et, en option, des figures PNG).

Exemples :

    python hdts.py                          # Synthea si dispo, sinon synthétique
    python hdts.py --patients 2000 --figures
    python hdts.py --no-synthea             # force le générateur synthétique
    python hdts.py --omop-dir /data/omop    # part de CSV OMOP déjà présents
    python hdts.py --synthea-jar ./synthea-with-dependencies.jar

Aucune installation préalable requise : le script ajoute le dépôt au PYTHONPATH.
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

# Rend le package importable même sans installation.
_REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_REPO_ROOT))

from hospital_simulator import (  # noqa: E402
    OmopDataset,
    Scenario,
    estimate_length_of_stay,
    estimate_transition_probabilities,
    ks_exponential,
    length_of_stay_samples,
    patients_from_omop,
    peak_concurrency,
    run_replications,
    run_scenario,
    stays_from_omop,
)
from hospital_simulator.omop import parse_omop_date  # noqa: E402
from hospital_simulator.scenario import TERMINALS  # noqa: E402

SYNTHEA_JAR_URL = (
    "https://github.com/synthetichealth/synthea/releases/download/"
    "master-branch-latest/synthea-with-dependencies.jar"
)


# --------------------------------------------------------------------------- #
# 1. Données
# --------------------------------------------------------------------------- #

def _log(msg: str) -> None:
    print(f"[hdts] {msg}")


def resolve_synthea_jar(jar: str | None, cache_dir: Path) -> Path | None:
    """Retourne le chemin du jar Synthea (fourni, en cache, ou téléchargé)."""
    if jar:
        p = Path(jar)
        return p if p.exists() else None

    cached = cache_dir / "synthea-with-dependencies.jar"
    if cached.exists():
        return cached

    cache_dir.mkdir(parents=True, exist_ok=True)
    _log(f"Téléchargement de Synthea vers {cached} ...")
    try:
        urllib.request.urlretrieve(SYNTHEA_JAR_URL, cached)
        return cached
    except Exception as exc:  # réseau indisponible, etc.
        _log(f"Échec du téléchargement de Synthea : {exc}")
        return None


def find_omop_dir(root: Path) -> Path | None:
    """Cherche récursivement un dossier contenant person.csv sous ``root``."""
    for candidate in root.rglob("person.csv"):
        return candidate.parent
    return None


def run_synthea(jar: Path, n_patients: int, seed: int, workdir: Path) -> Path | None:
    """Exécute Synthea avec export OMOP ; renvoie le dossier OMOP ou None."""
    workdir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "java", "-jar", str(jar),
        "-p", str(n_patients),
        "-s", str(seed),
        "--exporter.baseDirectory", str(workdir),
        "--exporter.omop.export", "true",
        "--exporter.fhir.export", "false",
        "--exporter.csv.export", "false",
        "--exporter.hospital.fhir.export", "false",
        "--exporter.practitioner.fhir.export", "false",
    ]
    _log(f"Exécution de Synthea ({n_patients} patients) ...")
    try:
        subprocess.run(cmd, check=True, timeout=1800,
                       stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    except Exception as exc:
        _log(f"Échec de l'exécution de Synthea : {exc}")
        return None
    return find_omop_dir(workdir)


def generate_synthetic(n_patients: int, seed: int) -> OmopDataset:
    """Génère un OMOP synthétique (vérité-terrain connue) via l'exemple testé."""
    from examples.synthea_omop_etl import generate_synthea_like_omop
    return generate_synthea_like_omop(n_patients=n_patients, seed=seed)


def obtain_dataset(args) -> tuple[OmopDataset, str]:
    """Résout la source de données selon les options ; renvoie (dataset, description)."""
    if args.omop_dir:
        _log(f"Chargement de l'OMOP depuis {args.omop_dir}")
        return OmopDataset.from_dir(args.omop_dir), f"OMOP réel ({args.omop_dir})"

    if not args.no_synthea and shutil.which("java"):
        jar = resolve_synthea_jar(args.synthea_jar, _REPO_ROOT / ".synthea")
        if jar is not None:
            omop_dir = run_synthea(jar, args.patients, args.seed, args.output / "synthea_raw")
            if omop_dir is not None:
                _log(f"OMOP Synthea généré : {omop_dir}")
                return OmopDataset.from_dir(omop_dir), f"Synthea OMOP ({omop_dir})"
            _log("Synthea indisponible — bascule sur le générateur synthétique.")
    elif not args.no_synthea:
        _log("Java introuvable — bascule sur le générateur synthétique.")

    return generate_synthetic(args.patients, args.seed), "synthétique (Synthea-like)"


# --------------------------------------------------------------------------- #
# 2-4. Calibration, validation, simulation
# --------------------------------------------------------------------------- #

def _service_universe(routing: dict[str, dict[str, float]]) -> set[str]:
    """Ensemble des services réels (sources + destinations non terminales)."""
    services = set(routing)
    for row in routing.values():
        services |= {dest for dest in row if dest not in TERMINALS}
    return services


def _entry_service(stays: list[dict], services: set[str]) -> str:
    """Service d'entrée = service le plus fréquent en début de trajectoire."""
    firsts: dict[str, int] = {}
    by_person: dict[str, list[dict]] = {}
    for s in stays:
        by_person.setdefault(str(s.get("person_id")), []).append(s)
    for seq in by_person.values():
        seq.sort(key=lambda s: parse_omop_date(s.get("start")) or 0)
        for s in seq:
            if s.get("service") in services:
                firsts[s["service"]] = firsts.get(s["service"], 0) + 1
                break
    if not firsts:
        return sorted(services)[0]
    return max(firsts, key=firsts.get)


def _arrival_rate(stays: list[dict], entry: str) -> float:
    """Arrivées/jour = nb d'entrées dans le service d'entrée / durée observée."""
    starts = [parse_omop_date(s.get("start")) for s in stays if s.get("service") == entry]
    starts = [d for d in starts if d is not None]
    if len(starts) < 2:
        return max(1.0, float(len(starts)))
    span_days = (max(starts) - min(starts)).total_seconds() / 86400.0
    return len(starts) / span_days if span_days > 0 else float(len(starts))


def build_calibrated_scenario(dataset: OmopDataset, seed: int):
    """Calibre un Scenario data-driven ; renvoie (scenario, contexte)."""
    stays = stays_from_omop(dataset)
    routing = estimate_transition_probabilities(stays)
    mean_los = {svc: st["mean"] for svc, st in estimate_length_of_stay(stays).items()}
    services = _service_universe(routing)
    entry = _entry_service(stays, services)
    peaks = peak_concurrency(stays)

    # Capacité = 1.3 x pic d'occupation observé (min 5).
    capacities = {svc: max(5, math.ceil(1.3 * peaks.get(svc, 0))) for svc in services}

    scenario = Scenario(
        name="calibrated",
        days=120,
        warmup_days=20,
        entry_service=entry,
        arrival_rate_per_day=round(_arrival_rate(stays, entry), 2),
        service_capacities=capacities,
        routing=routing,
        mean_los_days={svc: mean_los.get(svc, 3.0) for svc in services},
        seed=seed,
    )
    context = {"stays": stays, "mean_los": mean_los, "entry": entry, "peaks": peaks}
    return scenario, context


def validate_los(stays, mean_los) -> dict[str, dict]:
    """Test KS de l'hypothèse de séjour exponentiel par service (n >= 20)."""
    report = {}
    for service, sample in length_of_stay_samples(stays).items():
        mean = mean_los.get(service)
        if not mean or len(sample) < 20:
            continue
        d, p = ks_exponential(sample, mean)
        report[service] = {"n": len(sample), "mean": round(mean, 2),
                           "D": round(d, 4), "p": round(p, 4), "ok": p > 0.05}
    return report


# --------------------------------------------------------------------------- #
# 5. Rapport
# --------------------------------------------------------------------------- #

def build_report(source, dataset, scenario, context, seed, n_reps) -> str:
    patients = patients_from_omop(dataset)
    los_report = validate_los(context["stays"], context["mean_los"])

    baseline = run_replications(scenario, n_reps, base_seed=seed)
    surge = run_replications(
        scenario.with_admission_surge(1.3, name="+30% admissions"), n_reps, base_seed=seed
    )

    lines = [
        "=" * 64,
        "HDTS — rapport de simulation calibrée",
        "=" * 64,
        f"Source de données   : {source}",
        f"Patients            : {len(patients)}",
        f"Séjours             : {len(context['stays'])}",
        f"Service d'entrée     : {context['entry']}",
        f"Arrivées/jour (est.) : {scenario.arrival_rate_per_day}",
        "",
        "Capacités (1.3 x pic observé) :",
    ]
    for svc, cap in scenario.service_capacities.items():
        lines.append(f"    {svc:<8} pic_observé={context['peaks'].get(svc, 0):>4}  capacité={cap}")

    lines += ["", "Transitions calibrées :"]
    for src, row in scenario.routing.items():
        pretty = ", ".join(f"{d}={p:.2f}" for d, p in row.items())
        lines.append(f"    {src:<8} -> {pretty}")

    lines += ["", "Validation séjour exponentiel (KS) :"]
    if los_report:
        for svc, r in los_report.items():
            lines.append(f"    {svc:<8} n={r['n']:>4}  DMS={r['mean']:>5}j  "
                         f"D={r['D']:.3f} p={r['p']:.3f}  -> {'OK' if r['ok'] else 'REJETÉ'}")
    else:
        lines.append("    (pas assez de données par service)")

    metrics = ["admissions", "blocked_transfers", "deaths"]
    for svc in scenario.service_capacities:
        metrics.append(f"{svc}.mean_occupancy_rate")
    lines += ["", "-" * 64, "Scénario BASELINE"]
    lines.append(baseline.render_summary(metrics=metrics))
    lines += ["", "Scénario WHAT-IF (+30% admissions)"]
    lines.append(surge.render_summary(metrics=metrics))
    lines.append("=" * 64)
    return "\n".join(lines)


def maybe_figures(scenario, sweep_param, outdir: Path) -> None:
    try:
        from hospital_simulator.plotting import plot_occupancy, plot_stress, plot_sensitivity
        from hospital_simulator import sensitivity_sweep
    except ImportError:
        _log("Figures ignorées (extra 'viz' absent : pip install 'hospital_simulator[viz]').")
        return
    result = run_scenario(scenario)
    plot_occupancy(result, save_path=outdir / "occupancy.png")
    plot_stress(result, save_path=outdir / "stress.png")
    sweep = sensitivity_sweep(
        scenario, f"capacity:{sweep_param}",
        values=sorted({max(1, scenario.effective_capacity(sweep_param) + d)
                       for d in (-6, -3, 0, 3, 6, 12)}),
        metrics=["blocked_transfers"], n_replications=20,
    )
    plot_sensitivity(sweep, "blocked_transfers", save_path=outdir / "sensitivity.png")
    _log(f"Figures écrites dans {outdir}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="HDTS standalone: data -> calibrate -> validate -> simulate.")
    parser.add_argument("--patients", type=int, default=1000, help="Nombre de patients à générer.")
    parser.add_argument("--seed", type=int, default=2026, help="Graine (reproductibilité).")
    parser.add_argument("--replications", type=int, default=40, help="Réplications par scénario.")
    parser.add_argument("--output", type=Path, default=Path("hdts_output"), help="Dossier de sortie.")
    parser.add_argument("--omop-dir", type=str, default=None, help="Dossier de CSV OMOP existants.")
    parser.add_argument("--synthea-jar", type=str, default=None, help="Chemin du jar Synthea.")
    parser.add_argument("--no-synthea", action="store_true", help="Force le générateur synthétique.")
    parser.add_argument("--figures", action="store_true", help="Génère des figures PNG (extra 'viz').")
    args = parser.parse_args(argv)

    args.output.mkdir(parents=True, exist_ok=True)

    dataset, source = obtain_dataset(args)
    scenario, context = build_calibrated_scenario(dataset, args.seed)
    report = build_report(source, dataset, scenario, context, args.seed, args.replications)

    print(report)
    report_path = args.output / "report.txt"
    report_path.write_text(report + "\n", encoding="utf-8")
    _log(f"Rapport écrit : {report_path}")

    if args.figures:
        maybe_figures(scenario, context["entry"], args.output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
