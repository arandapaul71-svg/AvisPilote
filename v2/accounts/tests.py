"""Tests des fonctions critiques : comptes, isolation, rôles, sécurité, suppression."""
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse

from billing.models import Subscription
from locations.models import GoogleConnection, Location

from .models import Membership, Organization, Role, User

MDP = "Croissant-Doré-2026"


def creer_compte(email, nom="Boulangerie Test", role=Role.OWNER):
    user = User.objects.create_user(email, MDP)
    org = Organization.objects.create(name=nom, sector="boulangerie")
    Membership.objects.create(user=user, organization=org, role=role)
    Subscription.creer_essai(org)
    return user, org


class InscriptionConnexionTests(TestCase):
    def test_inscription_cree_entreprise_et_essai(self):
        r = self.client.post(reverse("accounts:inscription"), {
            "entreprise": "Fleurs de Toulon", "secteur": "fleuriste",
            "email": "Paul@Example.com", "mot_de_passe": MDP, "cgu": "on",
        })
        self.assertRedirects(r, reverse("accounts:tableau_de_bord"))
        user = User.objects.get(email="paul@example.com")  # e-mail mis en minuscules
        self.assertEqual(user.membership.role, Role.OWNER)
        self.assertEqual(user.membership.organization.subscription.status, Subscription.Statut.ESSAI)
        self.assertNotEqual(user.password, MDP)  # mot de passe haché, jamais en clair

    def test_mot_de_passe_faible_refuse(self):
        r = self.client.post(reverse("accounts:inscription"), {
            "entreprise": "X", "secteur": "autre", "email": "a@b.fr", "mot_de_passe": "12345678", "cgu": "on",
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_connexion_puis_tableau_de_bord(self):
        creer_compte("gerant@test.fr")
        r = self.client.post(reverse("accounts:connexion"), {"email": "gerant@test.fr", "mot_de_passe": MDP})
        self.assertRedirects(r, reverse("accounts:tableau_de_bord"))
        self.assertContains(self.client.get(reverse("accounts:tableau_de_bord")), "Boulangerie Test")

    def test_limite_tentatives_connexion(self):
        creer_compte("gerant@test.fr")
        for _ in range(10):
            self.client.post(reverse("accounts:connexion"), {"email": "gerant@test.fr", "mot_de_passe": "faux"})
        # Même le bon mot de passe est refusé tant que le blocage dure.
        r = self.client.post(reverse("accounts:connexion"), {"email": "gerant@test.fr", "mot_de_passe": MDP})
        self.assertContains(r, "Trop de tentatives")

    def test_pages_protegees_sans_connexion(self):
        for nom in ["tableau_de_bord", "abonnement", "supprimer_compte"]:
            r = self.client.get(reverse(f"accounts:{nom}"))
            self.assertEqual(r.status_code, 302, nom)
            self.assertIn(reverse("accounts:connexion"), r["Location"])

    def test_deconnexion_uniquement_en_post(self):
        # Un lien piégé (GET) ne doit pas pouvoir déconnecter l'utilisateur.
        user, _ = creer_compte("gerant@test.fr")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("accounts:deconnexion")).status_code, 405)


class SecuriteTests(TestCase):
    def test_csrf_obligatoire(self):
        client = self.client_class(enforce_csrf_checks=True)
        r = client.post(reverse("accounts:connexion"), {"email": "x@y.fr", "mot_de_passe": "x"})
        self.assertEqual(r.status_code, 403)

    def test_entetes_de_securite(self):
        r = self.client.get(reverse("accounts:connexion"))
        self.assertIn("default-src 'self'", r["Content-Security-Policy"])
        self.assertEqual(r["X-Frame-Options"], "DENY")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")

    def test_xss_echappe(self):
        user, org = creer_compte("gerant@test.fr", nom="<script>alert(1)</script>")
        self.client.force_login(user)
        r = self.client.get(reverse("accounts:tableau_de_bord"))
        self.assertNotContains(r, "<script>alert(1)</script>")
        self.assertContains(r, "&lt;script&gt;")

    def test_jetons_google_chiffres_en_base(self):
        _, org = creer_compte("gerant@test.fr")
        GoogleConnection.objects.create(organization=org, refresh_token="jeton-secret-123")
        with connection.cursor() as c:
            c.execute("SELECT refresh_token FROM locations_googleconnection")
            brut = c.fetchone()[0]
        self.assertNotIn("jeton-secret-123", brut)
        self.assertEqual(GoogleConnection.objects.get().refresh_token, "jeton-secret-123")


