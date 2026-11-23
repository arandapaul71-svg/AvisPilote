"""Tests de la liaison Google. Google est remplacé par de fausses réponses (mock) :
on vérifie NOTRE code (sécurité OAuth, stockage, erreurs), pas les serveurs de Google."""
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.tests import creer_compte
from reviews.models import ReplyDraft, Review

from . import google_client, sync
from .models import GoogleConnection, Location

GOOGLE_OK = override_settings(GOOGLE_CLIENT_ID="id-test", GOOGLE_CLIENT_SECRET="secret-test")

FICHES = [
    {"name": "accounts/1/locations/10", "title": "Boulangerie du Port", "new_review_uri": "https://g.page/r/x/review"},
    {"name": "accounts/1/locations/11", "title": "Boulangerie Gare", "new_review_uri": ""},
]


def page_avis(*avis, suivante=None):
    data = {"reviews": list(avis), "averageRating": 4.33, "totalReviewCount": len(avis)}
    if suivante:
        data["nextPageToken"] = suivante
    return data


def avis_google(rid, etoiles="FIVE", texte="Super", reponse=None):
    rv = {"reviewId": rid, "starRating": etoiles, "comment": texte,
          "reviewer": {"displayName": "Léa M."}, "createTime": "2026-11-20T13:32:11.123456789Z"}
    if reponse:
        rv["reviewReply"] = {"comment": reponse, "updateTime": "2026-11-21T08:00:00Z"}
    return rv


class OAuthTests(TestCase):
    def setUp(self):
        self.user, self.org = creer_compte("gerant@test.fr")
        self.client.force_login(self.user)

    def test_sans_acces_api_la_connexion_est_indiquee_indisponible(self):
        r = self.client.get(reverse("locations:google_connecter"))
        self.assertContains(r, "bientôt disponible")
        self.assertFalse(GoogleConnection.objects.exists())

    @GOOGLE_OK
    def test_redirection_vers_google_avec_state_et_pkce(self):
        r = self.client.get(reverse("locations:google_connecter"))
        self.assertTrue(r["Location"].startswith(google_client.AUTH_URL))
        self.assertIn("code_challenge_method=S256", r["Location"])
        self.assertIn(self.client.session["google_oauth"]["state"], r["Location"])
        # Le « verifier » PKCE ne doit jamais partir vers le navigateur.
        self.assertNotIn(self.client.session["google_oauth"]["verifier"], r["Location"])

    @GOOGLE_OK
    def test_retour_avec_state_invalide_refuse(self):
        self.client.get(reverse("locations:google_connecter"))
        with mock.patch.object(google_client, "echanger_code") as echange:
            r = self.client.get(reverse("locations:google_retour"), {"state": "pirate", "code": "abc"})
        echange.assert_not_called()
        self.assertRedirects(r, reverse("accounts:tableau_de_bord"))

    @GOOGLE_OK
    @mock.patch.object(google_client, "lister_fiches", return_value=FICHES)
    @mock.patch.object(google_client, "echanger_code",
                       return_value={"access_token": "acc", "refresh_token": "ref", "expires_in": 3600})
    @mock.patch.object(google_client, "pages_avis", return_value=iter([page_avis(avis_google("r1"))]))
    def test_parcours_complet_et_choix_de_fiche(self, _pages, echange, _fiches):
        self.client.get(reverse("locations:google_connecter"))
        oauth = self.client.session["google_oauth"]
        r = self.client.get(reverse("locations:google_retour"), {"state": oauth["state"], "code": "abc"})
        self.assertRedirects(r, reverse("locations:choisir_fiche"))
        echange.assert_called_once_with("abc", oauth["verifier"])
        self.assertEqual(GoogleConnection.objects.get().refresh_token, "ref")

        # Une fiche qui n'a pas été proposée par Google est refusée.
        self.client.post(reverse("locations:choisir_fiche"), {"fiche": "accounts/999/locations/1"})
        self.assertFalse(Location.objects.exists())

        self.client.post(reverse("locations:choisir_fiche"), {"fiche": FICHES[1]["name"]})
        fiche = Location.objects.get()
        self.assertEqual(fiche.title, "Boulangerie Gare")
        self.assertEqual(fiche.reviews.count(), 1)

    @GOOGLE_OK
    def test_employe_ne_peut_pas_connecter_google(self):
        employe, _ = creer_compte("employe@test.fr", role=Role.MANAGER)
        self.client.force_login(employe)
        self.assertEqual(self.client.get(reverse("locations:google_connecter")).status_code, 403)


