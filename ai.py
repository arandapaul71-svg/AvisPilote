"""Analyse des avis et rédaction des réponses.

Deux moteurs :
- Claude (API Anthropic) si ANTHROPIC_API_KEY est défini : réponses plus naturelles.
- Un moteur de règles intégré sinon (ou si l'API échoue) : gratuit, hors ligne.

Les deux renvoient le même format :
    {"qualites": [...], "defauts": [...], "reply": "...", "solution": "...", "source": "..."}
où qualites/defauts sont des clés de THEMES (accueil, qualite, prix...).
"""
import json
import re
import unicodedata

import requests

import config

# ---------------------------------------------------------------------------
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
}
PHRASE_DEFAUT = {
    "accueil": "l'accueil", "prix": "nos prix", "attente": "l'attente",
    "proprete": "la propreté", "choix": "le choix disponible", "cadre": "le cadre",
}
PRODUITS_PAR_TYPE = {
    "boulangerie": "nos produits", "restaurant": "notre cuisine", "fleuriste": "nos compositions",
    "coiffeur": "nos prestations", "autre": "nos produits",
}

# Solutions proposées au commerçant pour chaque défaut
SOLUTIONS = {
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


def _liste_fr(elements):
    if len(elements) <= 1:
        return "".join(elements)
    return ", ".join(elements[:-1]) + " et " + elements[-1]


def rediger_regles(avis, business, qualites, defauts):
    prenom = (avis["author"] or "").split(" ")[0]
    if not prenom or prenom.lower() in ("un", "utilisateur", "anonyme"):
        prenom = ""
    nom = business["name"]
    ton = business["ton"]
    graine = sum(ord(c) for c in str(avis.get("external_id", ""))) + avis["stars"]
    etoiles = avis["stars"]
    produits = PRODUITS_PAR_TYPE.get(business["type"], "nos produits")
    p = f" {prenom}" if prenom else ""

    def phrase_q(cle):
        return produits if cle == "qualite" else PHRASE_QUALITE[cle]

    def phrase_d(cle):
        return "la qualité de " + produits if cle == "qualite" else PHRASE_DEFAUT[cle]

    lignes = []
    if etoiles >= 4:
        ouvertures = {
            "chaleureux": [f"Merci beaucoup{p} pour ce super retour !",
                           f"Quel plaisir de lire votre avis{',' + p if p else ''} !",
                           f"Un grand merci{p} pour ces jolis mots !"],
            "professionnel": [f"Merci{p} pour votre avis.",
                              f"Nous vous remercions{',' + p + ',' if p else ''} pour votre retour.",
                              f"Merci{p} d'avoir pris le temps de partager votre expérience."],
            "décontracté": [f"Merci{p}, ça fait super plaisir !",
                            f"Trop sympa{p}, merci pour ce retour !",
                            f"Merci{p}, vous nous faites notre journée !"],
        }
        lignes.append(_choix(ouvertures.get(ton, ouvertures["chaleureux"]), graine))
        if qualites:
            lignes.append(f"Nous sommes ravis que vous ayez apprécié {_liste_fr([phrase_q(q) for q in qualites[:2]])}.")
        elif avis.get("comment"):
            lignes.append("Nous sommes ravis que votre visite vous ait plu.")
        lignes.append(_choix([f"Au plaisir de vous revoir très bientôt chez {nom} !",
                              "À très vite !",
                              f"Toute l'équipe de {nom} vous attend pour votre prochaine visite."], graine // 3))
    elif etoiles == 3:
        lignes.append(f"Merci{p} pour votre retour.")
        if qualites:
            lignes.append(f"Nous sommes contents que vous ayez apprécié {_liste_fr([phrase_q(q) for q in qualites[:2]])}.")
        if defauts:
            lignes.append(f"Nous prenons note de votre remarque sur {_liste_fr([phrase_d(d) for d in defauts[:2]])} "
                          "et allons y travailler.")
        lignes.append("Nous espérons vous offrir une expérience parfaite lors de votre prochaine visite.")
    else:
        bonjour = f"Bonjour{p}," if ton != "décontracté" else f"Bonjour{p} !"
        lignes.append(_choix([
            f"{bonjour} merci d'avoir pris le temps de nous écrire. Nous sommes sincèrement désolés que votre "
            "expérience n'ait pas été à la hauteur.",
            f"{bonjour} nous sommes vraiment navrés de lire votre avis : ce n'est pas l'expérience que nous "
            "voulons offrir à nos clients.",
            f"{bonjour} merci pour ce retour, même s'il nous attriste. Toutes nos excuses pour cette déception.",
        ], graine))
        if defauts:
            sujet = _liste_fr([phrase_d(d) for d in defauts[:2]])
            lignes.append(_choix([
                f"Votre remarque sur {sujet} est prise très au sérieux et nous en avons parlé avec l'équipe.",
                f"Nous avons fait le point avec l'équipe sur {sujet} pour que cela ne se reproduise pas.",
            ], graine // 2))
        if business["contact"]:
            lignes.append(f"N'hésitez pas à nous contacter directement à {business['contact']} pour que nous "
                          "puissions en discuter.")
        else:
            lignes.append("N'hésitez pas à revenir nous voir pour que nous puissions en discuter de vive voix.")
        lignes.append(_choix(["Nous espérons avoir l'occasion de vous faire changer d'avis.",
                              "Nous serions heureux de vous accueillir à nouveau pour vous montrer le meilleur de nous-mêmes."],
                             graine // 3))

    signature = business["signature"].strip() or f"L'équipe {nom}"
    return " ".join(lignes) + "\n\n" + signature


def solution_pour_avis(etoiles, defauts, type_commerce):
    if etoiles > 3 and not defauts:
        return None
    actions = [solutions_pour(d, type_commerce)[0] for d in defauts[:3]]
    if etoiles <= 2:
        actions.append("Recontacter le client en privé et lui proposer un geste commercial.")
    if not actions:
        return None
    return " ".join(actions)


# ---------------------------------------------------------------------------
# Moteur Claude (API Anthropic)
# ---------------------------------------------------------------------------
PROMPT_SYSTEME = """Tu es le responsable de la relation client d'un commerce local français.
Tu rédiges les réponses publiques aux avis Google et tu analyses chaque avis.
Règles pour la réponse :
- en français (ou dans la langue de l'avis s'il est écrit dans une autre langue), vouvoiement ;
- 2 à 4 phrases, naturelles, qui reprennent un détail précis de l'avis ;
- jamais de promesse chiffrée, jamais d'information personnelle sur le client, jamais d'agressivité ;
- avis 1-2 étoiles : excuses sincères, montrer qu'on a compris le problème, inviter à poursuivre en privé ;
- ne pas mettre de signature, elle est ajoutée ensuite.
Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour."""


def _appel_claude(avis, business):
    themes = ", ".join(f'"{k}" ({v["qualite"]} / {v["defaut"]})' for k, v in THEMES.items())
    contact = business["contact"] or "aucun (inviter à repasser en boutique)"
    demande = f"""Commerce : {business['name']} ({business['type']})
Ton souhaité : {business['ton']}
Contact pour les clients mécontents : {contact}
Avis de {avis['author']} — {avis['stars']} étoile(s) :
\"\"\"{avis.get('comment') or '(aucun texte, seulement la note)'}\"\"\"

Thèmes possibles : {themes}

Renvoie ce JSON :
{{"qualites": [clés des thèmes cités positivement],
  "defauts": [clés des thèmes cités négativement],
  "reply": "la réponse publique",
  "solution": "si l'avis signale un problème : 1 à 3 actions concrètes pour le commerçant, sinon null"}}"""

    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": config.ANTHROPIC_MODEL,
            "max_tokens": 600,
            "system": PROMPT_SYSTEME,
            "messages": [{"role": "user", "content": demande}],
        },
        timeout=30,
    )
    r.raise_for_status()
    texte = "".join(b.get("text", "") for b in r.json().get("content", []))
    debut, fin = texte.find("{"), texte.rfind("}")
    data = json.loads(texte[debut:fin + 1])

    qualites = [q for q in data.get("qualites", []) if q in THEMES]
    defauts = [d for d in data.get("defauts", []) if d in THEMES and d not in qualites]
    reply = str(data.get("reply", "")).strip()
    if not reply:
        raise ValueError("réponse vide")
    signature = business["signature"].strip() or f"L'équipe {business['name']}"
    solution = data.get("solution")
    return {
        "qualites": qualites,
        "defauts": defauts,
        "reply": reply + "\n\n" + signature,
        "solution": str(solution).strip() if solution else None,
        "source": "claude",
    }


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------
def traiter_avis(avis, business):
    """avis : dict avec author, stars, comment, external_id. business : ligne de la table businesses."""
    business = dict(business)
    if config.ANTHROPIC_API_KEY:
        try:
            return _appel_claude(avis, business)
        except Exception as e:  # réseau, quota API, JSON invalide... on bascule sur les règles
            print(f"[ai] Claude indisponible ({e.__class__.__name__}), utilisation des règles")

    qualites, defauts = analyser_regles(avis.get("comment", ""), avis["stars"])
    return {
        "qualites": qualites,
        "defauts": defauts,
        "reply": rediger_regles(avis, business, qualites, defauts),
        "solution": solution_pour_avis(avis["stars"], defauts, business["type"]),
        "source": "regles",
    }
