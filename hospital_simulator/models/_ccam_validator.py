"""Validateur de codes CCAM (procédures médicales).

Un code CCAM est composé de 4 lettres majuscules suivies de 3 chiffres,
par exemple ``ZZLF900`` (radiographie du thorax) ou ``DZQM006``.
"""

from __future__ import annotations

import re

_CCAM_PATTERN: str = r"^[A-Z]{4}\d{3}$"
_CCAM_RE = re.compile(_CCAM_PATTERN)


class CCAMValidator:
    """Valide et normalise un code CCAM."""

    @staticmethod
    def validate(code: str) -> bool:
        """Renvoie True si ``code`` respecte le format CCAM."""
        if not isinstance(code, str):
            return False
        return bool(_CCAM_RE.fullmatch(code.strip().upper()))

    @staticmethod
    def is_valid(code: str) -> bool:
        """Alias de :meth:`validate`."""
        return CCAMValidator.validate(code)

    @staticmethod
    def normalize(code: str) -> str:
        """Renvoie la forme canonique du code (majuscules, sans espaces).

        Raises:
            ValueError: si le code n'est pas un code CCAM valide.
        """
        if not CCAMValidator.validate(code):
            raise ValueError(f"Code CCAM invalide : {code!r}.")
        return code.strip().upper()
