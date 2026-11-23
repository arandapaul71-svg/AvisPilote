"""Rédaction des réponses par règles (sans IA), en respectant les réglages du commerçant.

Moins naturel que Claude, mais gratuit et sans risque d'invention : les phrases
ne contiennent que ce qui est dans l'avis (thèmes repérés) et les réglages.
"""
from .regles import PHRASE_DEFAUT, PHRASE_QUALITE, PRODUITS_PAR_TYPE

EMOJI_POSITIF = " 😊"


def _choix(options, graine):
    return options[graine % len(options)]


def _liste_fr(elements):
    if len(elements) <= 1:
        return "".join(elements)
    return ", ".join(elements[:-1]) + " et " + elements[-1]


def _prenom(auteur):
    prenom = (auteur or "").split(" ")[0]
    return "" if not prenom or prenom.lower() in ("un", "utilisateur", "anonyme", "client") else prenom


OUVERTURES_POSITIVES = {
    "chaleureux": ["Merci beaucoup{p} pour ce super retour !", "Quel plaisir de lire {votre} avis{v} !",
                   "Un grand merci{p} pour ces jolis mots !"],
    "professionnel": ["Merci{p} pour {votre} avis.", "Merci{p} d'avoir pris le temps de partager {votre} expérience.",
                      "Nous {vous} remercions{p} pour {votre} retour."],
    "convivial": ["Merci{p}, ça nous fait super plaisir !", "Merci{p} pour ce chouette retour !",
                  "Merci{p}, on est ravis de lire ça !"],
    "elegant": ["Merci{p} pour ces mots délicats.", "Nous sommes très touchés par {votre} message{v}.",
                "Merci infiniment{p} pour {votre} confiance."],
    "decontracte": ["Merci{p}, ça fait super plaisir !", "Trop sympa{p}, merci pour ce retour !",
                    "Merci{p}, {vous} nous faites notre journée !"],
}


def rediger(avis, reglages, organisation, qualites, defauts, variante=0):
    tu = reglages.tutoiement
    mots = {"vous": "te" if tu else "vous", "votre": "ton" if tu else "votre", "vos": "tes" if tu else "vos"}
    prenom = _prenom(avis.author)
    p = f" {prenom}" if prenom else ""
    v = f", {prenom}" if prenom else ""
    nom = organisation.name
    produits = PRODUITS_PAR_TYPE.get(organisation.sector, "nos produits")
    graine = sum(ord(c) for c in avis.google_review_id) + avis.stars + variante * 7
    remplir = lambda s: s.format(p=p, v=v, **mots)  # noqa: E731

    def phrase_q(cle):
        return produits if cle == "qualite" else PHRASE_QUALITE[cle]

    def phrase_d(cle):
        return "la qualité de " + produits if cle == "qualite" else PHRASE_DEFAUT[cle]

    lignes = []
    if avis.stars >= 4:
        lignes.append(remplir(_choix(OUVERTURES_POSITIVES.get(reglages.tone, OUVERTURES_POSITIVES["chaleureux"]), graine)))
        if qualites:
            sujet = _liste_fr([phrase_q(q) for q in qualites[:2]])
            ayez = "tu aies" if tu else "vous ayez"
            avez = "tu as" if tu else "vous avez"
            lignes.append(_choix([
                f"Nous sommes ravis que {ayez} apprécié {sujet}.",
                f"Savoir que {avez} aimé {sujet} fait vraiment plaisir à toute l'équipe.",
                f"C'est une belle récompense pour nous que {ayez} remarqué {sujet}.",
                f"Nous transmettons {mots['vos']} compliments sur {sujet} à l'équipe.",
            ], graine // 2))
        # Seules les vraies phrases (3 mots ou plus) peuvent servir de fin de réponse ;
        # les mots-clés courts (« fait maison ») ne sont utilisables que par Claude.
        preferees = [e.strip() for e in (reglages.preferred_phrases or "").splitlines() if len(e.split()) >= 3]
        fin = preferees[graine % len(preferees)] if preferees else _choix(
            [f"Au plaisir de {mots['vous']} revoir très bientôt chez {nom} !", "À très vite !",
             f"Toute l'équipe de {nom} {mots['vous']} attend pour {mots['votre']} prochaine visite.",
             f"On {mots['vous']} attend avec plaisir pour {mots['votre']} prochain passage.",
             "Belle journée et à bientôt !"], graine // 5)
        lignes.append(fin + (EMOJI_POSITIF if reglages.emojis else ""))
    elif avis.stars == 3:
        lignes.append(f"Merci{p} pour {mots['votre']} retour.")
        if qualites:
            lignes.append(f"Nous sommes contents que {'tu aies' if tu else 'vous ayez'} apprécié {_liste_fr([phrase_q(q) for q in qualites[:2]])}.")
        if defauts:
            lignes.append(f"Nous prenons note de {'ta' if tu else 'votre'} remarque sur {_liste_fr([phrase_d(d) for d in defauts[:2]])}.")
        lignes.append(f"Nous espérons {mots['vous']} offrir une expérience encore meilleure lors de {mots['votre']} prochaine visite.")
    else:
        lignes.append(_choix([
            f"Bonjour{p}, merci d'avoir pris le temps de nous écrire. Nous sommes sincèrement désolés que {mots['votre']} expérience n'ait pas été à la hauteur.",
            f"Bonjour{p}, nous sommes navrés de lire {mots['votre']} avis : ce n'est pas l'expérience que nous voulons offrir.",
            f"Bonjour{p}, merci pour ce retour. Nous regrettons sincèrement {'ta' if tu else 'votre'} déception.",
        ], graine))
        if defauts:
            lignes.append(f"{'Ta' if tu else 'Votre'} remarque sur {_liste_fr([phrase_d(d) for d in defauts[:2]])} est prise au sérieux et nous allons en parler avec l'équipe.")
        lignes.append(f"N'hésite{'' if tu else 'z'} pas à nous contacter directement pour que nous puissions en discuter.")

    if reglages.length == "courte":
        lignes = [lignes[0], lignes[-1]] if len(lignes) > 2 else lignes
    signature = reglages.signature.strip() or f"L'équipe {nom}"
    return " ".join(lignes) + "\n\n" + signature


def actions_pour(etoiles, defauts, secteur):
    """Solutions concrètes proposées au commerçant (jamais publiées)."""
    from .regles import solutions_pour

    actions = [solutions_pour(d, secteur)[0] for d in defauts[:3] if solutions_pour(d, secteur)]
    if etoiles <= 2:
        actions.append("Recontacter le client en privé pour comprendre ce qui s'est passé.")
    return actions
