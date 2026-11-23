"""Avis : liste, validation / modification / publication des réponses, réglages de l'assistant."""
import re
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.permissions import organisation_requise
from audit.models import journaliser
from locations import google_client, sync

from . import exemples, traitement
from .ia import claude, sensible
from .models import AISettings, Mode, ReplyDraft, Review

PERIODES = {"7j": 7, "30j": 30, "3m": 91, "6m": 182, "1an": 365, "tout": None}
STATUTS = {
    "tous": "Tous",
    "a_valider": "À valider",
    "sans_reponse": "Sans réponse",
    "sensibles": "Sensibles",
    "negatifs": "1-2 étoiles",
    "hors_quota": "Hors quota",
}


def avis_de_l_organisation(request):
    """Point unique d'accès aux avis : toujours filtré par l'organisation connectée."""
    return Review.objects.filter(location__organization=request.organisation)


class ReponseForm(forms.Form):
    texte = forms.CharField(max_length=4000, min_length=2, strip=True)


@organisation_requise("voir")
def liste(request):
    fiche = sync.fiche_active(request.organisation)
    qs = avis_de_l_organisation(request).filter(location=fiche) if fiche else Review.objects.none()

    # Filtres : on n'accepte que des valeurs connues (le reste revient à la valeur par défaut).
    periode = request.GET.get("periode") if request.GET.get("periode") in PERIODES else "30j"
    statut = request.GET.get("statut") if request.GET.get("statut") in STATUTS else "tous"
    etoiles = request.GET.get("etoiles") if request.GET.get("etoiles") in {"1", "2", "3", "4", "5"} else ""
    if PERIODES[periode]:
        qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=PERIODES[periode]))
    if statut == "a_valider":
        qs = qs.filter(google_reply="", drafts__status=ReplyDraft.Statut.A_VALIDER).distinct()
    elif statut == "sans_reponse":
        qs = qs.filter(google_reply="")
    elif statut == "sensibles":
        qs = qs.exclude(analysis__sensitive_flags=[]).filter(analysis__isnull=False)
    elif statut == "negatifs":
        qs = qs.filter(stars__lte=2)
    elif statut == "hors_quota":
        qs = qs.filter(ai_status=Review.StatutIA.HORS_QUOTA)
    if etoiles:
        qs = qs.filter(stars=int(etoiles))

    page = Paginator(qs.select_related("analysis").prefetch_related("drafts"), 20).get_page(request.GET.get("page"))
    for avis in page:
        avis.brouillon = next(iter(avis.drafts.all()), None)  # le plus récent (tri par date décroissante)
        analyse = getattr(avis, "analysis", None)
        avis.sensibles = sensible.libelles(analyse.sensitive_flags) if analyse else []
    return render(request, "reviews/liste.html", {
        "fiche": fiche, "page": page,
        "periodes": PERIODES, "statuts": STATUTS, "filtres": {"periode": periode, "statut": statut, "etoiles": etoiles},
        "peut_repondre": request.membership.peut("repondre"),
        "a_valider": (avis_de_l_organisation(request).filter(location=fiche, google_reply="",
                      drafts__status=ReplyDraft.Statut.A_VALIDER).distinct().count() if fiche else 0),
    })


@organisation_requise("repondre")
@require_POST
def repondre(request, avis_id):
    """Publie le texte envoyé (proposition de l'IA, éventuellement modifiée, ou réponse écrite à la main)."""
    avis = get_object_or_404(avis_de_l_organisation(request).select_related("location__organization"), pk=avis_id)
    form = ReponseForm(request.POST)
    if not form.is_valid():
        messages.error(request, "La réponse doit faire entre 2 et 4000 caractères.")
        return redirect("reviews:liste")
    texte = form.cleaned_data["texte"]
    propose = avis.drafts.filter(source="ia").first()
    source = "ia" if propose and propose.text.strip() == texte else "humain"
    brouillon = ReplyDraft.objects.create(review=avis, text=texte, source=source, created_by=request.user,
                                          status=ReplyDraft.Statut.BROUILLON, decision=Mode.VALIDATION)
    if avis.location.is_demo:
        messages.info(request, "Démonstration : réponse validée et enregistrée, mais rien n'est publié sur Google.")
        return redirect("reviews:liste")
    try:
        traitement.publier(brouillon, request.user)
    except google_client.GoogleErreur as e:
        messages.error(request, str(e))
        return redirect("reviews:liste")
    journaliser(request, "reponse_publiee", avis=avis.pk, source=source)
    messages.success(request, "Réponse publiée sur Google.")
    return redirect("reviews:liste")


