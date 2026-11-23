"""Analyse des avis par règles (gratuite, hors ligne). Reprise de la version Flask.

Repère les thèmes cités positivement (qualités) ou négativement (défauts),
en gérant les négations (« pas frais ») et les phrases à plusieurs idées (« bon, mais cher »).
"""
import re
import unicodedata

# Thèmes analysés
# ---------------------------------------------------------------------------
THEMES = {
    "accueil": {
        "qualite": "Accueil chaleureux",
        "defaut": "Accueil à améliorer",
        "pos": ["accueillant", "accueillante", "aimable", "aimables", "souriant", "souriante", "souriants",
                "sympathique", "sympa", "gentil", "gentille", "gentils", "chaleureux", "chaleureuse",
                "adorable", "adorables", "serviable", "a l'ecoute", "bienveillant", "bienveillante",
                "de bon conseil", "bons conseils", "tres pro", "accueil au top", "super accueil",
                "bon accueil", "excellent accueil"],
        "neg": ["impoli", "impolie", "desagreable", "mal accueilli", "mal accueillie", "mal recu",
                "aucun bonjour", "sans un bonjour", "pas un bonjour", "pas bonjour", "meprisant", "meprisante", "agressif", "agressive",
                "accueil froid", "accueil glacial", "aimable comme une porte", "pas aimable",
                "accueil decevant", "accueil a revoir", "nous a ignores", "m'a ignore"],
        "neutre": ["accueil", "personnel", "vendeuse", "vendeur", "vendeuses", "serveur", "serveuse",
                   "serveurs", "equipe", "patron", "patronne", "caissiere", "coiffeuse", "coiffeur"],
    },
    "qualite": {
        "qualite": "Qualité des produits",
        "defaut": "Qualité irrégulière",
        "pos": ["delicieux", "delicieuse", "delicieuses", "savoureux", "savoureuse", "frais", "fraiche",
                "fraiches", "croustillant", "croustillante", "fondant", "moelleux", "gourmand", "succulent",
                "fait maison", "un regal", "regale", "tres bon", "tres bonne", "tres bons", "excellent pain",
                "bouquet magnifique", "fleurs magnifiques", "magnifique bouquet", "tient longtemps",
                "coupe parfaite", "resultat parfait", "qualite irreprochable", "produits de qualite"],
        "neg": ["rassis", "rassise", "fade", "brule", "brulee", "immangeable", "pas bon", "pas bonne",
                "pas terrible", "mauvais gout", "sans gout", "fane", "fanees", "fanes", "fanee", "plat froid",
                "trop cuit", "pas assez cuit", "pas cuit", "sec", "seche", "dur comme", "rate", "ratee",
                "abime", "abimees", "qualite en baisse", "moins bon", "mal coupe", "coloration ratee"],
        "neutre": ["pain", "baguette", "baguettes", "croissant", "croissants", "viennoiserie", "viennoiseries",
                   "patisserie", "patisseries", "gateau", "gateaux", "plat", "plats", "cuisine", "pizza",
                   "burger", "dessert", "fleurs", "bouquet", "bouquets", "composition", "coupe",
                   "coloration", "brushing", "produit", "produits", "qualite", "gout", "flan", "tarte"],
    },
    "prix": {
        "qualite": "Prix raisonnables",
        "defaut": "Prix jugés élevés",
        "pos": ["pas cher", "pas chere", "abordable", "abordables", "raisonnable", "raisonnables",
                "bon rapport qualite prix", "excellent rapport qualite prix", "prix correct", "prix corrects",
                "prix doux", "petits prix", "bon marche", "prix tres honnetes", "prix honnetes"],
        "neg": ["cher", "chere", "chers", "cheres", "trop cher", "hors de prix", "excessif", "arnaque",
                "abuse", "prix eleve", "prix eleves", "prix exorbitant", "beaucoup trop cher"],
        "neutre": ["prix", "tarif", "tarifs", "addition", "rapport qualite prix"],
    },
    "attente": {
        "qualite": "Service rapide",
        "defaut": "Attente trop longue",
        "pos": ["rapide", "rapidement", "sans attente", "efficace", "efficaces", "vite servi", "servi vite",
                "pas d'attente", "ponctuel", "dans les temps"],
        "neg": ["attente interminable", "trop d'attente", "trop long", "trop longue", "lent", "lente",
                "lenteur", "attendu", "attendre", "en retard", "retard", "oublie notre", "oublie ma",
                "interminable", "une eternite", "file enorme", "queue enorme"],
        "neutre": ["attente", "queue", "file", "minutes", "delai", "livraison"],
    },
    "proprete": {
        "qualite": "Établissement propre",
        "defaut": "Propreté à revoir",
        "pos": ["propre", "tres propre", "proprete irreprochable", "nickel", "impeccable"],
        "neg": ["sale", "sales", "salete", "cheveu", "poussiere", "mal entretenu", "mauvaise odeur",
                "mouche", "mouches", "insalubre", "crasseux", "hygiene douteuse", "pas propre", "douteuse"],
        "neutre": ["proprete", "hygiene", "toilettes"],
    },
    "choix": {
        "qualite": "Large choix",
        "defaut": "Manque de choix / ruptures",
        "pos": ["grand choix", "large choix", "beaucoup de choix", "variete", "varie", "variee", "large gamme",
                "originales", "original", "originale", "choix incroyable"],
        "neg": ["plus rien", "rupture", "peu de choix", "pas de choix", "manque de choix", "plus de pain",
                "plus de croissants", "presque vide", "vitrine vide", "plus aucun"],
        "neutre": ["choix", "gamme", "selection", "carte", "vitrine"],
    },
    "cadre": {
        "qualite": "Cadre agréable",
        "defaut": "Cadre peu agréable",
        "pos": ["cadre agreable", "joli", "jolie", "belle decoration", "jolie boutique", "belle boutique",
                "cosy", "terrasse agreable", "bonne ambiance", "ambiance agreable", "magnifique boutique"],
        "neg": ["bruyant", "bruyante", "trop de bruit", "exigu", "exigue", "mal agence", "vetuste", "sombre",
                "triste"],
        "neutre": ["cadre", "decoration", "deco", "ambiance", "salle", "boutique", "terrasse", "salon"],
    },
    "livraison": {
        "qualite": "Livraison soignée",
        "defaut": "Problèmes de livraison",
        "pos": ["livraison rapide", "livre rapidement", "livraison soignee", "livre a l'heure", "bien emballe"],
        "neg": ["livraison en retard", "livre en retard", "jamais livre", "pas livre", "jamais recu",
                "colis abime", "commande incomplete", "erreur de commande", "mauvaise commande", "livreur desagreable"],
        "neutre": ["livraison", "livreur", "colis", "commande en ligne", "click and collect"],
    },
}

