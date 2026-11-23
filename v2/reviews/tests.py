"""Tests de l'assistant IA : quota, modes, avis sensibles, contrôle qualité, repli sans Claude."""
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.tests import creer_compte
from billing import plans, quotas
from locations import google_client
from locations.models import GoogleConnection, Location

from . import traitement
from .ia import claude, controle, regles, sensible
from .models import AISettings, Mode, ReplyDraft, Review

SANS_CLAUDE = override_settings(ANTHROPIC_API_KEY="")


def nouvel_avis(fiche, rid, etoiles, texte, il_y_a=timedelta(hours=1)):
    return Review.objects.create(location=fiche, google_review_id=rid, author="Léa M.", stars=etoiles,
                                 comment=texte, created_at=timezone.now() - il_y_a)


class Base(TestCase):
    def setUp(self):
        self.user, self.org = creer_compte("gerant@test.fr")
        GoogleConnection.objects.create(organization=self.org, access_token="acc",
                                        token_expiry=timezone.now() + timedelta(hours=1))
        self.fiche = Location.objects.create(organization=self.org, title="Ma fiche",
                                             google_location_name="accounts/1/locations/10")
        # La fiche a été connectée hier : les avis d'aujourd'hui sont « nouveaux ».
        Location.objects.filter(pk=self.fiche.pk).update(created_at=timezone.now() - timedelta(days=1))
        self.fiche.refresh_from_db()


@SANS_CLAUDE
class PipelineTests(Base):
    def test_avis_positif_publie_automatiquement(self):
        avis = nouvel_avis(self.fiche, "r1", 5, "Accueil chaleureux et croissants délicieux, merci à l'équipe !")
        with mock.patch.object(google_client, "publier_reponse", return_value={}) as pub:
            self.assertEqual(traitement.traiter_en_attente(self.fiche), 1)
        pub.assert_called_once()
        avis.refresh_from_db()
        self.assertEqual(avis.ai_status, Review.StatutIA.TRAITE)
        self.assertIn("accueil", avis.analysis.themes_positifs)
        self.assertTrue(avis.google_reply)

    def test_avis_negatif_attend_validation(self):
        avis = nouvel_avis(self.fiche, "r1", 1, "Attendu 30 minutes, vendeuse désagréable.")
        with mock.patch.object(google_client, "publier_reponse") as pub:
            traitement.traiter_en_attente(self.fiche)
        pub.assert_not_called()
        brouillon = avis.drafts.get()
        self.assertEqual(brouillon.status, ReplyDraft.Statut.A_VALIDER)
        self.assertIn("attente", avis.analysis.themes_negatifs)
        self.assertTrue(avis.analysis.actions)  # des pistes d'action pour le commerçant

    def test_avis_sensible_jamais_publie_meme_en_mode_auto(self):
        AISettings.objects.create(location=self.fiche, mode_by_stars={str(n): Mode.AUTO for n in range(1, 6)})
        avis = nouvel_avis(self.fiche, "r1", 4, "Bon pain mais j'ai été malade après, je vais porter plainte.")
        with mock.patch.object(google_client, "publier_reponse") as pub:
            traitement.traiter_en_attente(self.fiche)
        pub.assert_not_called()
        self.assertEqual(sorted(avis.analysis.sensitive_flags), ["juridique", "sanitaire"])
        self.assertTrue(any("sensible" in r for r in avis.drafts.get().reasons))

    def test_mode_manuel_pas_de_brouillon(self):
        AISettings.objects.create(location=self.fiche, mode_by_stars={str(n): Mode.MANUEL for n in range(1, 6)})
        avis = nouvel_avis(self.fiche, "r1", 5, "Super !")
        traitement.traiter_en_attente(self.fiche)
        self.assertEqual(avis.drafts.count(), 0)
        self.assertEqual(Review.objects.get(pk=avis.pk).ai_status, Review.StatutIA.TRAITE)

    def test_historique_non_publie_automatiquement(self):
        # Avis reçu avant la connexion de la fiche : analysé, mais jamais publié tout seul.
        avis = nouvel_avis(self.fiche, "r1", 5, "Délicieux !", il_y_a=timedelta(days=3))
        with mock.patch.object(google_client, "publier_reponse") as pub:
            traitement.traiter_en_attente(self.fiche)
        pub.assert_not_called()
        self.assertEqual(avis.drafts.get().status, ReplyDraft.Statut.A_VALIDER)

    def test_avis_anciens_ne_consomment_pas_le_quota(self):
        vieux = nouvel_avis(self.fiche, "vieux", 1, "Attente interminable", il_y_a=timedelta(days=60))
        self.assertEqual(traitement.traiter_en_attente(self.fiche), 0)
        self.assertEqual(quotas.etat(self.org.subscription)["utilises"], 0)
        # Mais il reçoit une analyse de thèmes gratuite (référence pour la détection), sans réponse.
        vieux.refresh_from_db()
        self.assertEqual(vieux.analysis.source, traitement.SOURCE_HISTORIQUE)
        self.assertIn("attente", vieux.analysis.themes_negatifs)
        self.assertEqual(vieux.drafts.count(), 0)
        self.assertEqual(vieux.ai_status, Review.StatutIA.NON_TRAITE)

    def test_quota_atteint_avis_hors_quota_mais_visible(self):
        quota = plans.PLANS["starter"]["quota"]
        for i in range(quota + 3):
            nouvel_avis(self.fiche, f"r{i}", 1, "Froid.", il_y_a=timedelta(minutes=i + 1))
        with mock.patch.object(google_client, "publier_reponse"):
            self.assertEqual(traitement.traiter_en_attente(self.fiche), quota)
        self.assertEqual(Review.objects.filter(ai_status=Review.StatutIA.HORS_QUOTA).count(), 3)
        self.assertFalse(ReplyDraft.objects.filter(review__ai_status=Review.StatutIA.HORS_QUOTA).exists())
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("reviews:liste"), {"statut": "hors_quota"}), "Hors quota")

    def test_echec_publication_auto_passe_en_validation(self):
        avis = nouvel_avis(self.fiche, "r1", 5, "Accueil chaleureux, merci !")
        with mock.patch.object(google_client, "publier_reponse", side_effect=google_client.GoogleErreur("limite")):
            traitement.traiter_en_attente(self.fiche)
        brouillon = avis.drafts.get()
        self.assertEqual(brouillon.decision, Mode.VALIDATION)
        self.assertEqual(brouillon.status, ReplyDraft.Statut.A_VALIDER)

    def test_regeneration_limitee_et_sans_quota(self):
        avis = nouvel_avis(self.fiche, "r1", 2, "Pain rassis.")
        traitement.traiter_en_attente(self.fiche)
        avis.refresh_from_db()
        utilises = quotas.etat(self.org.subscription)["utilises"]
        for _ in range(traitement.MAX_REGENERATIONS):
            traitement.regenerer(avis, self.user)
        with self.assertRaises(ValueError):
            traitement.regenerer(avis, self.user)
        self.assertEqual(quotas.etat(self.org.subscription)["utilises"], utilises)


