"""Avis, analyses IA, brouillons de réponse et réglages de l'assistant.

On sépare bien trois choses :
- Review : l'avis récupéré chez Google (toujours stocké et consultable) ;
- ReviewAnalysis : l'analyse IA (seulement si le quota le permet) ;
- ReplyDraft : les réponses proposées / modifiées / publiées.
"""
from django.db import models

from locations.models import Location


class Mode(models.TextChoices):
    AUTO = "auto", "Automatique"
    VALIDATION = "validation", "À valider"
    MANUEL = "manuel", "Manuel"


def modes_par_defaut():
    # Avis 4-5★ publiés automatiquement, 1-3★ toujours validés par un humain.
    return {"5": Mode.AUTO, "4": Mode.AUTO, "3": Mode.VALIDATION, "2": Mode.VALIDATION, "1": Mode.VALIDATION}


class AISettings(models.Model):
    class Ton(models.TextChoices):
        PROFESSIONNEL = "professionnel", "Professionnel"
        CHALEUREUX = "chaleureux", "Chaleureux"
        CONVIVIAL = "convivial", "Convivial"
        ELEGANT = "elegant", "Élégant"
        DECONTRACTE = "decontracte", "Décontracté"

    class Longueur(models.TextChoices):
        COURTE = "courte", "Courte (1-2 phrases)"
        MOYENNE = "moyenne", "Moyenne (3-4 phrases)"
        LONGUE = "longue", "Détaillée"

    location = models.OneToOneField(Location, on_delete=models.CASCADE, related_name="ai_settings")
    tone = models.CharField("ton", max_length=15, choices=Ton.choices, default=Ton.CHALEUREUX)
    length = models.CharField("longueur", max_length=10, choices=Longueur.choices, default=Longueur.MOYENNE)
    emojis = models.BooleanField("émojis", default=False)
    tutoiement = models.BooleanField(default=False)
    preferred_phrases = models.TextField("expressions à privilégier", blank=True, max_length=1000)
    forbidden_phrases = models.TextField("expressions interdites", blank=True, max_length=1000)
    business_info = models.TextField("informations sur l'établissement", blank=True, max_length=2000)
    negative_instructions = models.TextField("consignes pour les avis négatifs", blank=True, max_length=1000)
    signature = models.CharField(max_length=120, blank=True)
    mode_by_stars = models.JSONField(default=modes_par_defaut)
    sensitive_requires_validation = models.BooleanField("avis sensibles toujours validés", default=True)

    def mode_pour(self, etoiles):
        return self.mode_by_stars.get(str(etoiles), Mode.VALIDATION)


class Review(models.Model):
    class StatutIA(models.TextChoices):
        NON_TRAITE = "non_traite", "En attente"
        TRAITE = "traite", "Traité"
        HORS_QUOTA = "hors_quota", "Hors quota"

    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="reviews")
    google_review_id = models.CharField(max_length=200)
    author = models.CharField(max_length=200)
    stars = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField()
    google_reply = models.TextField(blank=True)  # réponse déjà présente chez Google
    google_reply_at = models.DateTimeField(null=True, blank=True)
    policy_violation = models.CharField(max_length=200, blank=True)
    ai_status = models.CharField(max_length=12, choices=StatutIA.choices, default=StatutIA.NON_TRAITE)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["location", "google_review_id"], name="avis_unique_par_fiche"),
            models.CheckConstraint(condition=models.Q(stars__gte=1, stars__lte=5), name="etoiles_1_a_5"),
        ]
        indexes = [models.Index(fields=["location", "created_at"])]


class ReviewAnalysis(models.Model):
    class Sentiment(models.TextChoices):
        POSITIF = "positif", "Positif"
        NEUTRE = "neutre", "Neutre"
        NEGATIF = "negatif", "Négatif"

    review = models.OneToOneField(Review, on_delete=models.CASCADE, related_name="analysis")
    sentiment = models.CharField(max_length=10, choices=Sentiment.choices)
    themes_positifs = models.JSONField(default=list)
    themes_negatifs = models.JSONField(default=list)
    sensitive_flags = models.JSONField(default=list)  # ex. ["sanitaire", "remboursement"]
    actions = models.JSONField(default=list)  # solutions proposées au commerçant (jamais publiées)
    source = models.CharField(max_length=40)  # "regles" ou nom du modèle IA
    created_at = models.DateTimeField(auto_now_add=True)


class ReplyDraft(models.Model):
    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        A_VALIDER = "a_valider", "À valider"
        PUBLIEE = "publiee", "Publiée"
        REJETEE = "rejetee", "Rejetée par Google"

    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="drafts")
    text = models.TextField(max_length=4000)
    source = models.CharField(max_length=10, choices=[("ia", "IA"), ("humain", "Humain")])
    status = models.CharField(max_length=10, choices=Statut.choices, default=Statut.A_VALIDER)
    quality_checks = models.JSONField(default=list)  # problèmes détectés par le contrôle qualité
    # Pourquoi ce brouillon est (ou n'est pas) publié automatiquement : affiché au commerçant.
    decision = models.CharField(max_length=10, choices=Mode.choices, default=Mode.VALIDATION)
    reasons = models.JSONField(default=list)
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
