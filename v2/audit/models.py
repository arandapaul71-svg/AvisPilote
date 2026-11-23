"""Journal des actions importantes (qui a fait quoi, quand, depuis quelle IP)."""
from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    # SET_NULL : le journal survit à la suppression d'un compte (preuve en cas de litige),
    # mais ne garde alors plus de lien vers la personne.
    organization = models.ForeignKey("accounts.Organization", null=True, on_delete=models.SET_NULL)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=60)
    details = models.JSONField(default=dict)
    ip = models.GenericIPAddressField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


def journaliser(request, action, **details):
    user = request.user if request.user.is_authenticated else None
    AuditLog.objects.create(
        organization=getattr(request, "organisation", None),
        user=user,
        action=action,
        details=details,
        ip=request.META.get("REMOTE_ADDR"),
    )