class ControleQualiteTests(TestCase):
    def setUp(self):
        self.reglages = AISettings(forbidden_phrases="désolé pour la gêne\n")
        self.avis = Review(stars=1, comment="Les croissants étaient brûlés et la vendeuse désagréable.",
                           google_review_id="x", author="A")

    def test_detecte_promesse_aveu_et_resolution(self):
        for texte in ["Nous allons vous rembourser intégralement.",
                      "Nous reconnaissons notre erreur sur les croissants.",
                      "Le problème est réglé, les croissants sont parfaits."]:
            self.assertTrue(controle.controler(texte, self.avis, self.reglages), texte)

    def test_expression_interdite_et_ton(self):
        problemes = controle.controler("Ravis de votre retour ! Désolé pour la gêne sur les croissants.",
                                       self.avis, self.reglages)
        self.assertTrue(any("interdite" in p for p in problemes))
        self.assertTrue(any("enthousiaste" in p for p in problemes))

    def test_reponse_generique_et_repetition(self):
        self.assertTrue(any("générique" in p for p in controle.controler("Merci pour votre message.", self.avis, self.reglages)))
        bonne = "Bonjour, nous sommes navrés pour ces croissants trop cuits et l'accueil reçu."
        self.assertEqual(controle.controler(bonne, self.avis, self.reglages), [])
        self.assertTrue(controle.controler(bonne, self.avis, self.reglages, reponses_precedentes=[bonne]))

    def test_detection_sensible(self):
        self.assertEqual(sensible.detecter("Très bon, je recommande"), [])
        self.assertIn("remboursement", sensible.detecter("Je demande à être remboursé !"))
        self.assertIn("agressif", sensible.detecter("Bande d'abrutis"))

    def test_negation_dans_l_analyse(self):
        positifs, negatifs = regles.analyser_regles("Pain pas frais du tout, mais vendeuse adorable.", 3)
        self.assertIn("qualite", negatifs)
        self.assertIn("accueil", positifs)


