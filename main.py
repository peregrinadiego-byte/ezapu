"""Panel de inicio: tablero con el estado de los proyectos."""
from __future__ import annotations

from flask import Blueprint, render_template

from .. import db
from ..domain import existencias, totales, valor_ganado
from ..domain.avance import estado_de_cuenta
from ..domain.planeacion import avance_ponderado

bp = Blueprint("main", __name__)


@bp.route("/")
def inicio():
    con = db.get_db()
    proyectos = [dict(p) for p in con.execute("SELECT * FROM proyecto ORDER BY clave").fetchall()]

    for p in proyectos:
        resumen = totales(con, p["id"])
        p["presupuesto"] = resumen.get("subtotal", 0.0)
        p["importe_total"] = resumen.get("total", 0.0)
        p["avance"] = avance_ponderado(con, p["id"])
        cuenta = estado_de_cuenta(con, p["id"])
        p["estimado"] = cuenta["total_estimado"]
        p["cobrado"] = cuenta["total_pagado"]
        indicadores = valor_ganado(con, p["id"])
        p["spi"] = indicadores.get("spi", 0)
        p["cpi"] = indicadores.get("cpi", 0)
        p["ev"] = indicadores.get("ev", 0)
        p["ac"] = indicadores.get("ac", 0)

    conteos = {
        "insumos": con.execute("SELECT COUNT(*) FROM recurso").fetchone()[0],
        "matrices": con.execute("SELECT COUNT(*) FROM matriz").fetchone()[0],
        "conceptos": con.execute("SELECT COUNT(*) FROM concepto").fetchone()[0],
        "estimaciones": con.execute("SELECT COUNT(*) FROM estimacion").fetchone()[0],
        "tareas": con.execute("SELECT COUNT(*) FROM tarea").fetchone()[0],
        "movimientos": con.execute("SELECT COUNT(*) FROM movimiento_bodega").fetchone()[0],
    }

    inventario = existencias(con)

    return render_template(
        "inicio.html",
        proyectos=proyectos,
        conteos=conteos,
        valor_bodega=sum(e["importe"] for e in inventario),
        top_bodega=sorted(inventario, key=lambda e: -e["importe"])[:6],
        empresa=con.execute("SELECT * FROM empresa LIMIT 1").fetchone(),
    )


@bp.route("/acerca")
def acerca():
    con = db.get_db()
    versiones = {
        "sqlite": con.execute("SELECT sqlite_version()").fetchone()[0],
        "tablas": [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
        ],
    }
    return render_template("acerca.html", versiones=versiones)
