"""Synchronisation des avis Google vers la base (récupération + stockage, sans IA).

Le traitement IA (analyse + réponse, qui consomme le quota) est séparé : il viendra
au lot de l'assistant IA. Ici, on ne fait que récupérer et stocker.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from reviews.models import Review

from . import google_client
from .models import Location

INTERVALLE_MIN_MANUEL = timedelta(minutes=2)   # anti-abus du bouton « Mettre à jour »
INTERVALLE_AUTO = timedelta(minutes=15)        # synchro planifiée


def fiche_active(organisation):
    """MVP : un établissement par organisation (le multi-sites viendra à l'étape 5)."""
    return organisation.locations.order_by("is_demo", "created_at").first()


def synchro_trop_recente(location, intervalle=INTERVALLE_MIN_MANUEL):
    return location.last_sync_at is not None and timezone.now() - location.last_sync_at < intervalle


def synchroniser(location):
    """Importe ou met à jour les avis de la fiche. Renvoie {"ajoutes": n, "mis_a_jour": n}."""
    if location.is_demo:
        return {"ajoutes": 0, "mis_a_jour": 0}
    connexion = location.organization.google
    ajoutes = mis_a_jour = 0
    for page in google_client.pages_avis(connexion, location.google_location_name):
        if "averageRating" in page:
            location.average_rating = round(page["averageRating"], 2)
        if "totalReviewCount" in page:
            location.total_review_count = page["totalReviewCount"]
        changements_dans_page = 0
        with transaction.atomic():
            for rv in page.get("reviews", []):
                reponse = rv.get("reviewReply") or {}
                violation = rv.get("policyViolation") or {}
                valeurs = {
                    "author": (rv.get("reviewer") or {}).get("displayName") or "Client Google",
                    "stars": google_client.ETOILES.get(rv.get("starRating"), 3),
                    "comment": rv.get("comment", "")[:10000],
                    "created_at": google_client.lire_date(rv["createTime"]),
                    "google_reply": reponse.get("comment", ""),
                    "google_reply_at": google_client.lire_date(reponse["updateTime"]) if reponse.get("updateTime") else None,
                    "policy_violation": str(violation.get("type", ""))[:200] if violation else "",
                }
                avis, cree = Review.objects.get_or_create(
                    location=location, google_review_id=rv["reviewId"], defaults=valeurs
                )
                if cree:
                    ajoutes += 1
                    changements_dans_page += 1
                    continue
                modifs = [k for k, v in valeurs.items() if getattr(avis, k) != v]
                if modifs:
                    for k in modifs:
                        setattr(avis, k, valeurs[k])
                    avis.save(update_fields=modifs)
                    mis_a_jour += 1
                    changements_dans_page += 1
        # Tri par date de modification : une page sans aucun changement = le reste est déjà à jour.
        if changements_dans_page == 0:
            break
    location.last_sync_at = timezone.now()
    location.save(update_fields=["average_rating", "total_review_count", "last_sync_at"])
    return {"ajoutes": ajoutes, "mis_a_jour": mis_a_jour}


def a_synchroniser():
    """Fiches Google dont la dernière synchro date de plus de 15 minutes."""
    limite = timezone.now() - INTERVALLE_AUTO
    return (Location.objects.filter(is_demo=False, organization__google__status="ok")
            .exclude(google_location_name="")
            .filter(Q(last_sync_at__isnull=True) | Q(last_sync_at__lt=limite))
            .select_related("organization__google"))
