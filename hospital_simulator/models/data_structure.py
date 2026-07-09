"""Définitions cliniques : Diagnostic (CIM-10), code local, Procédure (CCAM)."""

from __future__ import annotations

from hospital_simulator.models._cid_validator import CID10Validator
from hospital_simulator.models._ccam_validator import CCAMValidator


class Diagnosis:
    """Diagnostic identifié par un code CIM-10.

    Attributs :
        code: Code CIM-10 normalisé (majuscules, sans point).
        description: Libellé humain optionnel.
        expected_los_days: Durée de séjour attendue (jours), optionnelle.
    """

    def __init__(
        self,
        code: str,
        description: str = "",
        expected_los_days: int | None = None,
    ) -> None:
        if not CID10Validator.is_valid(code):
            raise ValueError(
                f"Code CIM-10 invalide pour {code!r} : format attendu 'J18', 'J189' ou 'J18.9'."
            )

        self.code = CID10Validator.normalize(code)
        self.description = description or ""
        self.expected_los_days: int | None = expected_los_days

    def get_code(self) -> str:
        return self.code

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Diagnosis) and other.code == self.code

    def __hash__(self) -> int:
        return hash(self.code)

    def __repr__(self) -> str:  # pragma: no cover - debug string
        return f"Diagnosis(code={self.code!r}, description={self.description!r})"


class DiagnosisLocal(Diagnosis):
    """Diagnostic CIM-10 standard enrichi d'un code local (nomenclature interne)."""

    def __init__(self, code: str, locale_code: str = "", **kwargs) -> None:  # type: ignore[override]
        super().__init__(code, **kwargs)
        self.locale_code: str = locale_code


class MedicalProcedure:
    """Procédure médicale identifiée par un code CCAM.

    Attributs :
        name: Libellé de la procédure (ex: "Chest X-Ray").
        code: Code CCAM normalisé (optionnel), ex: "ZZLF900".
        duration_minutes: Durée estimée en minutes (0 = non spécifiée).
    """

    def __init__(
        self,
        name: str,
        duration_minutes: int = 0,
        code: str | None = None,
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name doit être une chaîne non vide.")

        if isinstance(duration_minutes, bool) or not isinstance(duration_minutes, int):
            raise TypeError("duration_minutes doit être un entier.")
        if duration_minutes < 0:
            raise ValueError(f"duration_minutes doit être >= 0, reçu {duration_minutes}.")

        if code is not None and not CCAMValidator.is_valid(code):
            raise ValueError(
                f"Code CCAM invalide pour {code!r} : format attendu 4 lettres + 3 chiffres."
            )

        self.name: str = name.strip()
        self.duration_minutes: int = duration_minutes
        self.code: str | None = CCAMValidator.normalize(code) if code else None

    def __repr__(self) -> str:  # pragma: no cover - debug string
        return f"MedicalProcedure(name={self.name!r}, code={self.code!r})"
