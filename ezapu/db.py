"""Acceso a datos: SQLite puro, sin ORM.

El proyecto completo vive en un solo archivo .db (por omisión ``ezapu.db`` en la
raíz del repositorio, o el que indique la variable de entorno ``EZAPU_DB``).
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA = Path(__file__).with_name("schema.sql")


# ----------------------------------------------------------------- conexión --
def _connect(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def get_db() -> sqlite3.Connection:
    """Conexión de la petición en curso."""
    if "db" not in g:
        g.db = _connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None) -> None:
    con = g.pop("db", None)
    if con is not None:
        con.close()


def connect(path: str | Path) -> sqlite3.Connection:
    """Conexión independiente (fuera de una petición: CLI, tests, seed)."""
    return _connect(path)


# ---------------------------------------------------------------- helpers ---
def query(sql: str, args=(), one: bool = False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql: str, args=()) -> int:
    con = get_db()
    cur = con.execute(sql, args)
    con.commit()
    last = cur.lastrowid
    cur.close()
    return last


def insert(table: str, data: dict) -> int:
    cols = list(data)
    sql = "INSERT INTO {} ({}) VALUES ({})".format(
        table, ", ".join(cols), ", ".join("?" * len(cols))
    )
    return execute(sql, [data[c] for c in cols])


def update(table: str, row_id: int, data: dict) -> None:
    if not data:
        return
    sql = "UPDATE {} SET {} WHERE id = ?".format(
        table, ", ".join(f"{c} = ?" for c in data)
    )
    execute(sql, [data[c] for c in data] + [row_id])


def delete(table: str, row_id: int) -> None:
    execute(f"DELETE FROM {table} WHERE id = ?", [row_id])


def scalar(sql: str, args=(), default=0):
    row = query(sql, args, one=True)
    if row is None:
        return default
    value = row[0]
    return default if value is None else value


def dicts(sql: str, args=()) -> list[dict]:
    return [dict(r) for r in query(sql, args)]


def one_dict(sql: str, args=()) -> dict | None:
    row = query(sql, args, one=True)
    return dict(row) if row else None


# ------------------------------------------------------------- inicializar --
def init_db(path: str | Path, seed: bool = True) -> None:
    """Crea el esquema (idempotente) y carga los datos de ejemplo."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = _connect(path)
    with SCHEMA.open(encoding="utf-8") as fh:
        con.executescript(fh.read())
    con.commit()

    if seed:
        from . import seed as seed_mod

        seed_mod.seed(con, reset=True)
    con.close()


def register(app) -> None:
    app.teardown_appcontext(close_db)


def default_path() -> str:
    return os.environ.get(
        "EZAPU_DB",
        str(Path(current_app.root_path).parent / "ezapu.db")
        if current_app
        else "ezapu.db",
    )
