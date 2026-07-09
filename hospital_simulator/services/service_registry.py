"""Service Registry: gestion des admissions, dispatching, files d'attente par service."""

from __future__ import annotations

from hospital_simulator.patient import Patient


# Limite maximale de patients simultanément accueillis dans un même service.
_MAX_CAPACITY = 100  # Par défaut, on limite la taille.


class _ServiceManagerBase:
    """Classe de base qui définit l'état commun à tous les gestionnaires de services.

    Fournit le mécanisme d'enregistrement des types de service valides pour la simulation.
    """

    def __init__(self) -> None:
        self.service_types: list[str] = []


class ServiceRegistry(_ServiceManagerBase):
    """Gère la liste des services disponibles et orchestre l'admission / dispatching.

    Hérite de :class:`_ServiceManagerBase` et ajoute :

        * Le suivi de la capacité maximale par service.
        * Le suivi du nombre de lits occupés par service.
        * L'enregistrement, l'admission et le calcul de capacité restante.

    Exemple d'usage typique ::

        registry = ServiceRegistry()
        registry.register_service("ED", capacity=50)

        patient = Patient(sexe="M", age=67)
        registry.admit(patient, service_name="ED")

    Attributes:
        service_types: Noms des services enregistrés.
        _service_capacities: Capacité maximale de chaque service.
        _service_occupancy: Nombre de lits occupés dans chaque service.
    """

    def __init__(self) -> None:
        super().__init__()
        self._service_capacities: dict[str, int] = {}
        self._service_occupancy: dict[str, int] = {}

    # ---- Enregistrement des services ----

    def register_service(self, name: str, capacity: int = _MAX_CAPACITY) -> None:
        """Enregistre un nouveau service disponible.

        Args:
            name: Identifiant du service (ex: "ED").
            capacity: Nombre de lits/places (entier strictement positif).

        Raises:
            ValueError: si le nom n'est pas une chaîne non vide, si la capacité
                n'est pas > 0, ou si le service est déjà enregistré.
            TypeError: si la capacité n'est pas un entier (les booléens sont refusés).
        """
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Le nom du service doit être une chaîne de caractères non vide.")

        name = name.strip()

        # bool est une sous-classe de int : on le refuse explicitement.
        if isinstance(capacity, bool) or not isinstance(capacity, int):
            raise TypeError(
                f"La capacité doit être un entier positif, reçu {type(capacity).__name__}."
            )
        if capacity <= 0:
            raise ValueError(f"La capacité doit être un entier > 0, reçu {capacity}.")

        if name in self.service_types:
            raise ValueError(f"Le service {name!r} est déjà enregistrée dans {self.service_types}.")

        self.service_types.append(name)
        self._service_capacities[name] = capacity
        self._service_occupancy[name] = 0

    # ---- Interrogation de capacité ----

    def get_service_capacity(self, name: str) -> int | None:
        """Renvoie la capacité maximale d'un service, ou None s'il n'existe pas."""
        return self._service_capacities.get(name)

    def get_service_occupancy(self, name: str) -> int:
        """Renvoie le nombre de lits occupés dans un service (0 si inconnu)."""
        return self._service_occupancy.get(name, 0)

    def get_remaining_capacity(self, name: str) -> int:
        """Renvoie le nombre de places restantes dans un service (0 si inconnu ou plein)."""
        if name not in self._service_capacities:
            return 0
        return self._service_capacities[name] - self._service_occupancy[name]

    # ---- Admission ----

    def admit(self, patient: Patient, service_name: str) -> bool:
        """Admet un patient dans un service si une place est disponible.

        Args:
            patient: Le patient à admettre.
            service_name: Le service cible.

        Returns:
            True si le patient a été admis, False si le service est inconnu ou plein
            (dans ce cas le statut du patient reste inchangé).
        """
        if self.get_remaining_capacity(service_name) <= 0:
            return False

        self._service_occupancy[service_name] += 1
        patient.set_status(
            Patient.STATUS_ASSIGNED_TO_SERVICE,
            service_name_str_or_None=service_name,
        )
        return True
