"""Synchronisation planifiée : `python manage.py synchroniser_avis`.

À lancer toutes les 15 minutes par le planificateur de l'hébergeur (cron, tâche
planifiée Windows…). Ne touche que les fiches pas synchronisées depuis 15 minutes.
"""
from django.core.management.base import BaseCommand

from locations import google_client, sync
from reviews import traitement


class Command(BaseCommand):
    help = "Récupère les nouveaux avis Google de toutes les fiches connectées."

    def handle(self, *args, **options):
        ok = erreurs = 0
        for fiche in sync.a_synchroniser():
            try:
                res = sync.synchroniser(fiche)
                n = traitement.traiter_en_attente(fiche)
                ok += 1
                self.stdout.write(f"{fiche.pk} {fiche.title} : +{res['ajoutes']} / ~{res['mis_a_jour']} / IA {n}")
            except google_client.GoogleErreur as e:
                erreurs += 1
                self.stderr.write(f"{fiche.pk} {fiche.title} : {e.code}")
                if e.code == "limite":
                    break  # Google nous freine : on arrête, la prochaine exécution reprendra
        self.stdout.write(self.style.SUCCESS(f"Terminé : {ok} fiche(s) synchronisée(s), {erreurs} erreur(s)."))
