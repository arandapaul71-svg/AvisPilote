# AvisPilote : analyse et conception (étapes 1 et 2)

Document de référence avant le développement du MVP complet.
Date : 23/11/2026. Point de départ : le code actuel (Flask + SQLite, voir `CLAUDE.md`).

---

## 1. Analyse

### 1.1 Objectif commercial

Vendre un abonnement mensuel à des commerces locaux qui n'ont ni le temps ni l'envie de gérer
leurs avis Google. Le marché est déjà occupé (IgorIA, ReplyTop, MARA, Partoo, Respondyr…) et
**la réponse automatique n'est plus un argument de vente** : tout le monde la fait.
Le différenciateur retenu est **la détection des problèmes avant la crise** (section 6 du cahier
des charges) : tendances, alertes, recommandations et suivi après action.

Conséquence directe : ce différenciateur doit être **visible dès la formule la moins chère**,
sinon la majorité des clients (qui prendront Starter) ne le verront jamais. Voir 2.6.

### 1.2 Ce que l'API Google permet vraiment

| Besoin | Possible ? | Détail |
|---|---|---|
| Lire tous les avis de **sa propre** fiche | Oui | API Business Profile v4 `accounts.locations.reviews.list`, paginée, historique complet. Renvoie aussi `averageRating` et `totalReviewCount`. |
| Répondre / modifier / supprimer une réponse | Oui | `reviews.updateReply` (PUT) et `deleteReply`. Uniquement sur une fiche **validée**. |
| Savoir si Google a rejeté une réponse | Oui (2026) | Les violations de règles (`PolicyViolation`) sont renvoyées avec les avis. À afficher au commerçant. |
| Lister les fiches d'un compte (multi-sites) | Oui | Account Management API + Business Information API. |
| Lien « laisser un avis » pour le QR code | Oui | Champ `metadata.newReviewUri` de la fiche (Business Information API). |
| Temps de réponse moyen | Oui | Écart entre `createTime` de l'avis et `updateTime` de la réponse. |
| Notifications en temps réel | Partiel | Notifications Pub/Sub possibles, mais plus complexe ; une synchro toutes les 15-30 min suffit au départ. |
| Lire les avis des **concurrents** | **Très limité** | Seulement via l'API Places : 5 avis maximum par lieu, et interdiction de stocker le contenu (sauf `place_id`). Donc pas d'historique, pas d'« évolution de la réputation » d'un concurrent. |

**Accès à l'API** : non public. Demande à faire à Google avec un projet Google Cloud, une
entreprise et un site web en ligne, réponse sous ~14 jours, pas de bac à sable. Tant que l'accès
n'est pas accordé, **aucune donnée Google réelle ne peut être testée**. C'est le risque n°1 du projet.

### 1.3 Risques et fonctionnalités difficiles

1. **Accès API Google refusé ou retardé** → bloque tout le produit. À demander maintenant.
2. **Analyse concurrentielle** : juridiquement fragile (conditions Google Maps Platform, section
   3.2.3 sur le stockage). Seule version sûre : afficher en direct note + nombre d'avis des
   concurrents, sans rien stocker. Je recommande de la repousser après le lancement.
3. **IA qui dit une bêtise publiquement** (promesse de remboursement, aveu de faute). Mitigation :
   consignes strictes, contrôle automatique de la réponse avant publication, validation humaine
   obligatoire pour les avis ≤ 3★ et les avis sensibles.
4. **Fausses alertes** : sur un petit commerce (10-30 avis/mois), quelques avis suffisent à créer
   un faux « pic ». Il faut des seuils minimums (ex. au moins 4 avis concernés) en plus du ratio.
5. **RGPD** : les avis contiennent des noms de clients. Il faut une durée de conservation, la
   suppression du compte et de ses données, et un contrat de sous-traitance avec le fournisseur IA.
6. **Coût IA** : faible avec un petit modèle (Claude Haiku), mais à surveiller : une analyse +
   une réponse par avis, et des analyses globales mises en cache plutôt que recalculées.

### 1.4 Écart entre le code actuel et le MVP demandé

