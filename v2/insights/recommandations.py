"""Recommandations concrètes, justifiées par les avis, et suivies dans le temps.

Le cycle (cahier des charges, section 6) :
1. repérer un défaut qui revient (≥ 3 avis sur 30 jours) ;
2. le comparer aux 30 jours d'avant ;
3. créer (ou mettre à jour) UNE recommandation par thème, avec importance, preuves et actions ;
4. le commerçant la passe « En cours » quand il agit : la date sert de point de départ ;
5. suivi : combien d'avis parlent encore du problème depuis, contre la même durée avant ;
6. un problème « Résolu » qui revient (≥ 3 nouveaux avis) rouvre une nouvelle recommandation.
On propose aussi de valoriser le point fort le plus cité.
"""
from collections import Counter
from datetime import timedelta

from django.utils import timezone

from reviews.ia import regles

from .models import Recommendation
from .stats import MOIS, QUALITE_PAR_SECTEUR

FENETRE = timedelta(days=30)
MINIMUM = 3

ACTIONS_VALORISER = [
    "Le mettre en avant sur ta fiche Google (photos, description) et en boutique.",
    "Le citer dans tes réponses aux avis et sur tes réseaux sociaux.",
    "En parler à l'équipe : c'est ce que les clients apprécient le plus, à garder au même niveau.",
]


def _avis_avec_theme(fiche, debut, fin, champ, theme):
    qs = fiche.reviews.filter(created_at__gte=debut, created_at__lt=fin, analysis__isnull=False).select_related("analysis")
    return [a for a in qs if theme in getattr(a.analysis, champ)]


def _compter(fiche, debut, fin, champ):
    c = Counter()
    for valeurs in (fiche.reviews.filter(created_at__gte=debut, created_at__lt=fin, analysis__isnull=False)
                    .values_list(f"analysis__{champ}", flat=True)):
        c.update(set(valeurs or []))
    return c


def _importance(n, part, preuves):
    if n >= 5 or part >= 20 or any(a.stars == 1 for a in preuves):
        return Recommendation.Importance.HAUTE
    return Recommendation.Importance.MOYENNE


def generer(fiche, maintenant=None):
    """Crée ou met à jour les recommandations. Renvoie la liste des recommandations nouvelles."""
    maintenant = maintenant or timezone.now()
    debut = maintenant - FENETRE
    total = fiche.reviews.filter(created_at__gte=debut, analysis__isnull=False).count() or 1
    nouvelles = []

    actuels = _compter(fiche, debut, maintenant, "themes_negatifs")
    avant = _compter(fiche, debut - FENETRE, debut, "themes_negatifs")
    for theme, n in actuels.items():
        if n < MINIMUM:
            continue
        existante = (Recommendation.objects.filter(location=fiche, theme=theme, type=Recommendation.Type.CORRIGER)
                     .order_by("-created_at").first())
        preuves = _avis_avec_theme(fiche, debut, maintenant, "themes_negatifs", theme)
        if existante and existante.status == Recommendation.Statut.RESOLUE:
            # Rouvrir seulement si le problème revient APRÈS la résolution.
            apres = [a for a in preuves if a.created_at > existante.status_changed_at]
            if len(apres) < MINIMUM:
                continue
            existante, preuves = None, apres
        part = round(100 * n / total)
        evolution = n - avant.get(theme, 0)
        tendance = (f"en hausse ({avant.get(theme, 0)} le mois d'avant)" if evolution > 0
                    else f"stable ou en baisse ({avant.get(theme, 0)} le mois d'avant)")
        valeurs = {
            "titre": regles.THEMES[theme]["defaut"],
            "problem": f"{n} avis sur 30 jours ({part} % des avis analysés) signalent ce problème, {tendance}.",
            "evidence_review_ids": [a.pk for a in preuves][:10],
            "importance": _importance(n, part, preuves),
            "actions": regles.solutions_pour(theme, fiche.sector)[:3],
        }
        if existante:
            for k, v in valeurs.items():
                setattr(existante, k, v)
            existante.save()
        else:
            nouvelles.append(Recommendation.objects.create(location=fiche, theme=theme, **valeurs))

    # Point fort à valoriser : le plus cité, s'il l'est assez.
    forts = _compter(fiche, debut, maintenant, "themes_positifs").most_common(1)
    if forts and forts[0][1] >= 5:
        theme, n = forts[0]
        nom = QUALITE_PAR_SECTEUR.get(fiche.sector, regles.THEMES[theme]["qualite"]) if theme == "qualite" \
            else regles.THEMES[theme]["qualite"]
        preuves = _avis_avec_theme(fiche, debut, maintenant, "themes_positifs", theme)
        _, cree = Recommendation.objects.update_or_create(
            location=fiche, type=Recommendation.Type.VALORISER, status__in=[Recommendation.Statut.OUVERTE,
                                                                             Recommendation.Statut.EN_COURS],
            defaults={"theme": theme, "titre": f"Mettre en avant : {nom.lower()}",
                      "problem": f"C'est ton point fort le plus cité : {n} avis sur 30 jours.",
                      "evidence_review_ids": [a.pk for a in preuves][:10],
                      "importance": Recommendation.Importance.BASSE, "actions": ACTIONS_VALORISER},
        )
    return nouvelles


def suivi(reco, maintenant=None):
    """Effet des actions : avis qui citent le thème depuis la mise « En cours », vs la même durée avant."""
    if reco.type != Recommendation.Type.CORRIGER or not reco.status_changed_at:
        return None
    maintenant = maintenant or timezone.now()
    duree = max(maintenant - reco.status_changed_at, timedelta(days=1))
    depuis = len(_avis_avec_theme(reco.location, reco.status_changed_at, maintenant, "themes_negatifs", reco.theme))
    avant = len(_avis_avec_theme(reco.location, reco.status_changed_at - duree, reco.status_changed_at,
                                 "themes_negatifs", reco.theme))
    d = reco.status_changed_at
    if depuis < avant:
        tendance = "amelioration"
    elif depuis > avant:
        tendance = "degradation"
    else:
        tendance = "stable"
    return {"depuis": depuis, "avant": avant, "tendance": tendance, "jours": duree.days,
            "date": f"{d.day} {MOIS[d.month - 1]}"}
