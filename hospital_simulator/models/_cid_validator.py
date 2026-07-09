"""Validateur de codes CIM-10 (diagnostic).

Un code CIM-10 est constitué d'une lettre de chapitre, de deux chiffres de
catégorie, puis d'une éventuelle sous-catégorie (1 à 4 caractères alphanumériques),
avec ou sans point séparateur. Exemples valides : ``J18``, ``J189``, ``J18.9``,
``E11.9``, ``I50.0``.
"""

from __future__ import annotations

import re

# Lettre + 2 chiffres, puis sous-catégorie optionnelle (point facultatif).
_CIM10_PATTERN: str = r"^[A-Z]\d{2}(?:\.?[A-Za-z0-9]{1,4})?$"
_CIM10_RE = re.compile(_CIM10_PATTERN)


class CID10Validator:
    """Valide et normalise un code CIM-10 selon une regex simplifiée."""

    @staticmethod
    def validate(code: str) -> bool:
        """Renvoie True si ``code`` respecte le format CIM-10 (dotté ou non)."""
        if not isinstance(code, str):
            return False
        return bool(_CIM10_RE.fullmatch(code.strip().upper()))

    @staticmethod
    def is_valid(code: str) -> bool:
        """Alias de :meth:`validate`, d'usage plus courant."""
        return CID10Validator.validate(code)

    @staticmethod
    def normalize(code: str) -> str:
        """Renvoie la forme canonique du code (majuscules, sans point).

        Args:
            code: Un code CIM-10 valide.

        Raises:
            ValueError: si le code n'est pas un code CIM-10 valide.
        """
        if not CID10Validator.validate(code):
            raise ValueError(f"Code CIM-10 invalide : {code!r}.")
        return code.strip().upper().replace(".", "")
