"""Tests du tableau de bord et des analyses : chiffres justes, périodes, isolation, rendu SVG."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.tests import creer_compte
from locations.models import Location
from reviews.models import Mode, ReplyDraft, Review, ReviewAnalysis

from . import graphiques, stats
from .templatetags.insights_tags import duree


class StatsTests(TestCase):
    def setUp(self):
        self.user, self.org = creer_compte("gerant@test.fr")
        self.fiche = Location.objects.create(organization=self.org, title="Fiche", google_location_name="a/1/l/1",
                                             average_rating=4.2, total_review_count=120)
        maintenant = timezone.now()

        def avis(rid, etoiles, jours, reponse_apres=None, texte="Texte"):
            a = Review.objects.create(location=self.fiche, google_review_id=rid, author="A", stars=etoiles,
                                      comment=texte, created_at=maintenant - timedelta(days=jours))
            if reponse_apres:
                a.google_reply = "Merci"
                a.google_reply_at = a.created_at + reponse_apres
                a.save()
            return a

        # Période 7 jours : 3 avis (5, 4, 1). Période précédente : 1 avis (2).
        self.a1 = avis("r1", 5, 1, reponse_apres=timedelta(hours=2), texte="Accueil adorable")
        self.a2 = avis("r2", 4, 2, reponse_apres=timedelta(hours=4))
        self.a3 = avis("r3", 1, 3, texte="Attente interminable")
        avis("r4", 2, 10)
        ReviewAnalysis.objects.create(review=self.a1, sentiment="positif", themes_positifs=["accueil"], source="regles")
        ReviewAnalysis.objects.create(review=self.a3, sentiment="negatif", themes_negatifs=["attente"], source="regles")
        ReplyDraft.objects.create(review=self.a1, text="Merci", source="ia", decision=Mode.AUTO,
                                  status=ReplyDraft.Statut.PUBLIEE)

    def test_indicateurs(self):
        i = stats.indicateurs(self.fiche, "7j")
        self.assertEqual((i["total"], i["positifs"], i["neutres"], i["negatifs"]), (3, 2, 0, 1))
        self.assertEqual(i["total_delta"], 2)
        self.assertEqual(i["note_periode"], 3.33)
        self.assertEqual(i["note_delta"], 1.33)
        self.assertEqual(i["taux_reponse"], 67)
        self.assertEqual(i["delai_moyen"], timedelta(hours=3))
        self.assertEqual((i["reponses_ia"], i["publiees_auto"]), (1, 1))

    def test_series_et_note_cumulee(self):
        serie = stats.series(self.fiche, "7j")
        self.assertEqual(sum(s["total"] for s in serie), 3)
        # Note cumulée finale = moyenne de TOUS les avis (5+4+1+2)/4
        self.assertEqual(serie[-1]["note_cumulee"], 3.0)

    def test_regroupement_par_semaine_et_mois(self):
        self.assertLessEqual(len(stats.series(self.fiche, "3m")), 15)
        self.assertLessEqual(len(stats.series(self.fiche, "1an")), 13)

    def test_forces_faiblesses_avec_exemples_et_solutions(self):
        ff = stats.forces_faiblesses(self.fiche, "7j")
        self.assertEqual(ff["analyses"], 2)
        self.assertEqual(ff["qualite"][0]["theme"], "accueil")
        self.assertEqual(ff["qualite"][0]["exemples"], ["Accueil adorable"])
        self.assertTrue(ff["defaut"][0]["solutions"])

    def test_periode_inconnue_remplacee(self):
        self.assertEqual(stats.periode_valide("pirate"), "30j")

    def test_graphiques_sans_virgule_dans_les_coordonnees(self):
        serie = stats.series(self.fiche, "30j")
        for g in (graphiques.colonnes_empilees(serie), graphiques.courbe_note(serie)):
            self.assertFalse(g["vide"])
        self.client.force_login(self.user)
        html = self.client.get(reverse("accounts:tableau_de_bord"), {"periode": "30j"}).content.decode()
        # Les nombres français (« 194,0 ») casseraient le SVG : les coordonnées doivent utiliser un point.
        import re
        self.assertFalse(re.search(r' (?:x|y|x1|x2|y1|y2|cx|cy|width|height)="[^"]*\d,\d', html))
        self.assertIn("<svg", html)

    def test_duree(self):
        self.assertEqual(duree(timedelta(minutes=25)), "25 min")
        self.assertEqual(duree(timedelta(hours=26)), "1 j 2 h")


class VuesStatsTests(TestCase):
    def test_isolation_et_acces(self):
        user, org = creer_compte("a@test.fr", nom="A")
        _, autre = creer_compte("b@test.fr", nom="B")
        fiche_b = Location.objects.create(organization=autre, title="B")
        Review.objects.create(location=fiche_b, google_review_id="x", author="Z", stars=1,
                              comment="Secret B", created_at=timezone.now())
        ReviewAnalysis.objects.create(review=Review.objects.get(), sentiment="negatif",
                                      themes_negatifs=["attente"], source="regles")
        Location.objects.create(organization=org, title="A")
        self.client.force_login(user)
        r = self.client.get(reverse("insights:analyses"))
        self.assertNotContains(r, "Secret B")
        self.assertContains(r, "Aucun avis analysé")
        self.client.logout()
        self.assertEqual(self.client.get(reverse("insights:analyses")).status_code, 302)
