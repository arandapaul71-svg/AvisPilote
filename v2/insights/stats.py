"""Statistiques du tableau de bord et de la page Analyses.

Tout est calculé à partir des avis stockés de la fiche active, sur une période
choisie (7 jours → 1 an), avec comparaison à la période précédente de même durée.
"""
from collections import Counter
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.utils import timezone

from reviews.ia import regles
from reviews.models import Mode, ReplyDraft, Review, ReviewAnalysis

PERIODES = {
    "7j": {"jours": 7, "nom": "7 jours", "pas": "jour"},
    "30j": {"jours": 30, "nom": "30 jours", "pas": "jour"},
    "3m": {"jours": 91, "nom": "3 mois", "pas": "semaine"},
    "6m": {"jours": 182, "nom": "6 mois", "pas": "semaine"},
    "1an": {"jours": 365, "nom": "1 an", "pas": "mois"},
}
PERIODE_PAR_DEFAUT = "30j"
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]

# Libellé du thème « qualité » adapté au secteur (les autres thèmes sont communs).
QUALITE_PAR_SECTEUR = {
    "boulangerie": "Qualité des produits", "restaurant": "Qualité de la cuisine", "fleuriste": "Qualité des fleurs",
    "coiffeur": "Qualité des prestations", "hotel": "Qualité du séjour", "artisan": "Qualité du travail",
}


def periode_valide(cle):
    return cle if cle in PERIODES else PERIODE_PAR_DEFAUT


def bornes(cle, maintenant=None):
    maintenant = maintenant or timezone.now()
    jours = PERIODES[cle]["jours"]
    debut = maintenant - timedelta(days=jours)
    return debut, maintenant, debut - timedelta(days=jours)


def _a_repondu(fiche):
    """Avis considéré comme « répondu ». En démo : réponse validée ou qui serait publiée (rien n'est publié)."""
    q = ~Q(google_reply="")
    if fiche.is_demo:
        q |= Q(drafts__status=ReplyDraft.Statut.BROUILLON)
    return q


def _moyenne(qs):
    m = qs.aggregate(m=Avg("stars"))["m"]
    return round(m, 2) if m is not None else None


def _delta(actuel, precedent):
    if actuel is None or precedent is None:
        return None
    return round(actuel - precedent, 2)


def indicateurs(fiche, cle, plage=None):
    """`plage` = (début, fin, début de la période précédente) pour une période sur mesure (rapports)."""
    debut, fin, debut_prec = plage or bornes(cle)
    avis = fiche.reviews.filter(created_at__gte=debut, created_at__lte=fin)
    precedents = fiche.reviews.filter(created_at__gte=debut_prec, created_at__lt=debut)
    total = avis.count()
    repondus = avis.filter(_a_repondu(fiche)).distinct().count()
    brouillons_ia = ReplyDraft.objects.filter(review__in=avis, source="ia")
    statut_auto = ReplyDraft.Statut.BROUILLON if fiche.is_demo else ReplyDraft.Statut.PUBLIEE

    # Temps de réponse : seulement quand Google fournit la date de la réponse.
    delais = [a.google_reply_at - a.created_at for a in avis.exclude(google_reply_at=None).only("created_at", "google_reply_at")]
    delai_moyen = sum(delais, timedelta()) / len(delais) if delais else None

    note_periode = _moyenne(avis)
    return {
        "note_google": fiche.average_rating,
        "nb_google": fiche.total_review_count,
        "total": total,
        "total_delta": total - precedents.count(),
        "total_delta_abs": abs(total - precedents.count()),
        "note_periode": note_periode,
        "note_delta": _delta(note_periode, _moyenne(precedents)),
        "note_delta_abs": abs(_delta(note_periode, _moyenne(precedents)) or 0),
        "positifs": avis.filter(stars__gte=4).count(),
        "neutres": avis.filter(stars=3).count(),
        "negatifs": avis.filter(stars__lte=2).count(),
        "taux_reponse": round(100 * repondus / total) if total else None,
        "reponses_ia": brouillons_ia.values("review").distinct().count(),
        "publiees_auto": brouillons_ia.filter(decision=Mode.AUTO, status=statut_auto).count(),
        "delai_moyen": delai_moyen,
        "a_valider": (avis.filter(google_reply="", drafts__status=ReplyDraft.Statut.A_VALIDER).distinct().count()),
    }


def _debut_seau(d, pas):
    d = timezone.localtime(d).date()
    if pas == "semaine":
        return d - timedelta(days=d.weekday())
    if pas == "mois":
        return d.replace(day=1)
    return d