class SynchroTests(TestCase):
    def setUp(self):
        _, self.org = creer_compte("gerant@test.fr")
        self.connexion = GoogleConnection.objects.create(
            organization=self.org, access_token="acc", refresh_token="ref",
            token_expiry=timezone.now() + timedelta(hours=1))
        self.fiche = Location.objects.create(organization=self.org, title="Fiche",
                                             google_location_name="accounts/1/locations/10")

    def _sync(self, *pages):
        with mock.patch.object(google_client, "pages_avis", return_value=iter(pages)):
            return sync.synchroniser(self.fiche)

    def test_import_puis_mise_a_jour_sans_doublon(self):
        res = self._sync(page_avis(avis_google("r1"), avis_google("r2", "ONE", "Froid")))
        self.assertEqual(res["ajoutes"], 2)
        self.assertEqual(Review.objects.get(google_review_id="r2").stars, 1)
        self.fiche.refresh_from_db()
        self.assertEqual(float(self.fiche.average_rating), 4.33)

        # Le commerçant a répondu directement sur Google entre-temps.
        res = self._sync(page_avis(avis_google("r2", "ONE", "Froid", reponse="Désolé"), avis_google("r1")))
        self.assertEqual(res, {"ajoutes": 0, "mis_a_jour": 1})
        self.assertEqual(Review.objects.count(), 2)
        self.assertEqual(Review.objects.get(google_review_id="r2").google_reply, "Désolé")

    def test_dates_google_a_9_decimales(self):
        self._sync(page_avis(avis_google("r1")))
        self.assertEqual(Review.objects.get().created_at.year, 2026)

    @GOOGLE_OK
    def test_jeton_expire_rafraichi_ou_marque_expire(self):
        self.connexion.token_expiry = timezone.now() - timedelta(minutes=1)
        self.connexion.save()
        with mock.patch.object(google_client, "_appel",
                               side_effect=google_client.GoogleErreur("autorisation", "invalid_grant")):
            with self.assertRaises(google_client.GoogleErreur):
                google_client.jeton_valide(self.connexion)
        self.connexion.refresh_from_db()
        self.assertEqual(self.connexion.status, GoogleConnection.Statut.EXPIREE)

    def test_erreurs_http_traduites(self):
        reponse = mock.Mock(status_code=429, text="RESOURCE_EXHAUSTED", content=b"x")
        with mock.patch("requests.request", return_value=reponse):
            with self.assertRaises(google_client.GoogleErreur) as ctx:
                google_client._appel("GET", "https://exemple")
        self.assertEqual(ctx.exception.code, "limite")

    def test_commande_planifiee_ignore_les_fiches_recentes(self):
        self.fiche.last_sync_at = timezone.now()
        self.fiche.save()
        self.assertNotIn(self.fiche, list(sync.a_synchroniser()))
        self.fiche.last_sync_at = timezone.now() - timedelta(minutes=20)
        self.fiche.save()
        self.assertIn(self.fiche, list(sync.a_synchroniser()))


