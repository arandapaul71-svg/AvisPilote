from django import forms
from django.contrib.auth import authenticate, password_validation
from django.utils.safestring import mark_safe

from .models import Secteur, User


class InscriptionForm(forms.Form):
    entreprise = forms.CharField(label="Nom de l'établissement", max_length=120)
    secteur = forms.ChoiceField(label="Secteur", choices=Secteur.choices)
    email = forms.EmailField(label="Adresse e-mail", max_length=254)
    mot_de_passe = forms.CharField(label="Mot de passe", widget=forms.PasswordInput,
                                   help_text="10 caractères minimum, pas un mot de passe courant.")
    cgu = forms.BooleanField(label=mark_safe(  # texte fixe écrit par nous : aucun contenu utilisateur
        "J'accepte les <a href=\"/cgu/\" target=\"_blank\">conditions d'utilisation</a> et la "
        "<a href=\"/confidentialite/\" target=\"_blank\">politique de confidentialité</a>"))

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Un compte existe déjà avec cette adresse.")
        return email

    def clean(self):
        donnees = super().clean()
        mdp = donnees.get("mot_de_passe")
        if mdp:
            # Vérifie longueur, mots de passe courants, ressemblance avec l'e-mail…
            password_validation.validate_password(mdp, User(email=donnees.get("email", "")))
        return donnees


class ConnexionForm(forms.Form):
    email = forms.EmailField(label="Adresse e-mail")
    mot_de_passe = forms.CharField(label="Mot de passe", widget=forms.PasswordInput)

    def __init__(self, request, *args, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        donnees = super().clean()
        if self.errors:
            return donnees
        self.user = authenticate(self.request, email=donnees["email"].lower(), password=donnees["mot_de_passe"])
        if self.user is None:
            # Message volontairement vague : on ne dit pas si l'e-mail existe.
            raise forms.ValidationError("E-mail ou mot de passe incorrect.")
        return donnees


class SuppressionCompteForm(forms.Form):
    mot_de_passe = forms.CharField(label="Confirme avec ton mot de passe", widget=forms.PasswordInput)
    confirmation = forms.CharField(label='Tape SUPPRIMER pour confirmer')

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_mot_de_passe(self):
        mdp = self.cleaned_data["mot_de_passe"]
        if not self.user.check_password(mdp):
            raise forms.ValidationError("Mot de passe incorrect.")
        return mdp

    def clean_confirmation(self):
        if self.cleaned_data["confirmation"].strip() != "SUPPRIMER":
            raise forms.ValidationError("Tape exactement SUPPRIMER.")
        return "SUPPRIMER"
