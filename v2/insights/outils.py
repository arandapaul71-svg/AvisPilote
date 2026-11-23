"""Outils : QR code de collecte d'avis et simulateur de note Google.

QR code — règles Google : la collecte doit rester NEUTRE. Interdit de ne solliciter que
les clients satisfaits (« review gating ») ou d'offrir une contrepartie à un avis.
Le QR code renvoie donc vers la page officielle de dépôt d'avis, pour tous les clients.

Simulateur — Google affiche la note arrondie à 0,1 : afficher 4,5 demande une moyenne
réelle d'au moins 4,45. Les résultats sont des ESTIMATIONS (Google peut filtrer des avis).
"""
import io
import math
from datetime import timedelta
from urllib.parse import urlparse

import segno
from django.core.exceptions import ValidationError
from django.db.models import Avg, Count
from django.utils import timezone

# Seuls les liens d'avis Google sont acceptés : le QR code ne peut pas pointer vers un site piégé.
HOTES_AUTORISES = {"g.page", "search.google.com", "www.google.com", "google.com", "maps.app.goo.gl",
                   "g.co", "www.google.fr", "google.fr"}


def valider_lien_avis(url):
    """Lève ValidationError si l'adresse n'est pas un lien Google en https."""
    p = urlparse(url.strip())
    if p.scheme != "https" or (p.hostname or "").lower() not in HOTES_AUTORISES:
        raise ValidationError("Colle le lien « Demander des avis » de ta fiche Google (il commence par "
                              "https://g.page/ ou https://search.google.com/).")
    if len(url) > 500:
        raise ValidationError("Lien trop long.")


def qr_svg(url):
    """SVG en ligne (affichage). Contenu : uniquement l'URL validée."""
    # omitsize : SVG avec viewBox, redimensionnable en CSS (écran comme impression).
    return segno.make(url, error="m").svg_inline(dark="#000000", light="#ffffff", border=2, omitsize=True)


def qr_fichier(url, format_):
    tampon = io.BytesIO()
    qr = segno.make(url, error="m")
    if format_ == "png":
        qr.save(tampon, kind="png", scale=20, border=2)  # ~ 600 px : net à l'impression
    else:
        qr.save(tampon, kind="svg", scale=10, border=2, xmldecl=True)
    return tampon.getvalue()


# --- Simulateur -----------------------------------------------------------------

def situation(fiche):
    """Note et nombre d'avis actuels : ceux de Google si connus, sinon calculés sur les avis récupérés."""
    if fiche.average_rating and fiche.total_review_count:
        note, nombre, source = float(fiche.average_rating), int(fiche.total_review_count), "google"
    else:
        r = fiche.reviews.aggregate(n=Count("id"), m=Avg("stars"))
        note, nombre, source = (r["m"] or 0.0), r["n"], "calcul"
    depuis = timezone.now() - timedelta(days=90)
    cinq_par_mois = fiche.reviews.filter(created_at__gte=depuis, stars=5).count() / 3
    return {"note": note, "nombre": nombre, "source": source, "affichee": round(note + 1e-9, 1),
            "cinq_par_mois": round(cinq_par_mois, 1)}


def avis_5_necessaires(note, nombre, cible):
    """Nombre d'avis 5★ pour que Google affiche `cible` (ou plus). None si impossible."""
    seuil = cible - 0.05  # arrondi de Google à 0,1
    if cible > 5 or seuil >= 5:
        return None
    if note >= seuil:
        return 0
    # (note·N + 5k) / (N + k) ≥ seuil  ⇔  k ≥ N·(seuil − note) / (5 − seuil)
    return max(0, math.ceil(nombre * (seuil - note) / (5 - seuil) - 1e-9))


def note_apres(note, nombre, ajout, etoiles):
    if nombre + ajout == 0:
        return None
    return (note * nombre + etoiles * ajout) / (nombre + ajout)


def avis_1_pour_baisser(note, nombre):
    """Combien d'avis 1★ feraient baisser la note affichée de 0,1 (repère de « solidité »)."""
    seuil = round(note + 1e-9, 1) - 0.05
    if seuil <= 1:
        return None
    # (note·N + k) / (N + k) < seuil  ⇔  k > N·(note − seuil) / (seuil − 1)
    return math.floor(nombre * (note - seuil) / (seuil - 1)) + 1


def simuler(fiche, cible=None, ajout=None, etoiles=None):
    s = situation(fiche)
    res = {"situation": s, "solidite": avis_1_pour_baisser(s["note"], s["nombre"]) if s["nombre"] else None}
    if cible is not None and s["nombre"]:
        k = avis_5_necessaires(s["note"], s["nombre"], cible)
        res["objectif"] = {"cible": cible, "necessaires": k,
                           "mois": (math.ceil(k / s["cinq_par_mois"]) if k and s["cinq_par_mois"] else None)}
    if ajout is not None and etoiles is not None:
        nouvelle = note_apres(s["note"], s["nombre"], ajout, etoiles)
        res["scenario"] = {"ajout": ajout, "etoiles": etoiles, "note": nouvelle,
                           "affichee": round(nouvelle + 1e-9, 1) if nouvelle is not None else None}
    return res
