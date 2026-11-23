"""Tests des rapports : périodes, contenu, PDF, e-mail, envoi automatique, droits."""
from datetime import datetime, timedelta
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.tests import creer_compte
from locations.models import Location
from reviews.models import Review, ReviewAnalysis

from . import rapport_pdf, rapports


def _date(annee, mois, jour):
    return timezone.make_aware(datetime(annee, mois, jour, 12))


class BornesTests(TestCase):
    def test_mois_precedent(self):
        debut, fin, prec, titre = rapports.bornes("mois", 1, _date(2026, 3, 15))
        self.assertEqual((debut.month, debut.day, fin.month, prec.month), (2, 1, 3, 1))
        self.assertEqual(titre, "Février 2026")
        debut, _, prec, titre = rapports.bornes("mois", 1, _date(2026, 1, 5))  # changement d'année
        self.assertEqual((debut.year, debut.month, prec.month, titre), (2025, 12, 11, "Décembre 2025"))

    def test_semaine_precedente(self):
        debut, fin, _, titre = rapports.bornes("semaine", 1, _date(2026, 11, 25))  # mercredi
        self.assertEqual((debut.weekday(), debut.day, (fin - debut).days), (0, 16, 7))
        self.assertIn("16 novembre", titre)


class RapportTests(TestCase):
    def setUp(self):
        self.user, self.org = creer_compte("gerant@test.fr")
        self.fiche = Location.objects.create(organization=self.org, title="Boulangerie <b>Test</b>",
                                             google_location_name="a/1/l/1")
        debut, _, _, _ = rapports.bornes("mois", 1)
        for i, (etoiles, texte, neg) in enumerate([(5, "Super pain", []), (1, "Attente <script>x</script>", ["attente"]),
                                                    (4, "Bien", [])]):
            a = Review.objects.create(location=self.fiche, google_review_id=f"r{i}", author="A", stars=etoiles,
                                      comment=texte, created_at=debut + timedelta(days=3 + i))
            ReviewAnalysis.objects.create(review=a, sentiment="x", themes_negatifs=neg,
                                          themes_positifs=["qualite"] if etoiles >= 4 else [], source="regles")
        self.client.force_login(self.user)

    def test_contenu(self):
        r = rapports.construire(self.fiche, "mois", 1)
        self.assertEqual(r["ind"]["total"], 3)
        self.assertEqual(r["ff"]["defaut"][0]["theme"], "attente")
        self.assertIn("3 avis reçus", rapports.phrase_bilan(r))

    def test_pdf_valide_et_texte_echappe(self):
        pdf = rapport_pdf.generer(rapports.construire(self.fiche, "mois", 1))
        self.assertTrue(pdf.startswith(b"%PDF"))
        r = self.client.get(reverse("insights:rapport_pdf"), {"type": "mois", "decalage": "1"})
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn("attachment", r["Content-Disposition"])

    def test_envoi_manuel_et_limite(self):
        for _ in range(3):
            self.client.post(reverse("insights:rapport_envoyer"))
        self.assertEqual(len(mail.outbox), 3)
        m = mail.outbox[0]
        self.assertEqual(m.to, ["gerant@test.fr"])
        self.assertEqual(m.attachments[0][2], "application/pdf")
        html = m.alternatives[0][0]
        self.assertNotIn("<b>Test</b>", html)  # nom échappé dans l'e-mail HTML
        self.client.post(reverse("insights:rapport_envoyer"))
        self.assertEqual(len(mail.outbox), 3)  # 4e envoi dans l'heure refusé

    def test_commande_automatique_une_fois_par_periode(self):
        call_command("envoyer_rapports", stdout=StringIO())
        call_command("envoyer_rapports", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)
        self.org.refresh_from_db()
        self.assertTrue(self.org.dernier_rapport)

    def test_desabonnement_respecte(self):
        self.client.post(reverse("insights:rapports"), {"rapport_frequence": "semaine"})  # case décochée
        self.org.refresh_from_db()
        self.assertFalse(self.org.rapport_email)
        self.assertEqual(self.org.rapport_frequence, "semaine")
        call_command("envoyer_rapports", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

    def test_starter_payant_sans_rapports(self):
        sub = self.org.subscription
        sub.status = "actif"
        sub.save()
        self.assertContains(self.client.get(reverse("insights:rapports")), "formule")
        self.assertEqual(self.client.get(reverse("insights:rapport_pdf")).status_code, 404)
        call_command("envoyer_rapports", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 0)

    def test_employe_ne_peut_ni_envoyer_ni_regler(self):
        employe, org = creer_compte("employe@test.fr", role=Role.MANAGER)
        Location.objects.create(organization=org, title="X")
        self.client.force_login(employe)
        self.assertEqual(self.client.post(reverse("insights:rapport_envoyer")).status_code, 403)
        self.assertEqual(self.client.post(reverse("insights:rapports"), {"rapport_frequence": "mois"}).status_code, 403)
