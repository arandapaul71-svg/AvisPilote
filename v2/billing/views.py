import logging

from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.permissions import organisation_requise
from audit.models import journaliser

from . import paiement, plans
from .models import Subscription

log = logging.getLogger("avispilote")


@organisation_requise("abonnement")
@require_POST
def payer(request):
    """Redirige vers la page de paiement Stripe pour la formule choisie."""
    sub = request.organisation.subscription
    plan = request.POST.get("plan")
    if not paiement.est_configure() or plan not in plans.PLANS:
        messages.error(request, "Paiement indisponible pour le moment.")
        return redirect("accounts:abonnement")
    if sub.stripe_subscription_id and sub.status != Subscription.Statut.ANNULE:
        return redirect("billing:portail_get")  # déjà abonné : on change de formule dans le portail
    try:
        url = paiement.creer_session_paiement(request, sub, plan)
    except paiement.PaiementErreur as e:
        messages.error(request, str(e))
        return redirect("accounts:abonnement")
    journaliser(request, "paiement_demarre", plan=plan)
    return redirect(url)


@organisation_requise("abonnement")
def portail(request):
    try:
        return redirect(paiement.url_portail(request.organisation.subscription))
    except paiement.PaiementErreur as e:
        messages.error(request, str(e))
        return redirect("accounts:abonnement")


@csrf_exempt  # Stripe ne peut pas envoyer de jeton CSRF : la signature Stripe le remplace.
@require_POST
def webhook(request):
    if not paiement.est_configure():
        return HttpResponse(status=503)
    try:
        resultat = paiement.traiter_webhook(request.body, request.META.get("HTTP_STRIPE_SIGNATURE"))
    except ValueError:
        log.warning("Webhook Stripe refusé : signature invalide (IP %s)", request.META.get("REMOTE_ADDR"))
        return HttpResponseBadRequest("signature invalide")
    return HttpResponse(resultat)
