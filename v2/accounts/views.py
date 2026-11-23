from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from audit.models import journaliser
from billing import paiement, quotas
from billing.models import Subscription, UsageCounter
from billing.plans import PLANS, prix_affiche
from insights import graphiques, stats
from locations import demo, google_client, sync
from locations.models import GoogleConnection
from reviews import traitement

from . import limiteur
from .forms import ConnexionForm, InscriptionForm, SuppressionCompteForm
from .models import Membership, Organization, Role, User
from .permissions import organisation_requise


def accueil(request):
    """Page de présentation pour les visiteurs ; les utilisateurs connectés vont au tableau de bord."""
    if request.user.is_authenticated:
        return redirect("accounts:tableau_de_bord")
    formules = [{"cle": k, "prix": prix_affiche(k), **v} for k, v in PLANS.items()]
    return render(request, "accounts/accueil.html", {"formules": formules, "demo_autorisee": settings.DEMO_AUTORISEE})


@require_http_methods(["GET", "POST"])
def inscription(request):
    if request.user.is_authenticated:
        return redirect("accounts:tableau_de_bord")
    form = InscriptionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():  # tout est créé, ou rien
            user = User.objects.create_user(d["email"], d["mot_de_passe"])
            org = Organization.objects.create(name=d["entreprise"], sector=d["secteur"])
            Membership.objects.create(user=user, organization=org, role=Role.OWNER)
            Subscription.creer_essai(org)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        request.organisation = org
        journaliser(request, "inscription")
        messages.success(request, "Compte créé : ton essai gratuit de 14 jours commence.")
        return redirect("accounts:tableau_de_bord")
    return render(request, "accounts/inscription.html", {"form": form})


@require_http_methods(["GET", "POST"])
def connexion(request):
    if request.user.is_authenticated:
        return redirect("accounts:tableau_de_bord")
    form = ConnexionForm(request, request.POST or None)
    if request.method == "POST":
        email = request.POST.get("email", "")
        if limiteur.est_bloque(request, email):
            form.add_error(None, "Trop de tentatives. Réessaie dans 10 minutes.")
        elif form.is_valid():
            limiteur.reinitialiser(request, email)
            login(request, form.user)  # Django change l'identifiant de session (anti-vol de session)
            request.organisation = form.user.membership.organization
            journaliser(request, "connexion")
            return redirect("accounts:tableau_de_bord")
        else:
            limiteur.noter_echec(request, email)
    return render(request, "accounts/connexion.html", {"form": form, "demo_autorisee": settings.DEMO_AUTORISEE})


PAGES_LEGALES = {"cgu": "Conditions générales d'utilisation et de vente", "confidentialite": "Politique de confidentialité",
                 "mentions": "Mentions légales"}


def page_legale(request, page):
    return render(request, f"legal/{page}.html", {"titre_page": PAGES_LEGALES[page]})


DEMO_EMAIL = "demo@demo.avispilote.local"


@require_POST
def demo_express(request):
    """« Découvrir avec la démo » : compte de démonstration prêt à l'emploi, en un clic.

    Uniquement si DEMO_AUTORISEE (désactivé en production). Le compte n'a pas de mot de passe
    utilisable : on ne peut y entrer que par ce bouton. Les données fictives sont régénérées
    si elles datent de plus d'un jour, pour que les dates restent récentes.
    """
    if not settings.DEMO_AUTORISEE:
        raise Http404
    with transaction.atomic():
        user, cree = User.objects.get_or_create(email=DEMO_EMAIL)
        if cree:
            user.set_unusable_password()
            user.save()
            org = Organization.objects.create(name="Boulangerie des Arts", sector="boulangerie")
            Membership.objects.create(user=user, organization=org, role=Role.OWNER)
            Subscription.creer_essai(org)
        org = user.membership.organization
        sub = org.subscription
        if not sub.est_utilisable:  # l'essai de la démo ne doit jamais expirer
            sub.trial_ends = timezone.now() + timedelta(days=14)
            sub.status = Subscription.Statut.ESSAI
            sub.save()
    fiche = sync.fiche_active(org)
    if fiche is None or fiche.created_at < timezone.now() - timedelta(days=1):
        UsageCounter.objects.filter(organization=org).delete()
        demo.creer_fiche_demo(org)
        traitement.traiter_en_attente(sync.fiche_active(org))
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    messages.success(request, "Bienvenue dans la démo : avis fictifs, rien n'est envoyé à Google.")
    return redirect("accounts:tableau_de_bord")


