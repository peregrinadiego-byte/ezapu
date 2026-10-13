#!/usr/bin/env python3
"""Punto de entrada de EZAPU.

Uso:
    python run.py                 # servidor de desarrollo en http://localhost:5000
    flask --app run init-db       # crea la base y carga los datos de ejemplo
    flask --app run reset-db      # borra y vuelve a crear la base
"""
from __future__ import annotations

import os
from pathlib import Path

from ezapu import create_app, db
from ezapu.config import Config

app = create_app()


@app.cli.command("init-db")
def init_db_command() -> None:
    """Crea el esquema y carga el juego de datos de ejemplo."""
    ruta = app.config["DATABASE"]
    if Path(ruta).exists():
        print(f"La base {ruta} ya existe: no se hace nada. Usa reset-db para recrearla.")
        return
    db.init_db(ruta, seed=True)
    print(f"Base creada en {ruta} con datos de ejemplo.")


@app.cli.command("reset-db")
def reset_db_command() -> None:
    """Recrea la base desde cero con los datos de ejemplo."""
    ruta = app.config["DATABASE"]
    db.init_db(ruta, seed=True)
    print(f"Base recreada en {ruta}.")


@app.cli.command("sembrar")
def sembrar_command() -> None:
    """Carga los datos de ejemplo si la base está vacía."""
    from ezapu.seed import seed

    con = db.connect(app.config["DATABASE"])
    creado = seed(con, reset=False)
    con.close()
    print("Datos de ejemplo cargados." if creado else "La base ya tenía datos.")


if __name__ == "__main__":
    ruta = app.config["DATABASE"]
    if not Path(ruta).exists():
        print(f"No existe {ruta}; se crea con datos de ejemplo…")
        db.init_db(ruta, seed=True)
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "1") == "1",
    )
