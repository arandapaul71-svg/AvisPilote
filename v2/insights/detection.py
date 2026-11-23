"""Détection d'anomalies dans les avis → alertes sur le tableau de bord.

Fonction différenciante d'AvisPilote : repérer un problème AVANT qu'il abîme la note.

Pour éviter les fausses alertes (un petit commerce reçoit peu d'avis), chaque règle
exige à la fois un MINIMUM d'avis concernés ET un ÉCART net avec l'habitude :
- hausse_negatifs : ≥ 3 avis 1-2★ sur 7 jours ET ≥ 2× la moyenne hebdomadaire des 8 semaines d'avant ;
- plainte_recurrente : un même défaut dans ≥ 3 avis sur 14 jours ET ≥ 2× son rythme habituel ;
- baisse_note / amelioration : ≥ 5 avis sur 14 jours (dont ≥ 3 négatifs / ≥ 5 positifs) ET écart ≥ 0,5★
  avec les 60 jours d'avant (≥ 5 avis) ;
- pic_avis : un jour avec ≥ 4 avis ET ≥ 2,5× la moyenne quotidienne des 30 jours d'avant.
Une alerte n'est jamais recréée en double (même type + même clé dans les 7 derniers jours).
"""
from collections import Counter
from datetime import timedelta

from django.utils import timezone

from reviews.ia import regles

from .models import Alert
from .stats import MOIS, _extrait

SEMAINE = timedelta(days=7)


def _nom_defaut(theme):
    return regles.THEMES[theme]["defaut"].lower()


def _date_fr(d):
    return f"{d.day} {MOIS[d.month - 1]}"


def _avis(fiche, debut, fin):
    return list(fiche.reviews.filter(created_at__gte=debut, created_at__lt=fin)
                .select_related("analysis").order_by("-created_at"))


def _defauts(avis):
    c = Counter()
    for a in avis:
        analyse = getattr(a, "analysis", None)
        if analyse:
            c.update(set(analyse.themes_negatifs))
    return c


def _moyenne(avis):
    return sum(a.stars for a in avis) / len(avis) if avis else None


def _creer(fiche, kind, cle, niveau, message, details, preuves):
    """Crée l'alerte sauf si la même (type + clé) existe déjà depuis moins de 7 jours."""
    if Alert.objects.filter(location=fiche, kind=kind, cle=cle,
                            created_at__gte=timezone.now() - SEMAINE).exists():
        return None
    return Alert.objects.create(location=fiche, kind=kind, cle=cle, niveau=niveau, message=message,
                                details=details, evidence_review_ids=[a.pk for a in preuves][:10])


def hausse_negatifs(fiche, maintenant):
    recents = [a for a in _avis(fiche, maintenant - SEMAINE, maintenant) if a.stars <= 2]
    avant = [a for a in _avis(fiche, maintenant - 9 * SEMAINE, maintenant - SEMAINE) if a.stars <= 2]
    habituel = len(avant) / 8
    if len(recents) < 3 or len(recents) < 2 * max(habituel, 0.5):
        return None
    message = (f"Attention : tu as reçu {len(recents)} avis négatifs cette semaine, contre "
               f"{_arrondi(habituel)} habituellement.")
    themes = [t for t, n in _defauts(recents).most_common(2) if n >= 2]
    if themes:
        message += f" Plusieurs clients parlent de : {', '.join(_nom_defaut(t) for t in themes)}."
    return _creer(fiche, "hausse_negatifs", maintenant.strftime("%G-%V"), Alert.Niveau.ATTENTION, message,
                  {"periode": len(recents), "habituel": round(habituel, 1)}, recents)


def _arrondi(x):
    return str(int(round(x))) if abs(x - round(x)) < 0.05 else f"{x:.1f}".replace(".", ",")


def plaintes_recurrentes(fiche, maintenant):
    recents = _avis(fiche, maintenant - 2 * SEMAINE, maintenant)
    avant = _avis(fiche, maintenant - 10 * SEMAINE, maintenant - 2 * SEMAINE)
    c_recent, c_avant = _defauts(recents), _defauts(avant)
    alertes = []
    for theme, n in c_recent.items():
        habituel = c_avant.get(theme, 0) / 4  # même durée (2 semaines) sur 8 semaines d'historique
        if n < 3 or n < 2 * max(habituel, 0.5):
            continue
        preuves = [a for a in recents if getattr(a, "analysis", None) and theme in a.analysis.themes_negatifs]
        exemple = next((_extrait(a.comment, 120) for a in preuves if a.comment), "")
        message = (f"Plainte qui revient : {n} clients mentionnent « {_nom_defaut(theme)} » ces 14 derniers jours "
                   f"(habituellement {_arrondi(habituel)}).")
        if exemple:
            message += f" Exemple : « {exemple} »"
        alerte = _creer(fiche, "plainte_recurrente", theme, Alert.Niveau.ATTENTION, message,
                        {"theme": theme, "periode": n, "habituel": round(habituel, 1)}, preuves)
        if alerte:
            alertes.append(alerte)
    return alertes