@override_settings(ANTHROPIC_API_KEY="cle-test", ANTHROPIC_MODEL="claude-haiku-5-5")
class ClaudeTests(Base):
    def _reponse(self, texte, stop="end_turn"):
        bloc = mock.Mock(type="text", text=texte)
        return mock.Mock(stop_reason=stop, content=[bloc])

    def test_reponse_claude_utilisee_et_controlee(self):
        avis = nouvel_avis(self.fiche, "r1", 1, "Attente interminable.")
        json_ok = ('{"sentiment":"negatif","themes_positifs":[],"themes_negatifs":["attente"],"sensible":[],'
                   '"reponse":"Bonjour Léa, désolés pour cette attente. Nous allons vous rembourser.","actions":["Renfort"]}')
        with mock.patch.object(claude, "_client") as client:
            client.return_value.messages.create.return_value = self._reponse(json_ok)
            traitement.traiter_en_attente(self.fiche)
            appel = client.return_value.messages.create.call_args.kwargs
        self.assertEqual(appel["model"], "claude-haiku-5-5")
        self.assertIn("<avis>\nAttente interminable.\n</avis>", appel["messages"][0]["content"])
        self.assertEqual(avis.analysis.source, "claude-haiku-5-5")
        # La promesse de remboursement inventée par l'IA est bloquée par le contrôle qualité.
        self.assertTrue(any("rembours" in p for p in avis.drafts.get().quality_checks))

    def test_repli_sur_les_regles_si_claude_echoue(self):
        avis = nouvel_avis(self.fiche, "r1", 2, "Pain rassis.")
        with mock.patch.object(claude, "_client") as client:
            client.return_value.messages.create.return_value = self._reponse("", stop="refusal")
            traitement.traiter_en_attente(self.fiche)
        self.assertEqual(avis.analysis.source, "regles")
        self.assertTrue(avis.drafts.exists())


@SANS_CLAUDE
class VuesTests(Base):
    def test_valider_brouillon_publie(self):
        avis = nouvel_avis(self.fiche, "r1", 2, "Pain rassis.")
        traitement.traiter_en_attente(self.fiche)
        texte = avis.drafts.get().text
        self.client.force_login(self.user)
        with mock.patch.object(google_client, "publier_reponse", return_value={}) as pub:
            self.client.post(reverse("reviews:repondre", args=[avis.pk]), {"texte": texte})
        pub.assert_called_once()
        self.assertEqual(ReplyDraft.objects.get(status=ReplyDraft.Statut.PUBLIEE).source, "ia")

    def test_reglages_enregistres_et_valides(self):
        self.client.force_login(self.user)
        donnees = {"tone": "elegant", "length": "courte", "tutoiement": "on", "signature": "Marie",
                   "mode_5": "auto", "mode_4": "validation", "mode_3": "validation", "mode_2": "manuel", "mode_1": "manuel",
                   "sensitive_requires_validation": "on"}
        self.client.post(reverse("reviews:assistant"), donnees)
        r = AISettings.objects.get(location=self.fiche)
        self.assertEqual(r.tone, "elegant")
        self.assertEqual(r.mode_pour(4), Mode.VALIDATION)
        self.assertTrue(r.tutoiement)
        # Valeur inventée refusée par le serveur.
        self.client.post(reverse("reviews:assistant"), {**donnees, "mode_5": "pirate"})
        self.assertEqual(AISettings.objects.get(location=self.fiche).mode_pour(5), Mode.AUTO)

    def test_lecteur_ne_peut_pas_regler_l_assistant(self):
        lecteur, _ = creer_compte("lecteur@test.fr", role=Role.VIEWER)
        self.client.force_login(lecteur)
        self.assertEqual(self.client.get(reverse("reviews:assistant")).status_code, 403)


class ExemplesReglagesTests(Base):
    def test_exemples_affiches_et_pre_remplissage_sans_enregistrement(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse("reviews:assistant"))
        self.assertContains(r, "Voir un exemple")
        r = self.client.get(reverse("reviews:assistant"), {"exemples": "1"})
        self.assertContains(r, "Pré-remplir")
        self.assertContains(r, "Ouvert du")  # exemple inséré dans le champ
        self.assertFalse(AISettings.objects.filter(location=self.fiche).exists())  # rien d'enregistré

    def test_crochets_non_remplaces_refuses(self):
        self.client.force_login(self.user)
        donnees = {"tone": "chaleureux", "length": "moyenne", "mode_5": "auto", "mode_4": "auto",
                   "mode_3": "validation", "mode_2": "validation", "mode_1": "validation",
                   "business_info": "Commandes au [numéro]"}
        r = self.client.post(reverse("reviews:assistant"), donnees)
        self.assertContains(r, "crochets")
        self.assertFalse(AISettings.objects.filter(location=self.fiche).exists())
        self.client.post(reverse("reviews:assistant"), {**donnees, "business_info": "Commandes au 04 94 00 00 00"})
        self.assertEqual(AISettings.objects.get(location=self.fiche).business_info, "Commandes au 04 94 00 00 00")
