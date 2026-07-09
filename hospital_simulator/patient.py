"""Modèle de l'entite patient pour les simulations hospitalieres."""

from __future__ import annotations

import typing
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from hospital_simulator.models._cid_validator import CID10Validator


@dataclass
class Patient:
    """Represent une entite patient virtuelle dans le simulateur.
    
    Attributs :
        id: Identifiant unique du patient
        date_naissance: Date de naissance (optionnelle)
        age: Age du patient en annees
        sexe: Sexe ('M' ou 'F') 
        poids: Poids en kilogrammes (optionnel)
        taille: Taille en centimetres (optionel)
        diagnostic_principal: Code CIM-10 du diagnostic principal
        
        # Cycle de vie Phase 1 :
        status_admission: str - statut courant ('incoming', 'dispatch_queued', 'assigned_to_service', 'transferred_in', 'transferred_out', 'discharged') 
        arrival_time: datetime | None - heure d'entree en admission
        discharge_time: datetime | None - heure de sortie  
        current_admission_service_name: str | None - nom du service actif ou recent
    """

    STATUS_INCOMING = "incoming"
    STATUS_DISPATCH_QUEUED = "dispatch_queued"
    STATUS_ASSIGNED_TO_SERVICE = "assigned_to_service"  
    STATUS_TRANSFERRED_IN = "transferred_in"
    STATUS_TRANSFERRED_OUT = "transferred_out"
    STATUS_DISCHARGED = "discharged"
    
    VALID_STATUSES: typing.ClassVar[typing.Tuple[str, ...]] = (
        STATUS_INCOMING,
        STATUS_DISPATCH_QUEUED, 
        STATUS_ASSIGNED_TO_SERVICE,
        STATUS_TRANSFERRED_IN,
        STATUS_TRANSFERRED_OUT,
        STATUS_DISCHARGED,
    )

    
    id: str = field(default_factory=lambda: f"P{uuid.uuid4().hex[:8]}")
    date_naissance: typing.Optional[datetime] = None
    age: typing.Optional[int] = None
    sexe: typing.Optional[str] = None  
    poids: typing.Optional[float] = None
    taille: typing.Optional[float] = None
    diagnostic_principal: str = field(default='', metadata={'comment': 'Code CIM-10'})
    diagnostics_secondaires: list[str] = field(default_factory=list, metadata={'comment': 'Comorbidités CIM-10'})

    # Champs cycle de vie (Phase 1) - initialisés à des valeurs par defaut cohérentes.
    status_admission: str | None = STATUS_INCOMING  
    arrival_time: typing.Optional[datetime] = None
    discharge_time: typing.Optional[datetime] = None
    current_admission_service_name: typing.Optional[str] = None
    
    # Historique des services (nom -> date) pour les transfers.
    transfer_history: dict[str, typing.Optional[datetime]] = field(default_factory=lambda: {})
    
    def __post_init__(self) -> None:
        """Validation post-initialisation."""
        self._validate_status(self.status_admission or Patient.STATUS_INCOMING)
        self._validate_diagnosis(self.diagnostic_principal)
        for code in self.diagnostics_secondaires:
            self._validate_diagnosis(code)

    @staticmethod
    def _validate_status(status: str) -> None:
        """Valide qu'un statut fait partie des etats valides."""
        if status not in Patient.VALID_STATUSES:
            raise ValueError(
                f"Statut invalide ! Attendu parmi {Patient.VALID_STATUSES}, recu '{status}'."
            )

    @staticmethod
    def _validate_diagnosis(code: str) -> None:
        """Valide un code CIM-10 s'il est renseigné (chaîne vide = pas de diagnostic)."""
        if code and not CID10Validator.is_valid(code):
            raise ValueError(f"Code CIM-10 invalide : {code!r}.")
    
    @property  
    def is_incoming(self) -> bool:
        """Le patient vient d'arriver (premier contact)."""
        return self.status_admission == Patient.STATUS_INCOMING
        
    @property
    def is_dispatch_queued(self) -> bool:
        """Le patient est en attente de dispatch dans une file."""
        return self.status_admission == Patient.STATUS_DISPATCH_QUEUED
        
    @property
    def is_transferred_out(self) -> bool:
        """Le patient a recemment quitté un service vers un autre."""  
        return self.status_admission == Patient.STATUS_TRANSFERRED_OUT
    
    @property
    def current_service_name_if_assigned(self) -> typing.Optional[str]:
        """Retourne le nom du service actuel si assigne, sinon None."""
        if (
            self.current_admission_service_name is not None and 
            self.status_admission != Patient.STATUS_INCOMING
        ):
            return self.current_admission_service_name
        return None

    # ---- Comorbidités (Phase 2) ----

    def add_comorbidity(self, code: str) -> None:
        """Ajoute une comorbidité (diagnostic secondaire) au patient.

        Args:
            code: Code CIM-10 de la comorbidité.

        Raises:
            ValueError: si le code CIM-10 est invalide.
        """
        self._validate_diagnosis(code)
        if code not in self.diagnostics_secondaires:
            self.diagnostics_secondaires.append(code)

    @property
    def comorbidity_count(self) -> int:
        """Nombre de comorbidités (diagnostics secondaires) enregistrées."""
        return len(self.diagnostics_secondaires)

    @property
    def has_comorbidities(self) -> bool:
        """True si le patient a au moins une comorbidité."""
        return self.comorbidity_count > 0

    # ---- Méthodes publiques Phase 1 ----
        
    def set_status(
        self, 
        new_status: str, 
        service_name_str_or_None: typing.Optional[str] = None  
    ) -> None:
        """Definit le nouveau statut du patient.
        
        Args:
            new_status: un status parmi VALID_STATUSES.
            service_name_str_or_None: si non-None, met á jour current_admission_service_name.
            
        Raises:
            ValueError: si new_status invalide.
        """
        self._validate_status(new_status)  
        
        self.status_admission = new_status
        
        if service_name_str_or_None is not None: 
            old_name = self.current_admission_service_name
            
            # Sauvegarde dans transfer_history (timestamp=None pour une entree simple).
            self.transfer_history[old_name] = self.discharge_time if new_status == Patient.STATUS_DISCHARGED else None
                
            self.current_admission_service_name = service_name_str_or_None

    def is_assigned_to_current_service(self, expected_service: str) -> bool:
        """Verifie que le patient a bien un current_admission_service_name egale à expected."""
        return (
            self.current_admission_service_name == expected_service and 
            self.status_admission != Patient.STATUS_INCOMING
        )

    def is_in_service(self, service_name_match: str) -> bool:
        """Le patient est affecté à un service et y est encore présente physiquement."""  
        return (
            self.current_admission_service_name == service_name_match and 
            self.status_admission in {Patient.STATUS_ASSIGNED_TO_SERVICE, Patient.STATUS_TRANSFERRED_IN}
        )  
        
    # ---- Affichage debug / representation ---
    
    def __repr__(self) -> str:  # pragma: no cover - debug only  
        return (  
            f"Patient("
            f"id='{self.id}', "  
            f"status_admission={self.status_admission!r}, "
            f"arrival_time={self.arrival_time!r}, "
            f"discharge_time={self.discharge_time if self.discharge_time is not None else None!s}, "  
            f"current_service_name={self.current_admission_service_name}, "
            f"diagnostic_principal='{self.diagnostic_principal[:30]}'"  # Troncature  
            f")"  
        )