| MVP demandé | État actuel |
|---|---|
| Inscription / connexion | ✅ fait (mots de passe hachés, CSRF, limite de tentatives) |
| Connexion Google Business Profile | 🟡 codée, non testée ; prend la 1re fiche, pas de choix |
| Récupération des avis | 🟡 synchro manuelle seulement |
| Réponses IA | 🟡 règles + Claude ; peu de personnalisation |
| 3 modes (auto / validation / manuel) | 🟡 seulement « auto pour 4-5★ » ou validation |
| Modifier une réponse avant publication | ✅ fait |
| Paramètres de l'assistant IA | 🔴 seulement ton + signature |
| Dashboard + filtres 7j / 30j / 3m / 6m / 1an | 🟡 dashboard 90 jours fixe, indicateurs incomplets |
| Points forts / faibles | ✅ fait (7 thèmes, à adapter par secteur) |
| Quotas | 🟡 par mois civil, pas d'alerte « bientôt atteint » |
| Avis sensibles | 🔴 absent |
| Contrôle qualité des réponses | 🔴 absent |
| Tokens chiffrés, journal d'actions, suppression de compte | 🔴 absent |

**Conclusion : on ne repart pas de zéro.** Environ la moitié du MVP existe. Le plus gros manque
concerne la personnalisation IA, les avis sensibles et la sécurité des données.

---

## 2. Conception

### 2.1 Choix de la stack (décision importante)

Le cahier des charges suggère React Native + Node.js/TypeScript + PostgreSQL.

| Option | Pour | Contre |
|---|---|---|
| **A. Garder Python (Flask) + PostgreSQL + appli web responsive installable (PWA)** — *recommandé* | Tu connais Python ; le code existant est conservé ; un seul code pour mobile et PC ; pas de frais App Store (99 $/an chez Apple) ni de validation des stores | Pas dans les stores au lancement (mais installable sur l'écran d'accueil) |
| B. Tout réécrire en Node/TS + React Native (Expo) | Vraie appli mobile, écosystème JS unifié | Deux langages à apprendre, réécriture complète (plusieurs semaines), deux interfaces à maintenir (web + mobile) |

**Décision (23/11/2026) : Django + PostgreSQL + appli web installable (PWA).**
Critères de Paul : gratuit, simple, pro, sécurisé. Django est gratuit et open source, très utilisé
pour les SaaS, et c'est le framework Python le plus sécurisé par défaut (CSRF, échappement XSS,
ORM anti-injection SQL, hachage des mots de passe, anti-clickjacking, sessions sécurisées).
Flask obligeait à coder ces protections à la main. Une appli web installable évite les frais et
la validation des stores ; une appli React Native pourra être ajoutée plus tard par-dessus l'API.

La nouvelle version est développée dans `v2/`. L'ancienne version Flask reste lançable tant que
la v2 n'a pas toutes ses fonctions. La logique métier (`ai.py`, `analytics.py`, quotas) est reprise.

Détails :
- Backend : Django, une « app » par module ; SQLite en développement, PostgreSQL en production
  (même code, seul le réglage `DATABASE_URL` change).
- Interface : gabarits Django (échappement automatique, CSRF dans chaque formulaire) + un peu de JS.
- Tâches de fond : synchro des avis, rapports, alertes → commande Django lancée par un planificateur.
- IA : API Anthropic, Claude Haiku pour les réponses et l'analyse (économique), clé côté serveur uniquement.
- Paiement : Stripe Checkout + webhooks (prévu dès maintenant dans le modèle de données).
- Graphiques : Chart.js (léger, interactif, sans framework).
- Hébergement de départ : un petit serveur (Render, Railway ou un VPS) + PostgreSQL managé.
- Chiffrement des jetons Google : bibliothèque `cryptography` (Fernet), clé dans les variables d'environnement.

### 2.2 Structure du projet

```
avispilote/
  app/
    __init__.py          création de l'appli, sécurité (CSRF, en-têtes)
    auth/                inscription, connexion, rôles, suppression de compte
    google/              OAuth, choix de la fiche, synchro, publication
    reviews/             liste, filtres, validation, modification
    ai/                  rédaction, analyse, détection des avis sensibles, contrôle qualité
    analytics/           indicateurs, tendances, alertes, recommandations
    billing/             formules, quotas, Stripe (plus tard)
    reports/             rapports périodiques, PDF, e-mail (étape 5)
    audit.py             journal des actions importantes
  worker.py              tâches planifiées (synchro, alertes, rapports)
  static/                interface web (HTML/CSS/JS + Chart.js)
  migrations/            évolutions du schéma de base
  tests/
```

