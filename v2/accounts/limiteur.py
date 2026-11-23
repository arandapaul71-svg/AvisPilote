"""Limite les tentatives de connexion (contre les attaques par force brute).

Compte les échecs par adresse IP et par e-mail dans le cache Django.
En production avec plusieurs serveurs, il faudra un cache partagé (Redis).
"""
from django.conf import settings
from django.core.cache import cache


def _cles(request, email):
    ip = request.META.get("REMOTE_ADDR", "inconnue")
    return [f"connexion:ip:{ip}", f"connexion:email:{(email or '').lower()}"]


def est_bloque(request, email):
    return any(cache.get(c, 0) >= settings.CONNEXION_MAX_TENTATIVES for c in _cles(request, email))


def noter_echec(request, email):
    for c in _cles(request, email):
        cache.add(c, 0, settings.CONNEXION_FENETRE_SECONDES)
        cache.incr(c)


def reinitialiser(request, email):
    cache.delete_many(_cles(request, email))
