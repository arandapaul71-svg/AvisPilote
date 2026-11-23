"""Export PDF du rapport (bibliothèque reportlab, 100 % Python : fonctionne sous Windows et Linux).

Sécurité : reportlab interprète un mini-langage de balises dans les paragraphes. Tout texte
venant d'un avis (donc d'un inconnu) est échappé avec `escape()` avant d'être placé dans le PDF.
Police : Helvetica (intégrée à tous les lecteurs PDF) ; elle n'a pas le caractère « ★ »,
on écrit donc les notes « 4,2 / 5 ».
"""
import io
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .rapports import phrase_bilan

BLEU = colors.HexColor("#2a78d6")
ROUGE = colors.HexColor("#c0392b")
VERT = colors.HexColor("#1f8a4c")
GRIS = colors.HexColor("#5b6578")
NUIT = colors.HexColor("#1b2540")


def _styles():
    base = getSampleStyleSheet()
    return {
        "titre": ParagraphStyle("titre", parent=base["Title"], fontName="Helvetica-Bold", fontSize=20,
                                textColor=NUIT, alignment=0, spaceAfter=2 * mm),
        "sous": ParagraphStyle("sous", parent=base["Normal"], fontSize=10, textColor=GRIS, spaceAfter=6 * mm),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=13,
                             textColor=NUIT, spaceBefore=6 * mm, spaceAfter=2 * mm),
        "texte": ParagraphStyle("texte", parent=base["Normal"], fontSize=10, leading=14),
        "citation": ParagraphStyle("citation", parent=base["Normal"], fontSize=9, leading=12, textColor=GRIS,
                                   leftIndent=5 * mm, fontName="Helvetica-Oblique"),
        "petit": ParagraphStyle("petit", parent=base["Normal"], fontSize=8, textColor=GRIS),
    }


def _note(n):
    return "–" if n is None else f"{n:.2f}".replace(".", ",") + " / 5"


def _ecart(v, suffixe=""):
    if v is None:
        return "–"
    signe = "+" if v > 0 else ""
    return f"{signe}{v:.2f}".replace(".", ",").replace(",00", "") + suffixe


def _tuiles(r, s):
    ind = r["ind"]
    taux = "–" if ind["taux_reponse"] is None else f"{ind['taux_reponse']} %"
    donnees = [
        ["Avis reçus", "Note de la période", "Taux de réponse", "Réponses de l'assistant"],
        [str(ind["total"]), _note(ind["note_periode"]), taux, str(ind["reponses_ia"])],
        [f"{_ecart(ind['total_delta'])} vs précédente", f"{_ecart(ind['note_delta'])} vs précédente",
         f"{ind['a_valider']} à valider", f"dont {ind['publiees_auto']} automatiques"],
    ]
    t = Table(donnees, colWidths=[42 * mm] * 4)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica", 8), ("TEXTCOLOR", (0, 0), (-1, 0), GRIS),
        ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 16), ("TEXTCOLOR", (0, 1), (-1, 1), NUIT),
        ("FONT", (0, 2), (-1, 2), "Helvetica", 8), ("TEXTCOLOR", (0, 2), (-1, 2), GRIS),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e5eb")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#eef0f3")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _barres_etoiles(repartition):
    largeur, ligne = 120 * mm, 6 * mm
    d = Drawing(largeur, ligne * 5 + 2)
    maximum = max([x["nombre"] for x in repartition] + [1])
    for i, x in enumerate(repartition):
        y = (4 - i) * ligne
        d.add(String(0, y + 1.5 * mm, f"{x['etoiles']} étoile{'s' if x['etoiles'] > 1 else ''}", fontName="Helvetica",
                     fontSize=8, fillColor=GRIS))
        l = (largeur - 40 * mm) * x["nombre"] / maximum
        if l:
            d.add(Rect(22 * mm, y + 1 * mm, l, 3.5 * mm, fillColor=BLEU, strokeColor=None))
        d.add(String(22 * mm + l + 2 * mm, y + 1.5 * mm, str(x["nombre"]), fontName="Helvetica-Bold", fontSize=8))
    return d


def generer(r):
    """Renvoie les octets du PDF du rapport `r` (dict produit par rapports.construire)."""
    s = _styles()
    tampon = io.BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"{r['type_nom']} - {r['fiche'].title}", author="AvisPilote")
    e = escape
    elements = [
        Paragraph(f"{e(r['type_nom'])} · {e(r['titre'])}", s["titre"]),
        Paragraph(f"{e(r['fiche'].title)} · généré le {r['genere_le']:%d/%m/%Y} par AvisPilote", s["sous"]),
        Paragraph(e(phrase_bilan(r)), s["texte"]), Spacer(1, 4 * mm), _tuiles(r, s),
    ]
    if r["ind"]["note_google"]:
        elements.append(Paragraph(f"Note Google actuelle : {_note(float(r['ind']['note_google']))} "
                                  f"({r['ind']['nb_google'] or 0} avis au total).", s["petit"]))

    elements += [Paragraph("Répartition des notes", s["h2"]), _barres_etoiles(r["repartition"])]

    for cle, titre, couleur in (("qualite", "Points forts", VERT), ("defaut", "Problèmes relevés", ROUGE)):
        elements.append(Paragraph(titre, s["h2"]))
        lignes = r["ff"][cle][:5]
        if not lignes:
            elements.append(Paragraph("Rien de notable sur cette période.", s["texte"]))
        for t in lignes:
            evol = f" ({'+' if t['evolution'] > 0 else ''}{t['evolution']} vs précédente)" if t["evolution"] else ""
            elements.append(Paragraph(f"<font color='{couleur.hexval()}'>■</font> <b>{e(t['nom'])}</b> : "
                                      f"{t['nombre']} avis, {t['part']} %{e(evol)}", s["texte"]))
            for ex in t["exemples"][:1]:
                elements.append(Paragraph(f"« {e(ex)} »", s["citation"]))

    elements.append(Paragraph("Événements inhabituels", s["h2"]))
    if not r["alertes"]:
        elements.append(Paragraph("Aucune anomalie détectée.", s["texte"]))
    for a in r["alertes"]:
        elements.append(Paragraph(f"• {e(a.message)}", s["texte"]))

    elements.append(Paragraph(f"Recommandations en cours (au {r['genere_le']:%d/%m/%Y})", s["h2"]))
    if not r["recos"]:
        elements.append(Paragraph("Aucune recommandation en cours.", s["texte"]))
    for reco in r["recos"]:
        elements.append(Paragraph(f"<b>{e(reco.titre)}</b> · importance {e(reco.get_importance_display().lower())} · "
                                  f"{e(reco.get_status_display().lower())}", s["texte"]))
        elements.append(Paragraph(e(reco.problem), s["texte"]))
        for act in reco.actions[:3]:
            elements.append(Paragraph(f"– {e(act)}", s["citation"]))
        if reco.suivi:
            elements.append(Paragraph(f"Suivi : {reco.suivi['depuis']} avis depuis le {e(reco.suivi['date'])}, "
                                      f"contre {reco.suivi['avant']} avant.", s["petit"]))
        elements.append(Spacer(1, 2 * mm))
    for reco in r["resolues"]:
        elements.append(Paragraph(f"✓ Réglé pendant la période : {e(reco.titre)}", s["texte"]))

    elements += [Spacer(1, 8 * mm), Paragraph("Chiffres calculés sur les avis récupérés par AvisPilote ; la note "
                                              "affichée par Google peut légèrement différer.", s["petit"])]
    doc.build(elements)
    return tampon.getvalue()
