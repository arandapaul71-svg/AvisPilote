from datetime import timedelta

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.core.cache import cache
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from accounts.permissions import organisation_requise
from audit.models import journaliser
from locations import sync

from . import envoi, outils, rapport_pdf, rapports, recommandations, stats
from .models import Alert, Recommendation


@organisation_requise("voir")
def analyses(request):
    """Points forts / points faibles relevés dans les avis, avec exemples et solutions."""
    fiche = sync.fiche_active(request.organisation)
    if fiche is None:
        messages.info(request, "Connecte d'abord ta fiche (ou la démo) pour voir les analyses.")
        return redirect("accounts:tableau_de_bord")
    periode = stats.periode_valide(request.GET.get("periode"))
    return render(request, "insights/analyses.html", {
        "fiche": fiche, "periode": periode, "periodes": stats.PERIODES, "nom_periode": stats.PERIODES[periode]["nom"],
        "ff": stats.forces_faiblesses(fiche, periode),
    })


def _preuves(fiche, ids, n=3):
    """Avis justificatifs, TOUJOURS filtrés par la fiche de l'utilisateur (isolation)."""
    return list(fiche.reviews.filter(pk__in=ids[:n]).order_by("-created_at"))


@organisation_requise("voir")
def recommandations_vue(request):
    fiche = sync.fiche_active(request.organisation)
    if fiche is None:
        messages.info(request, "Connecte d'abord ta fiche (ou la démo).")
        return redirect("accounts:tableau_de_bord")
    sub = request.organisation.subscription
    detail = sub.a_la_fonction("anomalies")
    alertes = list(fiche.alerts.filter(created_at__gte=timezone.now() - timedelta(days=60)))
    for a in alertes:
        a.preuves = _preuves(fiche, a.evidence_review_ids) if detail else []
    recos = []
    if sub.a_la_fonction("recommandations"):
        recos = list(fiche.recommendations.all())
        for r in recos:
            r.preuves = _preuves(fiche, r.evidence_review_ids)
            r.suivi = recommandations.suivi(r)
    return render(request, "insights/recommandations.html", {
        "fiche": fiche, "alertes": alertes, "recos": recos, "detail": detail,
        "avec_recos": sub.a_la_fonction("recommandations"), "statuts": Recommendation.Statut.choices,
        "peut_agir": request.membership.peut("repondre"),
    })


@organisation_requise("voir")
@require_POST
def alerte_lue(request, alerte_id):
    alerte = get_object_or_404(Alert, pk=alerte_id, location__organization=request.organisation)
    alerte.read_at = alerte.read_at or timezone.now()
    alerte.save(update_fields=["read_at"])
    # Destination de retour choisie parmi deux valeurs connues (jamais une URL envoyée par le navigateur).
    if request.POST.get("retour") == "tableau":
        return redirect("accounts:tableau_de_bord")
    return redirect("insights:recommandations")


@organisation_requise("repondre")
@require_POST
def changer_statut(request, reco_id):
    reco = get_object_or_404(Recommendation, pk=reco_id, location__organization=request.organisation)
    statut = request.POST.get("statut")
    if statut not in Recommendation.Statut.values:
        messages.error(request, "Statut inconnu.")
    elif statut != reco.status:
        reco.status, reco.status_changed_at = statut, timezone.now()
        reco.save(update_fields=["status", "status_changed_at", "updated_at"])
        journaliser(request, "recommandation_statut", reco=reco.pk, statut=statut)
        messages.success(request, f"« {reco.titre} » : {reco.get_status_display().lower()}. "
                                  "AvisPilote suivra l'évolution des avis à partir d'aujourd'hui.")
    return redirect("insights:recommandations")


# --- Outils : QR code et simulateur -------------------------------------------

class LienAvisForm(forms.Form):
    lien = forms.CharField(label="Lien « Demander des avis » de ta fiche Google", max_length=500)

    def clean_lien(self):
        lien = self.cleaned_data["lien"].strip()
        outils.valider_lien_avis(lien)
        return lien


class SimulateurForm(forms.Form):
    cible = forms.DecimalField(label="Note visée", min_value=1, max_value=5, decimal_places=1, required=False)
    ajout = forms.IntegerField(label="Nombre de nouveaux avis", min_value=1, max_value=10000, required=False)
    etoiles = forms.TypedChoiceField(label="Étoiles", choices=[(n, f"{n} ★") for n in range(5, 0, -1)],
                                     coerce=int, required=False, empty_value=None)


@organisation_requise("voir")
def outils_vue(request):
    fiche = sync.fiche_active(request.organisation)
    if fiche is None:
        messages.info(request, "Connecte d'abord ta fiche (ou la démo).")
        return redirect("accounts:tableau_de_bord")
    form_lien = LienAvisForm(request.POST or None, initial={"lien": fiche.new_review_uri})
    if request.method == "POST":
        if not request.membership.peut("google"):
            raise PermissionDenied
        if form_lien.is_valid():
            fiche.new_review_uri = form_lien.cleaned_data["lien"]
            fiche.save(update_fields=["new_review_uri"])
            journaliser(request, "lien_avis_modifie")
            messages.success(request, "Lien enregistré : ton QR code est prêt.")
            return redirect("insights:outils")

    form_sim = SimulateurForm(request.GET or None)
    params = form_sim.cleaned_data if form_sim.is_valid() else {}
    if params.get("cible") is not None:
        cible = float(params["cible"])
    else:
        # Proposition par défaut : 0,2 au-dessus de la note affichée (plafonnée à 5).
        cible = round(min(5.0, outils.situation(fiche)["affichee"] + 0.2), 1)
    ajout = params.get("ajout")
    sim = outils.simuler(fiche, cible=cible, ajout=ajout, etoiles=(params.get("etoiles") or 5) if ajout else None)
    return render(request, "insights/outils.html", {
        "fiche": fiche, "form_lien": form_lien, "form_sim": form_sim, "sim": sim,
        "qr": outils.qr_svg(fiche.new_review_uri) if fiche.new_review_uri else None,
        "peut_modifier_lien": request.membership.peut("google"),
    })


