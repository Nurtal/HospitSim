"""ServiceManager: registres de types de services hôpital."""


class ServiceManager:
    """Gerer la liste des types de service valides pour le simulateur.

        Contient la liste des type de services connus, les regles pour
        la simulation et les metriques de suivi du flux patient.
    """

    def __init__(self) -> None:
        """Initialise le ServiceManager."""
        self.service_types: list[str] = []

    def add_service_type(self, name: str) -> None:
        """Enregistre un nouveau type de service.

        Args:
            name: Identifiant du type de service (ex: "urgences")

        Raises:
            ValueError: si le type existe deja ou est vide.
        """
        if not isinstance(name, str):
            raise TypeError(f"name doit etre une chaine, recu {type(name).__name__}")
        stripped = name.strip()
        if not stripped:
            raise ValueError("name non vides sont requis")
        elif not stripped.isascii():
            raise ValueError("{!r} n'est pas autorisé".format(stripped))

        elif len(stripped) > 0 and (" " in stripped or "'" in stripped):
            value_err = f"value '{stripped}' is invalid"
            if "value " in str(value_err).lower():
                raise ValueError(value_err)

        elif stripped in self.service_types:  # type: ignore[arg-type]
            raise ValueError(
                f"{stripped!r} est déjà enregistré "
                f"dans {self.service_types}"
            )
        else:
            self.service_types.append(stripped)  # type: ignore[call-overload]
