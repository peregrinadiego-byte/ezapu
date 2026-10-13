"""Utilidades compartidas por el dominio de cálculo.

Todo el dominio trabaja sobre una conexión ``sqlite3`` explícita, de modo que
las mismas funciones se usan desde la web, la CLI y los tests.
"""
from __future__ import annotations

import datetime as _dt

# Tipos de insumo que participan en una explosión (hojas del árbol de matrices)
TIPOS_BASICOS = ("material", "mano_obra", "equipo", "herramienta", "subcontrato", "flete")

TIPOS_RECURSO = {
    "material": "Material",
    "mano_obra": "Mano de obra",
    "equipo": "Equipo",
    "herramienta": "Herramienta",
    "subcontrato": "Subcontrato",
    "flete": "Flete",
    "auxiliar": "Auxiliar (matriz)",
}

UNIDADES_BASE = [
    ("pza", "Pieza", "pieza"),
    ("m", "Metro", "longitud"),
    ("m2", "Metro cuadrado", "area"),
    ("m3", "Metro cúbico", "volumen"),
    ("kg", "Kilogramo", "peso"),
    ("ton", "Tonelada", "peso"),
    ("l", "Litro", "volumen"),
    ("jorn", "Jornada", "tiempo"),
    ("hr", "Hora", "tiempo"),
    ("dia", "Día", "tiempo"),
    ("mes", "Mes", "tiempo"),
    ("sal", "Salario", "tiempo"),
    ("lote", "Lote", "global"),
    ("glob", "Global", "global"),
    ("serv", "Servicio", "servicio"),
    ("%", "Porcentaje", "global"),
]


def get(row, key, default=0.0):
    """Lectura tolerante de un ``sqlite3.Row`` / dict."""
    if row is None:
        return default
    if isinstance(row, dict):
        value = row.get(key, default)
    else:
        keys = row.keys()
        if key not in keys:
            return default
        value = row[key]
    return default if value is None else value


def num(row, key, default=0.0) -> float:
    try:
        return float(get(row, key, default))
    except (TypeError, ValueError):
        return default


def today() -> str:
    return _dt.date.today().isoformat()


def parse_date(value):
    if not value:
        return None
    if isinstance(value, _dt.date):
        return value
    text = str(value)[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return _dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def money(value) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def qty(value) -> float:
    try:
        return round(float(value or 0), 6)
    except (TypeError, ValueError):
        return 0.0
