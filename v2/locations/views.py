"""Connexion Google (OAuth), choix de la fiche, synchronisation et mode démo."""
import secrets

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from accounts.permissions import organisation_requise
from audit.models import journaliser

from reviews import traitement

from . import demo, google_client, sync
from .models import GoogleConnection, Location

CLE_OAUTH = "google_oauth"      # state + code_verifier PKCE, en session (côté serveur)
CLE_FICHES = "google_fiches"    # fiches proposées par Google, en attente du choix


@organisation_requise("google")
def google_connecter(request):
    if not google_client.est_configure():
        return render(request, "locations/google_indisponible.html")
    verifier, challenge = google_client.nouveau_pkce()
    state = secrets.token_urlsafe(32)
    request.session[CLE_OAUTH] = {"state": state, "verifier": verifier}
    return redirect(google_client.url_autorisation(state, challenge))


@organisation_requise("google")
def google_retour(request):
    attendu = request.session.pop(CLE_OAUTH, None)
    # compare_digest : comparaison en temps constant (évite de deviner le state caractère par caractère)
    if not attendu or not secrets.compare_digest(attendu["state"], request.GET.get("state", "")):
        messages.error(request, "Lien de connexion Google invalide ou expiré. Recommence.")
        return redirect("accounts:tableau_de_bord")
    if request.GET.get("error") or not request.GET.get("code"):
        messages.error(request, "Connexion Google annulée.")
        return redirect("accounts:tableau_de_bord")
    try:
        jetons = google_client.echanger_code(request.GET["code"], attendu["verifier"])
        connexion, _ = GoogleConnection.objects.get_or_create(organization=request.organisation)
        google_client.enregistrer_jetons(connexion, jetons)
        fiches = google_client.lister_fiches(connexion.access_token)
    except google_client.GoogleErreur as e:
        messages.error(request, str(e))
        return redirect("accounts:tableau_de_bord")
    journaliser(request, "google_connecte", nb_fiches=len(fiches))
    if not fiches:
        messages.error(request, "Aucune fiche Google Business Profile n'est associée à ce compte Google.")
        return redirect("accounts:tableau_de_bord")
    request.session[CLE_FICHES] = fiches
    return redirect("locations:choisir_fiche")


@organisation_requise("google")
@require_http_methods(["GET", "POST"])
def choisir_fiche(request):
    fiches = request.session.get(CLE_FICHES)
    if not fiches:
        return redirect("accounts:tableau_de_bord")
    if request.method == "POST":
        # On n'accepte QUE une fiche proposée par Google à cet utilisateur
        # (jamais un identifiant arbitraire envoyé par le navigateur).
        choix = next((f for f in fiches if f["name"] == request.POST.get("fiche")), None)
        if choix is None:
            messages.error(request, "Choisis une fiche dans la liste.")
        else:
            with transaction.atomic():
                request.organisation.locations.filter(is_demo=True).delete()
                fiche, _ = Location.objects.update_or_create(
                    organization=request.organisation, google_location_name=choix["name"],
                    defaults={"title": choix["title"], "new_review_uri": choix["new_review_uri"],
                              "sector": request.organisation.sector},
                )
            request.session.pop(CLE_FICHES, None)
            journaliser(request, "fiche_choisie", fiche=choix["title"])
            try:
                res = sync.synchroniser(fiche)
                n = traitement.traiter_en_attente(fiche)
                messages.success(request, f"Fiche « {fiche.title} » connectée : {res['ajoutes']} avis récupérés, "
                                          f"{n} traités par l'assistant.")
            except google_client.GoogleErreur as e:
                messages.error(request, f"Fiche connectée, mais récupération des avis impossible : {e}")
            return redirect("reviews:liste")
    return render(request, "locations/choisir_fiche.html", {"fiches": fiches})


@organisation_requise("google")
@require_POST
def google_deconnecter(request):
    """Retire l'accès Google et supprime les fiches et avis récupérés via Google."""
    connexion = GoogleConnection.objects.filter(organization=request.organisation).first()
    if connexion:
        google_client.revoquer(connexion)
        with transaction.atomic():
            request.organisation.locations.filter(is_demo=False).delete()
            connexion.delete()
        journaliser(request, "google_deconnecte")
        messages.success(request, "Fiche Google déconnectée et avis supprimés de AvisPilote.")
    return redirect("accounts:tableau_de_bord")


@organisation_requise("voir")
@require_POST
def synchroniser(request):
    fiche = sync.fiche_active(request.organisation)
    if fiche is None or fiche.is_demo:
        raise Http404
    if sync.synchro_trop_recente(fiche):
        messages.info(request, "Avis déjà mis à jour il y a moins de 2 minutes.")
    else:
        try:
            res = sync.synchroniser(fiche)
            n = traitement.traiter_en_attente(fiche)
            messages.success(request, f"{res['ajoutes']} nouvel(s) avis, {res['mis_a_jour']} mis à jour, "
                                      f"{n} traité(s) par l'assistant.")
        except google_client.GoogleErreur as e:
            messages.error(request, str(e))
    return redirect("reviews:liste")


@organisation_requise("google")
@require_POST
def activer_demo(request):
    if not settings.DEMO_AUTORISEE:
        raise Http404
    if request.organisation.locations.filter(is_demo=False).exists():
        messages.error(request, "Ta vraie fiche Google est connectée : la démo n'est plus disponible.")
        return redirect("accounts:tableau_de_bord")
    n = demo.creer_fiche_demo(request.organisation)
    traites = traitement.traiter_en_attente(sync.fiche_active(request.organisation))
    journaliser(request, "demo_activee", nb_avis=n)
    messages.success(request, f"{n} avis de démonstration générés, {traites} traités par l'assistant. "
                              "Rien n'est envoyé à Google.")
    return redirect("reviews:liste")


@organisation_requise("google")
@require_POST
def supprimer_demo(request):
    request.organisation.locations.filter(is_demo=True).delete()
    messages.success(request, "Données de démonstration supprimées.")
    return redirect("accounts:tableau_de_bord")
