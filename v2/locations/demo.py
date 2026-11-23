"""Fiche de démonstration : faux avis pour essayer l'appli sans fiche Google.

Règles (cahier des charges : ne jamais faire croire que Google est connecté) :
- la fiche est marquée is_demo et un bandeau « Démonstration » s'affiche partout ;
- rien n'est jamais envoyé à Google ;
- désactivé en production (DEMO_AUTORISEE=0) ;
- supprimée automatiquement quand une vraie fiche Google est connectée.

Le jeu contient volontairement un pic positif (animation) et un pic négatif (attente).
"""
import math
import random
import uuid
from datetime import datetime, time, timedelta

from django.utils import timezone

from reviews.models import Review

from .models import Location

PRENOMS = ["Camille", "Lucas", "Léa", "Hugo", "Manon", "Nathan", "Chloé", "Louis", "Emma", "Jules", "Inès",
           "Tom", "Sarah", "Enzo", "Julie", "Théo", "Clara", "Maxime", "Laura", "Antoine", "Marie", "Karim",
           "Sophie", "Nicolas", "Élodie", "Yasmine", "Pierre", "Anaïs", "Mehdi", "Lina", "Romain"]

TEXTES = {
    "boulangerie": {
        "pos": ["Le pain est délicieux et toujours croustillant.", "Les croissants sont un régal, fondants à souhait.",
                "Accueil chaleureux, la vendeuse est adorable.", "Prix raisonnables pour cette qualité.",
                "Boutique très propre et bien rangée.", "Grand choix de pâtisseries, difficile de choisir !",
                "Service rapide même le dimanche matin.", "Meilleure baguette du quartier, je recommande."],
        "neg": ["Baguette rassise alors qu'achetée le matin même.", "Attendu 20 minutes, une seule vendeuse en caisse.",
                "Accueil froid, pas un bonjour.", "Trop cher pour ce que c'est.", "Plus de pain à 18h, dommage.",
                "Croissants secs et pas assez cuits.", "Le flan était fade."],
        "event": ["Super journée dégustation, les galettes étaient délicieuses !",
                  "Belle animation ce samedi, l'équipe était souriante.", "Dégustation géniale, accueil au top."],
    },
    "restaurant": {
        "pos": ["Les plats sont délicieux et copieux.", "Serveur très aimable et de bon conseil.",
                "Bon rapport qualité prix pour le menu du midi.", "Cadre agréable avec une jolie terrasse.",
                "Service rapide, parfait pour la pause déjeuner.", "Desserts faits maison, un régal."],
        "neg": ["Plat froid et sans goût.", "Attente interminable entre l'entrée et le plat.",
                "Beaucoup trop cher pour des portions minuscules.", "Salle très bruyante, impossible de discuter.",
                "Viande trop cuite alors que demandée saignante.", "Table sale à notre arrivée."],
        "event": ["Soirée concert géniale, les plats étaient délicieux !", "Super ambiance pour la soirée à thème."],
    },
    "fleuriste": {
        "pos": ["Bouquet magnifique, il tient longtemps.", "Fleuriste de très bon conseil.",
                "Compositions originales et fleurs fraîches.", "Prix doux pour de si beaux bouquets.",
                "Livraison rapide et soignée.", "Accueil chaleureux et souriant."],
        "neg": ["Fleurs fanées au bout de deux jours.", "Bouquet très cher pour sa taille.",
                "Livraison en retard pour un anniversaire, très déçu.", "Peu de choix le samedi après-midi."],
        "event": ["Atelier composition florale génial, très bons conseils !", "Super atelier, bouquet magnifique."],
    },
    "coiffeur": {
        "pos": ["Coupe parfaite, exactement ce que je voulais.", "Coiffeuse adorable et de bon conseil.",
                "Salon très propre et cosy.", "Prix corrects pour la prestation.", "Coloration magnifique."],
        "neg": ["Coloration ratée, rien à voir avec la photo.", "Attendu 40 minutes malgré le rendez-vous.",
                "Trop cher pour une simple coupe.", "Coupe mal faite, déçue."],
        "event": ["Journée portes ouvertes au top, coupe parfaite !", "Super animation au salon, équipe adorable."],
    },
    "autre": {
        "pos": ["Accueil chaleureux et équipe souriante.", "Produits de qualité, je recommande.",
                "Prix raisonnables.", "Service rapide et efficace.", "Endroit propre et bien rangé."],
        "neg": ["Accueil désagréable.", "Attente beaucoup trop longue.", "Trop cher par rapport à la concurrence.",
                "Produit abîmé, très déçu.", "Peu de choix."],
        "event": ["Super journée portes ouvertes, accueil au top !", "Belle animation, équipe très sympa."],
    },
}
TEXTES["hotel"] = TEXTES["commerce"] = TEXTES["artisan"] = TEXTES["autre"]
EVENEMENT_NEGATIF = ["Attente interminable aujourd'hui, une seule personne pour servir.",
                     "Trop d'attente et personnel débordé, dommage.",
                     "Attendu 25 minutes pour être servi, inadmissible.",
                     "Accueil désagréable, tout le monde était stressé."]


