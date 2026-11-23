"""Statistiques du dashboard et récapitulatif qualités / défauts."""
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import ai

JOURS_SEMAINE = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def _jour(iso):
    return iso[:10]


def _moyenne(valeurs):
    return round(sum(valeurs) / len(valeurs), 2) if valeurs else None


def _extrait(texte, n=140):
    texte = (texte or "").strip().replace("\n", " ")
    return texte if len(texte) <= n else texte[:n].rsplit(" ", 1)[0] + "…"


def _exemple_pic(avis, nature):
    """Choisit l'avis le plus représentatif du jour : note dans le sens du pic, et qui cite le plus de thèmes."""
    def accord(a):
        return (nature == "positif" and a["stars"] >= 4) or (nature == "negatif" and a["stars"] <= 2) or nature == "mitige"
    candidats = [a for a in avis if a["comment"] and accord(a)] or [a for a in avis if a["comment"]]
    if not candidats:
        return ""
    meilleur = max(candidats, key=lambda a: len(json.loads(a["qualites"])) + len(json.loads(a["defauts"])))
    return _extrait(meilleur["comment"])


def _note_fr(n):
    return f"{n:.1f}".replace(".", ",")


def detecter_pics(par_jour, avis_par_jour, fenetre=30, facteur=2.5, minimum=4):
    """Un jour est un « pic » s'il a au moins `minimum` avis ET au moins `facteur` fois
    la moyenne quotidienne des `fenetre` jours précédents."""
    jours = sorted(par_jour)
    pics = []
    for i, jour in enumerate(jours):
        nb = par_jour[jour]["nombre"]
        if nb < minimum:
            continue
        precedents = [par_jour[j]["nombre"] for j in jours[max(0, i - fenetre):i]]
        base = sum(precedents) / len(precedents) if precedents else 0
        if nb < facteur * max(base, 0.5):
            continue
        avis = avis_par_jour[jour]
        note = _moyenne([a["stars"] for a in avis])
        q, d = Counter(), Counter()
        for a in avis:
            q.update(json.loads(a["qualites"]))
            d.update(json.loads(a["defauts"]))
        if note >= 4:
            nature, texte = "positif", "Événement qui a attiré et plu aux clients"
        elif note <= 2.5:
            nature, texte = "negatif", "Problème probable ce jour-là"
        else:
            nature, texte = "mitige", "Affluence inhabituelle, avis partagés"
        d_jour = date.fromisoformat(jour)
        pics.append({
            "jour": jour,
            "jour_semaine": JOURS_SEMAINE[d_jour.weekday()],
            "nombre": nb,
            "moyenne_habituelle": round(base, 1),
            "note": note,
            "nature": nature,
            "interpretation": texte,
            "qualites": [ai.THEMES[k]["qualite"] for k, _ in q.most_common(2)],
            "defauts": [ai.THEMES[k]["defaut"] for k, _ in d.most_common(2)],
            "exemple": _exemple_pic(avis, nature),
        })
    return sorted(pics, key=lambda p: p["jour"], reverse=True)


def dashboard(db, business, jours=90):
    aujourd_hui = date.today()
    debut = aujourd_hui - timedelta(days=jours - 1)
    debut_prec = debut - timedelta(days=jours)
    lignes = db.execute(
        "SELECT * FROM reviews WHERE business_id = ? AND created_at >= ? ORDER BY created_at",
        (business["id"], debut_prec.isoformat()),
    ).fetchall()
    periode = [r for r in lignes if _jour(r["created_at"]) >= debut.isoformat()]
    precedente = [r for r in lignes if _jour(r["created_at"]) < debut.isoformat()]

    # Série jour par jour (tous les jours, même sans avis, pour un graphique régulier)
    par_jour, avis_par_jour = {}, defaultdict(list)
    for i in range(jours):
        j = (debut + timedelta(days=i)).isoformat()
        par_jour[j] = {"jour": j, "nombre": 0, "note": None}
    notes_jour = defaultdict(list)
    for r in periode:
        j = _jour(r["created_at"])
        par_jour[j]["nombre"] += 1
        notes_jour[j].append(r["stars"])
        if r["processed"]:
            avis_par_jour[j].append(r)
        else:
            avis_par_jour[j].append({**dict(r), "qualites": "[]", "defauts": "[]"})
    for j, notes in notes_jour.items():
        par_jour[j]["note"] = _moyenne(notes)

    # Jours de la semaine : quand les clients viennent et laissent des avis
    semaine = [{"jour": n, "nombre": 0, "notes": []} for n in JOURS_SEMAINE]
    for r in periode:
        s = semaine[datetime.fromisoformat(r["created_at"]).weekday()]
        s["nombre"] += 1
        s["notes"].append(r["stars"])
    for s in semaine:
        s["note"] = _moyenne(s.pop("notes"))

    # Note moyenne par mois (6 derniers mois)
    six_mois = db.execute(
        """SELECT month, ROUND(AVG(stars), 2) AS note, COUNT(*) AS nombre FROM reviews
           WHERE business_id = ? GROUP BY month ORDER BY month DESC LIMIT 6""",
        (business["id"],),
    ).fetchall()

    note = _moyenne([r["stars"] for r in periode])
    note_prec = _moyenne([r["stars"] for r in precedente])
    publiees = sum(1 for r in periode if r["status"] == "publiee")
    a_valider = db.execute(
        "SELECT COUNT(*) FROM reviews WHERE business_id = ? AND status = 'a_valider' AND processed = 1",
        (business["id"],),
    ).fetchone()[0]

    return {
        "periode_jours": jours,
        "kpi": {
            "note": note,
            "evolution_note": round(note - note_prec, 2) if note and note_prec else None,
            "nombre": len(periode),
            "nombre_precedent": len(precedente),
            "taux_reponse": round(100 * publiees / len(periode)) if periode else 0,
            "a_valider": a_valider,
            "negatifs": sum(1 for r in periode if r["stars"] <= 2),
        },
        "par_jour": list(par_jour.values()),
        "pics": detecter_pics(par_jour, avis_par_jour),
        "repartition": {str(n): sum(1 for r in periode if r["stars"] == n) for n in range(1, 6)},
        "semaine": semaine,
        "mois": [dict(m) for m in reversed(six_mois)],
    }


