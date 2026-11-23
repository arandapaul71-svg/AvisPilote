# AvisPilote : contexte du projet

Ce fichier est lu automatiquement par Claude Code au début de chaque session.

## Le projet

Application web (SaaS) pour les commerces locaux (boulangerie, restaurant, fleuriste, coiffeur…) qui :
- répond automatiquement aux avis Google de l'entreprise ;
- affiche un tableau de bord : avis par jour colorés selon la note, détection des jours inhabituels
  (pic d'avis = événement qui a attiré du monde ou problème), répartition des notes, jours de la semaine ;
- fait un récapitulatif qualités / défauts relevés par les clients, avec des solutions pour chaque défaut ;
- fonctionne par abonnement mensuel avec un quota d'avis traités par mois.

## Nouvelle version en cours : `v2/` (Django) — décision du 23/11/2026

Paul veut « le plus simple, gratuit, pro et sécurisé » → réécriture en **Django + PostgreSQL**, appli web
installable (PWA), dans `v2/`. L'ancienne version Flask (ce dossier) reste lançable tant que la v2 n'a pas tout.
Cahier des charges complet et conception : `docs/CONCEPTION.md` (lots du MVP en section 3).
- Lot 1 fait : modèles complets, comptes e-mail + rôles (owner/manager/viewer), isolation par organisation,
  quotas par période d'abonnement (réserve 15 % négatifs, alerte 80 %), jetons Google chiffrés (Fernet),
  journal d'audit, suppression de compte RGPD, CSP stricte, limite de tentatives.
- Lot 2 fait : OAuth Google (state + PKCE), choix de la fiche parmi celles renvoyées par Google, synchro
  (`locations/sync.py`, commande `manage.py synchroniser_avis` à planifier toutes les 15 min), erreurs Google
  traduites, révocation à la déconnexion / suppression, page Avis (filtres, pagination), réponse manuelle
  publiée sur Google, mode démo signalé. 35 tests (Google simulé par mock dans les tests uniquement).
  Non testé avec le vrai Google : accès API pas encore accordé.
- Lot 3 fait : assistant IA (`reviews/traitement.py` + `reviews/ia/`). Quota consommé par avis traité
  (30 derniers jours seulement), modes auto / à valider / manuel par note, avis sensibles toujours validés,
  contrôle qualité (promesse, aveu, « réglé », expressions interdites, générique, répétition, ton), pas de
  publication auto sur l'historique, régénération ×3 sans quota, page « Assistant IA ». Claude via SDK
  `anthropic`, modèle `claude-haiku-5-5` (économique, demandé par le cahier des charges), sortie JSON
  imposée, avis traité comme donnée non fiable ; repli sur les règles en cas d'erreur. 54 tests.
  Appel Claude non testé avec une vraie clé (mock dans les tests).
- Lot 4 fait : tableau de bord (`insights/stats.py`, `insights/graphiques.py`) avec filtre 7 j / 30 j / 3 m /
  6 m / 1 an, 6 indicateurs (note Google, avis reçus et écart, note de la période, taux de réponse, réponses IA
  dont auto, temps de réponse moyen), graphiques SVG dessinés côté serveur (avis empilés par sentiment, note
  moyenne cumulée, répartition des notes), info-bulles au survol et au clavier (`static/js/graphiques.js`),
  tableau des données, page « Analyses » (points forts / faibles avec exemples, évolution, solutions).
  Couleurs validées avec le validateur dataviz (bleu / gris / rouge, clair et sombre). Attention : les
  coordonnées SVG doivent être écrites hors localisation (`{% localize off %}`), sinon « 194,0 » casse le SVG.
  62 tests.
- Lot 5 fait : détection d'anomalies (`insights/detection.py` : hausse des négatifs, plainte récurrente,
  baisse / remontée de note, pics d'avis), toujours avec un minimum d'avis ET un écart à l'habitude, sans
  doublon ; recommandations (`insights/recommandations.py`) avec importance, preuves, actions, statut
  « J'agis dessus / C'est réglé », suivi de l'effet et réouverture si le problème revient ; point fort à
  valoriser. Les avis de plus de 30 jours reçoivent une analyse de thèmes par règles (gratuite, sans quota,
  sans réponse) pour servir de référence. Pendant l'essai, fonctions Pro ; en Starter payant : alertes sans
  détail, pas de recommandations. Page « Alertes », alertes non lues sur le tableau de bord. 73 tests.
- Lot 6 fait : page « Outils » (`insights/outils.py`). QR code (bibliothèque `segno`) vers le lien d'avis
  Google de la fiche (fourni par l'API ou collé à la main, seuls les liens Google en https sont acceptés),
  téléchargement PNG / SVG, affiche imprimable A6 neutre (pas d'incitation aux avis positifs, règles Google).
  Simulateur : avis 5★ nécessaires pour une note visée (arrondi Google à 0,1), délai au rythme actuel,
  scénario « si je reçois X avis à Y★ », nombre d'avis 1★ qui feraient baisser la note. 80 tests.
- Lot 7 fait : paiement Stripe (`billing/paiement.py`, SDK `stripe` 17, API 2026-11-18) : Checkout hébergé
  (essai conservé via `trial_end`), portail client Stripe (changement de formule, carte, factures,
  résiliation), webhook `/stripe/webhook/` à signature vérifiée + événements dédoublonnés (`StripeEvent`),
  l'abonnement n'est modifié que par le webhook (jamais par le retour navigateur), période/quota pris sur
  l'élément d'abonnement (`current_period_*` est sur les items dans cette version de l'API), impayé/annulé
  = IA en pause, résiliation automatique à la suppression du compte, refus des clés `sk_live_` en DEBUG.
  Les objets du SDK ne sont pas des dict : utiliser `.to_dict()`. Non testé avec un vrai compte Stripe. 92 tests.
- Avant de vendre : compte Stripe + produits/prix, CGV, mentions légales, politique RGPD, statut (micro-entreprise,
  franchise de TVA ?).
- Lot 8 fait : rapports mensuels / hebdomadaires (`insights/rapports.py`) sur une période terminée, comparée
  à la précédente : bilan en une phrase, indicateurs, répartition, points forts / problèmes avec exemples,
  événements (alertes), recommandations et problèmes réglés. Page « Rapports » (choix de la période),
  PDF via reportlab (`insights/rapport_pdf.py`, textes d'avis échappés), e-mail texte + HTML + PDF
  (`insights/envoi.py`, console en dev, SMTP via .env), envoi manuel limité à 3/h, commande
  `manage.py envoyer_rapports` (à planifier chaque jour, un seul envoi par période), désabonnement.
  Réservé à Pro (et à l'essai). 101 tests.
- Version « prête à ouvrir » : `Lancer AvisPilote.bat` (racine) → `v2\lancer.bat` (installe, migre, ouvre le
  navigateur). Bouton « Découvrir avec la démo » sur la page de connexion (compte démo sans mot de passe
  utilisable, données régénérées chaque jour, désactivé si DEMO_AUTORISEE=0). Pages légales modèles à
  compléter (`templates/legal/`, éléments entre [crochets]), pied de page, manifeste PWA + icônes.
  Guide utilisateur : `v2/README.md`. 104 tests.
- Refonte du design (demande de Paul) : thème CLAIR uniquement (plus de mode sombre ni de style bleu
  marine), neutres chauds + ambre de l'étoile, beaucoup d'espace. Application avec barre latérale
  (`templates/base.html` : groupes « Au quotidien / Comprendre / Configurer », pastilles « à valider » et
  « alertes non lues » via `accounts/context_processors.py`) ; sur mobile la barre devient une rangée
  d'onglets défilante (attention : `minmax(0, 1fr)` + `min-width: 0`, sinon la page déborde). Chaque
  page a un en-tête `.entete-page` (titre + phrase d'explication). Page de présentation publique à `/`
  (`accounts/accueil.html`, `base_public.html`, en-tête avec « Se connecter » / « Essai gratuit ») ; aucun
  faux témoignage ni chiffre inventé. 108 tests.
- Prochains lots possibles : multi-établissements, déploiement en ligne (HTTPS, PostgreSQL, tâches planifiées).
- Nouvelle grille (v2, `v2/billing/plans.py`) : Starter 9,99 € / 50 avis, Pro 19,99 € / 200, Business 39,99 € / 600.
  Une alerte simple est incluse dès Starter (le différenciateur doit être visible).
- Mode démo : gardé, mais à signaler clairement et sans jamais rien publier ; désactivé en production.
- Lancer la v2 : `v2\lancer.bat` → http://localhost:8000 ; tests : `python manage.py test` dans `v2/`.

## Décisions déjà prises (version Flask)

- Formules (dans `config.py`) : Essentiel 19 € HT / 40 avis, Pro 39 € / 150 avis, Multi-sites 79 € / 500 avis.
  Essai gratuit 14 jours. Objectif : maximiser le nombre de ventes, d'où un prix d'entrée sous 20 €.
- Au-delà du quota, l'avis est affiché « Hors quota » : pas de réponse, pas d'analyse dans le récap.
  15 % du quota est réservé aux avis 1-2 étoiles.
- Réponses aux avis 4-5 étoiles publiées automatiquement ; avis 1 à 3 étoiles : validation obligatoire.
- Liaison Google via OAuth 2.0 + API Google Business Profile (accès à demander à Google, ~14 jours).
- IA : API Anthropic (Claude) si `ANTHROPIC_API_KEY` est défini, sinon moteur de règles dans `ai.py`.

## Stack et lancement

Python + Flask + SQLite, interface en HTML/CSS/JS sans framework (`static/`).
- Windows : double-clic sur `lancer.bat` (crée `.venv`, installe les dépendances, ouvre le navigateur).
- Manuel : `pip install -r requirements.txt` puis `python app.py` → http://localhost:5000
- Tests : `python -m unittest discover tests`
- Mode démo : créer un compte puis « Charger la démo » (faux avis générés par `demo_data.py`).

## Organisation du code

- `app.py` : routes Flask, comptes, sécurité (CSRF, en-têtes, limite de tentatives)
- `config.py` : formules, quotas, lecture du `.env`
- `database.py` : schéma SQLite
- `quotas.py` : calcul du quota et traitement des avis (analyse + réponse + publication)
- `ai.py` : analyse des thèmes (accueil, qualité, prix, attente, propreté, choix, cadre) et rédaction
- `analytics.py` : statistiques du dashboard, détection des pics, récap
- `google_api.py` : OAuth et API des avis Google
- `demo_data.py` : avis de démonstration

## Reste à faire

1. Paiement Stripe Checkout + webhook dans `changer_plan()` (aujourd'hui le changement de formule est gratuit).
2. Synchronisation automatique des avis (tâche planifiée toutes les 15-30 min).
3. Chiffrer les jetons Google en base.
4. Multi-sites : choix de la fiche après connexion Google (aujourd'hui la première est prise).
5. Déploiement HTTPS (gunicorn), CGV, politique RGPD.

## Comment travailler avec Paul

- Toujours répondre en français, tutoiement, aller droit au but.
- Paul est étudiant en 1re année de bachelor cybersécurité, niveau débutant (Python, C, HTML) :
  expliquer simplement les changements, signaler les bonnes pratiques de sécurité.
- Il est sous Windows 11.
- Être honnête et critique si une idée est mauvaise, et proposer mieux.
