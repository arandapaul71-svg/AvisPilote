"""Tests du paiement Stripe. Les appels à Stripe sont simulés (mock) ; les signatures de webhook
sont calculées comme le fait Stripe, pour tester la vraie vérification du SDK."""
import hashlib
import hmac
import json
import time
from unittest import mock

import stripe
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.tests import MDP, creer_compte

from . import paiement, quotas
from .models import StripeEvent, Subscription

SECRET = "whsec_test_secret"
STRIPE_OK = override_settings(
    STRIPE_SECRET_KEY="sk_test_x", STRIPE_WEBHOOK_SECRET=SECRET,
    STRIPE_PRICES={"starter": "price_starter", "pro": "price_pro", "business": "price_business"},
)


def signer(payload, secret=SECRET, t=None):
    t = t or int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.{payload}".encode(), hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


def abonnement(statut="active", prix="price_pro", debut=None, fin=None):
    debut = debut or int(time.time())
    fin = fin or debut + 30 * 86400
    return stripe.Subscription.construct_from({
        "id": "sub_123", "customer": "cus_123", "status": statut,
        "items": {"object": "list", "data": [{"id": "si_1", "price": {"id": prix},
                                              "current_period_start": debut, "current_period_end": fin}]},
    }, "sk_test_x")


@STRIPE_OK
class WebhookTests(TestCase):
    def setUp(self):
        self.user, self.org = creer_compte("gerant@test.fr")
        self.sub = self.org.subscription
        self.sub.stripe_customer_id = "cus_123"
        self.sub.save()

    def envoyer(self, type_, objet, signature=None, event_id="evt_1"):
        payload = json.dumps({"id": event_id, "object": "event", "type": type_, "data": {"object": objet}})
        return self.client.post(reverse("billing:webhook"), data=payload, content_type="application/json",
                                HTTP_STRIPE_SIGNATURE=signature or signer(payload))

    def test_signature_invalide_refusee(self):
        r = self.envoyer("customer.subscription.updated", {"id": "sub_123"}, signature="t=1,v1=faux")
        self.assertEqual(r.status_code, 400)
        payload = json.dumps({"id": "evt_x", "type": "x", "data": {"object": {}}})
        r = self.client.post(reverse("billing:webhook"), data=payload, content_type="application/json",
                             HTTP_STRIPE_SIGNATURE=signer(payload, secret="whsec_pirate"))
        self.assertEqual(r.status_code, 400)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, Subscription.Statut.ESSAI)

    def test_abonnement_active_et_quota_remis_a_zero(self):
        quotas.consommer(self.sub, 1)
        with mock.patch.object(paiement, "_client") as client:
            client.return_value.v1.subscriptions.retrieve.return_value = abonnement()
            r = self.envoyer("checkout.session.completed", {"id": "cs_1", "customer": "cus_123", "subscription": "sub_123"})
        self.assertEqual(r.status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual((self.sub.status, self.sub.plan, self.sub.stripe_subscription_id),
                         (Subscription.Statut.ACTIF, "pro", "sub_123"))
        self.assertEqual(quotas.etat(self.sub)["utilises"], 0)  # nouvelle période payée
        self.assertEqual(quotas.etat(self.sub)["quota"], 200)

    def test_evenement_rejoue_traite_une_seule_fois(self):
        with mock.patch.object(paiement, "_client") as client:
            client.return_value.v1.subscriptions.retrieve.return_value = abonnement()
            self.envoyer("customer.subscription.updated", {"id": "sub_123"})
            self.assertEqual(self.envoyer("customer.subscription.updated", {"id": "sub_123"}).content, b"deja_traite")
            self.assertEqual(client.return_value.v1.subscriptions.retrieve.call_count, 1)
        self.assertEqual(StripeEvent.objects.count(), 1)

    def test_impaye_puis_annule_bloquent_l_ia(self):
        self.envoyer("invoice.payment_failed", {"id": "in_1", "customer": "cus_123"})
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, Subscription.Statut.IMPAYE)
        self.assertFalse(self.sub.est_utilisable)
        with mock.patch.object(paiement, "_client") as client:
            client.return_value.v1.subscriptions.retrieve.return_value = abonnement(statut="canceled")
            self.envoyer("customer.subscription.deleted", {"id": "sub_123"}, event_id="evt_2")
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, Subscription.Statut.ANNULE)
        self.assertEqual(self.sub.stripe_subscription_id, "")

    def test_changement_de_formule_par_le_portail(self):
        with mock.patch.object(paiement, "_client") as client:
            client.return_value.v1.subscriptions.retrieve.return_value = abonnement(prix="price_business")
            self.envoyer("customer.subscription.updated", {"id": "sub_123"})
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.plan, "business")

    def test_client_inconnu_ignore(self):
        with mock.patch.object(paiement, "_client") as client:
            client.return_value.v1.subscriptions.retrieve.return_value = stripe.Subscription.construct_from(
                {**abonnement().to_dict(), "customer": "cus_autre"}, "k")
            self.assertEqual(self.envoyer("customer.subscription.updated", {"id": "sub_x"}).status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, Subscription.Statut.ESSAI)


