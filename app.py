"""AvisPilote — serveur web (Flask).

Lancer :  python app.py   puis ouvrir http://localhost:5000
"""
import json
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, jsonify, redirect, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

import ai
import analytics
import config
import database
import demo_data
import google_api
import quotas

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config.update(
    SECRET_KEY=config.SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,      # cookie illisible par le JavaScript (limite le vol de session via XSS)
    SESSION_COOKIE_SAMESITE="Lax",     # cookie non envoyé par les formulaires d'autres sites
    SESSION_COOKIE_SECURE=config.SECURE_COOKIES,
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    MAX_CONTENT_LENGTH=64 * 1024,      # refuse les requêtes trop grosses
)
app.teardown_appcontext(database.close_db)
app.json.sort_keys = False  # garde l'ordre des formules (Essentiel, Pro, Multi-sites)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TAILLE_MAX_REPONSE = 4000  # Google limite les réponses à 4096 octets


# ---------------------------------------------------------------------------
# Sécurité
# ---------------------------------------------------------------------------
@app.after_request
def entetes_securite(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; frame-ancestors 'none'; form-action 'self'"
    )
    return resp


def jeton_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


@app.before_request
def verifier_csrf():
    """Toute requête qui modifie des données doit renvoyer le jeton CSRF en en-tête."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path.startswith("/api/"):
        envoye = request.headers.get("X-CSRF-Token", "")
        if not envoye or not secrets.compare_digest(envoye, session.get("csrf", "")):
            return jsonify(erreur="Jeton de sécurité invalide, recharge la page."), 403


_tentatives = defaultdict(deque)


def trop_de_tentatives(cle, maximum=10, fenetre=600):
    """Limite simple anti force brute : 10 essais / 10 min par IP (en mémoire)."""
    maintenant = time.time()
    file = _tentatives[cle]
    while file and file[0] < maintenant - fenetre:
        file.popleft()
    if len(file) >= maximum:
        return True
    file.append(maintenant)
    return False


def connexion_requise(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify(erreur="Connexion requise"), 401
        return f(*args, **kwargs)
    return wrapper


def entreprise():
    return database.get_db().execute(
        "SELECT * FROM businesses WHERE user_id = ?", (session["user_id"],)
    ).fetchone()


def entreprise_publique(b):
    plan = quotas.plan_de(b)
    return {
        "name": b["name"], "type": b["type"], "plan": b["plan"], "plan_nom": plan["nom"],
        "trial_ends": b["trial_ends"], "ton": b["ton"], "signature": b["signature"],
        "contact": b["contact"], "auto_publish": bool(b["auto_publish"]), "mode": b["mode"],
        "google_location_title": b["google_location_title"], "last_sync": b["last_sync"],
    }


def avis_public(r):
    return {
        "id": r["id"], "author": r["author"], "stars": r["stars"], "comment": r["comment"],
        "created_at": r["created_at"], "status": r["status"], "processed": bool(r["processed"]),
        "reply": r["reply"], "reply_published_at": r["reply_published_at"],
        "qualites": [ai.THEMES[k]["qualite"] for k in json.loads(r["qualites"])],
        "defauts": [ai.THEMES[k]["defaut"] for k in json.loads(r["defauts"])],
        "solution": r["solution"], "ai_source": r["ai_source"],
    }


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------------------------------------------------------------------------
# Comptes
# ---------------------------------------------------------------------------
@app.get("/api/me")
def me():
    donnees = {
        "csrf": jeton_csrf(),
        "plans": config.PLANS,
        "types": config.TYPES_COMMERCE,
        "tons": config.TONS,
        "google_configure": google_api.est_configure(),
        "ia": "claude" if config.ANTHROPIC_API_KEY else "regles",
        "connecte": False,
    }
    if "user_id" in session:
        b = entreprise()
        if b:
            db = database.get_db()
            a_valider = db.execute(
                "SELECT COUNT(*) FROM reviews WHERE business_id = ? AND status = 'a_valider' AND processed = 1",
                (b["id"],)).fetchone()[0]
            donnees.update(connecte=True, email=session.get("email"), entreprise=entreprise_publique(b),
                           quota=quotas.etat_quota(db, b), a_valider=a_valider)
    return jsonify(donnees)


@app.post("/api/register")
def inscription():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    mdp = str(data.get("password", ""))
    nom = str(data.get("name", "")).strip()[:80]
    type_c = data.get("type") if data.get("type") in config.TYPES_COMMERCE else "autre"
    plan = data.get("plan") if data.get("plan") in config.PLANS else "essentiel"

    if not EMAIL_RE.match(email):
        return jsonify(erreur="Adresse e-mail invalide"), 400
    if len(mdp) < 8:
        return jsonify(erreur="Le mot de passe doit faire au moins 8 caractères"), 400
    if not nom:
        return jsonify(erreur="Indique le nom de ton entreprise"), 400
    if trop_de_tentatives("register:" + (request.remote_addr or "")):
        return jsonify(erreur="Trop de tentatives, réessaie dans quelques minutes"), 429

    db = database.get_db()
    try:
        cur = db.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)",
                         (email, generate_password_hash(mdp)))
    except Exception:
        return jsonify(erreur="Un compte existe déjà avec cette adresse"), 409
    essai = (datetime.now() + timedelta(days=config.ESSAI_JOURS)).date().isoformat()
    db.execute("INSERT INTO businesses (user_id, name, type, plan, trial_ends) VALUES (?, ?, ?, ?, ?)",
               (cur.lastrowid, nom, type_c, plan, essai))
    db.commit()
    _ouvrir_session(cur.lastrowid, email)
    return jsonify(ok=True)


def _ouvrir_session(user_id, email):
    session.clear()  # nouvel identifiant de session : évite la fixation de session
    session.permanent = True
    session["user_id"] = user_id
    session["email"] = email
    jeton_csrf()


@app.post("/api/login")
def connexion():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    if trop_de_tentatives("login:" + (request.remote_addr or "")):
        return jsonify(erreur="Trop de tentatives, réessaie dans quelques minutes"), 429
    user = database.get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    # Même message que l'e-mail existe ou non : on ne révèle pas quels comptes existent
    if not user or not check_password_hash(user["password_hash"], str(data.get("password", ""))):
        return jsonify(erreur="E-mail ou mot de passe incorrect"), 401
    _ouvrir_session(user["id"], email)
    return jsonify(ok=True)


@app.post("/api/logout")
def deconnexion():
    session.clear()
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# Entreprise et abonnement
# ---------------------------------------------------------------------------
@app.post("/api/business/settings")
@connexion_requise
def reglages():
    data = request.get_json(silent=True) or {}
    b = entreprise()
    nom = str(data.get("name", b["name"])).strip()[:80] or b["name"]
    type_c = data.get("type") if data.get("type") in config.TYPES_COMMERCE else b["type"]
    ton = data.get("ton") if data.get("ton") in config.TONS else b["ton"]
    db = database.get_db()
    db.execute(
        "UPDATE businesses SET name = ?, type = ?, ton = ?, signature = ?, contact = ?, auto_publish = ? WHERE id = ?",
        (nom, type_c, ton, str(data.get("signature", b["signature"]))[:200],
         str(data.get("contact", b["contact"]))[:120], 1 if data.get("auto_publish", True) else 0, b["id"]),
    )
    db.commit()
    return jsonify(ok=True, entreprise=entreprise_publique(entreprise()))


@app.post("/api/business/plan")
@connexion_requise
def changer_plan():
    plan = (request.get_json(silent=True) or {}).get("plan")
    if plan not in config.PLANS:
        return jsonify(erreur="Formule inconnue"), 400
    db = database.get_db()
    b = entreprise()
    # TODO paiement : créer ici une session Stripe Checkout et ne changer la formule
    # qu'à la réception du webhook "checkout.session.completed".
    db.execute("UPDATE businesses SET plan = ? WHERE id = ?", (plan, b["id"]))
    db.commit()
    b = entreprise()
    traites = quotas.traiter_en_attente(db, b)  # les avis hors quota sont traités si la nouvelle formule le permet
    return jsonify(ok=True, traites=traites, quota=quotas.etat_quota(db, b))


@app.post("/api/demo")
@connexion_requise
def activer_demo():
    db = database.get_db()
    b = entreprise()
    db.execute("DELETE FROM reviews WHERE business_id = ?", (b["id"],))
    db.execute("""UPDATE businesses SET google_refresh_token = NULL, google_access_token = NULL,
                  google_account = NULL, google_location = NULL, google_location_title = NULL WHERE id = ?""",
               (b["id"],))
    db.commit()
    nb = demo_data.generer(db, entreprise())
    return jsonify(ok=True, avis=nb)


@app.post("/api/disconnect")
@connexion_requise
def deconnecter_source():
    db = database.get_db()
    b = entreprise()
    db.execute("DELETE FROM reviews WHERE business_id = ?", (b["id"],))
    db.execute("""UPDATE businesses SET mode = 'aucun', google_refresh_token = NULL, google_access_token = NULL,
                  google_account = NULL, google_location = NULL, google_location_title = NULL, last_sync = NULL
                  WHERE id = ?""", (b["id"],))
    db.commit()
    return jsonify(ok=True)


@app.post("/api/sync")
@connexion_requise
def synchroniser():
    db = database.get_db()
    b = entreprise()
    ajoutes = 0
    if b["mode"] == "google":
        try:
            ajoutes = google_api.synchroniser(db, b)
        except Exception as e:
            return jsonify(erreur=f"Synchronisation Google impossible ({e.__class__.__name__})"), 502
    traites = quotas.traiter_en_attente(db, entreprise())
    return jsonify(ok=True, ajoutes=ajoutes, traites=traites)


# ---------------------------------------------------------------------------
# Liaison Google (OAuth 2.0)
# ---------------------------------------------------------------------------
@app.get("/auth/google/start")
def google_debut():
    if "user_id" not in session:
        return redirect("/#/connexion")
    if not google_api.est_configure():
        return redirect("/#/demarrage?erreur=google_non_configure")
    session["oauth_state"] = secrets.token_urlsafe(24)
    return redirect(google_api.url_autorisation(session["oauth_state"]))


@app.get("/auth/google/callback")
def google_retour():
    if "user_id" not in session:
        return redirect("/#/connexion")
    attendu = session.pop("oauth_state", None)
    if not attendu or not secrets.compare_digest(attendu, request.args.get("state", "")):
        return redirect("/#/demarrage?erreur=etat_invalide")
    if request.args.get("error") or not request.args.get("code"):
        return redirect("/#/demarrage?erreur=refus")
    try:
        jetons = google_api.echanger_code(request.args["code"])
        etablissements = google_api.lister_etablissements(jetons["access_token"])
    except Exception:
        return redirect("/#/demarrage?erreur=google")
    if not etablissements:
        return redirect("/#/demarrage?erreur=aucune_fiche")

    # Version simple : on prend la première fiche. (Multi-sites : laisser choisir.)
    fiche = etablissements[0]
    db = database.get_db()
    b = entreprise()
    db.execute("DELETE FROM reviews WHERE business_id = ? AND external_id LIKE 'demo-%'", (b["id"],))
    db.execute(
        """UPDATE businesses SET mode = 'google', google_refresh_token = COALESCE(?, google_refresh_token),
           google_access_token = ?, google_token_expiry = ?, google_account = ?, google_location = ?,
           google_location_title = ? WHERE id = ?""",
        (jetons.get("refresh_token"), jetons["access_token"], time.time() + int(jetons.get("expires_in", 3600)),
         fiche["account"], fiche["location"], fiche["title"], b["id"]),
    )
    db.commit()
    try:
        google_api.synchroniser(db, entreprise())
        quotas.traiter_en_attente(db, entreprise(), auto_publier=False)  # pas de publication à la 1re connexion
    except Exception:
        return redirect("/#/dashboard?erreur=sync")
    return redirect("/#/dashboard")


# ---------------------------------------------------------------------------
# Avis
# ---------------------------------------------------------------------------
FILTRES = {
    "tous": "",
    "a_valider": "AND status = 'a_valider' AND processed = 1",
    "negatifs": "AND stars <= 2",
    "hors_quota": "AND processed = 0",
    "publiees": "AND status = 'publiee'",
}


@app.get("/api/reviews")
@connexion_requise
def liste_avis():
    filtre = request.args.get("filtre", "tous")
    clause = FILTRES.get(filtre, "")  # valeur choisie dans un dictionnaire fixe : pas d'injection possible
    page = max(1, request.args.get("page", 1, type=int))
    par_page = 20
    b = entreprise()
    db = database.get_db()
    total = db.execute(f"SELECT COUNT(*) FROM reviews WHERE business_id = ? {clause}", (b["id"],)).fetchone()[0]
    lignes = db.execute(
        f"SELECT * FROM reviews WHERE business_id = ? {clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (b["id"], par_page, (page - 1) * par_page),
    ).fetchall()
    compteurs = {k: db.execute(f"SELECT COUNT(*) FROM reviews WHERE business_id = ? {v}", (b["id"],)).fetchone()[0]
                 for k, v in FILTRES.items()}
    return jsonify(avis=[avis_public(r) for r in lignes], total=total, page=page,
                   pages=max(1, -(-total // par_page)), compteurs=compteurs)


def _avis_de_l_entreprise(avis_id):
    b = entreprise()
    r = database.get_db().execute("SELECT * FROM reviews WHERE id = ? AND business_id = ?",
                                  (avis_id, b["id"])).fetchone()
    return b, r


@app.post("/api/reviews/<int:avis_id>/publish")
@connexion_requise
def publier_avis(avis_id):
    b, r = _avis_de_l_entreprise(avis_id)  # vérifie que l'avis appartient bien à cette entreprise
    if not r:
        return jsonify(erreur="Avis introuvable"), 404
    if not r["processed"]:
        return jsonify(erreur="Cet avis dépasse le quota de ton abonnement"), 403
    texte = str((request.get_json(silent=True) or {}).get("reply", "")).strip()
    if not texte:
        return jsonify(erreur="La réponse est vide"), 400
    if len(texte.encode("utf-8")) > TAILLE_MAX_REPONSE:
        return jsonify(erreur="Réponse trop longue pour Google"), 400
    db = database.get_db()
    ok, err = quotas.publier(db, b, r, texte)
    db.commit()
    if not ok:
        return jsonify(erreur=err), 502
    return jsonify(ok=True, avis=avis_public(db.execute("SELECT * FROM reviews WHERE id = ?", (avis_id,)).fetchone()))


@app.post("/api/reviews/<int:avis_id>/regenerate")
@connexion_requise
def regenerer(avis_id):
    b, r = _avis_de_l_entreprise(avis_id)
    if not r:
        return jsonify(erreur="Avis introuvable"), 404
    if not r["processed"]:
        return jsonify(erreur="Cet avis dépasse le quota de ton abonnement"), 403
    # On change la "graine" pour obtenir une autre formulation avec le moteur de règles
    avis = dict(r)
    avis["external_id"] = avis["external_id"] + secrets.token_hex(2)
    resultat = ai.traiter_avis(avis, b)
    return jsonify(ok=True, reply=resultat["reply"])


# ---------------------------------------------------------------------------
# Dashboard et récap
# ---------------------------------------------------------------------------
@app.get("/api/dashboard")
@connexion_requise
def api_dashboard():
    jours = request.args.get("jours", 90, type=int)
    jours = jours if jours in (30, 60, 90) else 90
    db = database.get_db()
    b = entreprise()
    data = analytics.dashboard(db, b, jours)
    data["quota"] = quotas.etat_quota(db, b)
    return jsonify(data)


@app.get("/api/recap")
@connexion_requise
def api_recap():
    periode = request.args.get("periode", "mois")
    if periode not in ("mois", "mois_precedent", "semaine"):
        periode = "mois"
    b = entreprise()
    if periode == "semaine" and quotas.plan_de(b)["recap"] != "hebdomadaire":
        return jsonify(erreur="Le récap hebdomadaire est inclus à partir de la formule Pro", upgrade=True), 403
    return jsonify(analytics.recap(database.get_db(), b, periode))


database.init_db()

if __name__ == "__main__":
    # debug=False par défaut : le mode debug de Flask permet d'exécuter du code à distance s'il est exposé
    app.run(host="127.0.0.1", port=5000, debug=False)
