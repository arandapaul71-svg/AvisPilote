"""Champ de base de données chiffré (pour les jetons Google).

Si quelqu'un vole le fichier de la base, il ne peut pas utiliser les jetons
sans la clé FIELD_ENCRYPTION_KEY, stockée à part (variables d'environnement).
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet():
    cle = settings.FIELD_ENCRYPTION_KEY
    if not cle:
        # Développement uniquement : clé dérivée de SECRET_KEY (settings refuse ce cas en production).
        cle = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(cle)


def chiffrer(texte):
    return _fernet().encrypt(texte.encode()).decode()


def dechiffrer(texte):
    try:
        return _fernet().decrypt(texte.encode()).decode()
    except InvalidToken:
        return None  # clé changée ou donnée corrompue : on traite comme absent


class EncryptedTextField(models.TextField):
    """Texte chiffré en base, en clair uniquement dans le code Python."""

    def from_db_value(self, value, expression, connection):
        return None if value is None else dechiffrer(value)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return None if value in (None, "") else chiffrer(value)
