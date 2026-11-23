from django.urls import path

from . import views

app_name = "locations"

urlpatterns = [
    path("google/connecter/", views.google_connecter, name="google_connecter"),
    path("google/retour/", views.google_retour, name="google_retour"),
    path("google/fiche/", views.choisir_fiche, name="choisir_fiche"),
    path("google/deconnecter/", views.google_deconnecter, name="google_deconnecter"),
    path("avis/synchroniser/", views.synchroniser, name="synchroniser"),
    path("demo/activer/", views.activer_demo, name="activer_demo"),
    path("demo/supprimer/", views.supprimer_demo, name="supprimer_demo"),
]
