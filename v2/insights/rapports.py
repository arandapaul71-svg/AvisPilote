"""Rapports périodiques : contenu commun à la page web, au PDF et à l'e-mail.

Un rapport couvre un mois civil ou une semaine (lundi → dimanche) TERMINÉS, et se
compare à la période précédente de même type.
"""
from datetime import datetime, time, timedelta

from django.utils import timezone

from . import recommandations, stats
from .models import Alert, Recommendation

MOIS_LONGS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
              "octobre", "novembre", "décembre"]
TYPES = {"mois": "Rapport mensuel", "semaine": "Rapport hebdomadaire"}


def _minuit(d):
    return timezone.make_aware(datetime.combine(d, time.min))


def bornes(type_, decalage=1, maintenant=None):
    """(début, fin, début précédent, titre) de la période terminée n° `decalage` (1 = la dernière)."""
    aujourd_hui = timezone.localtime(maintenant or timezone.now()).date()
    if type_ == "semaine":
        lundi = aujourd_hui - timedelta(days=aujourd_hui.weekday()) - timedelta(weeks=decalage)
        debut, fin, precedent = lundi, lundi + timedelta(weeks=1), lundi - timedelta(weeks=1)
        dimanche = fin - timedelta(days=1)
        titre = f"Semaine du {lundi.day} {MOIS_LONGS[lundi.month - 1]} au {dimanche.day} {MOIS_LONGS[dimanche.month - 1]} {dimanche.year}"
    else:
        premier = aujourd_hui.replace(day=1)
        for _ in range(decalage):
            premier = (premier - timedelta(days=1)).replace(day=1)
        debut = premier
        fin = (premier.replace(day=28) + timedelta(days=4)).replace(day=1)
        precedent = (premier - timedelta(days=1)).replace(day=1)
        titre = f"{MOIS_LONGS[premier.month - 1].capitalize()} {premier.year}"
    return _minuit(debut), _minuit(fin), _minuit(precedent), titre


def construire(fiche, type_="mois", decalage=1, maintenant=None):
    type_ = type_ if type_ in TYPES else "mois"
    debut, fin, precedent, titre = bornes(type_, decalage, maintenant)
    plage = (debut, fin, precedent)
    ind = stats.indicateurs(fiche, None, plage=plage)
    ff = stats.forces_faiblesses(fiche, None, plage=plage)
    alertes = list(Alert.objects.filter(location=fiche, created_at__gte=debut, created_at__lt=fin)
                   .order_by("created_at"))
    ordre = {"haute": 0, "moyenne": 1, "basse": 2}
    recos = sorted(Recommendation.objects.filter(location=fiche).exclude(status=Recommendation.Statut.RESOLUE),
                   key=lambda r: (r.type != Recommendation.Type.CORRIGER, ordre.get(r.importance, 3)))
    for r in recos:
        r.suivi = recommandations.suivi(r, fin)
    resolues = list(Recommendation.objects.filter(location=fiche, status=Recommendation.Statut.RESOLUE,
                                                  status_changed_at__gte=debut, status_changed_at__lt=fin))
    return {
        "type": type_, "type_nom": TYPES[type_], "titre": titre, "debut": debut, "fin": fin,
        "fiche": fiche, "ind": ind, "ff": ff, "alertes": alertes, "recos": recos, "resolues": resolues,
        "repartition": stats.repartition_etoiles(fiche, None, plage=plage),
        "genere_le": timezone.localtime(maintenant or timezone.now()),
    }


def phrase_bilan(r):
    """Une phrase de synthèse en tête de rapport."""
    ind = r["ind"]
    if not ind["total"]:
        return "Aucun avis reçu sur cette période."
    morceaux = [f"{ind['total']} avis reçus"]
    if ind["total_delta"]:
        morceaux[0] += f" ({'+' if ind['total_delta'] > 0 else ''}{ind['total_delta']} par rapport à la période précédente)"
    if ind["note_periode"] is not None:
        note = f"{ind['note_periode']:.2f}".replace(".", ",")
        morceaux.append(f"note moyenne de {note} ★")
    if r["ff"]["qualite"]:
        morceaux.append(f"point fort : {r['ff']['qualite'][0]['nom'].lower()}")
    if r["ff"]["defaut"]:
        morceaux.append(f"à surveiller : {r['ff']['defaut'][0]['nom'].lower()}")
    phrase = ", ".join(morceaux) + "."
    return phrase[0].upper() + phrase[1:]
