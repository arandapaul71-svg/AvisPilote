"""Client des API officielles Google Business Profile (OAuth 2.0 + avis).

IMPORTANT : ces API ne sont pas publiques. Il faut demander l'accès à Google
(projet Google Cloud + entreprise + site web, réponse sous ~14 jours). Tant que
GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET ne sont pas renseignés, la connexion
Google est indiquée comme indisponible : elle n'est jamais simulée.

Sécurité :
- « state » aléatoire vérifié au retour (anti-CSRF sur OAuth) ;
- PKCE : même si quelqu'un intercepte le code de retour, il ne peut pas l'échanger ;
- les jetons ne transitent jamais par le navigateur et sont chiffrés en base.
"""
import base64
import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

log = logging.getLogger("avispilote")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SCOPE = "https://www.googleapis.com/auth/business.manage"
ACCOUNTS_URL = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"
LOCATIONS_URL = "https://mybusinessbusinessinformation.googleapis.com/v1/{account}/locations"
REVIEWS_URL = "https://mybusiness.googleapis.com/v4/{location}/reviews"
REPLY_URL = "https://mybusiness.googleapis.com/v4/{location}/reviews/{review_id}/reply"
TIMEOUT = 20
ETOILES = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


class GoogleErreur(Exception):
    """Erreur Google traduite pour l'utilisateur. `code` sert au traitement."""

    MESSAGES = {
        "non_configure": "La connexion Google n'est pas encore disponible : l'accès à l'API Google est en cours de validation.",
        "autorisation": "Google a refusé l'accès : reconnecte ta fiche Google.",
        "acces_api": "Google n'autorise pas encore cette application à utiliser l'API Business Profile.",
        "limite": "Google limite le nombre de requêtes : réessaie dans quelques minutes.",
        "fiche_non_validee": "Cette fiche Google n'est pas validée : Google n'autorise pas les réponses.",
        "reseau": "Google ne répond pas pour le moment. Réessaie plus tard.",
        "inconnue": "Erreur inattendue avec Google. Réessaie plus tard.",
    }

    def __init__(self, code, detail=""):
        self.code = code
        self.detail = detail
        super().__init__(self.MESSAGES.get(code, self.MESSAGES["inconnue"]))


def est_configure():
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def redirect_uri():
    return settings.APP_URL + reverse("locations:google_retour")


def nouveau_pkce():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def url_autorisation(state, code_challenge):
    if not est_configure():
        raise GoogleErreur("non_configure")
    return AUTH_URL + "?" + urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",  # pour obtenir un refresh_token (synchro en arrière-plan)
        "prompt": "consent",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })


