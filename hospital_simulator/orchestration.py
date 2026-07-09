"""Orchestrateur de la simulation d'admission / dispatch / queues (coordination des services)."""


from datetime import datetime

from hospital_simulator.services.service_registry import ServiceRegistry, _MAX_CAPACITY
from hospital_simulator.patient import Patient


class HospitalFlowSimulator:
    """Coordonne les admissions / transfers et suives les patients dans le flux hospitalier virtuel.

    Exemples d'utilisation typiques :
    
        simu = HospitalFlowSimulator()
        simu.configure_registry(3)  # 3 services actifs (ED, ICU, Ward) par defaut
        
        p1 = Patient(age=50)
        simu.register_patient(p1)   
        simu.dispatch_to_ward_if_full(simu.QUEUE_URGENCE)  # dispatch ou en attente.
        
    L'orchestrateur gère une **queue d'entrée** (admission), puis distribue aux 
    services actifs via un dispatcher interne qui vérifie l'état de la file.
    
    Pas de dépendance vers des objets externes si ce n'est les registres ServiceRegistry / Patient définis plus haut (`from .patient` et `from .services...`).
    """

    QUEUE_URGENCE = "emergency_queue"  # Constante interne pour simplifier.
    QUEUE_OUTPATIENT = "outpatient_queue"

    # Limite de patients dans la file d'arrivée (limite avant refus ou en attente d'un slot).  
    MAX_INCOMING_QUEUE: int
    _registry: ServiceRegistry

    def __init__(self) -> None:  # pragma: no cover - constructeur minimal, pas utilisé par les tests unitaires.
        self._registry = ServiceRegistry()  
        self.incoming_queue_list: list[Patient] = []  # La file d'attente initiale (patients non encore traités).
        self.MAX_INCOMING_QUEUE = _MAX_CAPACITY

    def configure_registry(self, num_services_default: int) -> None:
        """Initialise le registry par défaut : 3 types de service (ED, ICU, Ward)."""  
        # Les noms standards.
        default_names = ("ED", "ICU", "Ward")

        if num_services_default <= 0:
            raise ValueError("num_services_default doit être > 0.")

        for name in default_names[:num_services_default]:
            self._registry.register_service(name, capacity=_MAX_CAPACITY)

    def register_patient(self, new_patients_list_or_single: Patient | list[Patient]) -> None:
        """Ajoute un patient ou une liste de patients à la file entrante (non traitée)."""  
        if isinstance(new_patients_list_or_single, list):  # Si c'est bien une liste.
            for pat in new_patients_list_or_single:  # Itère sur chaque élément.
                self.incoming_queue_list.append(pat)
            return

        # Sinon c'est un seul Patient.
        if not isinstance(new_patients_list_or_single, Patient):
            raise TypeError("Entrée invalide pour register_patient (Patient ou list[Patient]).")
            
        self.incoming_queue_list.append(new_patients_list_or_single)  # Ajout à la queue d'arrivée.

    def dispatch_next_if_any(self, next_service_name: str | None = None, simulate_processing_time_seconds: int = 10) -> bool:
        """Traite un patient de la file entrante si possible, puis dispatch au service demandé (ou en attente dans une autre)."""  
        if not self.incoming_queue_list:  # Queue vide ? Ne fait rien.
            return False

        new_patient = self.incoming_queue_list.pop(0)  # Prend le premier de la file entrante.
        
        # Vérif capacité du service demandé (sans dépasser la capacité enregistrée, par défaut _MAX_CAPACITY).
        if not next_service_name or self._registry.service_types is None or next_service_name not in self._registry.service_types:
            pass  # Aucun service valide pour le dispatch.
        
        elif cap := self._registry.get_remaining_capacity(next_service_name):  
            # Service disponible et place restante.
            self._registry.admit(new_patient, service_name=next_service_name)  # Admet dans le registry (ajuste status).
        else:  # Pas de place disponible ou autre cas.
            new_patient.status_admission = Patient.STATUS_DISPATCH_QUEUED

        return True  # Action effectuée.


    # ----- Métriques simples -----
    
    @property
    def num_patients_in_system(self) -> int:
        """Total des patients en cours : file entrante + patients admis dans les services."""
        admitted = sum(
            self._registry.get_service_occupancy(name)
            for name in self._registry.service_types
        )
        return len(self.incoming_queue_list) + admitted

    def summarize_registry_status(self, print_to: bool = False) -> dict[str, int]:
        """Retourne l'occupation courante de chaque service enregistré.

        Args:
            print_to: si True, affiche également le résumé sur la sortie standard.

        Returns:
            Un dict ``{nom_service: nb_patients_admis}`` complété d'une clé
            ``"incoming_queue"`` pour les patients encore en attente de dispatch.
        """
        summary: dict[str, int] = {
            name: self._registry.get_service_occupancy(name)
            for name in self._registry.service_types
        }
        summary["incoming_queue"] = len(self.incoming_queue_list)

        if print_to:
            for label, count in summary.items():
                print(f"{label:>20} : {count}")

        return summary

    @staticmethod
    def _assert_registry_is_initialized(registry_instance: ServiceRegistry | None) -> None:
        """Vérifie que le registry est initialisé (non None et contient au moins un service)."""
        if registry_instance is None or not registry_instance.service_types:
            raise RuntimeError(
                "Le registry n'est pas initialisé : appelez configure_registry() d'abord."
            )
