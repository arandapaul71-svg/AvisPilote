"""Tests de la détection d'anomalies et des recommandations.

Données construites à la main pour savoir exactement ce qui doit, ou ne doit pas, déclencher une alerte.
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.tests import creer_compte
from locations.models import Location
from reviews.models import Review, ReviewAnalysis

from . import detection, recommandations
from .models import Alert, Recommendation


class Base(TestCase):
    def setUp(self):
        self.user, self.org = creer_compte("gerant@test.fr")
        self.fiche = Location.objects.create(organization=self.org, title="Fiche", sector="boulangerie")
        self.maintenant = timezone.now()
        self.n = 0

    def avis(self, etoiles, il_y_a_jours, texte="", negatifs=(), positifs=()):
        self.n += 1
        a = Review.objects.create(location=self.fiche, google_review_id=f"r{self.n}", author="A", stars=etoiles,
                                  comment=texte, created_at=self.maintenant - timedelta(days=il_y_a_jours, hours=1))
        ReviewAnalysis.objects.create(review=a, sentiment="x", themes_negatifs=list(negatifs),
                                      themes_positifs=list(positifs), source="regles")
        return a

    def historique_calme(self):
        # 8 semaines normales : 1 avis positif tous les 2 jours, 1 négatif toutes les 2 semaines.
        for j in range(8, 63, 2):
            self.avis(5, j, "Très bon", positifs=["qualite"])
        for j in (14, 28, 42, 56):
            self.avis(2, j, "Bof", negatifs=["prix"])


class DetectionTests(Base):
    def test_hausse_negatifs_et_plainte_recurrente(self):
        self.historique_calme()
        for j in range(4):
            self.avis(1, j, "Attendu 30 minutes", negatifs=["attente"])
        nouvelles = detection.analyser(self.fiche, self.maintenant)
        types = {a.kind for a in nouvelles}
        self.assertIn("hausse_negatifs", types)
        self.assertIn("plainte_recurrente", types)
        hausse = next(a for a in nouvelles if a.kind == "hausse_negatifs")
        self.assertIn("4 avis négatifs cette semaine", hausse.message)
        self.assertIn("attente", hausse.message)
        self.assertEqual(len(hausse.evidence_review_ids), 4)

    def test_pas_de_fausse_alerte_avec_peu_d_avis(self):
        self.historique_calme()
        self.avis(1, 0, "Pas content", negatifs=["attente"])
        self.avis(1, 1, "Attente", negatifs=["attente"])  # 2 avis : sous le minimum de 3
        self.assertEqual([a.kind for a in detection.analyser(self.fiche, self.maintenant)], [])

    def test_pas_d_alerte_si_c_est_habituel(self):
        # Le prix est critiqué tous les 2 jours depuis 2 mois : ce n'est pas une anomalie.
        for j in range(0, 63, 2):
            self.avis(2, j, "Cher", negatifs=["prix"])
        kinds = {a.kind for a in detection.analyser(self.fiche, self.maintenant)}
        self.assertNotIn("plainte_recurrente", kinds)
        self.assertNotIn("hausse_negatifs", kinds)

    def test_pas_de_doublon(self):
        self.historique_calme()
        for j in range(4):
            self.avis(1, j, "Attente", negatifs=["attente"])
        detection.analyser(self.fiche, self.maintenant)
        nb = Alert.objects.count()
        detection.analyser(self.fiche, self.maintenant)
        self.assertEqual(Alert.objects.count(), nb)

    def test_pic_positif(self):
        self.historique_calme()
        for _ in range(6):
            self.avis(5, 3, "Super dégustation", positifs=["qualite"])
        pic = next(a for a in detection.analyser(self.fiche, self.maintenant) if a.kind == "pic_avis")
        self.assertEqual(pic.niveau, Alert.Niveau.POSITIF)
        self.assertIn("événement", pic.message)

    def test_baisse_de_note(self):
        for j in range(15, 70, 3):
            self.avis(5, j)
        for j in range(6):
            self.avis(2, j)
        self.assertIn("baisse_note", {a.kind for a in detection.analyser(self.fiche, self.maintenant)})


class RecommandationsTests(Base):
    def test_cycle_complet_avec_suivi(self):
        for j in range(5):
            self.avis(1, 11 + j, "Attente interminable", negatifs=["attente"])
        recommandations.generer(self.fiche, self.maintenant)
        reco = Recommendation.objects.get(theme="attente")
        self.assertEqual(reco.importance, Recommendation.Importance.HAUTE)
        self.assertTrue(reco.actions)
        self.assertEqual(len(reco.evidence_review_ids), 5)

        recommandations.generer(self.fiche, self.maintenant)
        self.assertEqual(Recommendation.objects.filter(theme="attente").count(), 1)  # pas de doublon

        # Le commerçant agit il y a 10 jours ; depuis, un seul avis parle encore d'attente.
        reco.status = Recommendation.Statut.EN_COURS
        reco.status_changed_at = self.maintenant - timedelta(days=10)
        reco.save()
        self.avis(2, 2, "Encore un peu d'attente", negatifs=["attente"])
        s = recommandations.suivi(reco, self.maintenant)
        self.assertEqual((s["depuis"], s["tendance"]), (1, "amelioration"))

    def test_probleme_resolu_qui_revient_rouvre(self):
        for j in range(3):
            self.avis(1, 25 + j, negatifs=["accueil"])
        recommandations.generer(self.fiche, self.maintenant)
        reco = Recommendation.objects.get(theme="accueil")
        reco.status, reco.status_changed_at = Recommendation.Statut.RESOLUE, self.maintenant - timedelta(days=20)
        reco.save()
        recommandations.generer(self.fiche, self.maintenant)
        self.assertEqual(Recommendation.objects.filter(theme="accueil").count(), 1)  # rien de nouveau depuis
        for j in range(3):
            self.avis(1, j, negatifs=["accueil"])
        recommandations.generer(self.fiche, self.maintenant)
        self.assertEqual(Recommendation.objects.filter(theme="accueil").count(), 2)

    def test_point_fort_a_valoriser(self):
        for j in range(6):
            self.avis(5, j, "Pain délicieux", positifs=["qualite"])
        recommandations.generer(self.fiche, self.maintenant)
        r = Recommendation.objects.get(type=Recommendation.Type.VALORISER)
        self.assertIn("qualité des produits", r.titre)


class VuesAlertesTests(Base):
    def test_page_isolation_et_statut(self):
        a = self.avis(1, 1, "Secret de ma fiche", negatifs=["attente"])
        alerte = Alert.objects.create(location=self.fiche, kind="x", message="Alerte A", evidence_review_ids=[a.pk])
        reco = Recommendation.objects.create(location=self.fiche, theme="attente", titre="Attente",
                                             problem="p", importance="haute")
        intrus, autre_org = creer_compte("intrus@test.fr", nom="Intrus")
        Location.objects.create(organization=autre_org, title="Autre")

        # Un autre commerçant ne peut ni lire ni modifier.
        self.client.force_login(intrus)
        self.assertNotContains(self.client.get(reverse("insights:recommandations")), "Alerte A")
        self.assertEqual(self.client.post(reverse("insights:alerte_lue", args=[alerte.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("insights:changer_statut", args=[reco.pk]),
                                          {"statut": "resolue"}).status_code, 404)

        # Le gérant (essai = fonctions Pro) voit tout et change le statut.
        self.client.force_login(self.user)
        r = self.client.get(reverse("insights:recommandations"))
        self.assertContains(r, "Alerte A")
        self.assertContains(r, "Secret de ma fiche")
        self.client.post(reverse("insights:changer_statut", args=[reco.pk]), {"statut": "en_cours"})
        reco.refresh_from_db()
        self.assertEqual(reco.status, "en_cours")
        self.assertIsNotNone(reco.status_changed_at)
        self.client.post(reverse("insights:changer_statut", args=[reco.pk]), {"statut": "pirate"})
        reco.refresh_from_db()
        self.assertEqual(reco.status, "en_cours")

    def test_starter_payant_sans_recommandations(self):
        sub = self.org.subscription
        sub.status = "actif"
        sub.save()
        Recommendation.objects.create(location=self.fiche, theme="attente", titre="Reco cachée", problem="p",
                                      importance="haute")
        self.client.force_login(self.user)
        r = self.client.get(reverse("insights:recommandations"))
        self.assertNotContains(r, "Reco cachée")
        self.assertContains(r, "formule")