def _appel(methode, url, **kwargs):
    """Fait la requête et traduit les erreurs HTTP en GoogleErreur."""
    try:
        r = requests.request(methode, url, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as e:
        raise GoogleErreur("reseau", str(e.__class__.__name__)) from e
    if r.status_code < 400:
        return r.json() if r.content else {}
    detail = r.text[:300]
    log.warning("Google %s %s → %s %s", methode, url.split("?")[0], r.status_code, detail)
    if r.status_code in (400, 401) and ("invalid_grant" in detail or r.status_code == 401):
        raise GoogleErreur("autorisation", detail)
    if r.status_code == 403:
        code = "fiche_non_validee" if "verif" in detail.lower() else "acces_api"
        raise GoogleErreur(code, detail)
    if r.status_code == 429:
        raise GoogleErreur("limite", detail)
    if r.status_code >= 500:
        raise GoogleErreur("reseau", detail)
    raise GoogleErreur("inconnue", detail)


def echanger_code(code, code_verifier):
    return _appel("POST", TOKEN_URL, data={
        "code": code,
        "code_verifier": code_verifier,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri(),
        "grant_type": "authorization_code",
    })


def enregistrer_jetons(connexion, jetons):
    connexion.access_token = jetons["access_token"]
    if jetons.get("refresh_token"):
        connexion.refresh_token = jetons["refresh_token"]
    connexion.token_expiry = timezone.now() + timedelta(seconds=int(jetons.get("expires_in", 3600)))
    connexion.status = connexion.Statut.OK
    connexion.save()


def jeton_valide(connexion):
    """Renvoie un access_token valide, en le rafraîchissant si besoin."""
    if connexion.access_token and connexion.token_expiry and connexion.token_expiry > timezone.now() + timedelta(seconds=60):
        return connexion.access_token
    if not connexion.refresh_token:
        raise GoogleErreur("autorisation", "pas de refresh_token")
    try:
        jetons = _appel("POST", TOKEN_URL, data={
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "refresh_token": connexion.refresh_token,
            "grant_type": "refresh_token",
        })
    except GoogleErreur as e:
        if e.code == "autorisation":
            connexion.status = connexion.Statut.EXPIREE
            connexion.save(update_fields=["status"])
        raise
    enregistrer_jetons(connexion, jetons)
    return connexion.access_token


def _entete(token):
    return {"Authorization": f"Bearer {token}"}


def lister_fiches(access_token):
    """Toutes les fiches accessibles : [{"name": "accounts/1/locations/2", "title", "new_review_uri"}]."""
    fiches = []
    comptes = _appel("GET", ACCOUNTS_URL, headers=_entete(access_token)).get("accounts", [])
    for compte in comptes:
        page = None
        while True:
            params = {"readMask": "name,title,metadata", "pageSize": 100}
            if page:
                params["pageToken"] = page
            data = _appel("GET", LOCATIONS_URL.format(account=compte["name"]), params=params,
                          headers=_entete(access_token))
            for loc in data.get("locations", []):
                fiches.append({
                    "name": f"{compte['name']}/{loc['name']}",  # format attendu par l'API des avis (v4)
                    "title": loc.get("title") or loc["name"],
                    "new_review_uri": (loc.get("metadata") or {}).get("newReviewUri", ""),
                })
            page = data.get("nextPageToken")
            if not page:
                break
    return fiches


def lire_date(iso):
    """'2026-11-20T13:32:11.123456789Z' → datetime avec fuseau (Python n'accepte que 6 décimales)."""
    iso = iso.replace("Z", "+00:00")
    if "." in iso:
        avant, apres = iso.split(".", 1)
        fuseau = apres[apres.find("+"):] if "+" in apres else "+00:00"
        iso = avant + fuseau
    return datetime.fromisoformat(iso)


def pages_avis(connexion, location_name, max_pages=20):
    """Générateur de pages d'avis, des plus récemment modifiés aux plus anciens."""
    page = None
    for _ in range(max_pages):
        params = {"pageSize": 50, "orderBy": "updateTime desc"}
        if page:
            params["pageToken"] = page
        data = _appel("GET", REVIEWS_URL.format(location=location_name), params=params,
                      headers=_entete(jeton_valide(connexion)))
        yield data
        page = data.get("nextPageToken")
        if not page:
            return


def publier_reponse(connexion, location_name, review_id, texte):
    url = REPLY_URL.format(location=location_name, review_id=review_id)
    return _appel("PUT", url, json={"comment": texte}, headers=_entete(jeton_valide(connexion)))


def supprimer_reponse(connexion, location_name, review_id):
    url = REPLY_URL.format(location=location_name, review_id=review_id)
    return _appel("DELETE", url, headers=_entete(jeton_valide(connexion)))


def revoquer(connexion):
    """Retire l'accès chez Google (déconnexion, suppression de compte). Ne lève jamais d'erreur."""
    jeton = connexion.refresh_token or connexion.access_token
    if not jeton:
        return
    try:
        requests.post(REVOKE_URL, data={"token": jeton}, timeout=TIMEOUT)
    except requests.RequestException:
        log.warning("Révocation Google impossible pour l'organisation %s", connexion.organization_id)
