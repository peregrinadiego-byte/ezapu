"""Configuración de EZAPU."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "ezapu-clave-de-desarrollo")
    DATABASE = os.environ.get("EZAPU_DB", str(BASE_DIR / "ezapu.db"))
    JSON_AS_ASCII = False
    TEMPLATES_AUTO_RELOAD = True


class TestConfig(Config):
    TESTING = True
    DATABASE = ":memory:"