def bornes_periode(periode):
    aujourd_hui = date.today()
    if periode == "semaine":
        debut = aujourd_hui - timedelta(days=aujourd_hui.weekday())
        return debut, aujourd_hui, f"Semaine du {debut.strftime('%d/%m')}"
    if periode == "mois_precedent":
        fin = aujourd_hui.replace(day=1) - timedelta(days=1)
        return fin.replace(day=1), fin, "Mois précédent"
    return aujourd_hui.replace(day=1), aujourd_hui, "Mois en cours"


def recap(db, business, periode="mois"):
    debut, fin, libelle = bornes_periode(periode)
    lignes = db.execute(
        """SELECT * FROM reviews WHERE business_id = ? AND created_at >= ? AND created_at < ?
           ORDER BY created_at DESC""",
        (business["id"], debut.isoformat(), (fin + timedelta(days=1)).isoformat()),
    ).fetchall()
    traites = [r for r in lignes if r["processed"]]
    ignores = len(lignes) - len(traites)

    q, d = Counter(), Counter()
    exemples_q, exemples_d = defaultdict(list), defaultdict(list)
    for r in traites:
        for k in json.loads(r["qualites"]):
            q[k] += 1
            if r["comment"] and len(exemples_q[k]) < 2 and _extrait(r["comment"]) not in [e["texte"] for e in exemples_q[k]]:
                exemples_q[k].append({"auteur": r["author"], "etoiles": r["stars"], "texte": _extrait(r["comment"])})
        for k in json.loads(r["defauts"]):
            d[k] += 1
            if r["comment"] and len(exemples_d[k]) < 2 and _extrait(r["comment"]) not in [e["texte"] for e in exemples_d[k]]:
                exemples_d[k].append({"auteur": r["author"], "etoiles": r["stars"], "texte": _extrait(r["comment"])})

    n = len(traites) or 1
    qualites = [{"cle": k, "libelle": ai.THEMES[k]["qualite"], "nombre": c, "pourcentage": round(100 * c / n),
                 "exemples": exemples_q[k]} for k, c in q.most_common()]
    defauts = [{"cle": k, "libelle": ai.THEMES[k]["defaut"], "nombre": c, "pourcentage": round(100 * c / n),
                "exemples": exemples_d[k], "solutions": ai.solutions_pour(k, business["type"])}
               for k, c in d.most_common()]

    if not traites:
        synthese = "Aucun avis analysé sur cette période."
    else:
        morceaux = [f"{len(traites)} avis analysés, note moyenne {_note_fr(_moyenne([r['stars'] for r in traites]))}/5."]
        if qualites:
            morceaux.append(f"Point fort principal : {qualites[0]['libelle'].lower()} "
                            f"(cité dans {qualites[0]['pourcentage']} % des avis).")
        if defauts:
            morceaux.append(f"À travailler en priorité : {defauts[0]['libelle'].lower()} "
                            f"({defauts[0]['nombre']} avis).")
        synthese = " ".join(morceaux)

    return {
        "periode": periode,
        "libelle": libelle,
        "debut": debut.isoformat(),
        "fin": fin.isoformat(),
        "analyses": len(traites),
        "ignores": ignores,
        "synthese": synthese,
        "qualites": qualites,
        "defauts": defauts,
    }
