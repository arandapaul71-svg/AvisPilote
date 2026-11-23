from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Membership, Organization, User


@admin.register(User)
class AdminUtilisateur(UserAdmin):
    ordering = ["email"]
    list_display = ["email", "is_staff", "date_joined"]
    search_fields = ["email"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Droits", {"fields": ("is_active", "is_staff", "is_superuser")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)


@admin.register(Organization)
class AdminOrganisation(admin.ModelAdmin):
    list_display = ["name", "sector", "created_at"]
    search_fields = ["name"]


admin.site.register(Membership)
