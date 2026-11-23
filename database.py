"""Accès à la base SQLite.

Toutes les requêtes utilisent des paramètres (?) : jamais de concaténation
de chaînes avec des données utilisateur, pour éviter les injections SQL.
"""
import sqlite3

from flask import g

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS businesses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'autre',
    plan TEXT NOT NULL DEFAULT 'essentiel',
    trial_ends TEXT,
    ton TEXT NOT NULL DEFAULT 'chaleureux',
    signature TEXT NOT NULL DEFAULT '',
    contact TEXT NOT NULL DEFAULT '',
    auto_publish INTEGER NOT NULL DEFAULT 1,
    mode TEXT NOT NULL DEFAULT 'aucun',          -- aucun | demo | google
    google_refresh_token TEXT,
    google_access_token TEXT,
    google_token_expiry REAL,
    google_account TEXT,
    google_location TEXT,
    google_location_title TEXT,
    last_sync TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    external_id TEXT NOT NULL,
    author TEXT NOT NULL,
    stars INTEGER NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,                    -- ISO 8601
    month TEXT NOT NULL,                         -- AAAA-MM, sert au quota
    status TEXT NOT NULL DEFAULT 'hors_quota',   -- hors_quota | a_valider | publiee
    processed INTEGER NOT NULL DEFAULT 0,
    reply TEXT,
    reply_published_at TEXT,
    qualites TEXT NOT NULL DEFAULT '[]',         -- liste JSON de thèmes
    defauts TEXT NOT NULL DEFAULT '[]',
    solution TEXT,
    ai_source TEXT,
    UNIQUE (business_id, external_id)
);

CREATE INDEX IF NOT EXISTS idx_reviews_business_month ON reviews (business_id, month);
CREATE INDEX IF NOT EXISTS idx_reviews_business_date ON reviews (business_id, created_at);
"""


def connect(path=None):
    conn = sqlite3.connect(path or config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """Une connexion par requête HTTP, fermée automatiquement à la fin."""
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(path=None):
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
