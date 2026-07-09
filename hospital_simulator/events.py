"""Événements cliniques stochastiques (Phase 1 — Event simulation).

Fournit un moteur d'événements simple et reproductible : chaque événement possède
une probabilité de survenue par pas de temps. Le tirage utilise une instance
``random.Random`` locale afin de garantir des simulations reproductibles via une seed.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from hospital_simulator.patient import Patient
from hospital_simulator.constants import DispositionType


@dataclass
class ClinicalEvent:
    """Un événement clinique susceptible de survenir chez un patient.

    Attributs :
        name: Nom de l'événement (ex: "sepsis").
        probability: Probabilité de survenue par évaluation, dans [0, 1].
        disposition: Devenir induit (facultatif), parmi :class:`DispositionType`.
    """

    name: str
    probability: float
    disposition: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError(
                f"probability doit être dans [0, 1], reçu {self.probability}."
            )


@dataclass
class EventEngine:
    """Moteur de tirage d'événements cliniques reproductible.

    Exemple ::

        engine = EventEngine(seed=42)
        engine.register(ClinicalEvent("sepsis", 0.04,
                                      disposition=DispositionType.TRANSFER_TO_ICU))
        triggered = engine.evaluate(patient)
    """

    seed: int | None = None
    events: list[ClinicalEvent] = field(default_factory=list)
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def register(self, event: ClinicalEvent) -> None:
        """Ajoute un événement au moteur."""
        if not isinstance(event, ClinicalEvent):
            raise TypeError("register attend une instance de ClinicalEvent.")
        self.events.append(event)

    def evaluate(self, patient: Patient) -> list[ClinicalEvent]:
        """Évalue tous les événements enregistrés pour un patient.

        Chaque événement est tiré indépendamment selon sa probabilité. Les
        événements déclenchés sont retournés dans l'ordre d'enregistrement ; le
        premier événement portant une ``disposition`` met à jour le statut du
        patient (transfert / sortie / décès).

        Returns:
            La liste des événements déclenchés (éventuellement vide).
        """
        triggered: list[ClinicalEvent] = []
        for event in self.events:
            if self._rng.random() < event.probability:
                triggered.append(event)

        for event in triggered:
            if event.disposition is not None:
                self._apply_disposition(patient, event.disposition)
                break

        return triggered

    @staticmethod
    def _apply_disposition(patient: Patient, disposition: str) -> None:
        """Traduit un devenir clinique en changement de statut du patient."""
        if disposition == DispositionType.TRANSFER_TO_ICU:
            patient.set_status(Patient.STATUS_TRANSFERRED_OUT, service_name_str_or_None="ICU")
        elif disposition == DispositionType.TRANSFER_TO_WARD:
            patient.set_status(Patient.STATUS_TRANSFERRED_OUT, service_name_str_or_None="Ward")
        elif disposition in (
            DispositionType.DISCHARGE_HOME,
            DispositionType.DISCHARGE_ANOTHER_FACILITY,
            DispositionType.DEATH,
        ):
            patient.set_status(Patient.STATUS_DISCHARGED)
