"""
config.py - SmartBill configuration.

Every secret (database password, secret key, admin password) is read from
environment variables. Nothing sensitive is written in the source code.
For local work, copy .env.example to .env and fill in the values.
"""
import os
import secrets

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _to_int(name, default):
    """Read an integer environment variable; use the default if invalid."""
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _to_bool(name, default=False):
    """Read a True/False environment variable (1, true, yes, on)."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class Config:
    # ---- Flask -----------------------------------------------------------
    # Set SECRET_KEY in production. If it is missing a random key is used,
    # which logs everybody out every time the server restarts.
    SECRET_KEY_FROM_ENV = bool(os.environ.get("SECRET_KEY"))
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _to_bool("SESSION_COOKIE_SECURE", False)
    MAX_CONTENT_LENGTH = 1024 * 1024          # reject requests above 1 MB

    # ---- MySQL -----------------------------------------------------------
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = _to_int("DB_PORT", 3306)
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "smartbill")
    # Optional TLS settings for cloud databases:
    DB_SSL_CA = os.environ.get("DB_SSL_CA", "")          # path to a CA file
    DB_SSL_CA_PEM = os.environ.get("DB_SSL_CA_PEM", "")  # CA text (for Render)

    # ---- Login (single shop owner account) --------------------------------
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

    # ---- Shop details printed on invoices ---------------------------------
    SHOP_NAME = os.environ.get("SHOP_NAME", "Kashmir General Store")
    SHOP_ADDRESS = os.environ.get("SHOP_ADDRESS", "Jammu")
    SHOP_GSTIN = os.environ.get("SHOP_GSTIN", "")
    SHOP_PHONE = os.environ.get("SHOP_PHONE", "")

    # ---- Business rules ---------------------------------------------------
    LOW_STOCK_LIMIT = _to_int("LOW_STOCK_LIMIT", 10)   # stock below this = low
    GST_SLABS = (0, 5, 12, 18, 28)

    # ---- Folders ----------------------------------------------------------
    EXPORT_DIR = os.path.join(BASE_DIR, "exports")
    SCHEMA_FILE = os.path.join(BASE_DIR, "schema.sql")
