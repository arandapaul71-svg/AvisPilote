"""Exemples pour remplir les réglages de l'assistant, adaptés au secteur.

Affichés sous chaque champ, et utilisables pour pré-remplir le formulaire
(le commerçant les relit et les adapte avant d'enregistrer : rien n'est enregistré seul).
Les crochets [ ] signalent ce qu'il faut remplacer par ses vraies informations.
"""

EXEMPLES = {
    "boulangerie": {
        "business_info": "Boulangerie artisanale, pain au levain cuit sur place chaque matin.\n"
                         "Ouvert du mardi au dimanche, 6 h 30 – 19 h 30, fermé le lundi.\n"
                         "Spécialités : baguette tradition, croissant pur beurre, flan pâtissier.\n"
                         "Commandes de gâteaux 48 h à l'avance par téléphone au [numéro].",
        "preferred_phrases": "À très vite au fournil !\nToute l'équipe vous remercie\nfait maison",
        "forbidden_phrases": "industriel\nsurgelé\ndésolé pour la gêne occasionnée",
        "negative_instructions": "Proposer au client de repasser en boutique et de demander [prénom du gérant].\n"
                                 "Pour une rupture de stock, rappeler qu'on peut réserver sa baguette par téléphone.\n"
                                 "Ne jamais citer le nom d'un employé.",
    },
    "restaurant": {
        "business_info": "Restaurant de cuisine provençale, produits frais du marché.\n"
                         "Service le midi du lundi au samedi, le soir du jeudi au samedi.\n"
                         "Menu du jour à [prix] €, terrasse ombragée, réservation conseillée le week-end.",
        "preferred_phrases": "Au plaisir de vous recevoir à nouveau\nnotre chef\nproduits frais",
        "forbidden_phrases": "désolé pour la gêne occasionnée\npas de chance\nc'est la faute du client",
        "negative_instructions": "Inviter le client à nous contacter à [e-mail] pour en parler.\n"
                                 "Pour l'attente, expliquer que tout est cuisiné à la commande, sans se justifier longuement.\n"
                                 "Ne jamais remettre en cause ce que dit le client.",
    },
    "fleuriste": {
        "business_info": "Fleuriste de quartier, fleurs de saison et compositions sur mesure.\n"
                         "Livraison à [ville] et alentours, du mardi au samedi.\n"
                         "Ateliers de composition florale un samedi par mois.",
        "preferred_phrases": "Au plaisir de fleurir vos prochains moments\nfleurs de saison\nfait main",
        "forbidden_phrases": "fleurs artificielles\ndésolé pour la gêne occasionnée",
        "negative_instructions": "Pour un bouquet qui a mal tenu, inviter le client à repasser avec une photo.\n"
                                 "Pour un retard de livraison, proposer d'appeler la boutique au [numéro].",
    },
    "coiffeur": {
        "business_info": "Salon de coiffure mixte, coupe, couleur et soins.\n"
                         "Sur rendez-vous du mardi au samedi, en ligne ou au [numéro].\n"
                         "Produits professionnels [marque].",
        "preferred_phrases": "À bientôt au salon\nprenez soin de vous\nnotre équipe",
        "forbidden_phrases": "c'est vous qui avez demandé ça\ndésolé pour la gêne occasionnée",
        "negative_instructions": "Proposer de revenir pour en discuter avec le coiffeur, sans promettre de retouche gratuite.\n"
                                 "Ne jamais discuter publiquement du résultat en détail.",
    },
    "autre": {
        "business_info": "[Activité] à [ville] depuis [année].\n"
                         "Ouvert du [jour] au [jour], de [heure] à [heure].\n"
                         "Ce qui fait notre différence : [vos points forts].",
        "preferred_phrases": "Merci pour votre confiance\nÀ très bientôt\ntoute l'équipe",
        "forbidden_phrases": "désolé pour la gêne occasionnée\nnous ne sommes pas responsables",
        "negative_instructions": "Inviter le client à nous contacter directement à [e-mail ou téléphone].\n"
                                 "Rester courtois et bref, ne jamais contredire le client publiquement.",
    },
}
EXEMPLES["hotel"] = EXEMPLES["commerce"] = EXEMPLES["artisan"] = EXEMPLES["autre"]

AIDE = {
    "business_info": "Ce que l'assistant peut dire de ton établissement : horaires, spécialités, services. "
                     "Il n'utilisera que ces faits (il n'invente rien).",
    "preferred_phrases": "Une expression par ligne. L'assistant les glisse dans ses réponses, sans les répéter à chaque fois.",
    "forbidden_phrases": "Une expression par ligne. Une réponse qui en contient une n'est jamais publiée automatiquement.",
    "negative_instructions": "Comment répondre aux clients mécontents : qui contacter, quoi proposer, ce qu'il ne faut jamais dire.",
}


def pour(secteur):
    return EXEMPLES.get(secteur, EXEMPLES["autre"])