@organisation_requise("voir")
def qr_telecharger(request, format_):
    fiche = sync.fiche_active(request.organisation)
    if fiche is None or not fiche.new_review_uri or format_ not in ("png", "svg"):
        raise Http404
    reponse = HttpResponse(outils.qr_fichier(fiche.new_review_uri, format_),
                           content_type="image/png" if format_ == "png" else "image/svg+xml")
    reponse["Content-Disposition"] = f'attachment; filename="qr-avis-google.{format_}"'  # nom fixe : pas d'injection
    return reponse


@organisation_requise("voir")
def qr_affiche(request):
    fiche = sync.fiche_active(request.organisation)
    if fiche is None or not fiche.new_review_uri:
        raise Http404
    return render(request, "insights/affiche_qr.html", {"fiche": fiche, "qr": outils.qr_svg(fiche.new_review_uri)})


# --- Rapports -------------------------------------------------------------------

class ReglagesRapportForm(forms.Form):
    rapport_email = forms.BooleanField(label="Recevoir le rapport par e-mail", required=False)
    rapport_frequence = forms.ChoiceField(label="Fréquence", choices=[("mois", "Chaque mois"), ("semaine", "Chaque semaine")])


def _choix_periode(request):
    type_ = request.GET.get("type") if request.GET.get("type") in rapports.TYPES else "mois"
    try:
        decalage = min(max(int(request.GET.get("decalage", 1)), 1), 12)
    except ValueError:
        decalage = 1
    return type_, decalage


@organisation_requise("voir")
@require_http_methods(["GET", "POST"])
def rapports_vue(request):
    fiche = sync.fiche_active(request.organisation)
    if fiche is None:
        messages.info(request, "Connecte d'abord ta fiche (ou la démo).")
        return redirect("accounts:tableau_de_bord")
    org = request.organisation
    form = ReglagesRapportForm(request.POST or None, initial={"rapport_email": org.rapport_email,
                                                             "rapport_frequence": org.rapport_frequence})
    if request.method == "POST":
        if not request.membership.peut("abonnement"):
            raise PermissionDenied
        if form.is_valid():
            org.rapport_email = form.cleaned_data["rapport_email"]
            org.rapport_frequence = form.cleaned_data["rapport_frequence"]
            org.save(update_fields=["rapport_email", "rapport_frequence"])
            messages.success(request, "Préférences des rapports enregistrées.")
            return redirect("insights:rapports")
    autorise = org.subscription.a_la_fonction("rapports")
    type_, decalage = _choix_periode(request)
    r = rapports.construire(fiche, type_, decalage) if autorise else None
    periodes = [(i, rapports.bornes(type_, i)[3]) for i in range(1, 7 if type_ == "mois" else 9)]
    return render(request, "insights/rapports.html", {
        "fiche": fiche, "r": r, "bilan": rapports.phrase_bilan(r) if r else "", "autorise": autorise,
        "type": type_, "decalage": decalage, "periodes": periodes, "types": rapports.TYPES, "form": form,
        "peut_regler": request.membership.peut("abonnement"),
    })


@organisation_requise("voir")
def rapport_pdf_vue(request):
    fiche = sync.fiche_active(request.organisation)
    if fiche is None or not request.organisation.subscription.a_la_fonction("rapports"):
        raise Http404
    type_, decalage = _choix_periode(request)
    r = rapports.construire(fiche, type_, decalage)
    reponse = HttpResponse(rapport_pdf.generer(r), content_type="application/pdf")
    reponse["Content-Disposition"] = f'attachment; filename="rapport-{type_}-{r["debut"]:%Y-%m-%d}.pdf"'
    return reponse


@organisation_requise("abonnement")
@require_POST
def rapport_envoyer(request):
    """Envoi manuel au gérant. Limité à 3 par heure (évite d'utiliser l'appli pour spammer)."""
    fiche = sync.fiche_active(request.organisation)
    if fiche is None or not request.organisation.subscription.a_la_fonction("rapports"):
        raise Http404
    cle = f"envoi-rapport:{request.organisation.pk}"
    if cache.get(cle, 0) >= 3:
        messages.error(request, "Trop d'envois en une heure. Réessaie plus tard.")
        return redirect("insights:rapports")
    cache.set(cle, cache.get(cle, 0) + 1, 3600)
    type_, decalage = _choix_periode(request)
    n = envoi.envoyer(fiche, rapports.construire(fiche, type_, decalage))
    journaliser(request, "rapport_envoye", type=type_)
    messages.success(request, f"Rapport envoyé à {n} adresse{'s' if n > 1 else ''} (gérant).")
    return redirect(f"{reverse('insights:rapports')}?type={type_}&decalage={decalage}")