@STRIPE_OK
class PaiementVuesTests(TestCase):
    def setUp(self):
        self.user, self.org = creer_compte("gerant@test.fr")
        self.client.force_login(self.user)

    def test_payer_redirige_vers_stripe_avec_essai_conserve(self):
        with mock.patch.object(paiement, "_client") as client:
            client.return_value.v1.customers.create.return_value = mock.Mock(id="cus_new")
            client.return_value.v1.checkout.sessions.create.return_value = mock.Mock(url="https://checkout.stripe.com/c/pay/x")
            r = self.client.post(reverse("billing:payer"), {"plan": "pro"})
            params = client.return_value.v1.checkout.sessions.create.call_args.kwargs["params"]
        self.assertEqual(r["Location"], "https://checkout.stripe.com/c/pay/x")
        self.assertEqual(params["line_items"], [{"price": "price_pro", "quantity": 1}])
        self.assertEqual(params["subscription_data"]["trial_end"], int(self.org.subscription.trial_ends.timestamp()))
        self.org.subscription.refresh_from_db()
        self.assertEqual(self.org.subscription.stripe_customer_id, "cus_new")
        # Le retour du navigateur n'active rien : seul le webhook le fera.
        self.client.get(reverse("accounts:abonnement"), {"paiement": "ok"})
        self.org.subscription.refresh_from_db()
        self.assertEqual(self.org.subscription.status, Subscription.Statut.ESSAI)

    def test_formule_inventee_refusee(self):
        with mock.patch.object(paiement, "_client") as client:
            self.client.post(reverse("billing:payer"), {"plan": "gratuit_a_vie"})
            client.assert_not_called()

    def test_seul_le_gerant_paie(self):
        employe, _ = creer_compte("employe@test.fr", role=Role.MANAGER)
        self.client.force_login(employe)
        self.assertEqual(self.client.post(reverse("billing:payer"), {"plan": "pro"}).status_code, 403)

    def test_suppression_du_compte_resilie_stripe(self):
        sub = self.org.subscription
        sub.stripe_customer_id, sub.stripe_subscription_id, sub.status = "cus_1", "sub_1", "actif"
        sub.save()
        with mock.patch.object(paiement, "_client") as client:
            self.client.post(reverse("accounts:supprimer_compte"), {"mot_de_passe": MDP, "confirmation": "SUPPRIMER"})
            client.return_value.v1.subscriptions.cancel.assert_called_once_with("sub_1")

    @override_settings(STRIPE_SECRET_KEY="")
    def test_sans_stripe_pas_de_bouton(self):
        r = self.client.get(reverse("accounts:abonnement"))
        self.assertNotContains(r, "Choisir Pro")
        self.assertContains(r, "pas encore activé")


class EssaiSansStripeTests(TestCase):
    def test_periode_stripe_non_avancee_localement(self):
        _, org = creer_compte("x@test.fr")
        sub = org.subscription
        sub.stripe_subscription_id = "sub_1"
        sub.period_end = timezone.now() - timezone.timedelta(days=1)
        sub.save()
        sub.renouveler_si_besoin()
        self.assertLess(sub.period_end, timezone.now())  # seul Stripe fait avancer la période
