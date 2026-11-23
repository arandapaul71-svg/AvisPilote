"""Génère de faux avis réalistes pour tester l'appli sans fiche Google.

Le jeu de données contient volontairement :
- un pic positif ce mois-ci (animation / événement),
- un pic négatif le mois dernier (rush, attente),
- un mois en cours qui dépasse le quota de la formule Essentiel (40 avis).
"""
import math
import random
import uuid
from datetime import datetime, timedelta

import quotas

PRENOMS = ["Camille", "Lucas", "Léa", "Hugo", "Manon", "Nathan", "Chloé", "Louis", "Emma", "Jules", "Inès",
           "Tom", "Sarah", "Enzo", "Julie", "Théo", "Clara", "Maxime", "Laura", "Antoine", "Marie", "Paul",
           "Sophie", "Nicolas", "Élodie", "Karim", "Yasmine", "Pierre", "Anaïs", "Mehdi", "Lina", "Romain"]

TEXTES = {
    "boulangerie": {
        "pos": ["Le pain est délicieux et toujours croustillant.", "Les croissants sont un régal, fondants à souhait.",
                "Accueil chaleureux, la vendeuse est adorable.", "Prix raisonnables pour cette qualité.",
                "Boutique très propre et bien rangée.", "Grand choix de pâtisseries, difficile de choisir !",
                "Service rapide même le dimanche matin.", "Meilleure baguette du quartier, je recommande.",
                "Équipe souriante et de bon conseil.", "Les tartes aux fruits sont savoureuses."],
        "neg": ["Baguette rassise alors qu'achetée le matin même.", "Attendu 20 minutes, une seule vendeuse en caisse.",
                "Accueil froid, pas un bonjour.", "Trop cher pour ce que c'est.", "Plus de pain à 18h, dommage.",
                "Croissants secs et pas assez cuits.", "Vendeuse désagréable ce matin.", "Le flan était fade."],
        "event_pos": ["Super journée dégustation, les galettes étaient délicieuses !",
                      "Belle animation ce samedi, l'équipe était souriante.",
                      "Venu pour la fête du pain, quel régal !", "Dégustation géniale, accueil au top."],
    },
    "restaurant": {
        "pos": ["Les plats sont délicieux et copieux.", "Serveur très aimable et de bon conseil.",
                "Bon rapport qualité prix pour le menu du midi.", "Cadre agréable avec une jolie terrasse.",
                "Service rapide, parfait pour la pause déjeuner.", "Desserts faits maison, un régal.",
                "Salle propre et bien décorée.", "Carte variée, il y en a pour tous les goûts."],
        "neg": ["Plat froid et sans goût.", "Attente interminable entre l'entrée et le plat.", "Serveuse désagréable.",
                "Beaucoup trop cher pour des portions minuscules.", "Salle très bruyante, impossible de discuter.",
                "Viande trop cuite alors que demandée saignante.", "Table sale à notre arrivée."],
        "event_pos": ["Soirée concert géniale, les plats étaient délicieux !", "Super ambiance pour la soirée à thème.",
                      "Menu spécial excellent, équipe au top.", "Soirée dégustation de vins très réussie."],
    },
    "fleuriste": {
        "pos": ["Bouquet magnifique, il tient longtemps.", "Fleuriste de très bon conseil.",
                "Compositions originales et fleurs fraîches.", "Prix doux pour de si beaux bouquets.",
                "Jolie boutique, on a envie de tout acheter.", "Livraison rapide et soignée.",
                "Accueil chaleureux et souriant."],
        "neg": ["Fleurs fanées au bout de deux jours.", "Bouquet très cher pour sa taille.",
                "Livraison en retard pour un anniversaire, très déçu.", "Accueil froid, pas aimable.",
                "Peu de choix le samedi après-midi."],
        "event_pos": ["Atelier composition florale génial, très bons conseils !",
                      "Super atelier, bouquet magnifique à la fin.", "Atelier fête des mères au top, merci !"],
    },
    "coiffeur": {
        "pos": ["Coupe parfaite, exactement ce que je voulais.", "Coiffeuse adorable et de bon conseil.",
                "Salon très propre et cosy.", "Prix corrects pour la prestation.", "Pris rapidement sans rendez-vous.",
                "Coloration magnifique, je recommande."],
        "neg": ["Coloration ratée, rien à voir avec la photo.", "Attendu 40 minutes malgré le rendez-vous.",
                "Trop cher pour une simple coupe.", "Coiffeur pas aimable du tout.", "Coupe mal faite, déçue."],
        "event_pos": ["Journée portes ouvertes au top, coupe parfaite !", "Super animation au salon, équipe adorable."],
    },
    "autre": {
        "pos": ["Accueil chaleureux et équipe souriante.", "Produits de qualité, je recommande.",
                "Prix raisonnables.", "Service rapide et efficace.", "Boutique propre et bien rangée.",
                "Grand choix, on trouve ce qu'on cherche."],
        "neg": ["Accueil désagréable.", "Attente beaucoup trop longue.", "Trop cher par rapport à la concurrence.",
                "Produit abîmé, très déçu.", "Peu de choix en rayon."],
        "event_pos": ["Super journée portes ouvertes, accueil au top !", "Belle animation, équipe très sympa."],
    },
}
EVENT_NEG = ["Attente interminable aujourd'hui, une seule personne pour servir.",
             "Plus rien en vitrine à midi, très déçu.", "Trop d'attente et personnel débordé, dommage.",
             "Attendu 25 minutes pour être servi, inadmissible.", "Accueil désagréable, tout le monde était stressé."]


