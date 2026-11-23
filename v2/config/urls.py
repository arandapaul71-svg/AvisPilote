from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Adresse d'administration non devinable : moins de robots qui tentent /admin/.
    path("gestion-interne/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("locations.urls")),
    path("", include("reviews.urls")),
    path("", include("insights.urls")),
    path("", include("billing.urls")),
]
