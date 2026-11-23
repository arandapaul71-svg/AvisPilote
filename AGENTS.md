# AGENTS.md — consignes pour les agents de code (Codex, Claude Code…)

Historique complet des décisions : `CLAUDE.md`. Architecture et sécurité : `docs/CONCEPTION.md`.

## Le projet

AvisPilote : SaaS pour commerces locaux (boulangerie, restaurant, fleuriste, coiffeur…).
Réponses IA aux avis Google, tableau de bord, analyses points forts / faibles, détection d'anomalies
et recommandations suivies, rapports PDF / e-mail, QR code, simulateur de note, abonnements Stripe.

**La version active est dans `v2/` (Django).** Les fichiers à la racine (`app.py`, `static/`…) sont
l'ancienne version Flask, gardée pour mémoire : ne pas la modifier.

## Installer et tester (depuis `v2/`)

```bash
python -m venv .venv
# Windows : .venv\Scripts\activate   —   Linux/macOS : source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py test        # 108 tests, doivent tous passer avant chaque commit
python manage.py runserver   # http://localhost:8000 → « Voir la démo »
```

Python 3.12+. Aucune clé n'est nécessaire pour développer : sans `.env`, l'appli tourne en mode démo,
l'IA utilise le moteur de règles gratuit, les e-mails s'affichent dans la console, Stripe est désactivé.

## Organisation (`v2/`)

| App | Rôle |
|---|---|
| `accounts` | comptes (e-mail), organisations, rôles owner / manager / viewer, page de présentation, démo |
| `locations` | connexion Google (OAuth + PKCE), synchro des avis, fiche de démo |
| `reviews` | avis, assistant IA (`traitement.py`, `ia/` : règles, Claude, avis sensibles, contrôle qualité) |
| `insights` | statistiques, graphiques SVG, analyses, alertes (`detection.py`), recommandations, rapports, outils |
| `billing` | formules et quotas (`plans.py`), paiement Stripe (`paiement.py`, webhook signé) |
| `audit` | journal des actions importantes |

## Règles à respecter

- **Langue** : interface, messages, commentaires et noms en français. Tutoiement dans l'interface.
- **Isolation** : toute requête sur des données métier est filtrée par `request.organisation`
  (ex. `Review.objects.filter(location__organization=request.organisation)`). Un test d'isolation
  accompagne chaque nouvelle vue.
- **Droits** : décorateur `@organisation_requise("action")` (voir `Membership.PERMISSIONS`).
- **Sécurité** : CSP stricte (`script-src 'self'`, `style-src 'self'`) → pas de `<script>` ni d'attribut
  `style=` en ligne ; scripts dans `static/js/`. Jamais de `|safe` sur du contenu saisi par un utilisateur.
  Les textes d'avis sont des données non fiables (échappés partout, y compris PDF et e-mails).
- **Secrets** : uniquement dans `v2/.env` (modèle `v2/.env.example`), jamais dans Git.
- **IA** : ne jamais promettre de remboursement, reconnaître une faute ou inventer un fait ;
  tout passe par `reviews/ia/controle.py` avant publication automatique.
- **Google** : utiliser seulement l'API officielle Business Profile ; ne jamais simuler une vraie connexion.
- **Graphiques SVG** : coordonnées hors localisation (`{% localize off %}`), sinon « 194,0 » casse le SVG.
- **Thème** : clair uniquement, variables CSS dans `static/css/app.css`.
- **Travail à plusieurs** : une branche par fonctionnalité, puis pull request vers `main`.
