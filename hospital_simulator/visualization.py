"""Visualisation simple de l'état de la simulation (Phase 1 — Simple visualization).

Rendu texte (ASCII) de l'occupation des services, sans dépendance externe. Une
visualisation matplotlib pourra être ajoutée en Phase 4 (extra ``viz``).
"""

from __future__ import annotations

from hospital_simulator.services.service_registry import ServiceRegistry


def render_occupancy_bar(occupied: int, capacity: int, width: int = 20) -> str:
    """Rend une barre de progression ASCII pour un service.

    Args:
        occupied: Nombre de lits occupés.
        capacity: Capacité totale (doit être > 0).
        width: Largeur de la barre en caractères.

    Returns:
        Une chaîne du type ``"[#####---------------] 5/20 (25%)"``.
    """
    if capacity <= 0:
        raise ValueError("capacity doit être > 0.")

    ratio = max(0.0, min(1.0, occupied / capacity))
    filled = round(ratio * width)
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {occupied}/{capacity} ({round(ratio * 100)}%)"


def render_registry(registry: ServiceRegistry, width: int = 20) -> str:
    """Rend un tableau texte de l'occupation de tous les services d'un registry.

    Args:
        registry: Le registry à afficher.
        width: Largeur des barres de progression.

    Returns:
        Une chaîne multi-lignes prête à être imprimée (une ligne par service).
    """
    if not registry.service_types:
        return "(aucun service enregistré)"

    label_width = max(len(name) for name in registry.service_types)
    lines = []
    for name in registry.service_types:
        capacity = registry.get_service_capacity(name) or 0
        occupied = registry.get_service_occupancy(name)
        bar = render_occupancy_bar(occupied, capacity, width=width)
        lines.append(f"{name:>{label_width}} {bar}")

    return "\n".join(lines)


def print_registry(registry: ServiceRegistry, width: int = 20) -> None:
    """Affiche l'occupation des services sur la sortie standard."""
    print(render_registry(registry, width=width))
