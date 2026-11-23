# AvisPilote

Application web qui répond automatiquement aux avis Google d'un commerce (boulangerie, restaurant,
fleuriste…), affiche un tableau de bord des avis et fait un récap des qualités et défauts relevés
par les clients.

## Lancer l'appli en local (5 minutes)

Il faut Python 3.10 ou plus récent.

```bash
cd avispilote
python -m venv .venv
# Windows :
.venv\Scripts\activate
# macOS / Linux :
source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Ouvre ensuite http://localhost:5000, crée un compte entreprise et clique sur **Charger la démo**.
Tu obtiens trois mois de faux avis avec un événement, un jour difficile et un mois qui dépasse
le quota de la formule Essentiel. Tout fonctionne sans clé ni compte Google.

Lancer les tests :

```bash
python -m unittest discover tests
```

## Ce que fait l'appli

| Écran | Contenu |
|---|---|
| Inscription | Compte entreprise (nom, type de commerce, formule), essai de 14 jours |
| Démarrage | Connexion de la fiche Google (OAuth) ou mode démo |
| Tableau de bord | Note moyenne, avis par jour colorés selon la note, **détection des jours inhabituels** (événement qui a attiré du monde ou problème), répartition des notes, jours de la semaine, note par mois |
| Avis et réponses | Réponse proposée pour chaque avis, publication en un clic, autre formulation, solutions proposées pour les avis négatifs |
| Récapitulatif | Qualités et défauts classés, avec citations et actions concrètes pour chaque défaut |
| Abonnement | 3 formules, quota visible, avis hors quota traités dès qu'on monte en gamme |
| Paramètres | Ton des réponses, signature, contact pour les clients mécontents, publication automatique |

### Les formules (modifiables dans `config.py`)

| Formule | Prix HT/mois | Avis traités par mois |
|---|---|---|
| Essentiel | 19 € | 40 |
| Pro | 39 € | 150 |
| Multi-sites | 79 € | 500 |

« Traiter » un avis = l'analyser (récap) + rédiger sa réponse. Au-delà du quota, l'avis s'affiche
avec la mention « Hors quota » et il n'est ni répondu ni compté dans le récap.
15 % du quota est réservé aux avis de 1-2 étoiles pour qu'un client mécontent ne reste pas sans
réponse parce que les avis positifs ont tout consommé.

### Règles de publication

- Avis 4-5 étoiles : réponse publiée automatiquement (désactivable dans les paramètres).
- Avis 1 à 3 étoiles : la réponse attend **toujours** la validation du commerçant.
- À la première connexion Google, rien n'est publié automatiquement.

### Détection des jours inhabituels

Un jour est signalé s'il reçoit au moins 4 avis **et** au moins 2,5 fois la moyenne quotidienne des
30 jours précédents. Sa note moyenne indique si c'était un bon événement (≥ 4), un problème (≤ 2,5)
ou une affluence avec des avis partagés. Réglages dans `analytics.detecter_pics()`.

## Organisation du code

```
app.py          serveur Flask : routes, comptes, sécurité
config.py       formules, quotas, lecture du fichier .env
database.py     schéma SQLite
quotas.py       calcul du quota et traitement des avis
ai.py           analyse des avis et rédaction des réponses (Claude ou règles)
analytics.py    statistiques du tableau de bord et récap
google_api.py   connexion OAuth et API Google Business Profile
demo_data.py    génération des avis de démonstration
static/         interface (HTML, CSS, JavaScript sans framework)
tests/          tests automatiques
```

## Connecter de vraies fiches Google

Les API Google Business Profile **ne sont pas ouvertes au public** : Google doit valider ton projet.
C'est l'étape la plus longue, commence-la tôt.

1. Crée un projet sur https://console.cloud.google.com.
2. Demande l'accès via le formulaire de contact de l'API Business Profile, option
   « Application for Basic API Access » (réponse sous environ 14 jours). Il faut une vraie entreprise
   (une micro-entreprise suffit) et un site web.
3. Une fois l'accès accordé, active dans ton projet : *My Business Account Management API*,
   *My Business Business Information API* et *Google My Business API*.
4. Crée un identifiant **OAuth 2.0 (application Web)** avec comme URI de redirection
   `http://localhost:5000/auth/google/callback` (puis l'URL de production).
5. Copie `.env.example` en `.env` et remplis `GOOGLE_CLIENT_ID` et `GOOGLE_CLIENT_SECRET`.
6. Relance l'appli : le bouton **Connecter Google** fonctionne.

Google interdit les fausses fiches de test : teste avec la fiche d'un vrai commerçant qui t'y autorise.

## Réponses rédigées par l'IA

Sans clé, l'appli utilise un moteur de règles intégré (gratuit, hors ligne, correct mais un peu
répétitif). Pour des réponses vraiment personnalisées, ajoute une clé API Anthropic dans `.env` :
`ANTHROPIC_API_KEY=...`. En cas d'erreur de l'API, l'appli bascule automatiquement sur les règles.
Le coût par avis avec un petit modèle est de l'ordre d'une fraction de centime.

## Sécurité déjà en place

- Mots de passe hachés (`werkzeug.security`), jamais stockés en clair.
- Cookie de session `HttpOnly` + `SameSite=Lax` (+ `Secure` en production avec `SECURE_COOKIES=1`).
- Jeton CSRF obligatoire sur toutes les requêtes qui modifient des données.
- Paramètre `state` vérifié au retour OAuth Google.
- Requêtes SQL paramétrées (pas d'injection SQL).
- Chaque requête vérifie que l'avis appartient bien à l'entreprise connectée (test d'isolation inclus).
- Échappement de tout le texte affiché côté navigateur + Content-Security-Policy stricte (pas de script inline).
- Limitation des tentatives de connexion (10 par 10 minutes et par IP).
- Mode debug de Flask désactivé.

## Avant de mettre en production

- **Paiement** : brancher Stripe Checkout dans `changer_plan()` (le changement de formule est
  aujourd'hui immédiat et gratuit) et gérer la fin de l'essai.
- **Synchronisation automatique** : appeler `/api/sync` toutes les 15-30 min pour chaque entreprise
  (tâche planifiée), ou utiliser les notifications Pub/Sub de Google.
- **Chiffrer les jetons Google** stockés en base (par exemple avec `cryptography.fernet`).
- **Multi-sites** : laisser choisir la fiche après la connexion Google (aujourd'hui, la première est prise).
- Héberger derrière HTTPS avec un vrai serveur (`gunicorn`), passer à PostgreSQL si beaucoup de clients.
- Légal : statut (micro-entreprise), CGV, politique de confidentialité RGPD.