@organisation_requise("repondre")
@require_POST
def regenerer(request, avis_id):
    avis = get_object_or_404(avis_de_l_organisation(request).select_related("location__organization"), pk=avis_id)
    try:
        traitement.regenerer(avis, request.user)
        messages.success(request, "Nouvelle proposition de réponse.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("reviews:liste")


class ReglagesForm(forms.ModelForm):
    """Réglages de l'assistant. Les modes par note sont des champs séparés (validés côté serveur)."""

    class Meta:
        model = AISettings
        fields = ["tone", "length", "tutoiement", "emojis", "signature", "business_info", "preferred_phrases",
                  "forbidden_phrases", "negative_instructions", "sensitive_requires_validation"]
        widgets = {f: forms.Textarea(attrs={"rows": 3}) for f in
                   ["business_info", "preferred_phrases", "forbidden_phrases", "negative_instructions"]}
        help_texts = {**exemples.AIDE,
                      "sensitive_requires_validation": "Hygiène, menace juridique, remboursement, accusation, agressivité."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for n in range(5, 0, -1):
            self.fields[f"mode_{n}"] = forms.ChoiceField(
                label=f"Avis {n} ★", choices=Mode.choices, initial=self.instance.mode_pour(n))

    def clean(self):
        donnees = super().clean()
        # Un exemple enregistré tel quel ferait écrire « [numéro] » dans une réponse publique.
        for champ in exemples.AIDE:
            if re.search(r"\[[^\]]+\]", donnees.get(champ) or ""):
                self.add_error(champ, "Remplace les éléments entre [crochets] par tes vraies informations.")
        return donnees

    def save(self, commit=True):
        self.instance.mode_by_stars = {str(n): self.cleaned_data[f"mode_{n}"] for n in range(1, 6)}
        return super().save(commit)


@organisation_requise("regler_ia")
@require_http_methods(["GET", "POST"])
def assistant(request):
    fiche = sync.fiche_active(request.organisation)
    if fiche is None:
        messages.info(request, "Connecte d'abord ta fiche (ou la démo) pour régler l'assistant.")
        return redirect("accounts:tableau_de_bord")
    reglages = traitement.reglages_de(fiche)
    ex = exemples.pour(fiche.sector)
    initial = {}
    if request.method == "GET" and request.GET.get("exemples") == "1":
        # Pré-remplit seulement les champs vides ; rien n'est enregistré avant « Enregistrer ».
        initial = {champ: texte for champ, texte in ex.items() if not getattr(reglages, champ)}
        messages.info(request, "Exemples insérés dans les champs vides : relis-les, remplace les [crochets] "
                               "par tes informations, puis clique sur Enregistrer.")
    form = ReglagesForm(request.POST or None, instance=reglages, initial=initial)
    if request.method == "POST" and form.is_valid():
        form.save()
        journaliser(request, "assistant_regle")
        messages.success(request, "Réglages de l'assistant enregistrés. Ils s'appliquent aux prochains avis.")
        return redirect("reviews:assistant")
    return render(request, "reviews/assistant.html", {
        "form": form, "fiche": fiche,
        "champs_modes": [form[f"mode_{n}"] for n in range(5, 0, -1)],
        "champs_textes": [(form[f], ex[f]) for f in ["business_info", "preferred_phrases", "forbidden_phrases",
                                                     "negative_instructions"]],
        "moteur": "Claude" if claude.est_disponible() else "moteur de règles intégré (gratuit)",
    })
