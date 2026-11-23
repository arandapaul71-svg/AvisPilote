"""Configuration de l'application AvisPilote.

Les valeurs sensibles (clés, secrets) sont lues dans les variables
d'environnement ou dans un fichier .env à la racine du projet.
Ne jamais mettre de vrais secrets directement dans le code.
"""
import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv(path):
    """Mini-lecteur de fichier .env (évite une dépendance en plus)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(os.path.join(BASE_DIR, ".env"))

# Clé de signature des cookies de session. En production, mets une valeur
# fixe et longue dans .env, sinon tout le monde est déconnecté à chaque redémarrage.
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "avispilote.db"))

# URL publique de l'appli (sert à construire l'adresse de retour Google OAuth)
APP_URL = os.environ.get("APP_URL", "http://localhost:5000").rstrip("/")

# Mettre à 1 en production derrière HTTPS (cookie envoyé uniquement en HTTPS)
SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "0") == "1"

# --- Google Business Profile (liaison de la fiche) ---
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = APP_URL + "/auth/google/callback"

# --- IA (rédaction des réponses et analyse) ---
# Sans clé, l'appli utilise un moteur de règles intégré (moins fin mais gratuit).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")

# --- Formules d'abonnement ---
# quota = nombre d'avis traités (réponse + analyse) par mois calendaire.
# reserve_negatifs = part du quota réservée aux avis 1-2 étoiles :
# les avis positifs ne peuvent consommer que (1 - reserve) du quota,
# pour qu'un avis négatif ne reste jamais sans réponse à cause des positifs.
PLANS = {
    "essentiel": {
        "nom": "Essentiel",
        "prix": 19,
        "quota": 40,
        "recap": "mensuel",
        "etablissements": 1,
        "atouts": [
            "40 avis traités par mois",
            "Réponses automatiques personnalisées",
            "Dashboard : pics d'activité et étoiles",
            "Récap qualités / défauts mensuel",
            "Solutions proposées aux avis négatifs",
        ],
    },
    "pro": {
        "nom": "Pro",
        "prix": 39,
        "quota": 150,
        "recap": "hebdomadaire",
        "etablissements": 1,
        "atouts": [
            "150 avis traités par mois",
            "Tout Essentiel",
            "Récap hebdomadaire",
            "Plan d'action détaillé sur les défauts",
        ],
    },
    "multi": {
        "nom": "Multi-sites",
        "prix": 79,
        "quota": 500,
        "recap": "hebdomadaire",
        "etablissements": 5,
        "atouts": [
            "500 avis traités par mois",
            "Tout Pro",
            "Jusqu'à 5 établissements (bientôt)",
            "Export PDF du récap (bientôt)",
        ],
    },
}
RESERVE_NEGATIFS = 0.15
ESSAI_JOURS = 14

TYPES_COMMERCE = ["boulangerie", "restaurant", "fleuriste", "coiffeur", "autre"]
TONS = ["chaleureux", "professionnel", "décontracté"]
