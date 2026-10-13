"""Punto de entrada para servidores WSGI (gunicorn, uWSGI, Waitress…).

Uso local:
    gunicorn wsgi:app --bind 127.0.0.1:8000

En un PaaS (Render, Railway, Fly.io, PythonAnywhere) el comando de arranque es
    gunicorn wsgi:app --bind 0.0.0.0:$PORT

Si la base de datos no existe (primer arranque en un servidor nuevo), se crea y
se carga con los datos de ejemplo.
"""
from __future__ import annotations

from pathlib import Path

from ezapu import create_app, db

app = create_app()

_ruta = Path(app.config["DATABASE"])
if not _ruta.exists():
    db.init_db(_ruta, seed=True)