GENERIC_POS = ["super", "top", "excellent", "excellente", "parfait", "parfaite", "genial", "bravo", "ravi",
               "ravie", "adore", "meilleur", "meilleure", "incroyable", "impeccable", "magnifique", "merci",
               "agreable", "tres bien", "au top", "recommande", "je recommande"]
GENERIC_NEG = ["decu", "decue", "decevant", "decevante", "nul", "nulle", "horrible", "mauvais", "mauvaise",
               "bof", "dommage", "inadmissible", "catastrophique", "a eviter", "honteux", "lamentable",
               "pas top", "pas terrible", "regrettable", "jamais plus", "plus jamais"]
# Toutes les expressions marquées, triées de la plus longue à la plus courte
EXPRESSIONS = sorted(
    [(p, +1, cle) for cle, t in THEMES.items() for p in t["pos"]]
    + [(p, -1, cle) for cle, t in THEMES.items() for p in t["neg"]],
    key=lambda x: -len(x[0]),
)

# Façon de citer un thème dans une réponse, selon le type de commerce
PHRASE_QUALITE = {
    "accueil": "notre accueil", "prix": "nos prix", "attente": "la rapidité du service",
    "proprete": "la propreté des lieux", "choix": "notre choix", "cadre": "le cadre",
    "livraison": "notre livraison",
}
PHRASE_DEFAUT = {
    "accueil": "l'accueil", "prix": "nos prix", "attente": "l'attente",
    "proprete": "la propreté", "choix": "le choix disponible", "cadre": "le cadre",
    "livraison": "la livraison",
}
PRODUITS_PAR_TYPE = {
    "boulangerie": "nos produits", "restaurant": "notre cuisine", "fleuriste": "nos compositions",
    "coiffeur": "nos prestations", "hotel": "votre séjour", "commerce": "nos produits",
    "artisan": "notre travail", "autre": "nos produits",
}

# Solutions proposées au commerçant pour chaque défaut
SOLUTIONS = {
    "livraison": [
        "Vérifier chaque commande avant le départ (liste de contrôle) et prévenir le client en cas de retard.",
        "Revoir les créneaux de livraison promis pour qu'ils soient tenables aux heures chargées.",
    ],
    "attente": [
        "Repérer les heures de pointe dans le dashboard et y prévoir un renfort.",
        "Préparer à l'avance les produits les plus demandés.",
        "Proposer la commande à l'avance (téléphone, en ligne) avec retrait rapide.",
    ],
    "accueil": [
        "Faire un point avec l'équipe sur l'accueil : bonjour, sourire, prise en charge rapide.",
        "Désigner une personne référente en caisse aux heures chargées.",
        "Recontacter le client pour comprendre ce qui s'est passé.",
    ],
    "qualite": {
        "boulangerie": [
            "Vérifier les temps et températures de cuisson sur les fournées concernées.",
            "Ajuster les quantités produites pour ne pas vendre de produits de la veille.",
            "Proposer un geste au client (produit offert à sa prochaine visite).",
        ],
        "restaurant": [
            "Contrôler la température et le dressage des plats au passe avant l'envoi.",
            "Revoir la fiche technique du plat cité avec la cuisine.",
            "Proposer un geste au client (dessert ou café offert à sa prochaine visite).",
        ],
        "fleuriste": [
            "Vérifier la fraîcheur des tiges à réception et changer l'eau tous les jours.",
            "Remettre une fiche de conseils d'entretien avec chaque bouquet.",
            "Proposer de refaire le bouquet ou un avoir au client.",
        ],
        "coiffeur": [
            "Valider le résultat attendu avec le client avant de commencer (photo, échange).",
            "Proposer une retouche gratuite dans la semaine.",
        ],
        "autre": [
            "Identifier le produit ou la prestation concernée et vérifier le processus.",
            "Proposer un geste commercial au client.",
        ],
    },
    "prix": [
        "Mettre en avant une offre d'entrée de gamme ou une formule.",
        "Expliquer ce qui justifie le prix (fait maison, produits locaux) sur place et dans la réponse.",
        "Créer une carte de fidélité pour les clients réguliers.",
    ],
    "proprete": [
        "Mettre en place une check-list de nettoyage avec horaires et responsable.",
        "Vérifier en priorité les zones visibles : vitrine, comptoir, toilettes.",
    ],
    "choix": [
        "Noter à quelle heure les ruptures arrivent et ajuster la production.",
        "Proposer la réservation des produits phares et prévenir quand un produit est épuisé.",
    ],
    "cadre": [
        "Prévoir de petits aménagements : lumière, plantes, rangement.",
        "Limiter les nuisances sonores aux heures chargées.",
    ],
}


