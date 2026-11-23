def organisation(request):
    """Variables disponibles dans tous les gabarits : organisation, démo, compteurs de la barre latérale."""
    org = getattr(request, "organisation", None)
    contexte = {"organisation": org, "membership": getattr(request, "membership", None),
                "en_demo": False, "nb_a_valider": 0, "nb_alertes": 0, "fiche_active": None}
    if org is None:
        return contexte
    # Imports locaux : évite un import circulaire au démarrage de Django.
    from locations.sync import fiche_active
    from reviews.models import ReplyDraft

    fiche = fiche_active(org)
    contexte["fiche_active"] = fiche
    if fiche is not None:
        contexte["en_demo"] = fiche.is_demo
        contexte["nb_a_valider"] = (fiche.reviews.filter(google_reply="", drafts__status=ReplyDraft.Statut.A_VALIDER)
                                    .distinct().count())
        contexte["nb_alertes"] = fiche.alerts.filter(read_at__isnull=True).count()
    return contexte