### 2.3 Schéma de la base de données

```
organizations      id, name, sector, created_at
users              id, email, password_hash, created_at, deleted_at
memberships        user_id, organization_id, role (owner | manager | viewer)
locations          id, organization_id, google_location_name, title, sector,
                   new_review_uri, average_rating, total_review_count, last_sync_at
google_connections id, organization_id, google_account, refresh_token_enc, access_token_enc,
                   token_expiry, status (ok | expirée | révoquée)
ai_settings        location_id, tone, length, emojis, tutoiement, preferred_phrases,
                   forbidden_phrases, business_info, negative_instructions,
                   mode_by_stars (ex. {"5":"auto","4":"auto","3":"validation",...}),
                   sensitive_requires_validation
reviews            id, location_id, google_review_id, author, stars, comment, created_at,
                   google_reply, google_reply_at, policy_violation,
                   ai_status (non_traite | traite | hors_quota), UNIQUE(location_id, google_review_id)
review_analyses    review_id, sentiment, themes_positifs, themes_negatifs, sensitive_flags,
                   model, created_at
reply_drafts       id, review_id, text, source (ia | humain), status
                   (brouillon | a_valider | publiee | rejetee_google), quality_checks,
                   created_by, published_at
subscriptions      organization_id, plan, status (essai | actif | impayé | annulé),
                   period_start, period_end, stripe_customer_id, stripe_subscription_id
usage_counters     organization_id, period_start, reviews_processed
alerts             id, location_id, kind, message, evidence_review_ids, created_at, read_at
recommendations    id, location_id, theme, problem, evidence_review_ids, importance,
                   actions, status (ouverte | en_cours | résolue), created_at
audit_log          id, organization_id, user_id, action, details, ip, created_at
```

Points clés :
- **Toutes** les requêtes filtrent par `organization_id` de l'utilisateur connecté (isolation stricte).
- Récupération (`reviews`), analyse (`review_analyses`) et réponse (`reply_drafts`) sont séparées,
  comme le demande le cahier des charges : un avis hors quota est stocké et consultable, mais n'a ni analyse ni brouillon.

### 2.4 API (JSON, toutes protégées sauf auth)

```
POST   /api/auth/signup | /login | /logout        DELETE /api/account   (suppression RGPD)
GET    /api/me
GET    /api/google/connect     → redirection OAuth   GET /api/google/callback
GET    /api/google/locations   POST /api/google/locations/select
POST   /api/sync               (synchro manuelle, limitée en fréquence)
GET    /api/reviews?periode=&etoiles=&statut=&sensible=
PATCH  /api/reviews/{id}/draft        POST /api/reviews/{id}/publish
POST   /api/reviews/{id}/regenerate   DELETE /api/reviews/{id}/reply
GET    /api/ai-settings       PUT /api/ai-settings
GET    /api/dashboard?periode=7j|30j|3m|6m|1an
GET    /api/insights?periode=   (points forts / faibles)
GET    /api/alerts            POST /api/alerts/{id}/read
GET    /api/recommendations   PATCH /api/recommendations/{id}
GET    /api/subscription      POST /api/subscription/checkout   POST /api/stripe/webhook
GET    /api/audit-log         (owner uniquement)
```

### 2.5 Rôles

| Rôle | Peut |
|---|---|
| **owner** (gérant) | tout, y compris abonnement, connexion Google, suppression du compte, journal |
| **manager** (employé de confiance) | valider / modifier / publier des réponses, régler l'assistant IA |
| **viewer** | consulter dashboard, avis et analyses |
| admin plateforme | toi : support, pas d'accès au contenu sans raison (à journaliser) |

Au MVP, un seul utilisateur owner par organisation ; les invitations viendront ensuite.

### 2.6 Quotas et formules

Fonctionnement :
- Le quota compte les **avis traités par l'IA** (analyse + brouillon de réponse), pas les avis récupérés.
- Il se remet à zéro à chaque **renouvellement de l'abonnement** (`period_start`), pas au 1er du mois.
- Alerte à 80 % et à 100 % dans le dashboard (et par e-mail plus tard).
- Au-delà : avis stockés et visibles, marqués « Hors quota », bouton « Passer à la formule supérieure ».
- 15 % du quota reste réservé aux avis 1-2★ (déjà en place).
- Régénérer une réponse ne consomme pas de quota (mais limité à 3 par avis pour maîtriser le coût).