# ---------------------------------------------------------------------------
# Outils texte
# ---------------------------------------------------------------------------
def normaliser(texte):
    """minuscules, sans accents, tirets -> espaces, apostrophes unifiées"""
    texte = unicodedata.normalize("NFD", texte or "")
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    texte = texte.lower().replace("’", "'").replace("-", " ")
    return re.sub(r"\s+", " ", texte)


def _cherche(phrase, texte):
    """Trouve 'phrase' en mot entier dans 'texte'. Renvoie la liste des positions."""
    motif = r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])"
    return [m.span() for m in re.finditer(motif, texte)]


NEGATION_RE = re.compile(r"(?<![a-z])(pas|plus|jamais|aucun|aucune|guere|n'\w*)\s+([a-z]+\s+)?$")


def _nie(texte, debut):
    """Vrai si l'expression est précédée d'une négation (au plus un mot entre les deux) :
    « pas frais », « pas assez aimable » -> nié ; « pas cher et délicieux » -> délicieux non nié."""
    return bool(NEGATION_RE.search(texte[max(0, debut - 25):debut]))


def solutions_pour(theme, type_commerce):
    sol = SOLUTIONS.get(theme, [])
    if isinstance(sol, dict):
        sol = sol.get(type_commerce) or sol["autre"]
    return sol


# ---------------------------------------------------------------------------
# Moteur de règles
# ---------------------------------------------------------------------------
def analyser_regles(commentaire, etoiles):
    """Renvoie (qualites, defauts) : listes de clés de thèmes."""
    texte = normaliser(commentaire)
    propositions = re.split(r"[.!?;\n]+| mais | cependant | par contre | en revanche ", texte)
    qualites, defauts = [], []

    for prop in propositions:
        prop = " " + prop.strip() + " "
        if len(prop.strip()) < 2:
            continue
        gen_pos = any(_cherche(m, prop) for m in GENERIC_POS)
        gen_neg = any(_cherche(m, prop) for m in GENERIC_NEG)

        # 1) Expressions marquées (positives / négatives), de la plus longue à la plus courte,
        #    tous thèmes confondus. Le texte trouvé est "consommé" : "pas cher" ne compte pas
        #    aussi "cher", et "plus de pain" (rupture) ne compte pas aussi "pain" (qualité).
        travail = prop
        scores = dict.fromkeys(THEMES, 0)
        for phrase, signe, cle in EXPRESSIONS:
            for debut, fin in _cherche(phrase, travail):
                s = -1 if signe > 0 and _nie(travail, debut) else signe
                scores[cle] += s
                travail = travail[:debut] + "#" * (fin - debut) + travail[fin:]

        # 2) Mots neutres (« pain », « accueil »...) sur le texte restant
        deja_marque = any(scores.values())
        for cle, theme in THEMES.items():
            score = scores[cle]
            neutre = any(_cherche(m, travail) for m in theme["neutre"])
            if score == 0 and neutre:
                # Le thème est cité sans adjectif clair : on se fie au ton de la phrase,
                # puis aux étoiles (seulement si la phrase ne parle pas déjà d'autre chose)
                if deja_marque:
                    pass  # l'adjectif de la phrase se rapporte déjà à un autre thème
                elif gen_neg and not gen_pos:
                    score = -1
                elif gen_pos and not gen_neg:
                    score = 1
                elif etoiles >= 4:
                    score = 1
                elif etoiles <= 2:
                    score = -1
            if score > 0 and cle not in qualites:
                qualites.append(cle)
            elif score < 0 and cle not in defauts:
                defauts.append(cle)

    # Un même thème ne peut pas être à la fois qualité et défaut : on tranche avec les étoiles
    for cle in list(set(qualites) & set(defauts)):
        if etoiles >= 4:
            defauts.remove(cle)
        else:
            qualites.remove(cle)
    return qualites, defauts


def _choix(options, graine):
    return options[graine % len(options)]