def evolution_note(fiche, maintenant):
    recents = _avis(fiche, maintenant - 2 * SEMAINE, maintenant)
    avant = _avis(fiche, maintenant - 2 * SEMAINE - timedelta(days=60), maintenant - 2 * SEMAINE)
    if len(recents) < 5 or len(avant) < 5:
        return None
    m_recent, m_avant = _moyenne(recents), _moyenne(avant)
    ecart = m_recent - m_avant
    details = {"recente": round(m_recent, 2), "avant": round(m_avant, 2), "nb": len(recents)}
    # « Plusieurs avis vont dans le même sens » : au moins 3 avis négatifs (ou positifs) récents.
    if ecart <= -0.5 and sum(a.stars <= 2 for a in recents) >= 3:
        return _creer(fiche, "baisse_note", maintenant.strftime("%G-%V"), Alert.Niveau.ATTENTION,
                      f"Baisse inhabituelle de la note : {_arrondi(m_recent)}★ en moyenne sur les {len(recents)} "
                      f"derniers avis (14 jours), contre {_arrondi(m_avant)}★ avant.",
                      details, [a for a in recents if a.stars <= 2])
    if ecart >= 0.5 and sum(a.stars >= 4 for a in recents) >= 5:
        return _creer(fiche, "amelioration", maintenant.strftime("%G-%V"), Alert.Niveau.POSITIF,
                      f"Bonne nouvelle : la satisfaction remonte, {_arrondi(m_recent)}★ en moyenne sur les "
                      f"{len(recents)} derniers avis, contre {_arrondi(m_avant)}★ avant.",
                      details, [a for a in recents if a.stars >= 4])
    return None


def pics(fiche, maintenant, jours=30):
    """Jours d'affluence inhabituelle : événement qui a plu, ou problème ce jour-là."""
    debut = maintenant - timedelta(days=jours + 30)
    par_jour = {}
    for a in _avis(fiche, debut, maintenant):
        par_jour.setdefault(timezone.localtime(a.created_at).date(), []).append(a)
    alertes = []
    aujourd_hui = timezone.localtime(maintenant).date()
    for decalage in range(jours, -1, -1):
        jour = aujourd_hui - timedelta(days=decalage)
        avis_jour = par_jour.get(jour, [])
        if len(avis_jour) < 4:
            continue
        precedents = sum(len(par_jour.get(jour - timedelta(days=k), [])) for k in range(1, 31)) / 30
        if len(avis_jour) < 2.5 * max(precedents, 0.5):
            continue
        note = _moyenne(avis_jour)
        if note >= 4:
            niveau, sens = Alert.Niveau.POSITIF, "probablement un événement qui a attiré et plu"
        elif note <= 2.5:
            niveau, sens = Alert.Niveau.ATTENTION, "probablement un problème ce jour-là"
        else:
            niveau, sens = Alert.Niveau.INFO, "affluence inhabituelle, avis partagés"
        message = (f"Pic d'avis le {_date_fr(jour)} : {len(avis_jour)} avis (habituellement {_arrondi(precedents)} "
                   f"par jour), note moyenne {_arrondi(note)}★ — {sens}.")
        defauts = _defauts(avis_jour).most_common(1)
        if note <= 3 and defauts and defauts[0][1] >= 2:
            message += f" Sujet principal : {_nom_defaut(defauts[0][0])}."
        alerte = _creer(fiche, "pic_avis", jour.isoformat(), niveau, message,
                        {"jour": jour.isoformat(), "nombre": len(avis_jour), "habituel": round(precedents, 1),
                         "note": round(note, 2)}, avis_jour)
        if alerte:
            alertes.append(alerte)
    return alertes


def analyser(fiche, maintenant=None):
    """Lance toutes les règles. Renvoie la liste des nouvelles alertes."""
    maintenant = maintenant or timezone.now()
    nouvelles = [hausse_negatifs(fiche, maintenant), evolution_note(fiche, maintenant)]
    nouvelles += plaintes_recurrentes(fiche, maintenant) + pics(fiche, maintenant)
    return [a for a in nouvelles if a]
