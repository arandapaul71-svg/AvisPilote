"""Quotas d'abonnement et traitement des avis (analyse + réponse + publication)."""
import json
from datetime import datetime

import ai
import config
import google_api


def mois_courant():
    return datetime.now().strftime("%Y-%m")


def plan_de(business):
    return config.PLANS.get(business["plan"], config.PLANS["essentiel"])


def etat_quota(db, business, mois=None):
    mois = mois or mois_courant()
    plan = plan_de(business)
    ligne = db.execute(
        """SELECT
             SUM(CASE WHEN processed = 1 THEN 1 ELSE 0 END) AS utilises,
             SUM(CASE WHEN processed = 1 AND stars >= 3 THEN 1 ELSE 0 END) AS positifs,
             SUM(CASE WHEN processed = 0 THEN 1 ELSE 0 END) AS hors_quota,
             COUNT(*) AS total
           FROM reviews WHERE business_id = ? AND month = ?""",
        (business["id"], mois),
    ).fetchone()
    utilises = ligne["utilises"] or 0
    return {
        "mois": mois,
        "plan": business["plan"],
        "quota": plan["quota"],
        "utilises": utilises,
        "restants": max(0, plan["quota"] - utilises),
        "positifs": ligne["positifs"] or 0,
        "hors_quota": ligne["hors_quota"] or 0,
        "total": ligne["total"] or 0,
        "depasse": (ligne["hors_quota"] or 0) > 0,
        "pourcentage": min(100, round(100 * utilises / plan["quota"])) if plan["quota"] else 0,
    }


def peut_traiter(etat, etoiles):
    """Les avis 1-2 étoiles peuvent utiliser tout le quota.
    Les autres s'arrêtent avant, pour garder une réserve aux avis négatifs."""
    if etoiles <= 2:
        return etat["utilises"] < etat["quota"]
    plafond_positifs = int(etat["quota"] * (1 - config.RESERVE_NEGATIFS))
    return etat["utilises"] < etat["quota"] and etat["positifs"] < plafond_positifs


def publier(db, business, avis, texte):
    """Publie la réponse : sur Google en mode google, simulé en mode démo.
    Renvoie (ok, message_erreur)."""
    if business["mode"] == "google":
        ok, err = google_api.repondre_avis(db, business, avis["external_id"], texte)
        if not ok:
            return False, err
    db.execute(
        "UPDATE reviews SET reply = ?, status = 'publiee', reply_published_at = ? WHERE id = ?",
        (texte, datetime.now().isoformat(timespec="seconds"), avis["id"]),
    )
    return True, None


def traiter_en_attente(db, business, auto_publier=True):
    """Traite, dans l'ordre chronologique, tous les avis pas encore traités,
    tant que le quota de leur mois le permet. Renvoie le nombre d'avis traités."""
    avis_list = db.execute(
        "SELECT * FROM reviews WHERE business_id = ? AND processed = 0 ORDER BY created_at",
        (business["id"],),
    ).fetchall()
    etats = {}
    traites = 0
    for avis in avis_list:
        mois = avis["month"]
        if mois not in etats:
            etats[mois] = etat_quota(db, business, mois)
        etat = etats[mois]
        if not peut_traiter(etat, avis["stars"]):
            continue

        resultat = ai.traiter_avis(dict(avis), business)
        deja_repondu = avis["reply"] is not None and avis["status"] == "publiee"
        db.execute(
            """UPDATE reviews SET processed = 1, qualites = ?, defauts = ?, solution = ?, ai_source = ?,
                      reply = COALESCE(reply, ?), status = ?
               WHERE id = ?""",
            (json.dumps(resultat["qualites"]), json.dumps(resultat["defauts"]), resultat["solution"],
             resultat["source"], resultat["reply"], "publiee" if deja_repondu else "a_valider", avis["id"]),
        )
        etat["utilises"] += 1
        if avis["stars"] >= 3:
            etat["positifs"] += 1
        traites += 1

        # Publication automatique uniquement pour les avis 4-5 étoiles :
        # les avis négatifs attendent toujours la validation du commerçant.
        if auto_publier and not deja_repondu and business["auto_publish"] and avis["stars"] >= 4:
            avis_maj = db.execute("SELECT * FROM reviews WHERE id = ?", (avis["id"],)).fetchone()
            publier(db, business, avis_maj, avis_maj["reply"])
    db.commit()
    return traites
