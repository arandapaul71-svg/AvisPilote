"""Tests des quotas : consommation, réserve pour avis négatifs, renouvellement, fin d'essai."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import Organization

from . import plans, quotas
from .models import Subscription


class QuotaTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test")
        self.sub = Subscription.creer_essai(self.org)
        self.quota = plans.PLANS["starter"]["quota"]

    def test_quota_bloque_au_maximum(self):
        for _ in range(self.quota):
            self.assertTrue(quotas.consommer(self.sub, 1))
        self.assertFalse(quotas.consommer(self.sub, 1))
        e = quotas.etat(self.sub)
        self.assertTrue(e["atteint"])
        self.assertEqual(e["utilises"], self.quota)

    def test_reserve_pour_avis_negatifs(self):
        plafond_positifs = int(self.quota * (1 - plans.RESERVE_NEGATIFS))
        for _ in range(plafond_positifs):
            self.assertTrue(quotas.consommer(self.sub, 5))
        self.assertFalse(quotas.consommer(self.sub, 5))  # les positifs s'arrêtent
        self.assertTrue(quotas.consommer(self.sub, 1))   # les négatifs passent encore

    def test_alerte_a_80_pourcent(self):
        for _ in range(int(self.quota * 0.8)):
            quotas.consommer(self.sub, 1)
        self.assertTrue(quotas.etat(self.sub)["bientot_atteint"])

    def test_quota_remis_a_zero_au_renouvellement(self):
        for _ in range(self.quota):
            quotas.consommer(self.sub, 1)
        self.sub.status = Subscription.Statut.ACTIF
        self.sub.period_end = timezone.now() - timedelta(minutes=1)
        self.sub.save()
        self.assertTrue(quotas.consommer(self.sub, 1))
        self.assertEqual(quotas.etat(self.sub)["utilises"], 1)

    def test_essai_expire_bloque_l_ia(self):
        self.sub.trial_ends = timezone.now() - timedelta(days=1)
        self.sub.save()
        self.assertFalse(quotas.consommer(self.sub, 1))
