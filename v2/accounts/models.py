"""Comptes : utilisateurs, organisations (entreprises) et rôles.

Une organisation = une entreprise cliente. Toutes les données métier
(établissements, avis, abonnement…) sont rattachées à une organisation,
et chaque requête est filtrée par l'organisation de l'utilisateur connecté.
"""
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("L'adresse e-mail est obligatoire")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)  # hachage PBKDF2 par Django, jamais en clair
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)


class User(AbstractUser):
    """Utilisateur identifié par son e-mail (pas de nom d'utilisateur)."""

    username = None
    email = models.EmailField("adresse e-mail", unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email


class Secteur(models.TextChoices):
    BOULANGERIE = "boulangerie", "Boulangerie / pâtisserie"
    RESTAURANT = "restaurant", "Restaurant / café"
    FLEURISTE = "fleuriste", "Fleuriste"
    COIFFEUR = "coiffeur", "Coiffure / beauté"
    HOTEL = "hotel", "Hôtel / hébergement"
    COMMERCE = "commerce", "Commerce de détail"
    ARTISAN = "artisan", "Artisan / services"
    AUTRE = "autre", "Autre"


class Organization(models.Model):
    name = models.CharField("nom de l'entreprise", max_length=120)
    sector = models.CharField("secteur", max_length=20, choices=Secteur.choices, default=Secteur.AUTRE)
    created_at = models.DateTimeField(auto_now_add=True)
    # Rapports envoyés par e-mail au gérant (désactivables).
    rapport_email = models.BooleanField("recevoir le rapport par e-mail", default=True)
    rapport_frequence = models.CharField("fréquence", max_length=10, default="mois",
                                         choices=[("mois", "Chaque mois"), ("semaine", "Chaque semaine")])
    dernier_rapport = models.CharField(max_length=40, blank=True)  # titre du dernier rapport envoyé (anti-doublon)

    def __str__(self):
        return self.name


class Role(models.TextChoices):
    OWNER = "owner", "Gérant"
    MANAGER = "manager", "Responsable"
    VIEWER = "viewer", "Lecture seule"


class Membership(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="membership")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.OWNER)
    created_at = models.DateTimeField(auto_now_add=True)

    # Ce que chaque rôle a le droit de faire (vérifié côté serveur, jamais seulement dans l'interface).
    PERMISSIONS = {
        Role.OWNER: {"voir", "repondre", "regler_ia", "abonnement", "google", "supprimer_compte", "journal"},
        Role.MANAGER: {"voir", "repondre", "regler_ia"},
        Role.VIEWER: {"voir"},
    }

    def peut(self, action):
        return action in self.PERMISSIONS.get(self.role, set())

    def __str__(self):
        return f"{self.user} → {self.organization} ({self.role})"
