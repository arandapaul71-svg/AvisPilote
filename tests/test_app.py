"""Tests de base. Lancer depuis la racine du projet :  python -m unittest discover tests"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

import ai  # noqa: E402
import app as appli  # noqa: E402


class TestAnalyse(unittest.TestCase):
    def test_qualites_et_defauts(self):
        q, d = ai.analyser_regles("Pas cher et délicieux !", 5)
        self.assertIn("prix", q)
        self.assertIn("qualite", q)
        self.assertEqual(d, [])

    def test_negation(self):
        _, d = ai.analyser_regles("Le pain n'est pas frais et la vendeuse pas aimable.", 2)
        self.assertIn("qualite", d)
        self.assertIn("accueil", d)

    def test_rupture_ne_compte_pas_comme_qualite(self):
        q, d = ai.analyser_regles("Plus de pain à 18h, dommage.", 2)
        self.assertEqual(d, ["choix"])


class TestApi(unittest.TestCase):
    def setUp(self):
        self.c = appli.app.test_client()
        self.h = {"X-CSRF-Token": self.c.get("/api/me").json["csrf"]}

    def inscrire(self, email):
        r = self.c.post("/api/register", headers=self.h, json={
            "email": email, "password": "motdepasse123", "name": "Boulangerie Test", "type": "boulangerie"})
        self.assertEqual(r.status_code, 200)
        self.h = {"X-CSRF-Token": self.c.get("/api/me").json["csrf"]}

    def test_csrf_obligatoire(self):
        r = self.c.post("/api/register", json={"email": "x@y.fr", "password": "12345678", "name": "X"})
        self.assertEqual(r.status_code, 403)

    def test_parcours_complet(self):
        self.inscrire("parcours@test.fr")
        self.assertEqual(self.c.post("/api/demo", headers=self.h).status_code, 200)

        quota = self.c.get("/api/me").json["quota"]
        self.assertTrue(quota["depasse"])            # la démo dépasse le quota Essentiel
        self.assertLessEqual(quota["utilises"], 40)

        dash = self.c.get("/api/dashboard").json
        self.assertTrue(any(p["nature"] == "positif" for p in dash["pics"]))

        hors_quota = self.c.get("/api/reviews?filtre=hors_quota").json["avis"][0]
        r = self.c.post(f"/api/reviews/{hors_quota['id']}/publish", headers=self.h, json={"reply": "Merci"})
        self.assertEqual(r.status_code, 403)         # impossible de répondre à un avis hors quota

        self.assertEqual(self.c.get("/api/recap?periode=semaine").status_code, 403)  # réservé à Pro
        r = self.c.post("/api/business/plan", headers=self.h, json={"plan": "pro"}).json
        self.assertFalse(r["quota"]["depasse"])      # en passant Pro, tout est traité

    def test_isolation_entre_entreprises(self):
        self.inscrire("a@test.fr")
        self.c.post("/api/demo", headers=self.h)
        avis_id = self.c.get("/api/reviews").json["avis"][0]["id"]

        autre = appli.app.test_client()
        h = {"X-CSRF-Token": autre.get("/api/me").json["csrf"]}
        autre.post("/api/register", headers=h, json={"email": "b@test.fr", "password": "motdepasse123", "name": "B"})
        h = {"X-CSRF-Token": autre.get("/api/me").json["csrf"]}
        r = autre.post(f"/api/reviews/{avis_id}/publish", headers=h, json={"reply": "piratage"})
        self.assertEqual(r.status_code, 404)         # l'autre entreprise ne voit pas cet avis


if __name__ == "__main__":
    unittest.main()