def _seau_suivant(d, pas):
    if pas == "jour":
        return d + timedelta(days=1)
    if pas == "semaine":
        return d + timedelta(days=7)
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def _libelle(d, pas):
    if pas == "mois":
        return f"{MOIS[d.month - 1]} {d.year % 100:02d}"
    if pas == "semaine":
        return f"sem. {d.day} {MOIS[d.month - 1]}"
    return f"{d.day} {MOIS[d.month - 1]}"


def series(fiche, cle):
    """Une entrée par jour / semaine / mois : nombre d'avis par sentiment et note moyenne cumulée."""
    debut, fin, _ = bornes(cle)
    pas = PERIODES[cle]["pas"]
    # Point de départ de la note cumulée : tous les avis antérieurs à la période.
    avant = fiche.reviews.filter(created_at__lt=debut).aggregate(n=Count("id"), s=Avg("stars"))
    n_cumul = avant["n"] or 0
    somme_cumul = (avant["s"] or 0) * n_cumul

    seaux = {}
    d = _debut_seau(debut, pas)
    derniere = _debut_seau(fin, pas)
    while d <= derniere:
        seaux[d] = Counter()
        d = _seau_suivant(d, pas)
    for etoiles, date in fiche.reviews.filter(created_at__gte=debut, created_at__lte=fin).values_list("stars", "created_at"):
        c = seaux.setdefault(_debut_seau(date, pas), Counter())
        c["positifs" if etoiles >= 4 else "negatifs" if etoiles <= 2 else "neutres"] += 1
        c["somme"] += etoiles

    resultat = []
    for d in sorted(seaux):
        c = seaux[d]
        n = c["positifs"] + c["neutres"] + c["negatifs"]
        n_cumul += n
        somme_cumul += c["somme"]
        resultat.append({
            "date": d, "libelle": _libelle(d, pas), "positifs": c["positifs"], "neutres": c["neutres"],
            "negatifs": c["negatifs"], "total": n,
            "note_cumulee": round(somme_cumul / n_cumul, 2) if n_cumul else None,
        })
    return resultat


def repartition_etoiles(fiche, cle, plage=None):
    debut, fin, _ = plage or bornes(cle)
    compte = dict(fiche.reviews.filter(created_at__gte=debut, created_at__lte=fin)
                  .values_list("stars").annotate(n=Count("id")).values_list("stars", "n"))
    return [{"etoiles": e, "nombre": compte.get(e, 0)} for e in range(5, 0, -1)]


def _nom_theme(cle, polarite, secteur):
    if cle == "qualite" and polarite == "qualite":
        return QUALITE_PAR_SECTEUR.get(secteur, regles.THEMES[cle]["qualite"])
    return regles.THEMES[cle][polarite]


def _extrait(texte, n=160):
    texte = " ".join(texte.split())
    return texte if len(texte) <= n else texte[: n - 1].rsplit(" ", 1)[0] + "…"


def forces_faiblesses(fiche, cle, plage=None):
    """Thèmes cités positivement / négativement dans les avis analysés de la période, avec exemples."""
    debut, fin, debut_prec = plage or bornes(cle)
    analyses = (ReviewAnalysis.objects.filter(review__location=fiche, review__created_at__gte=debut,
                                              review__created_at__lte=fin)
                .select_related("review").order_by("-review__created_at"))
    precedentes = ReviewAnalysis.objects.filter(review__location=fiche, review__created_at__gte=debut_prec,
                                                review__created_at__lt=debut)
    nb = analyses.count()

    def compter(qs, champ):
        c = Counter()
        for valeurs in qs.values_list(champ, flat=True):
            c.update(set(valeurs))
        return c

    resultats = {}
    for champ, polarite in (("themes_positifs", "qualite"), ("themes_negatifs", "defaut")):
        actuel, avant = compter(analyses, champ), compter(precedentes, champ)
        lignes = []
        for theme, n in actuel.most_common():
            exemples = [_extrait(a.review.comment) for a in analyses if theme in getattr(a, champ) and a.review.comment][:2]
            lignes.append({
                "theme": theme, "nom": _nom_theme(theme, polarite, fiche.sector), "nombre": n,
                "part": round(100 * n / nb) if nb else 0, "evolution": n - avant.get(theme, 0),
                "exemples": exemples,
                "solutions": regles.solutions_pour(theme, fiche.sector)[:3] if polarite == "defaut" else [],
            })
        resultats[polarite] = lignes
    return {"analyses": nb, "hors_analyse": fiche.reviews.filter(created_at__gte=debut, created_at__lte=fin)
            .filter(analysis__isnull=True).count(), **resultats}
