"""Abonnement et compteur d'utilisation. Prévu pour Stripe (identifiants déjà en place)."""
from datetime import timedelta

from django.db import models
from django.utils import timezone

from accounts.models import Organization

from . import plans


class Subscription(models.Model):
    class Statut(models.TextChoices):
        ESSAI = "essai", "Essai gratuit"
        ACTIF = "actif", "Actif"
        IMPAYE = "impaye", "Paiement en échec"
        ANNULE = "annule", "Annulé"

    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="subscription")
    plan = models.CharField(max_length=20, choices=[(k, v["nom"]) for k, v in plans.PLANS.items()],
                            default=plans.PLAN_PAR_DEFAUT)
    status = models.CharField(max_length=10, choices=Statut.choices, default=Statut.ESSAI)
    trial_ends = models.DateTimeField(null=True, blank=True)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True)

    @classmethod
    def creer_essai(cls, organization):
        maintenant = timezone.now()
        return cls.objects.create(
            organization=organization,
            status=cls.Statut.ESSAI,
            trial_ends=maintenant + timedelta(days=plans.ESSAI_JOURS),
            period_start=maintenant,
            period_end=maintenant + timedelta(days=plans.DUREE_PERIODE_JOURS),
        )

    @property
    def infos_plan(self):
        return plans.PLANS.get(self.plan, plans.PLANS[plans.PLAN_PAR_DEFAUT])

    @property
    def est_utilisable(self):
        """L'IA ne travaille que pendant l'essai (non expiré) ou un abonnement actif."""
        if self.status == self.Statut.ESSAI:
            return self.trial_ends is not None and timezone.now() < self.trial_ends
        return self.status == self.Statut.ACTIF

    def a_la_fonction(self, fonction):
        # Pendant l'essai, on fait découvrir les fonctions de la formule Pro (meilleure conversion).
        if self.status == self.Statut.ESSAI and self.est_utilisable:
            return fonction in plans.PLANS["pro"]["fonctions"] | self.infos_plan["fonctions"]
        return fonction in self.infos_plan["fonctions"]

    def renouveler_si_besoin(self):
        """Passe à la période suivante quand la date de fin est dépassée (le quota repart à zéro).
        Abonnement Stripe : ce sont les webhooks de paiement qui font avancer la période."""
        if self.stripe_subscription_id:
            return
        maintenant = timezone.now()
        change = False
        while self.period_end <= maintenant:
            self.period_start = self.period_end
            self.period_end = self.period_start + timedelta(days=plans.DUREE_PERIODE_JOURS)
            change = True
        if change:
            self.save(update_fields=["period_start", "period_end"])


class StripeEvent(models.Model):
    """Événements Stripe déjà traités : Stripe peut renvoyer le même événement plusieurs fois."""

    event_id = models.CharField(max_length=100, unique=True)
    type = models.CharField(max_length=100)
    received_at = models.DateTimeField(auto_now_add=True)


class UsageCounter(models.Model):
    """Nombre d'avis traités par l'IA pendant une période d'abonnement."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="usage")
    period_start = models.DateTimeField()
    reviews_processed = models.PositiveIntegerField(default=0)
    positive_processed = models.PositiveIntegerField(default=0)  # avis 3-5★, pour la réserve négatifs

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "period_start"], name="compteur_unique")]