@require_POST
def deconnexion(request):
    logout(request)
    return redirect("accounts:connexion")


@organisation_requise("voir")
def tableau_de_bord(request):
    org = request.organisation
    sub = org.subscription
    fiche = sync.fiche_active(org)
    periode = stats.periode_valide(request.GET.get("periode"))
    contexte_stats = {}
    if fiche is not None:
        serie = stats.series(fiche, periode)
        contexte_stats = {
            "ind": stats.indicateurs(fiche, periode),
            "g_colonnes": graphiques.colonnes_empilees(serie),
            "g_note": graphiques.courbe_note(serie),
            "g_etoiles": graphiques.barres_etoiles(stats.repartition_etoiles(fiche, periode)),
            "serie": serie,
            "ff": stats.forces_faiblesses(fiche, periode),
            "alertes": list(fiche.alerts.filter(read_at__isnull=True)[:3]),
            "nb_recos": fiche.recommendations.exclude(status="resolue").filter(type="corriger").count(),
        }
    etapes = {
        "fiche_google": fiche is not None and not fiche.is_demo,
        "assistant_regle": org.locations.filter(ai_settings__isnull=False).exists(),
    }
    return render(request, "accounts/tableau_de_bord.html", {
        "sub": sub,
        "plan": sub.infos_plan,
        "prix": prix_affiche(sub.plan),
        "quota": quotas.etat(sub),
        "etapes": etapes,
        "fiche": fiche,
        "connexion_google": GoogleConnection.objects.filter(organization=org).first(),
        "demo_autorisee": settings.DEMO_AUTORISEE,
        "periode": periode,
        "periodes": stats.PERIODES,
        **contexte_stats,
    })


@organisation_requise("voir")
def abonnement(request):
    sub = request.organisation.subscription
    # Le retour de Stripe n'active RIEN : seul le webhook signé change l'abonnement.
    if request.GET.get("paiement") == "ok":
        messages.info(request, "Merci ! Le paiement est en cours de confirmation par Stripe : "
                               "ton abonnement s'active dans quelques secondes (recharge la page).")
    elif request.GET.get("paiement") == "annule":
        messages.info(request, "Paiement annulé : rien n'a été débité.")
    formules = [{"cle": k, "prix": prix_affiche(k), **v} for k, v in PLANS.items()]
    return render(request, "accounts/abonnement.html", {
        "sub": sub, "formules": formules, "quota": quotas.etat(sub),
        "paiement_actif": paiement.est_configure(),
        "abonne": bool(sub.stripe_subscription_id) and sub.status != Subscription.Statut.ANNULE,
    })


@organisation_requise("supprimer_compte")
@require_http_methods(["GET", "POST"])
def supprimer_compte(request):
    """Droit à l'effacement (RGPD) : supprime l'organisation et toutes ses données."""
    form = SuppressionCompteForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        org = request.organisation
        journaliser(request, "suppression_compte", entreprise=org.name)
        connexion = GoogleConnection.objects.filter(organization=org).first()
        if connexion:
            google_client.revoquer(connexion)  # retire aussi l'accès chez Google
        paiement.resilier_immediatement(org.subscription)  # plus aucun prélèvement après suppression
        with transaction.atomic():
            # list() : on lit les identifiants AVANT de supprimer l'organisation,
            # sinon le lien utilisateur → organisation a déjà disparu.
            ids_utilisateurs = list(User.objects.filter(membership__organization=org).values_list("id", flat=True))
            org.delete()          # supprime en cascade établissements, avis, abonnement…
            User.objects.filter(id__in=ids_utilisateurs).delete()
        logout(request)
        messages.success(request, "Ton compte et toutes ses données ont été supprimés.")
        return redirect("accounts:connexion")
    return render(request, "accounts/supprimer_compte.html", {"form": form})
