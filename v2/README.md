# AvisPilote

Application web pour les commerces locaux : elle répond aux avis Google, analyse ce que disent
les clients et alerte quand un problème revient, avant qu'il n'abîme la note.

## Lancer l'application (Windows)

1. Double-clique sur **`Lancer AvisPilote.bat`** (dans le dossier au-dessus de `v2`).
   La première fois, l'installation prend environ 2 minutes (Python 3.12 ou plus requis).
2. Le navigateur s'ouvre sur http://localhost:8000.
3. Clique sur **« Découvrir avec la démo »** : une boulangerie fictive avec 3 mois d'avis, sans rien créer.
   Ou crée ton propre compte avec « Essai gratuit 14 jours ».
4. Pour arrêter : ferme la fenêtre noire.

Sur téléphone (même réseau Wi-Fi) ou une fois en ligne, l'application peut s'installer sur l'écran
d'accueil (menu du navigateur → « Ajouter à l'écran d'accueil »).

## Ce que fait l'application

| Page | Contenu |
|---|---|
| Tableau de bord | note, avis reçus, taux et temps de réponse, graphiques (7 jours → 1 an), alertes |
| Avis | tous les avis, filtres, réponses proposées par l'assistant à valider, modifier ou publier |
| Analyses | points forts et points faibles, avec exemples d'avis et solutions |
| Alertes | anomalies détectées (hausse des avis négatifs, plainte qui revient, pics) et recommandations suivies |
| Rapports | rapport mensuel ou hebdomadaire, PDF, envoi par e-mail |
| Outils | QR code de collecte d'avis (affiche à imprimer) et simulateur de note |
| Assistant IA | ton, longueur, tutoiement, émojis, expressions, publication automatique ou validation selon la note |
| Abonnement | formules Starter / Pro / Business, paiement Stripe |

## Ce qui ne marche qu'une fois branché

L'application fonctionne entièrement en démo. Pour l'utiliser avec de vrais clients, il faut remplir
le fichier `.env` (modèle : `.env.example`) :

| Service | Pourquoi | Sans lui |
|---|---|---|
| Google Business Profile (accès à demander à Google, ~14 jours) | récupérer et répondre aux vrais avis | démo seulement |
| Clé Claude (Anthropic) | réponses plus naturelles | moteur de règles gratuit |
| Stripe (clés de test puis réelles) | encaisser les abonnements | pas de paiement |
| Service d'e-mails SMTP (ex. Brevo) | envoyer les rapports | e-mails affichés dans la console |

## Avant de vendre

- Mettre l'application en ligne (HTTPS, PostgreSQL, tâches planifiées `synchroniser_avis` toutes
  les 15 min et `envoyer_rapports` chaque jour).
- Compléter et faire relire les pages légales (CGU/CGV, confidentialité, mentions légales) :
  les éléments à remplir sont entre [crochets].
- Statut (micro-entreprise) et TVA.

## Pour les développeurs

- Tests : `.venv\Scripts\python manage.py test` (101 tests).
- Architecture, choix et sécurité : `../docs/CONCEPTION.md` et `../CLAUDE.md`.
