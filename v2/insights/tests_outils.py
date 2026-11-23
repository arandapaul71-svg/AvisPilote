"""Tests du QR code et du simulateur de note."""
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from accounts.tests import creer_compte
from locations.models import Location

from . import outils

LIEN = "https://g.page/r/CabcDEF123/review"


class SimulateurTests(TestCase):
    def test_avis_5_necessaires(self):
        # 4,2 sur 150 avis → afficher 4,5 demande une moyenne ≥ 4,45 : k ≥ 150 × 0,25 / 0,55 = 68,2
        self.assertEqual(outils.avis_5_necessaires(4.2, 150, 4.5), 69)
        # Vérification : avec 69 avis 5★ la note affichée est bien 4,5, avec 68 non.
        self.assertGreaterEqual(outils.note_apres(4.2, 150, 69, 5), 4.45)
        self.assertLess(outils.note_apres(4.2, 150, 68, 5), 4.45)

    def test_cas_limites(self):
        self.assertEqual(outils.avis_5_necessaires(4.6, 80, 4.5), 0)  # déjà atteint
        self.assertEqual(outils.avis_5_necessaires(4.6, 80, 5.0), 560)  # possible mais énorme : on le dit
        self.assertIsNone(outils.avis_5_necessaires(4.6, 80, 5.1))
        self.assertEqual(round(outils.note_apres(4.0, 10, 10, 5), 2), 4.5)

    def test_solidite(self):
        k = outils.avis_1_pour_baisser(4.5, 100)
        # Après k avis 1★, la note affichée descend sous 4,5 ; pas avant.
        self.assertLess(outils.note_apres(4.5, 100, k, 1), 4.45)
        self.assertGreaterEqual(outils.note_apres(4.5, 100, k - 1, 1), 4.45)


class QRTests(TestCase):
    def setUp(self):
        self.user, self.org = creer_compte("gerant@test.fr")
        self.fiche = Location.objects.create(organization=self.org, title="Ma boulangerie",
                                             average_rating=4.2, total_review_count=150)
        self.client.force_login(self.user)

    def test_lien_google_seulement(self):
        outils.valider_lien_avis(LIEN)
        for mauvais in ["http://g.page/r/x/review", "https://g.page.pirate.com/x", "javascript:alert(1)",
                        "https://evil.example/review"]:
            with self.assertRaises(ValidationError, msg=mauvais):
                outils.valider_lien_avis(mauvais)

    def test_enregistrer_lien_puis_qr_et_telechargements(self):
        r = self.client.post(reverse("insights:outils"), {"lien": "https://evil.example/r"})
        self.assertContains(r, "Demander des avis")
        self.fiche.refresh_from_db()
        self.assertEqual(self.fiche.new_review_uri, "")

        self.client.post(reverse("insights:outils"), {"lien": LIEN})
        self.fiche.refresh_from_db()
        self.assertEqual(self.fiche.new_review_uri, LIEN)
        page = self.client.get(reverse("insights:outils"))
        self.assertContains(page, "<svg")
        png = self.client.get(reverse("insights:qr_telecharger", args=["png"]))
        self.assertEqual(png["Content-Type"], "image/png")
        self.assertTrue(png.content.startswith(b"\x89PNG"))
        self.assertIn("attachment", png["Content-Disposition"])
        self.assertEqual(self.client.get(reverse("insights:qr_telecharger", args=["exe"])).status_code, 404)
        self.assertContains(self.client.get(reverse("insights:qr_affiche")), "Votre avis nous intéresse")

    def test_lecteur_ne_peut_pas_changer_le_lien(self):
        lecteur, org = creer_compte("lecteur@test.fr", role=Role.VIEWER)
        Location.objects.create(organization=org, title="X")
        self.client.force_login(lecteur)
        self.assertEqual(self.client.post(reverse("insights:outils"), {"lien": LIEN}).status_code, 403)

    def test_simulateur_dans_la_page(self):
        r = self.client.get(reverse("insights:outils"), {"cible": "4.5"})
        self.assertContains(r, "69 avis 5 ★")
        r = self.client.get(reverse("insights:outils"), {"ajout": "10", "etoiles": "1"})
        self.assertContains(r, "Ta note passerait à")
        # Valeurs hors limites : ignorées sans erreur.
        self.assertEqual(self.client.get(reverse("insights:outils"), {"cible": "9", "ajout": "-3"}).status_code, 200)
