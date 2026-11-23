"""Traitement IA des avis : quota → analyse → brouillon → contrôle → publication ou validation.

Règles importantes :
- Seuls les avis des 30 derniers jours sont traités (pas de consommation du quota sur l'historique).
- Un avis hors quota reste stocké et consultable, sans analyse ni brouillon.
- Publication automatique UNIQUEMENT si : mode « auto » pour cette note, avis reçu après la
  connexion de la fiche, avis non sensible (si l'option est active), contrôle qualité réussi,
  et vraie fiche Google (jamais en démo).
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from billing import quotas
from locations import google_client

from .ia import claude, controle, redaction, regles, sensible
from .models import AISettings, Mode, ReplyDraft, Review, ReviewAnalysis

log = logging.getLogger("avispilote")
FENETRE_TRAITEMENT = timedelta(days=30)
MAX_REGENERATIONS = 3


def reglages_de(location):
    """Réglages enregistrés, ou réglages par défaut (non enregistrés) s'il n'y en a pas encore."""
    try:
        return location.ai_settings
    except AISettings.DoesNotExist:
        return AISettings(location=location)


def _analyser_et_rediger(avis, reglages, organisation, variante=0):
    """Claude si disponible, sinon (ou en cas d'erreur) le moteur de règles.
    `variante` change la formulation du moteur de règles (bouton « Autre proposition »)."""
    sensibles_regles = sensible.detecter(avis.comment)
    if claude.est_disponible():
        try:
            d = claude.analyser_et_rediger(avis, reglages, organisation)
            signature = reglages.signature.strip() or f"L'équipe {organisation.name}"
            return {
                "sentiment": d["sentiment"], "positifs": d["themes_positifs"], "negatifs": d["themes_negatifs"],
                # Union : la détection par mots-clés reste active même si l'IA ne voit rien.
                "sensibles": sorted(set(d["sensible"]) | set(sensibles_regles)),
                "texte": d["reponse"].strip() + "\n\n" + signature,
                "actions": [a for a in d["actions"] if a.strip()][:3],
                "source": settings.ANTHROPIC_MODEL[:40],
            }
        except Exception:  # noqa: BLE001 - toute panne de l'IA → repli, jamais d'avis bloqué
            log.exception("Analyse Claude impossible pour l'avis %s", avis.pk)
    positifs, negatifs = regles.analyser_regles(avis.comment, avis.stars)
    sentiment = "positif" if avis.stars >= 4 else "negatif" if avis.stars <= 2 else "neutre"
    return {
        "sentiment": sentiment, "positifs": positifs, "negatifs": negatifs, "sensibles": sensibles_regles,
        "texte": redaction.rediger(avis, reglages, organisation, positifs, negatifs, variante),
        "actions": redaction.actions_pour(avis.stars, negatifs, organisation.sector),
        "source": "regles",
    }


def _reponses_precedentes(location, exclure_avis, signature):
    """Réponses déjà publiées (ou qui le seraient en démo), sans la signature commune."""
    textes = (ReplyDraft.objects.filter(review__location=location)
              .filter(Q(status=ReplyDraft.Statut.PUBLIEE) | Q(decision=Mode.AUTO))
              .exclude(review=exclure_avis).order_by("-created_at").values_list("text", flat=True)[:30])
    return [t.replace(signature, "").strip() for t in textes]


def _decider(avis, reglages, resultat, problemes):
    """Renvoie (mode, raisons) : pourquoi on publie ou pas automatiquement."""
    mode = reglages.mode_pour(avis.stars)
    if mode != Mode.AUTO:
        return mode, [f"Mode « {Mode(mode).label} » pour les avis {avis.stars}★."]
    raisons = []
    if reglages.sensitive_requires_validation and resultat["sensibles"]:
        raisons.append("Avis sensible : " + ", ".join(sensible.libelles(resultat["sensibles"])) + ".")
    if not avis.location.is_demo and avis.created_at < avis.location.created_at:
        raisons.append("Avis antérieur à la connexion de la fiche : pas de publication automatique.")
    raisons += problemes
    return (Mode.VALIDATION, raisons) if raisons else (Mode.AUTO, [])


def publier(brouillon, utilisateur=None):
    """Publie un brouillon sur Google. En démo, rien n'est envoyé. Lève GoogleErreur en cas d'échec."""
    avis = brouillon.review
    fiche = avis.location
    if fiche.is_demo:
        raise ValueError("Une fiche de démonstration ne publie jamais sur Google.")
    google_client.publier_reponse(fiche.organization.google, fiche.google_location_name,
                                  avis.google_review_id, brouillon.text)
    maintenant = timezone.now()
    brouillon.status, brouillon.published_at = ReplyDraft.Statut.PUBLIEE, maintenant
    brouillon.save(update_fields=["status", "published_at"])
    avis.google_reply, avis.google_reply_at = brouillon.text, maintenant
    avis.save(update_fields=["google_reply", "google_reply_at"])


def creer_brouillon(avis, reglages, resultat, utilisateur=None):
    signature = reglages.signature.strip() or f"L'équipe {avis.location.organization.name}"
    problemes = controle.controler(resultat["texte"].replace(signature, "").strip(), avis, reglages,
                                   _reponses_precedentes(avis.location, avis, signature),
                                   themes=resultat["positifs"] + resultat["negatifs"])
    decision, raisons = _decider(avis, reglages, resultat, problemes)
    if decision == Mode.MANUEL:
        return None
    statut = ReplyDraft.Statut.A_VALIDER
    if decision == Mode.AUTO and avis.location.is_demo:
        statut = ReplyDraft.Statut.BROUILLON  # « serait publiée automatiquement » : affiché comme tel
    return ReplyDraft.objects.create(review=avis, text=resultat["texte"], source="ia", status=statut,
                                     quality_checks=problemes, decision=decision, reasons=raisons,
                                     created_by=utilisateur)


def traiter_avis(avis, sub, reglages):
    """Traite un avis. Renvoie True s'il a consommé une unité de quota."""
    if not quotas.consommer(sub, avis.stars):
        if sub.est_utilisable:
            avis.ai_status = Review.StatutIA.HORS_QUOTA
            avis.save(update_fields=["ai_status"])
        return False
    resultat = _analyser_et_rediger(avis, reglages, avis.location.organization)
    with transaction.atomic():
        ReviewAnalysis.objects.update_or_create(review=avis, defaults={
            "sentiment": resultat["sentiment"], "themes_positifs": resultat["positifs"],
            "themes_negatifs": resultat["negatifs"], "sensitive_flags": resultat["sensibles"],
            "actions": resultat["actions"], "source": resultat["source"],
        })
        avis.ai_status = Review.StatutIA.TRAITE
        avis.save(update_fields=["ai_status"])
        brouillon = None if avis.google_reply else creer_brouillon(avis, reglages, resultat)
    if brouillon and brouillon.decision == Mode.AUTO and brouillon.status == ReplyDraft.Statut.A_VALIDER:
        try:
            publier(brouillon)
        except google_client.GoogleErreur as e:
            brouillon.decision = Mode.VALIDATION
            brouillon.reasons = [f"Publication automatique impossible : {e}"]
            brouillon.save(update_fields=["decision", "reasons"])
    return True


def traiter_en_attente(location):
    """Traite les avis récents pas encore traités, du plus ancien au plus récent. Renvoie le nombre traité."""
    sub = location.organization.subscription
    if not sub.est_utilisable:
        return 0
    reglages = reglages_de(location)
    a_traiter = (location.reviews.filter(ai_status=Review.StatutIA.NON_TRAITE,
                                         created_at__gte=timezone.now() - FENETRE_TRAITEMENT)
                 .select_related("location__organization").order_by("created_at"))
    traites = sum(1 for avis in a_traiter if traiter_avis(avis, sub, reglages))
    analyser_historique(location)
    # Les analyses sont à jour : on cherche les anomalies et on met à jour les recommandations.
    from insights import detection, recommandations  # import local : insights dépend déjà de reviews
    detection.analyser(location)
    recommandations.generer(location)
    return traites


SOURCE_HISTORIQUE = "regles-historique"


def analyser_historique(location):
    """Analyse des thèmes (règles, gratuite) des avis antérieurs à la fenêtre de traitement.

    Sans elle, la détection comparerait les avis récents à un historique jamais analysé
    (« habituellement 0 ») et inventerait des hausses. Elle ne rédige aucune réponse et
    ne consomme pas de quota ; les avis hors quota de la période en cours restent non analysés.
    """
    anciens = location.reviews.filter(analysis__isnull=True, ai_status=Review.StatutIA.NON_TRAITE,
                                      created_at__lt=timezone.now() - FENETRE_TRAITEMENT)
    nouvelles = []
    for avis in anciens.only("id", "comment", "stars"):
        positifs, negatifs = regles.analyser_regles(avis.comment, avis.stars)
        sentiment = "positif" if avis.stars >= 4 else "negatif" if avis.stars <= 2 else "neutre"
        nouvelles.append(ReviewAnalysis(review=avis, sentiment=sentiment, themes_positifs=positifs,
                                        themes_negatifs=negatifs, sensitive_flags=sensible.detecter(avis.comment),
                                        source=SOURCE_HISTORIQUE))
    ReviewAnalysis.objects.bulk_create(nouvelles, ignore_conflicts=True)
    return len(nouvelles)


def regenerer(avis, utilisateur):
    """Nouvelle proposition de réponse (ne consomme pas de quota, limitée à 3 par avis)."""
    if avis.ai_status != Review.StatutIA.TRAITE:
        raise ValueError("Cet avis n'a pas été traité par l'assistant (hors quota ou ancien).")
    if avis.drafts.filter(source="ia").count() > MAX_REGENERATIONS:
        raise ValueError(f"Maximum {MAX_REGENERATIONS} nouvelles propositions par avis.")
    reglages = reglages_de(avis.location)
    resultat = _analyser_et_rediger(avis, reglages, avis.location.organization, variante=avis.drafts.count())
    brouillon = creer_brouillon(avis, reglages, resultat, utilisateur)
    if brouillon and brouillon.decision == Mode.AUTO:
        # Une régénération est toujours relue par un humain avant publication.
        brouillon.decision, brouillon.status = Mode.VALIDATION, ReplyDraft.Statut.A_VALIDER
        brouillon.save(update_fields=["decision", "status"])
    return brouillon
