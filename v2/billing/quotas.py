"""Calcul et consommation du quota d'avis traités par l'IA."""
from django.db import transaction
from django.db.models import F

from . import plans
from .models import Subscription, UsageCounter


def compteur(subscription):
    subscription.renouveler_si_besoin()
    obj, _ = UsageCounter.objects.get_or_create(
        organization=subscription.organization, period_start=subscription.period_start
    )
    return obj


def etat(subscription):
    c = compteur(subscription)
    quota = subscription.infos_plan["quota"]
    utilises = c.reviews_processed
    pourcentage = min(100, round(100 * utilises / quota)) if quota else 100
    return {
        "quota": quota,
        "utilises": utilises,
        "restants": max(0, quota - utilises),
        "pourcentage": pourcentage,
        "bientot_atteint": plans.SEUIL_ALERTE_QUOTA * 100 <= pourcentage < 100,
        "atteint": utilises >= quota,
        "period_start": subscription.period_start,
        "period_end": subscription.period_end,
        "abonnement_utilisable": subscription.est_utilisable,
    }


def peut_traiter(subscription, etoiles):
    """Vrai si un avis de `etoiles` étoiles peut encore être traité par l'IA.
    Les avis 1-2★ peuvent utiliser tout le quota ; les autres s'arrêtent avant
    pour garder une réserve, afin qu'un avis négatif ne reste jamais sans réponse."""
    if not subscription.est_utilisable:
        return False
    c = compteur(subscription)
    quota = subscription.infos_plan["quota"]
    if c.reviews_processed >= quota:
        return False
    if etoiles >= 3:
        return c.positive_processed < int(quota * (1 - plans.RESERVE_NEGATIFS))
    return True


@transaction.atomic
def consommer(subscription, etoiles):
    """Réserve une unité de quota. Renvoie False si le quota est épuisé.
    Verrou de ligne (select_for_update) pour éviter de dépasser le quota
    si deux traitements tournent en même temps."""
    sub = Subscription.objects.select_for_update().get(pk=subscription.pk)
    if not peut_traiter(sub, etoiles):
        return False
    c = compteur(sub)
    maj = {"reviews_processed": F("reviews_processed") + 1}
    if etoiles >= 3:
        maj["positive_processed"] = F("positive_processed") + 1
    UsageCounter.objects.filter(pk=c.pk).update(**maj)
    return True