class RolesEtSuppressionTests(TestCase):
    def test_lecture_seule_ne_peut_pas_supprimer(self):
        user, org = creer_compte("employe@test.fr", role=Role.VIEWER)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("accounts:supprimer_compte")).status_code, 403)
        self.client.post(reverse("accounts:supprimer_compte"), {"mot_de_passe": MDP, "confirmation": "SUPPRIMER"})
        self.assertTrue(Organization.objects.filter(pk=org.pk).exists())

    def test_suppression_efface_les_donnees_de_l_entreprise_seulement(self):
        user, org = creer_compte("gerant@test.fr")
        _, autre = creer_compte("autre@test.fr", nom="Autre commerce")
        Location.objects.create(organization=org, title="Ma fiche")
        Location.objects.create(organization=autre, title="Fiche de l'autre")
        self.client.force_login(user)

        r = self.client.post(reverse("accounts:supprimer_compte"), {"mot_de_passe": "faux", "confirmation": "SUPPRIMER"})
        self.assertEqual(r.status_code, 200)  # mauvais mot de passe : rien n'est supprimé
        self.assertTrue(Organization.objects.filter(pk=org.pk).exists())

        self.client.post(reverse("accounts:supprimer_compte"), {"mot_de_passe": MDP, "confirmation": "SUPPRIMER"})
        self.assertFalse(Organization.objects.filter(pk=org.pk).exists())
        self.assertFalse(User.objects.filter(email="gerant@test.fr").exists())
        self.assertFalse(Location.objects.filter(organization_id=org.pk).exists())
        self.assertTrue(Location.objects.filter(organization=autre).exists())


@override_settings(DEBUG=False)
class IsolationTests(TestCase):
    def test_chaque_entreprise_ne_voit_que_ses_donnees(self):
        user_a, _ = creer_compte("a@test.fr", nom="Boulangerie A")
        creer_compte("b@test.fr", nom="Fleuriste B")
        self.client.force_login(user_a)
        r = self.client.get(reverse("accounts:tableau_de_bord"))
        self.assertContains(r, "Boulangerie A")
        self.assertNotContains(r, "Fleuriste B")


class DemoExpressTests(TestCase):
    def test_un_clic_puis_reutilisation(self):
        r = self.client.post(reverse("accounts:demo_express"))
        self.assertRedirects(r, reverse("accounts:tableau_de_bord"))
        user = User.objects.get(email="demo@demo.avispilote.local")
        self.assertFalse(user.has_usable_password())  # impossible d'y entrer par le formulaire
        self.assertGreater(Location.objects.get(organization=user.membership.organization).reviews.count(), 50)
        self.client.logout()
        self.client.post(reverse("accounts:demo_express"))
        self.assertEqual(User.objects.filter(email="demo@demo.avispilote.local").count(), 1)

    @override_settings(DEMO_AUTORISEE=False)
    def test_desactivee_en_production(self):
        self.assertEqual(self.client.post(reverse("accounts:demo_express")).status_code, 404)
        self.assertNotContains(self.client.get(reverse("accounts:connexion")), "Découvrir avec la démo")

    def test_pages_legales(self):
        for nom in ("cgu", "confidentialite", "mentions"):
            self.assertEqual(self.client.get(reverse(f"accounts:{nom}")).status_code, 200)


class PresentationTests(TestCase):
    def test_visiteur_voit_la_presentation(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        for texte in ("Se connecter", "Essai gratuit", "9,99 €", "Voir la démo"):
            self.assertContains(r, texte)

    def test_connecte_va_au_tableau_de_bord(self):
        user, _ = creer_compte("gerant@test.fr")
        self.client.force_login(user)
        self.assertRedirects(self.client.get("/"), reverse("accounts:tableau_de_bord"))
        self.assertContains(self.client.get(reverse("accounts:tableau_de_bord")), 'class="sidebar"')
