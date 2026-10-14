"""Configuración de EZAPU."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "ezapu-clave-de-desarrollo")
    DATABASE = os.environ.get("EZAPU_DB", str(BASE_DIR / "ezapu.db"))
    AUTH_DATABASE = os.environ.get("EZAPU_AUTH_DB", str(INSTANCE_DIR / "auth.db"))
    USER_DATA_DIR = os.environ.get("EZAPU_USER_DATA", str(INSTANCE_DIR / "usuarios"))
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    JSON_AS_ASCII = False
    TEMPLATES_AUTO_RELOAD = True


class TestConfig(Config):
    TESTING = True
    DATABASE = ":memory:"
