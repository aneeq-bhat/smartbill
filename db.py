"""
db.py - Python-MySQL connectivity for SmartBill.

Uses mysql-connector-python. Every query in the project is parameterised:
values are passed separately from the SQL text (%s placeholders), never
joined into the SQL string.
"""
import atexit
import os
import re
import tempfile

import mysql.connector
from mysql.connector import Error

from config import Config

_ssl_ca_path = None          # path of the CA file, if one is configured


def _find_ssl_ca():
    """Return the CA certificate path (from DB_SSL_CA or DB_SSL_CA_PEM)."""
    global _ssl_ca_path
    if _ssl_ca_path:
        return _ssl_ca_path
    if Config.DB_SSL_CA:
        _ssl_ca_path = Config.DB_SSL_CA
    elif Config.DB_SSL_CA_PEM.strip():
        pem_text = Config.DB_SSL_CA_PEM.replace("\\n", "\n")
        handle = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
        handle.write(pem_text)
        handle.close()
        _ssl_ca_path = handle.name
        atexit.register(lambda: os.path.exists(handle.name) and os.remove(handle.name))
    return _ssl_ca_path


def _connection_settings(with_database=True):
    """Build the argument dictionary for mysql.connector.connect()."""
    settings = {
        "host": Config.DB_HOST,
        "port": Config.DB_PORT,
        "user": Config.DB_USER,
        "password": Config.DB_PASSWORD,
        "charset": "utf8mb4",
        "connection_timeout": 10,
    }
    if with_database:
        settings["database"] = Config.DB_NAME
    ca_file = _find_ssl_ca()
    if ca_file:
        settings["ssl_ca"] = ca_file
    return settings


def get_connection():
    """Open and return a new connection to the smartbill database."""
    return mysql.connector.connect(**_connection_settings())


def fetch_all(sql, params=None):
    """Run a SELECT and return all rows as a list of dictionaries."""
    con = get_connection()
    try:
        cur = con.cursor(dictionary=True)
        cur.execute(sql, params or ())
        rows = cur.fetchall()
        cur.close()
        return rows
    finally:
        con.close()


def fetch_one(sql, params=None):
    """Run a SELECT and return the first row (a dictionary) or None."""
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def execute(sql, params=None):
    """
    Run one INSERT / UPDATE / DELETE and commit it.
    Returns (lastrowid, rowcount). Rolls back and re-raises on error.
    """
    con = get_connection()
    try:
        cur = con.cursor()
        cur.execute(sql, params or ())
        con.commit()
        result = (cur.lastrowid, cur.rowcount)
        cur.close()
        return result
    except Error:
        con.rollback()
        raise
    finally:
        con.close()


def _create_database_if_missing():
    """Create the database when it does not exist (needs CREATE privilege)."""
    if not re.fullmatch(r"[A-Za-z0-9_]+", Config.DB_NAME):
        raise ValueError("DB_NAME may contain only letters, digits and _")
    con = mysql.connector.connect(**_connection_settings(with_database=False))
    try:
        cur = con.cursor()
        cur.execute("CREATE DATABASE IF NOT EXISTS `%s`" % Config.DB_NAME)
        con.commit()
        cur.close()
    finally:
        con.close()


def _read_schema_statements():
    """Read schema.sql and return a list of single SQL statements."""
    with open(Config.SCHEMA_FILE, "r", encoding="utf-8") as schema_file:
        lines = [ln for ln in schema_file if not ln.strip().startswith("--")]
    statements = []
    for part in "".join(lines).split(";"):
        part = part.strip()
        if part:
            statements.append(part)
    return statements


def init_db():
    """Create the four tables (and the walk-in customer) if they are missing."""
    try:
        con = get_connection()
    except Error as err:
        if err.errno == 1049:                    # unknown database
            _create_database_if_missing()
            con = get_connection()
        else:
            raise
    try:
        cur = con.cursor()
        for statement in _read_schema_statements():
            cur.execute(statement)
        con.commit()
        cur.close()
    finally:
        con.close()