def _etoiles(rng):
    return rng.choices([5, 4, 3, 2, 1], weights=[55, 22, 10, 6, 7])[0]


def _commentaire(rng, textes, etoiles):
    if rng.random() < 0.15:
        return ""  # environ 15 % des avis Google n'ont que la note
    if etoiles >= 4:
        return " ".join(rng.sample(textes["pos"], rng.choice([1, 1, 2])))
    if etoiles == 3:
        neg = rng.choice(textes["neg"])
        return rng.choice(textes["pos"]).rstrip(".!") + ", mais " + neg[0].lower() + neg[1:]
    return " ".join(rng.sample(textes["neg"], rng.choice([1, 2])))


def _horodatage(rng, jour, maintenant):
    if jour == maintenant.date():
        minutes = maintenant.hour * 60 + maintenant.minute
        dt = maintenant - timedelta(minutes=rng.randint(0, max(0, min(minutes - 1, 600))))
    else:
        dt = datetime.combine(jour, datetime.min.time()) + timedelta(hours=rng.randint(8, 19),
                                                                      minutes=rng.randint(0, 59))
    return dt.isoformat(timespec="seconds")


def generer(db, business, jours=95):
    rng = random.Random(business["id"] * 7919)
    textes = TEXTES.get(business["type"], TEXTES["autre"])
    maintenant = datetime.now()
    aujourd_hui = maintenant.date()
    debut_mois = aujourd_hui.replace(day=1)
    avis = []

    def ajouter(jour, etoiles, texte):
        avis.append((jour, etoiles, texte))

    # Mois précédents : environ 1 avis par jour, un peu plus le week-end
    jour = aujourd_hui - timedelta(days=jours)
    while jour < debut_mois:
        lam = 1.5 if jour.weekday() >= 5 else 0.8
        for _ in range(_poisson(rng, lam)):
            e = _etoiles(rng)
            ajouter(jour, e, _commentaire(rng, textes, e))
        jour += timedelta(days=1)

    # Pic négatif le mois dernier, pic positif il y a ~2 mois
    jour_neg = debut_mois - timedelta(days=12)
    for t in rng.sample(EVENT_NEG, 5):
        ajouter(jour_neg, rng.choice([1, 1, 2]), t)
    ajouter(jour_neg, 3, "Bon produit, mais attente trop longue aujourd'hui.")
    jour_pos_ancien = debut_mois - timedelta(days=45)
    for _ in range(8):
        ajouter(jour_pos_ancien, rng.choice([5, 5, 4]), rng.choice(textes["event_pos"]))

    # Mois en cours : 46 avis (dépasse le quota Essentiel de 40), dont un pic positif
    jours_ecoules = (aujourd_hui - debut_mois).days + 1
    jour_event = debut_mois + timedelta(days=max(0, jours_ecoules - 7))
    for _ in range(12):
        e = rng.choice([5, 5, 5, 4])
        ajouter(jour_event, e, rng.choice(textes["event_pos"]))
    for _ in range(32):
        j = debut_mois + timedelta(days=rng.randrange(jours_ecoules))
        e = rng.choices([5, 4, 3, 2, 1], weights=[60, 25, 10, 3, 2])[0]
        ajouter(j, e, _commentaire(rng, textes, e))
    # Deux avis négatifs récents, à valider par le commerçant
    for decalage, etoiles in ((1, 2), (0, 1)):
        j = max(debut_mois, aujourd_hui - timedelta(days=decalage))
        ajouter(j, etoiles, " ".join(rng.sample(textes["neg"], 2)))

    for jour, etoiles, texte in avis:
        prenom = rng.choice(PRENOMS)
        cree = _horodatage(rng, jour, maintenant)
        db.execute(
            """INSERT INTO reviews (business_id, external_id, author, stars, comment, created_at, month)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (business["id"], "demo-" + uuid.uuid4().hex[:12], f"{prenom} {chr(rng.randint(65, 90))}.",
             etoiles, texte, cree, cree[:7]),
        )
    db.execute("UPDATE businesses SET mode = 'demo', last_sync = ? WHERE id = ?",
               (maintenant.isoformat(timespec="seconds"), business["id"]))
    db.commit()

    business = db.execute("SELECT * FROM businesses WHERE id = ?", (business["id"],)).fetchone()
    quotas.traiter_en_attente(db, business)
    # On simule un commerçant qui a déjà validé les réponses aux avis de plus d'une semaine
    db.execute(
        """UPDATE reviews SET status = 'publiee', reply_published_at = created_at
           WHERE business_id = ? AND status = 'a_valider' AND created_at < ?""",
        (business["id"], (aujourd_hui - timedelta(days=7)).isoformat()),
    )
    db.commit()
    return len(avis)


def _poisson(rng, lam):
    # Tirage de Poisson simple (algorithme de Knuth), suffisant pour de petites valeurs
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1
