"""Envoi du rapport par e-mail (texte + HTML + PDF en pièce jointe).

En développement, Django affiche l'e-mail dans la console au lieu de l'envoyer
(EMAIL_BACKEND console). En production : un service SMTP (Brevo, Mailjet…) dans le .env.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from accounts.models import Role

from . import rapport_pdf, rapports

log = logging.getLogger("avispilote")


def destinataires(organisation):
    return [m.user.email for m in organisation.memberships.select_related("user").filter(role=Role.OWNER)]


def envoyer(fiche, r=None):
    """Envoie le rapport au(x) gérant(s). Renvoie le nombre de destinataires."""
    r = r or rapports.construire(fiche, fiche.organization.rapport_frequence)
    a_qui = destinataires(fiche.organization)
    if not a_qui:
        return 0
    contexte = {"r": r, "bilan": rapports.phrase_bilan(r), "app_url": settings.APP_URL}
    message = EmailMultiAlternatives(
        subject=f"{r['type_nom']} AvisPilote · {r['titre']} · {fiche.title}",
        body=render_to_string("insights/email_rapport.txt", contexte),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=a_qui,
    )
    message.attach_alternative(render_to_string("insights/email_rapport.html", contexte), "text/html")
    nom = f"rapport-{r['type']}-{r['debut']:%Y-%m-%d}.pdf"
    message.attach(nom, rapport_pdf.generer(r), "application/pdf")
    message.send()
    return len(a_qui)
