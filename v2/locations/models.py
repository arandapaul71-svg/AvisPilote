"""Établissements (fiches Google) et connexion au compte Google."""
from django.db import models

from accounts.crypto import EncryptedTextField
from accounts.models import Organization, Secteur


class GoogleConnection(models.Model):
    class Statut(models.TextChoices):
        OK = "ok", "Connectée"
        EXPIREE = "expiree", "Autorisation expirée"
        REVOQUEE = "revoquee", "Accès retiré"

    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="google")
    google_account = models.CharField(max_length=200, blank=True)
    refresh_token = EncryptedTextField(null=True, blank=True)
    access_token = EncryptedTextField(null=True, blank=True)
    token_expiry = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Statut.choices, default=Statut.OK)
    created_at = models.DateTimeField(auto_now_add=True)


class Location(models.Model):
    """Un établissement géré. Soit une vraie fiche Google, soit une fiche de démonstration."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="locations")
    title = models.CharField("nom affiché", max_length=200)
    sector = models.CharField(max_length=20, choices=Secteur.choices, default=Secteur.AUTRE)
    google_location_name = models.CharField(max_length=200, blank=True)  # ex. accounts/1/locations/2
    new_review_uri = models.URLField(blank=True)  # lien « laisser un avis » (QR code)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    total_review_count = models.PositiveIntegerField(null=True, blank=True)
    is_demo = models.BooleanField(default=False)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "google_location_name"],
                condition=~models.Q(google_location_name=""),
                name="fiche_google_unique_par_organisation",
            )
        ]

    def __str__(self):
        return self.title
