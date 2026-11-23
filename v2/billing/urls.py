from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("abonnement/payer/", views.payer, name="payer"),
    path("abonnement/portail/", views.portail, name="portail_get"),
    path("stripe/webhook/", views.webhook, name="webhook"),
]
