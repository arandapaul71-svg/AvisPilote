"""Paiement des abonnements avec Stripe (SDK officiel `stripe`).

Principes de sécurité :
- la carte bancaire est saisie sur la page Stripe (Checkout), JAMAIS sur AvisPilote :
  aucune donnée de carte ne transite ni n'est stockée chez nous (conformité PCI gérée par Stripe) ;
- la clé secrète Stripe reste côté serveur (.env) ;
- l'état de l'abonnement n'est modifié QUE par les webhooks signés par Stripe, jamais par
  le retour du navigateur (qu'un utilisateur pourrait falsifier) ;
- changement de formule, carte, factures, résiliation : portail client hébergé par Stripe.
"""
import logging
from datetime import datetime, timedelta
from datetime import timezone as tz

import stripe
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from . import plans
from .models import StripeEvent, Subscription

log = logging.getLogger("avispilote")

STATUTS = {
    "active": Subscription.Statut.ACTIF, "trialing": Subscription.Statut.ACTIF,
    "past_due": Subscription.Statut.IMPAYE, "unpaid": Subscription.Statut.IMPAYE,
    "incomplete": Subscription.Statut.IMPAYE, "paused": Subscription.Statut.IMPAYE,
    "canceled": Subscription.Statut.ANNULE, "incomplete_expired": Subscription.Statut.ANNULE,
}


class PaiementErreur(Exception):
    pass


def est_configure():
    return bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_WEBHOOK_SECRET
                and all(settings.STRIPE_PRICES.get(p) for p in plans.PLANS))


def _client():
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY, max_network_retries=2)


def plan_depuis_prix(price_id):
    return next((p for p, prix in settings.STRIPE_PRICES.items() if prix == price_id), None)


def creer_session_paiement(request, sub, plan):
    """Renvoie l'URL de la page de paiement Stripe pour la formule `plan`."""
    if plan not in plans.PLANS:
        raise PaiementErreur("Formule inconnue.")
    client = _client()
    org = sub.organization
    try:
        if not sub.stripe_customer_id:
            client_stripe = client.v1.customers.create(params={
                "email": request.user.email, "name": org.name, "metadata": {"organisation_id": str(org.pk)},
            })
            sub.stripe_customer_id = client_stripe.id
            sub.save(update_fields=["stripe_customer_id"])
        donnees_abonnement = {"metadata": {"organisation_id": str(org.pk)}}
        # Le commerçant en essai n'est débité qu'à la fin de ses 14 jours gratuits
        # (Stripe exige une date de fin d'essai au moins 48 h dans le futur).
        if sub.status == Subscription.Statut.ESSAI and sub.trial_ends and sub.trial_ends > timezone.now() + timedelta(hours=49):
            donnees_abonnement["trial_end"] = int(sub.trial_ends.timestamp())
        base = settings.APP_URL
        session = client.v1.checkout.sessions.create(params={
            "mode": "subscription",
            "customer": sub.stripe_customer_id,
            "client_reference_id": str(org.pk),
            "line_items": [{"price": settings.STRIPE_PRICES[plan], "quantity": 1}],
            "subscription_data": donnees_abonnement,
            "locale": "fr",
            "allow_promotion_codes": True,
            "success_url": base + reverse("accounts:abonnement") + "?paiement=ok",
            "cancel_url": base + reverse("accounts:abonnement") + "?paiement=annule",
        })
    except stripe.StripeError as e:
        log.warning("Stripe Checkout impossible : %s", e.__class__.__name__)
        raise PaiementErreur("Le paiement est momentanément indisponible. Réessaie dans quelques minutes.") from e
    return session.url


def url_portail(sub):
    """Portail client Stripe : changer de formule ou de carte, factures, résiliation."""
    if not sub.stripe_customer_id:
        raise PaiementErreur("Aucun abonnement payant.")
    try:
        session = _client().v1.billing_portal.sessions.create(params={
            "customer": sub.stripe_customer_id, "locale": "fr",
            "return_url": settings.APP_URL + reverse("accounts:abonnement"),
        })
    except stripe.StripeError as e:
        raise PaiementErreur("Le portail de paiement est momentanément indisponible.") from e
    return session.url


def _date(ts):
    return datetime.fromtimestamp(int(ts), tz=tz.utc) if ts else None


def synchroniser_abonnement(abonnement_stripe):
    """Recopie l'état d'un abonnement Stripe dans notre base (appelé par les webhooks)."""
    if hasattr(abonnement_stripe, "to_dict"):
        abonnement_stripe = abonnement_stripe.to_dict()  # les objets du SDK ne sont pas des dict
    client_id = abonnement_stripe["customer"]
    sub = Subscription.objects.filter(stripe_customer_id=client_id).first()
    if sub is None:
        log.warning("Webhook Stripe pour un client inconnu : %s", client_id)
        return None
    items = abonnement_stripe["items"]["data"]
    element = items[0] if items else {}
    plan = plan_depuis_prix(element.get("price", {}).get("id")) if element else None
    debut, fin = _date(element.get("current_period_start")), _date(element.get("current_period_end"))
    statut = STATUTS.get(abonnement_stripe["status"], Subscription.Statut.IMPAYE)

    sub.stripe_subscription_id = abonnement_stripe["id"]
    sub.status = statut
    if plan:
        sub.plan = plan
    if debut and fin:
        sub.period_start, sub.period_end = debut, fin  # nouvelle période → le quota repart à zéro
    if statut == Subscription.Statut.ANNULE:
        sub.stripe_subscription_id = ""
    sub.save()
    return sub


TYPES_ABONNEMENT = {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted",
                    "customer.subscription.paused", "customer.subscription.resumed"}


def traiter_webhook(payload, signature):
    """Vérifie la signature Stripe puis applique l'événement. Lève ValueError si la signature est invalide."""
    try:
        evenement = stripe.Webhook.construct_event(payload, signature, settings.STRIPE_WEBHOOK_SECRET).to_dict()
    except (ValueError, stripe.SignatureVerificationError) as e:
        raise ValueError("signature invalide") from e

    with transaction.atomic():
        _, nouveau = StripeEvent.objects.get_or_create(event_id=evenement["id"], defaults={"type": evenement["type"]})
        if not nouveau:
            return "deja_traite"
        objet = evenement["data"]["object"]
        if evenement["type"] in TYPES_ABONNEMENT:
            # On relit l'abonnement chez Stripe : l'état le plus récent fait foi
            # (les événements peuvent arriver dans le désordre).
            abonnement = _client().v1.subscriptions.retrieve(objet["id"])
            synchroniser_abonnement(abonnement)
        elif evenement["type"] == "checkout.session.completed" and objet.get("subscription"):
            synchroniser_abonnement(_client().v1.subscriptions.retrieve(objet["subscription"]))
        elif evenement["type"] == "invoice.payment_failed":
            Subscription.objects.filter(stripe_customer_id=objet["customer"]).update(status=Subscription.Statut.IMPAYE)
    return "ok"


def resilier_immediatement(sub):
    """Suppression du compte : on arrête la facturation tout de suite. Ne lève jamais d'erreur."""
    if not (sub.stripe_subscription_id and settings.STRIPE_SECRET_KEY):
        return
    try:
        _client().v1.subscriptions.cancel(sub.stripe_subscription_id)
    except stripe.StripeError:
        log.error("Résiliation Stripe impossible pour l'organisation %s : à faire à la main !", sub.organization_id)
