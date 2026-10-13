"""M2 · Administración de proyectos: valor ganado y curva S."""
from __future__ import annotations

from flask import Blueprint, abort, render_template

from .. import db
from ..domain import estructura_costos, estructura_organizacion, valor_ganado

bp = Blueprint("administracion", __name__, url_prefix="/m2")


@bp.route("/valor-ganado/")
def valor_ganado_indice():
    con = db.get_db()
    proyectos = [dict(p) for p in con.execute("SELECT * FROM proyecto ORDER BY clave").fetchall()]
    for p in proyectos:
        indicadores = valor_ganado(con, p["id"])
        p.update({
            "bac": indicadores.get("bac", 0),
            "ev": indicadores.get("ev", 0),
            "ac": indicadores.get("ac", 0),
            "spi": indicadores.get("spi", 0),
            "cpi": indicadores.get("cpi", 0),
        })
    return render_template("administracion/seleccion.html", proyectos=proyectos)


@bp.route("/proyectos/<int:proyecto_id>/valor-ganado/")
def proyecto_valor_ganado(proyecto_id):
    con = db.get_db()
    proyecto = con.execute("SELECT * FROM proyecto WHERE id = ?", (proyecto_id,)).fetchone()
    if proyecto is None:
        abort(404)

    indicadores = valor_ganado(con, proyecto_id)
    serie = indicadores.get("serie", [])
    maximo = max([max(p["pv"], p["ev"], p["ac"]) for p in serie], default=0) or 1

    puntos_pv = _polilinea(serie, "pv", maximo)
    puntos_ev = _polilinea(serie, "ev", maximo)
    puntos_ac = _polilinea(serie, "ac", maximo)

    return render_template(
        "administracion/valor_ganado.html",
        proyecto=proyecto,
        kpi=indicadores,
        serie=serie,
        maximo=maximo,
        puntos={"pv": puntos_pv, "ev": puntos_ev, "ac": puntos_ac},
        centros=estructura_costos(con, proyecto_id),
        organizacion=estructura_organizacion(con, proyecto_id),
    )


def _polilinea(serie, clave, maximo):
    """Convierte una serie de valores en la polilínea de la curva S (SVG)."""
    if len(serie) < 2:
        return ""
    ancho, alto = 100.0, 100.0
    paso = ancho / (len(serie) - 1)
    puntos = []
    for indice, fila in enumerate(serie):
        valor = float(fila.get(clave) or 0)
        y = alto - (valor / maximo * (alto * 0.92))
        puntos.append(f"{indice * paso:.3f},{y:.3f}")
    return " ".join(puntos)
