"""Liaison avec Google Business Profile (OAuth 2.0 + API des avis).

IMPORTANT : ces API ne sont pas publiques. Il faut d'abord demander l'accès à Google
(formulaire "Application for Basic API Access", réponse sous ~14 jours) avec un projet
Google Cloud, une entreprise et un site web. Voir le README.

Le commerçant clique sur "Connecter Google", accepte l'écran de consentement, et l'appli
reçoit un jeton qui lui permet de lire ses avis et d'y répondre en son nom.
"""
import time
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

import config

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/business.manage"
ACCOUNTS_URL = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
LOCATIONS_URL = "https://mybusinessbusinessinformation.googleapis.com/v1/{account}/locations"
REVIEWS_URL = "https://mybusiness.googleapis.com/v4/{account}/{location}/reviews"
REPLY_URL = "https://mybusiness.googleapis.com/v4/{account}/{location}/reviews/{review_id}/reply"

ETOILES = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}
try:
    PARIS = ZoneInfo("Europe/Paris")
except ZoneInfoNotFoundError:
    # Windows n'a pas de base de fuseaux horaires : elle vient du paquet "tzdata".
    # S'il manque, on se rabat sur l'heure locale de l'ordinateur.
    PARIS = None
TIMEOUT = 20


def est_configure():
    return bool(config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET)


def url_autorisation(state):
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",   # pour obtenir un refresh_token
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,             # protège contre les attaques CSRF sur le retour OAuth
    }
    return AUTH_URL + "?" + urlencode(params)


def echanger_code(code):
    r = requests.post(TOKEN_URL, data={
        "code": code,
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _jeton_valide(db, business):
    """Renvoie un access_token valide, en le rafraîchissant si besoin."""
    if business["google_access_token"] and (business["google_token_expiry"] or 0) > time.time() + 60:
        return business["google_access_token"]
    if not business["google_refresh_token"]:
        raise RuntimeError("Fiche Google non connectée")
    r = requests.post(TOKEN_URL, data={
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "refresh_token": business["google_refresh_token"],
        "grant_type": "refresh_token",
    }, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    expiry = time.time() + int(data.get("expires_in", 3600))
    db.execute("UPDATE businesses SET google_access_token = ?, google_token_expiry = ? WHERE id = ?",
               (data["access_token"], expiry, business["id"]))
    db.commit()
    return data["access_token"]


def _get(db, business, url, params=None, token=None):
    token = token or _jeton_valide(db, business)
    r = requests.get(url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def lister_etablissements(access_token):
    """Liste (compte, établissement, nom) accessibles avec ce jeton."""
    resultats = []
    comptes = requests.get(ACCOUNTS_URL, headers={"Authorization": f"Bearer {access_token}"},
                           timeout=TIMEOUT)
    comptes.raise_for_status()
    for compte in comptes.json().get("accounts", []):
        page = None
        while True:
            params = {"readMask": "name,title", "pageSize": 100}
            if page:
                params["pageToken"] = page
            r = requests.get(LOCATIONS_URL.format(account=compte["name"]), params=params,
                             headers={"Authorization": f"Bearer {access_token}"}, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
            for loc in data.get("locations", []):
                resultats.append({"account": compte["name"], "location": loc["name"],
                                  "title": loc.get("title", loc["name"])})
            page = data.get("nextPageToken")
            if not page:
                break
    return resultats


def _date_locale(iso):
    """'2026-11-20T13:32:11.123Z' -> '2026-11-20T14:32:11' (heure de Paris)"""
    iso = iso.replace("Z", "+00:00")
    if "." in iso:  # Google peut renvoyer jusqu'à 9 décimales, Python en accepte 6
        avant, apres = iso.split(".", 1)
        fraction, _, fuseau = apres.partition("+")
        iso = avant + "+" + fuseau if fuseau else avant
    dt = datetime.fromisoformat(iso)
    local = dt.astimezone(PARIS) if PARIS else dt.astimezone()
    return local.replace(tzinfo=None).isoformat(timespec="seconds")


def synchroniser(db, business, max_pages=20):
    """Importe les nouveaux avis de la fiche. Renvoie le nombre d'avis ajoutés."""
    url = REVIEWS_URL.format(account=business["google_account"], location=business["google_location"])
    ajoutes, page = 0, None
    for _ in range(max_pages):
        params = {"pageSize": 50, "orderBy": "updateTime desc"}
        if page:
            params["pageToken"] = page
        data = _get(db, business, url, params)
        nouveaux_dans_page = 0
        for rv in data.get("reviews", []):
            created = _date_locale(rv["createTime"])
            reponse = (rv.get("reviewReply") or {}).get("comment")
            cur = db.execute(
                """INSERT OR IGNORE INTO reviews
                   (business_id, external_id, author, stars, comment, created_at, month, reply, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (business["id"], rv["reviewId"],
                 (rv.get("reviewer") or {}).get("displayName", "Client Google"),
                 ETOILES.get(rv.get("starRating"), 3), rv.get("comment", ""),
                 created, created[:7], reponse, "publiee" if reponse else "hors_quota"),
            )
            ajoutes += cur.rowcount
            nouveaux_dans_page += cur.rowcount
        page = data.get("nextPageToken")
        if not page or nouveaux_dans_page == 0:  # tout le reste est déjà en base
            break
    db.execute("UPDATE businesses SET last_sync = ? WHERE id = ?",
               (datetime.now().isoformat(timespec="seconds"), business["id"]))
    db.commit()
    return ajoutes


def repondre_avis(db, business, review_id, texte):
    """Publie (ou remplace) la réponse du propriétaire. Renvoie (ok, erreur)."""
    try:
        token = _jeton_valide(db, business)
        url = REPLY_URL.format(account=business["google_account"], location=business["google_location"],
                               review_id=review_id)
        r = requests.put(url, json={"comment": texte},
                         headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
        r.raise_for_status()
        return True, None
    except Exception as e:
        return False, f"Publication sur Google impossible : {e.__class__.__name__}"
