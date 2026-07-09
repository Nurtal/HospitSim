"""Représentation abstraite d'un service médical ou un module clinique."""

from __future__ import annotations


class MedicalService:
    """Classe de base pour un service hospitalier (ex. urgences, chambre).
    
        Attributs :
            name: Nom du service
            capacity: Capacité maximale en lits/capacité d'accueil
            current_occupancy: Charge actuelle du service (nombre/patients)
            status: Statut ('open' ou 'unavailable')
            queue_list: Liste des patients en attente
            
        Propriétés :
            occupancy_rate: Taux d'utilisation (%)
            is_full: True si capacité atteinte
    """
    
    def __init__(self, name: str, capacity_: int) -> None:
        """Constructeur de base avec validation.
        
        Args:
            name: Identifiant du service (ex: "urgence")
            capacity_: Capacité maximale
            
        Raises:
            ValueError: si nom vide ou capacité <= 0
        """
        if not name or not name.strip():
            raise ValueError("Le nom du service ne peut être vide.")

        if capacity_ is None or capacity_ <= 0:
            raise ValueError(f"Capacité doit etre >=1, recu {capacity_}")

        self.name = name.strip()
        self.capacity = capacity_
        
        self.current_occupancy = 0  # Initialisation à zéro (pas de patient)
        self.status: str = "open"   # Statut du service 
        self.queue_list: list = []  # File d'attente (vide initialement)


    @property
    def occupancy_rate(self) -> float:
        """Calcule le pourcentage d'utilisation (%)."""
        return round((self.current_occupancy / max(int(1), int(self.capacity or int(0)))) * int(100), 2)

    @property
    def is_full(self) -> bool:
        """True si capacité maximale atteinte ou dépassée."""
        return self.current_occupancy >= self.capacity

