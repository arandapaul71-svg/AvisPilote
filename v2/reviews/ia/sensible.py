"""Détection des avis sensibles : ils ne sont JAMAIS publiés automatiquement
(si l'option « avis sensibles toujours validés » est active, ce qui est le réglage par défaut).

Volontairement large : mieux vaut faire valider un avis de trop qu'en publier un mal géré.
"""
from .regles import _cherche, normaliser

CATEGORIES = {
    "accusation": {
        "nom": "Accusation grave",
        "mots": ["vol", "vole", "voleur", "voleurs", "arnaque", "arnaqueur", "escroc", "escrocs", "escroquerie",
                 "harcelement", "harcele", "raciste", "racisme", "discrimination", "discrimine", "menteur",
                 "menteuse", "fraude", "malhonnete", "agression", "agresse", "insulte", "m'a insulte"],
    },
    "sanitaire": {
        "nom": "Hygiène ou sécurité",
        "mots": ["intoxication", "intoxique", "intoxiques", "malade", "malades", "vomi", "vomir", "diarrhee",
                 "cafard", "cafards", "rat", "rats", "souris", "insecte", "insectes", "ver", "moisi", "moisissure",
                 "perime", "perimee", "allergie", "allergique", "brulure", "brule", "blesse", "blessee",
                 "hopital", "urgences", "verre dans", "corps etranger", "hygiene douteuse", "insalubre"],
    },
    "juridique": {
        "nom": "Menace juridique",
        "mots": ["avocat", "plainte", "porter plainte", "tribunal", "proces", "justice", "dgccrf", "police",
                 "gendarmerie", "huissier", "mise en demeure", "poursuites", "service des fraudes", "60 millions"],
    },
    "remboursement": {
        "nom": "Demande de remboursement",
        "mots": ["rembourse", "remboursement", "remboursez", "rembourser", "mon argent", "un avoir",
                 "dedommagement", "dedommager", "geste commercial"],
    },
    "agressif": {
        "nom": "Avis très agressif",
        "mots": ["connard", "connards", "connasse", "abruti", "abrutis", "debile", "debiles", "merde", "merdique",
                 "pourri", "pourris", "honte a vous", "crevez", "degueulasse", "minable", "minables", "incompetents"],
    },
}


def detecter(commentaire):
    """Renvoie la liste des catégories sensibles trouvées, ex. ["sanitaire", "juridique"]."""
    texte = " " + normaliser(commentaire) + " "
    return [cle for cle, cat in CATEGORIES.items() if any(_cherche(m, texte) for m in cat["mots"])]


def libelles(cles):
    return [CATEGORIES[c]["nom"] for c in cles if c in CATEGORIES]
