"""Décorateur de vue : connexion + organisation + permission du rôle."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def organisation_requise(action="voir"):
    def decorateur(vue):
        @login_required
        @wraps(vue)
        def enveloppe(request, *args, **kwargs):
            if request.membership is None or not request.membership.peut(action):
                raise PermissionDenied
            return vue(request, *args, **kwargs)

        return enveloppe

    return decorateur
