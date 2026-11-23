"""Formules d'abonnement. Hypothèses commerciales à tester : modifie les chiffres ici.

quota = nombre d'avis traités par l'IA (analyse + réponse) par période d'abonnement.
Les avis récupérés au-delà du quota restent stockés et consultables.
"""
PLANS = {
    "starter": {
        "nom": "Starter",
        "prix_centimes": 999,
        "quota": 50,
        "etablissements": 1,
        "fonctions": {"reponses_ia", "dashboard", "forces_faiblesses", "alerte_simple"},
    },
    "pro": {
        "nom": "Pro",
        "prix_centimes": 1999,
        "quota": 200,
        "etablissements": 1,
        "fonctions": {"reponses_ia", "dashboard", "forces_faiblesses", "alerte_simple",
                      "anomalies", "recommandations", "rapports", "alertes"},
    },
    "business": {
        "nom": "Business",
        "prix_centimes": 3999,
        "quota": 600,
        "etablissements": 5,
        "fonctions": {"reponses_ia", "dashboard", "forces_faiblesses", "alerte_simple",
                      "anomalies", "recommandations", "rapports", "alertes",
                      "multi_etablissements", "concurrence", "rapports_avances"},
    },
}

PLAN_PAR_DEFAUT = "starter"
ESSAI_JOURS = 14
RESERVE_NEGATIFS = 0.15   # part du quota gardée pour les avis 1-2★
SEUIL_ALERTE_QUOTA = 0.80  # prévenir l'utilisateur à 80 %
DUREE_PERIODE_JOURS = 30


def prix_affiche(cle):
    centimes = PLANS[cle]["prix_centimes"]
    return f"{centimes // 100},{centimes % 100:02d} €"