**Formules : il y a un conflit** entre l'ancienne grille (19 / 39 / 79 €) et celle du cahier des
charges (9,99 / 19,99 / 39,99 €). Mon avis :
- 9,99 € avec 50 avis est très attractif, mais il faut presque **2 fois plus de clients** pour le même
  chiffre d'affaires, et le coût du support par client reste le même.
- Réserver la détection d'anomalies et les alertes à Pro est une erreur : c'est ton différenciateur.
  Je propose de mettre en Starter **une alerte simple par mois** (« 3 clients parlent d'attente cette
  semaine ») et en Pro le détail, les recommandations complètes et le suivi après action.

Dans tous les cas, prix et quotas restent dans `config.py`, donc faciles à tester puis à changer.

### 2.7 Parcours utilisateur

1. Page d'accueil → « Essai gratuit 14 jours » → e-mail, mot de passe, nom et secteur de l'établissement.
2. « Connecter ma fiche Google » → écran officiel Google (OAuth) → retour dans l'appli.
3. Si plusieurs fiches : choix de la fiche à gérer.
4. Réglage de l'assistant en 3 questions (ton, tutoiement, émojis) + aperçu d'une réponse type.
5. Première synchro : les avis s'affichent ; ceux du mois en cours sont analysés dans la limite du quota.
6. Dashboard : note, alertes, avis à valider en premier.
7. Avis à valider : lire, modifier, publier en un clic.
8. Fin de l'essai → choix de la formule (Stripe).

### 2.8 Sécurité (ce qui sera ajouté)

- Chiffrement des jetons Google en base (Fernet) ; clé hors du code.
- Journal des actions importantes (connexion, publication, changement de formule, suppression).
- Suppression du compte : efface les données et révoque l'accès Google.
- Validation de toutes les entrées côté serveur (longueur, valeurs autorisées).
- Limitation des requêtes sur la synchro, la régénération IA et la connexion.
- Déjà en place : hachage des mots de passe, CSRF, cookies HttpOnly, requêtes SQL paramétrées, CSP.

### 2.9 Contrôle des réponses IA (avant toute publication automatique)

Vérifications automatiques, une réponse qui échoue passe en « à valider » :
- trop proche d'une réponse déjà publiée (similarité de texte > seuil) ;
- contient une expression interdite par le commerçant ;
- promet un remboursement, un geste commercial ou reconnaît une faute ;
- ne mentionne aucun élément de l'avis (réponse générique) ;
- ton incohérent avec la note (remercier chaleureusement un avis 1★).

Avis sensibles détectés (règles + IA) : accusation grave, hygiène / sécurité, menace juridique,
demande de remboursement, agressivité, mention nominative d'un employé → **toujours** en validation.

---

## 3. Plan du MVP (étape 3), par lots testables

1. **Socle** : découpage en modules, SQLAlchemy, nouveau schéma + migration des données existantes.
2. **Sécurité** : chiffrement des jetons, journal, suppression de compte, validation des entrées.
3. **Google** : choix de la fiche, synchro planifiée, gestion des erreurs et limites d'API.
4. **Assistant IA** : réglages complets, 3 modes par note, avis sensibles, contrôle qualité.
5. **Quotas** : période d'abonnement, alertes 80 / 100 %, structure prête pour Stripe.
6. **Dashboard** : filtres de période, tous les indicateurs demandés, graphiques Chart.js.
7. **Tests** : isolation entre entreprises, quotas, avis sensibles, contrôle qualité.

Étape 5 ensuite, dans cet ordre conseillé : alertes et tendances → recommandations avec suivi →
QR code → simulateur de note → rapports PDF / e-mail → multi-établissements → concurrence (si juridiquement validée).

## 4. Le mode démo

Le cahier des charges interdit de « simuler une connexion Google ou inventer des avis pour faire
croire que l'intégration fonctionne ». Le mode démo actuel génère de faux avis. Il reste utile pour
développer et pour montrer le produit à un prospect, **à condition** d'être clairement signalé
(bandeau « Données de démonstration, aucune connexion Google ») et de ne jamais rien publier.
À trancher : le garder ainsi, ou le supprimer.
