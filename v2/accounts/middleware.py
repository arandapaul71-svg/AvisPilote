"""Middlewares : organisation de l'utilisateur connecté + en-têtes de sécurité."""


class OrganisationMiddleware:
    """Ajoute request.organisation et request.membership pour l'utilisateur connecté.
    Les vues filtrent TOUJOURS les données avec request.organisation : c'est ce qui
    empêche une entreprise de voir les données d'une autre."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.membership = None
        request.organisation = None
        if request.user.is_authenticated:
            membership = getattr(request.user, "membership", None)
            if membership is not None:
                request.membership = membership
                request.organisation = membership.organization
        return self.get_response(request)


class EntetesSecuriteMiddleware:
    """Content-Security-Policy stricte : le navigateur refuse tout script ou style
    qui ne vient pas de notre propre serveur (bloque la plupart des attaques XSS)."""

    CSP = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://accounts.google.com"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/admin/"):
            response.setdefault("Content-Security-Policy", self.CSP)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response