def _poisson(rng, lam):
    limite, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limite:
            return k
        k += 1


def _commentaire(rng, textes, etoiles):
    if rng.random() < 0.15:
        return ""  # environ 15 % des avis Google n'ont qu'une note
    if etoiles >= 4:
        return " ".join(rng.sample(textes["pos"], rng.choice([1, 1, 2])))
    if etoiles == 3:
        neg = rng.choice(textes["neg"])
        return rng.choice(textes["pos"]).rstrip(".!") + ", mais " + neg[0].lower() + neg[1:]
    return " ".join(rng.sample(textes["neg"], rng.choice([1, 2])))


def creer_fiche_demo(organisation, jours=95):
    """Crée (ou recrée) la fiche de démonstration. Renvoie le nombre d'avis générés."""
    organisation.locations.filter(is_demo=True).delete()
    fiche = Location.objects.create(organization=organisation, title=f"{organisation.name} (démo)",
                                    sector=organisation.sector, is_demo=True)
    rng = random.Random(organisation.pk * 7919)
    textes = TEXTES.get(organisation.sector, TEXTES["autre"])
    tz = timezone.get_current_timezone()
    maintenant = timezone.localtime()
    aujourd_hui = maintenant.date()
    jour_pic_neg = aujourd_hui - timedelta(days=20)
    jour_pic_pos = aujourd_hui - timedelta(days=6)
    avis = []

    jour = aujourd_hui - timedelta(days=jours)
    while jour <= aujourd_hui:
        lam = 1.5 if jour.weekday() >= 5 else 0.8
        for _ in range(_poisson(rng, lam)):
            e = rng.choices([5, 4, 3, 2, 1], weights=[55, 22, 10, 6, 7])[0]
            avis.append((jour, e, _commentaire(rng, textes, e)))
        jour += timedelta(days=1)
    for t in EVENEMENT_NEGATIF:
        avis.append((jour_pic_neg, rng.choice([1, 1, 2]), t))
    for _ in range(9):
        avis.append((jour_pic_pos, rng.choice([5, 5, 4]), rng.choice(textes["event"])))
    avis.append((aujourd_hui, 1, " ".join(rng.sample(textes["neg"], 2))))

    objets = []
    for jour, etoiles, texte in avis:
        heure = time(rng.randint(8, 19), rng.randint(0, 59))
        date = datetime.combine(jour, heure).replace(tzinfo=tz)
        if date > maintenant:
            date = maintenant - timedelta(minutes=rng.randint(1, 120))
        objets.append(Review(
            location=fiche, google_review_id="demo-" + uuid.uuid4().hex[:16],
            author=f"{rng.choice(PRENOMS)} {chr(rng.randint(65, 90))}.",
            stars=etoiles, comment=texte, created_at=date,
        ))
    Review.objects.bulk_create(objets)
    notes = [o.stars for o in objets]
    fiche.average_rating = round(sum(notes) / len(notes), 2)
    fiche.total_review_count = len(notes)
    fiche.last_sync_at = timezone.now()
    fiche.save()
    return len(objets)
