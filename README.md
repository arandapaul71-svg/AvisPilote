# AvisPilote

Application web (SaaS) pour les commerces locaux : réponses aux avis Google par IA, tableau de bord,
analyse des points forts et faibles, détection des problèmes avant qu'ils n'abîment la note,
rapports, QR code de collecte d'avis et abonnements Stripe.

## Où est quoi

| Dossier / fichier | Contenu |
|---|---|
| `v2/` | **Version actuelle** (Django + PostgreSQL/SQLite). Guide complet : [`v2/README.md`](v2/README.md) |
| `Lancer AvisPilote.bat` | Lancement en un double-clic sous Windows (installe puis ouvre le navigateur) |
| `docs/CONCEPTION.md` | Analyse, architecture, schéma de base, sécurité |
| `CLAUDE.md` | Contexte du projet et décisions prises |
| fichiers à la racine (`app.py`, `static/`…) | Ancienne version Flask, gardée pour mémoire ([`README-version-flask.md`](README-version-flask.md)) |

## Démarrage rapide

```powershell
cd v2
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Puis http://localhost:8000 → « Voir la démo ». Tests : `python manage.py test`.

Les secrets (clés Google, Stripe, Claude, SMTP) vont dans `v2/.env`, jamais dans Git : voir `v2/.env.example`.
