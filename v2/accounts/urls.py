from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("inscription/", views.inscription, name="inscription"),
    path("connexion/", views.connexion, name="connexion"),
    path("demo/", views.demo_express, name="demo_express"),
    path("cgu/", views.page_legale, {"page": "cgu"}, name="cgu"),
    path("confidentialite/", views.page_legale, {"page": "confidentialite"}, name="confidentialite"),
    path("mentions-legales/", views.page_legale, {"page": "mentions"}, name="mentions"),
    path("deconnexion/", views.deconnexion, name="deconnexion"),
    path("tableau-de-bord/", views.tableau_de_bord, name="tableau_de_bord"),
    path("abonnement/", views.abonnement, name="abonnement"),
    path("compte/supprimer/", views.supprimer_compte, name="supprimer_compte"),
]
