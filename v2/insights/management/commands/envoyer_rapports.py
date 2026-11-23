"""Envoi automatique des rapports : `python manage.py envoyer_rapports`.

À planifier une fois par jour (ex. 7 h). Chaque organisation reçoit le rapport de la
dernière période terminée (mois ou semaine selon son réglage), une seule fois.
"""
from django.core.management.base import BaseCommand

from accounts.models import Organization
from insights import envoi, rapports
from locations import sync


class Command(BaseCommand):
    help = "Envoie les rapports mensuels / hebdomadaires aux gérants qui les ont activés."

    def handle(self, *args, **options):
        envoyes = 0
        for org in Organization.objects.filter(rapport_email=True).select_related("subscription"):
            sub = getattr(org, "subscription", None)
            fiche = sync.fiche_active(org)
            if fiche is None or fiche.is_demo or sub is None or not sub.est_utilisable or not sub.a_la_fonction("rapports"):
                continue
            titre = rapports.bornes(org.rapport_frequence)[3]
            cle = f"{org.rapport_frequence}:{titre}"[:40]
            if org.dernier_rapport == cle:
                continue  # déjà envoyé pour cette période
            try:
                envoi.envoyer(fiche, rapports.construire(fiche, org.rapport_frequence))
            except Exception as e:  # noqa: BLE001 - un échec d'envoi ne doit pas bloquer les autres
                self.stderr.write(f"{org.pk} : échec ({e.__class__.__name__})")
                continue
            org.dernier_rapport = cle
            org.save(update_fields=["dernier_rapport"])
            envoyes += 1
        self.stdout.write(self.style.SUCCESS(f"{envoyes} rapport(s) envoyé(s)."))
