from django.urls import path

from . import views

app_name = "insights"

urlpatterns = [
    path("analyses/", views.analyses, name="analyses"),
    path("recommandations/", views.recommandations_vue, name="recommandations"),
    path("alertes/<int:alerte_id>/lue/", views.alerte_lue, name="alerte_lue"),
    path("recommandations/<int:reco_id>/statut/", views.changer_statut, name="changer_statut"),
    path("outils/", views.outils_vue, name="outils"),
    path("outils/qr.<str:format_>", views.qr_telecharger, name="qr_telecharger"),
    path("outils/affiche/", views.qr_affiche, name="qr_affiche"),
    path("rapports/", views.rapports_vue, name="rapports"),
    path("rapports/pdf/", views.rapport_pdf_vue, name="rapport_pdf"),
    path("rapports/envoyer/", views.rapport_envoyer, name="rapport_envoyer"),
]
