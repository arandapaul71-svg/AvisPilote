"""Alertes (anomalies détectées) et recommandations suivies dans le temps."""
from django.db import models

from locations.models import Location


class Alert(models.Model):
    class Niveau(models.TextChoices):
        ATTENTION = "attention", "Attention"
        INFO = "info", "Information"
        POSITIF = "positif", "Bonne nouvelle"

    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="alerts")
    kind = models.CharField(max_length=40)  # hausse_negatifs, plainte_recurrente, baisse_note, pic_avis, amelioration
    cle = models.CharField(max_length=60, blank=True)  # thème ou date : évite les doublons
    niveau = models.CharField(max_length=10, choices=Niveau.choices, default=Niveau.ATTENTION)
    message = models.TextField()
    details = models.JSONField(default=dict)  # chiffres de comparaison (période, habituel…)
    evidence_review_ids = models.JSONField(default=list)  # avis qui justifient l'alerte
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class Recommendation(models.Model):
    class Statut(models.TextChoices):
        OUVERTE = "ouverte", "À traiter"
        EN_COURS = "en_cours", "En cours"
        RESOLUE = "resolue", "Résolue"

    class Importance(models.TextChoices):
        HAUTE = "haute", "Haute"
        MOYENNE = "moyenne", "Moyenne"
        BASSE = "basse", "Basse"

    class Type(models.TextChoices):
        CORRIGER = "corriger", "Problème à corriger"
        VALORISER = "valoriser", "Point fort à valoriser"

    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="recommendations")
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.CORRIGER)
    theme = models.CharField(max_length=40)
    titre = models.CharField(max_length=200, default="")
    problem = models.TextField()
    evidence_review_ids = models.JSONField(default=list)
    importance = models.CharField(max_length=10, choices=Importance.choices)
    actions = models.JSONField(default=list)
    status = models.CharField(max_length=10, choices=Statut.choices, default=Statut.OUVERTE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status_changed_at = models.DateTimeField(null=True, blank=True)  # début du suivi de l'effet des actions

    class Meta:
        ordering = ["status", "-updated_at"]
