from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path("avis/", views.liste, name="liste"),
    path("avis/<int:avis_id>/repondre/", views.repondre, name="repondre"),
    path("avis/<int:avis_id>/regenerer/", views.regenerer, name="regenerer"),
    path("assistant/", views.assistant, name="assistant"),
]