class ReponseEtIsolationTests(TestCase):
    def setUp(self):
        self.user, self.org = creer_compte("gerant@test.fr")
        GoogleConnection.objects.create(organization=self.org, access_token="acc",
                                        token_expiry=timezone.now() + timedelta(hours=1))
        fiche = Location.objects.create(organization=self.org, title="Ma fiche", google_location_name="accounts/1/locations/10")
        self.avis = Review.objects.create(location=fiche, google_review_id="r1", author="A", stars=2,
                                          comment="Bof", created_at=timezone.now())
        _, autre_org = creer_compte("autre@test.fr", nom="Concurrent")
        autre_fiche = Location.objects.create(organization=autre_org, title="Autre")
        self.avis_autre = Review.objects.create(location=autre_fiche, google_review_id="x", author="B", stars=5,
                                                comment="Secret du concurrent", created_at=timezone.now())
        self.client.force_login(self.user)

    def test_liste_ne_montre_que_mes_avis(self):
        r = self.client.get(reverse("reviews:liste"))
        self.assertContains(r, "Bof")
        self.assertNotContains(r, "Secret du concurrent")

    def test_impossible_de_repondre_a_l_avis_d_une_autre_entreprise(self):
        with mock.patch.object(google_client, "publier_reponse") as pub:
            r = self.client.post(reverse("reviews:repondre", args=[self.avis_autre.pk]), {"texte": "Piraté"})
        self.assertEqual(r.status_code, 404)
        pub.assert_not_called()

    def test_reponse_publiee_sur_google(self):
        with mock.patch.object(google_client, "publier_reponse", return_value={}) as pub:
            self.client.post(reverse("reviews:repondre", args=[self.avis.pk]), {"texte": "Merci pour votre retour."})
        pub.assert_called_once()
        self.avis.refresh_from_db()
        self.assertEqual(self.avis.google_reply, "Merci pour votre retour.")
        self.assertEqual(ReplyDraft.objects.get().status, ReplyDraft.Statut.PUBLIEE)

    def test_echec_google_ne_marque_pas_publie(self):
        with mock.patch.object(google_client, "publier_reponse",
                               side_effect=google_client.GoogleErreur("fiche_non_validee")):
            self.client.post(reverse("reviews:repondre", args=[self.avis.pk]), {"texte": "Merci."})
        self.avis.refresh_from_db()
        self.assertEqual(self.avis.google_reply, "")
        # Le texte est gardé (pas perdu) mais jamais marqué comme publié.
        self.assertFalse(ReplyDraft.objects.filter(status=ReplyDraft.Statut.PUBLIEE).exists())

    def test_lecture_seule_ne_peut_pas_repondre(self):
        lecteur, _ = creer_compte("lecteur@test.fr", role=Role.VIEWER)
        self.client.force_login(lecteur)
        r = self.client.post(reverse("reviews:repondre", args=[self.avis.pk]), {"texte": "Merci."})
        self.assertEqual(r.status_code, 403)


class DemoTests(TestCase):
    def setUp(self):
        self.user, self.org = creer_compte("gerant@test.fr")
        self.client.force_login(self.user)

    def test_demo_signalee_et_jamais_publiee(self):
        self.client.post(reverse("locations:activer_demo"))
        fiche = Location.objects.get()
        self.assertTrue(fiche.is_demo)
        self.assertGreater(fiche.reviews.count(), 50)
        self.assertContains(self.client.get(reverse("reviews:liste")), "Mode démonstration")

        avis = fiche.reviews.first()
        with mock.patch.object(google_client, "publier_reponse") as pub:
            self.client.post(reverse("reviews:repondre", args=[avis.pk]), {"texte": "Merci !"})
        pub.assert_not_called()
        avis.refresh_from_db()
        self.assertEqual(avis.google_reply, "")
        self.assertEqual(avis.drafts.filter(source="humain").get().status, ReplyDraft.Statut.BROUILLON)
        self.assertFalse(ReplyDraft.objects.filter(status=ReplyDraft.Statut.PUBLIEE).exists())

    @override_settings(DEMO_AUTORISEE=False)
    def test_demo_interdite_en_production(self):
        self.assertEqual(self.client.post(reverse("locations:activer_demo")).status_code, 404)
        self.assertFalse(Location.objects.exists())
