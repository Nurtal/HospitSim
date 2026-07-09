"""Parcours cliniques (Phase 2 — Clinical pathway YAML files).

Un parcours clinique décrit, pour un diagnostic donné, les procédures attendues
et les probabilités de transition vers les différents devenirs (ICU, Ward,
Discharge...). Les parcours sont définis en YAML, par exemple ::

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
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from hospital_simulator.models._cid_validator import CID10Validator

# Tolérance sur la somme des probabilités de transition (arrondis YAML).
_PROBABILITY_SUM_TOLERANCE = 1e-6


@dataclass
class ClinicalPathway:
    """Un parcours clinique associé à un diagnostic.

    Attributs :
        name: Nom du parcours (ex: "pneumonia").
        diagnosis_code: Code CIM-10 associé (optionnel).
        procedures: Liste des procédures attendues (labels ou codes).
        transitions: Devenirs possibles pondérés (``{destination: probabilité}``).
    """

    name: str
    diagnosis_code: str | None = None
    procedures: list[str] = field(default_factory=list)
    transitions: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or not str(self.name).strip():
            raise ValueError("Un parcours clinique doit avoir un nom non vide.")

        if self.diagnosis_code and not CID10Validator.is_valid(self.diagnosis_code):
            raise ValueError(
                f"Parcours {self.name!r} : code CIM-10 invalide {self.diagnosis_code!r}."
            )

        for destination, prob in self.transitions.items():
            if not isinstance(prob, (int, float)) or isinstance(prob, bool):
                raise ValueError(
                    f"Parcours {self.name!r} : probabilité non numérique pour {destination!r}."
                )
            if not 0.0 <= prob <= 1.0:
                raise ValueError(
                    f"Parcours {self.name!r} : probabilité hors [0, 1] pour {destination!r} ({prob})."
                )

        if self.transitions:
            total = sum(self.transitions.values())
            if abs(total - 1.0) > _PROBABILITY_SUM_TOLERANCE:
                raise ValueError(
                    f"Parcours {self.name!r} : la somme des transitions doit valoir 1.0 (reçu {total})."
                )

    def next_destination(self, rng: random.Random | None = None) -> str:
        """Tire un devenir selon les probabilités de transition.

        Args:
            rng: Générateur aléatoire (fournir un ``random.Random`` pour la
                reproductibilité). Par défaut, le module ``random`` global.

        Returns:
            Le nom de la destination tirée.

        Raises:
            ValueError: si le parcours ne définit aucune transition.
        """
        if not self.transitions:
            raise ValueError(f"Parcours {self.name!r} : aucune transition définie.")

        rng = rng or random
        destinations = list(self.transitions.keys())
        weights = list(self.transitions.values())
        return rng.choices(destinations, weights=weights, k=1)[0]


def _parse_pathway(name: str, spec: dict) -> ClinicalPathway:
    """Construit un :class:`ClinicalPathway` à partir d'un bloc YAML décodé."""
    if not isinstance(spec, dict):
        raise ValueError(f"Parcours {name!r} : la définition doit être un mapping.")

    diagnosis = spec.get("diagnosis") or {}
    diagnosis_code = diagnosis.get("icd10") if isinstance(diagnosis, dict) else None

    procedures = list(spec.get("procedures") or [])
    transitions = dict(spec.get("transitions") or {})

    return ClinicalPathway(
        name=name,
        diagnosis_code=diagnosis_code,
        procedures=procedures,
        transitions=transitions,
    )


def load_pathways_from_dict(data: dict) -> dict[str, ClinicalPathway]:
    """Construit les parcours à partir d'un dict (YAML déjà décodé)."""
    if not isinstance(data, dict):
        raise ValueError("Les définitions de parcours doivent être un mapping.")
    return {name: _parse_pathway(name, spec) for name, spec in data.items()}


def load_pathways_from_string(text: str) -> dict[str, ClinicalPathway]:
    """Charge les parcours depuis une chaîne YAML."""
    data = yaml.safe_load(text) or {}
    return load_pathways_from_dict(data)


def load_pathways(path: str | Path) -> dict[str, ClinicalPathway]:
    """Charge les parcours depuis un fichier YAML.

    Args:
        path: Chemin du fichier YAML.

    Returns:
        Un dict ``{nom_parcours: ClinicalPathway}``.
    """
    text = Path(path).read_text(encoding="utf-8")
    return load_pathways_from_string(text)
