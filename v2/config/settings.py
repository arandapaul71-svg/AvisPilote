"""Réglages Django d'AvisPilote.

Les secrets ne sont JAMAIS écrits ici : ils sont lus dans les variables
d'environnement ou dans le fichier v2/.env (non versionné, voir .env.example).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _charger_env(chemin):
    """Lit un fichier .env simple (CLE=valeur) sans dépendance supplémentaire."""
    if not chemin.exists():
        return
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if ligne and not ligne.startswith("#") and "=" in ligne:
            cle, valeur = ligne.split("=", 1)
            os.environ.setdefault(cle.strip(), valeur.strip().strip("\"'"))


_charger_env(BASE_DIR / ".env")


def env(nom, defaut=""):
    return os.environ.get(nom, defaut)


DEBUG = env("DEBUG", "1") == "1"

# En production (DEBUG=0), SECRET_KEY est obligatoire : on refuse de démarrer sans.
SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("SECRET_KEY manquante : ajoute-la dans le fichier .env")
    SECRET_KEY = "dev-seulement-ne-pas-utiliser-en-production"

ALLOWED_HOSTS = [h.strip() for h in env("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
APP_URL = env("APP_URL", "http://localhost:8000").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "locations",
    "reviews",
    "billing",
    "insights",
    "audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "accounts.middleware.OrganisationMiddleware",
    "accounts.middleware.EntetesSecuriteMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.organisation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# SQLite en développement. En production : PostgreSQL via les variables DB_*.
if env("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME"),
            "USER": env("DB_USER"),
            "PASSWORD": env("DB_PASSWORD"),
            "HOST": env("DB_HOST", "localhost"),
            "PORT": env("DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:connexion"
LOGIN_REDIRECT_URL = "accounts:tableau_de_bord"
LOGOUT_REDIRECT_URL = "accounts:connexion"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Sécurité des sessions et cookies ---
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 14 jours
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

if not DEBUG:
    # Production derrière HTTPS : cookies uniquement en HTTPS, redirection HTTP -> HTTPS, HSTS.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    CSRF_TRUSTED_ORIGINS = [APP_URL]

# Chiffrement des jetons Google en base (Fernet). Génère une clé avec :
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY")
if not FIELD_ENCRYPTION_KEY and not DEBUG:
    raise RuntimeError("FIELD_ENCRYPTION_KEY manquante : ajoute-la dans le fichier .env")

# --- Intégrations externes (clés côté serveur uniquement) ---
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", "claude-haiku-5-5")

# --- E-mails (rapports) ---
# Développement : affichés dans la console. Production : SMTP (identifiants dans le .env).
if env("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST")
    EMAIL_PORT = int(env("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = env("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
    EMAIL_USE_TLS = True  # connexion chiffrée vers le serveur d'e-mails
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "AvisPilote <rapports@avispilote.local>")

# --- Paiement Stripe ---
# Clés en mode TEST (sk_test_…) pendant le développement. Les prix (price_…) se créent dans
# le tableau de bord Stripe : un produit par formule, prix récurrent mensuel.
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICES = {
    "starter": env("STRIPE_PRICE_STARTER"),
    "pro": env("STRIPE_PRICE_PRO"),
    "business": env("STRIPE_PRICE_BUSINESS"),
}
if DEBUG and STRIPE_SECRET_KEY.startswith("sk_live_"):
    raise RuntimeError("Clé Stripe RÉELLE (sk_live_) en développement : utilise une clé de test (sk_test_).")

# Mode démo : faux avis clairement signalés, jamais publiés. Désactivé en production.
DEMO_AUTORISEE = env("DEMO_AUTORISEE", "1" if DEBUG else "0") == "1"

# Limite de tentatives de connexion (par adresse IP et par e-mail)
CONNEXION_MAX_TENTATIVES = 10
CONNEXION_FENETRE_SECONDES = 600

LOGGING = {
    "version": 1,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"avispilote": {"handlers": ["console"], "level": "INFO"}},
}
