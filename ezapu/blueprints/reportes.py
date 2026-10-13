"""Reportes: formatos imprimibles (PDF vía el navegador) y exportación a Excel/CSV."""
from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, abort, render_template

from .. import db
from ..domain import (
    desglose_concepto,
    detalle_matriz,
    explosion_proyecto,
    hoja,
    money,
    resumen_por_tipo,
    totales,
    valor_ganado,
)
from ..domain.avance import estado_de_cuenta, estado_de_servicios, resumen_estimacion
from ..domain.bodega import existencias
from ..domain.util import num, qty

bp = Blueprint("reportes", __name__, url_prefix="/reportes")


# ------------------------------------------------------------------ CSV -----
def _csv(nombre, encabezados, filas):
    buffer = io.StringIO()
    buffer.write("\ufeff")
    escritor = csv.writer(buffer)
    escritor.writerow(encabezados)
    escritor.writerows(filas)
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={nombre}.csv"},
    )


# --------------------------------------------------------------- índice -----
@bp.route("/")
def indice():
    con = db.get_db()
    proyectos = [dict(p) for p in con.execute("SELECT * FROM proyecto ORDER BY clave").fetchall()]
    matrices = [
        dict(m)
        for m in con.execute(
            "SELECT id, clave, descripcion, costo_directo FROM matriz ORDER BY clave"
        ).fetchall()
    ]
    almacenes = [dict(a) for a in con.execute("SELECT * FROM almacen ORDER BY clave").fetchall()]
    estimaciones = [
        dict(e)
        for e in con.execute(
            """
            SELECT e.*, p.clave AS proyecto FROM estimacion e
              JOIN proyecto p ON p.id = e.proyecto_id
             ORDER BY p.clave, e.numero
            """
        ).fetchall()
    ]
    return render_template(
        "reportes/indice.html",
        proyectos=proyectos,
        matrices=matrices,
        almacenes=almacenes,
        estimaciones=estimaciones,
    )


# ------------------------------------------------------- formatos impresos --
@bp.route("/presupuesto/<int:proyecto_id>/")
def presupuesto(proyecto_id):
    con = db.get_db()
    proyecto = _proyecto(con, proyecto_id)
    return render_template(
        "reportes/presupuesto.html",
        titulo_documento="Presupuesto de obra",
        proyecto=proyecto,
        empresa=_empresa(con),
        filas=hoja(con, proyecto_id),
        resumen=totales(con, proyecto_id),
    )


@bp.route("/catalogo-conceptos/<int:proyecto_id>/")
def catalogo_conceptos(proyecto_id):
    con = db.get_db()
    proyecto = _proyecto(con, proyecto_id)
    conceptos = [
        dict(c)
        for c in con.execute(
            """
            SELECT c.*, u.clave AS unidad, m.clave AS matriz
              FROM concepto c
              LEFT JOIN unidad u ON u.id = c.unidad_id
              LEFT JOIN matriz m ON m.id = c.matriz_id
             WHERE c.proyecto_id = ?
             ORDER BY c.orden, c.clave
            """,
            (proyecto_id,),
        ).fetchall()
    ]
    return render_template(
        "reportes/catalogo_conceptos.html",
        titulo_documento="Catálogo de conceptos",
        proyecto=proyecto,
        empresa=_empresa(con),
        conceptos=conceptos,
        importe=sum(num(c, "importe") for c in conceptos),
    )


@bp.route("/analisis-pu/<int:matriz_id>/")
def analisis_pu(matriz_id):
    con = db.get_db()
    matriz = con.execute(
        """
        SELECT m.*, u.clave AS unidad, p.clave AS proyecto
          FROM matriz m
          LEFT JOIN unidad u ON u.id = m.unidad_id
          LEFT JOIN proyecto p ON p.id = m.proyecto_id
         WHERE m.id = ?
        """,
        (matriz_id,),
    ).fetchone()
    if matriz is None:
        abort(404)
    componentes = detalle_matriz(con, matriz_id)
    return render_template(
        "reportes/analisis_pu.html",
        titulo_documento="Análisis de precio unitario",
        matriz=matriz,
        empresa=_empresa(con),
        componentes=componentes,
        costo_directo=sum(c["importe"] for c in componentes),
        proyecto=con.execute(
            "SELECT * FROM proyecto WHERE id = ?", (matriz["proyecto_id"],)
        ).fetchone()
        if matriz["proyecto_id"]
        else None,
    )


@bp.route("/explosion/<int:proyecto_id>/")
def explosion(proyecto_id):
    con = db.get_db()
    proyecto = _proyecto(con, proyecto_id)
    filas = explosion_proyecto(con, proyecto_id)
    return render_template(
        "reportes/explosion.html",
        titulo_documento="Explosión de insumos",
        proyecto=proyecto,
        empresa=_empresa(con),
        filas=filas,
        resumen=resumen_por_tipo(filas),
        total=sum(f["importe"] for f in filas),
    )


@bp.route("/estimacion/<int:estimacion_id>/")
def estimacion(estimacion_id):
    con = db.get_db()
    info = resumen_estimacion(con, estimacion_id)
    if not info:
        abort(404)
    return render_template(
        "reportes/estimacion.html",
        titulo_documento="Estimación de obra",
        estimacion=info,
        empresa=_empresa(con),
        proyecto=con.execute("SELECT * FROM proyecto WHERE id = ?", (info["proyecto_id"],)).fetchone(),
    )


@bp.route("/estado-cuenta/<int:proyecto_id>/")
def estado_cuenta(proyecto_id):
    con = db.get_db()
    proyecto = _proyecto(con, proyecto_id)
    return render_template(
        "reportes/estado_cuenta.html",
        titulo_documento="Estado de cuenta",
        proyecto=proyecto,
        empresa=_empresa(con),
        cuenta=estado_de_cuenta(con, proyecto_id),
    )


@bp.route("/catalogo-insumos/")
def catalogo_insumos():
    con = db.get_db()
    insumos = [
        dict(r)
        for r in con.execute(
            """
            SELECT r.*, u.clave AS unidad, f.nombre AS familia
              FROM recurso r
              LEFT JOIN unidad u ON u.id = r.unidad_id
              LEFT JOIN familia f ON f.id = r.familia_id
             WHERE r.activo = 1
             ORDER BY r.tipo, r.clave
            """
        ).fetchall()
    ]
    from ..domain.costos import costo_recurso

    for i in insumos:
        i["costo_vigente"] = costo_recurso(con, i["id"])
    return render_template(
        "reportes/catalogo_insumos.html",
        titulo_documento="Catálogo de insumos",
        empresa=_empresa(con),
        insumos=insumos,
    )


@bp.route("/bodega/<int:almacen_id>/")
def bodega(almacen_id):
    con = db.get_db()
    almacen = con.execute("SELECT * FROM almacen WHERE id = ?", (almacen_id,)).fetchone()
    if almacen is None:
        abort(404)
    inventario = existencias(con, almacen_id=almacen_id)
    return render_template(
        "reportes/bodega.html",
        titulo_documento="Inventario de almacén",
        empresa=_empresa(con),
        almacen=almacen,
        inventario=inventario,
        total=sum(i["importe"] for i in inventario),
    )


@bp.route("/valor-ganado/<int:proyecto_id>/")
def valor_ganado_reporte(proyecto_id):
    con = db.get_db()
    proyecto = _proyecto(con, proyecto_id)
    indicadores = valor_ganado(con, proyecto_id)
    return render_template(
        "reportes/valor_ganado.html",
        titulo_documento="Reporte de valor ganado",
        empresa=_empresa(con),
        proyecto=proyecto,
        kpi=indicadores,
    )


# ------------------------------------------------------ exportación CSV ----
@bp.route("/csv/presupuesto/<int:proyecto_id>.csv")
def csv_presupuesto(proyecto_id):
    con = db.get_db()
    filas = [
        [f.get("clave", ""), f.get("descripcion") or f.get("nombre", ""),
         f.get("unidad") or "", "Concepto" if f.get("es_concepto") else "Partida",
         qty(f.get("cantidad")) if f.get("es_concepto") else "",
         money(f.get("pu")) if f.get("es_concepto") else "",
         money(f.get("importe") if f.get("es_concepto") else f.get("total"))]
        for f in hoja(con, proyecto_id)
    ]
    return _csv(
        f"presupuesto_{proyecto_id}",
        ["Clave", "Descripción", "Unidad", "Tipo", "Volumen", "P.U.", "Importe"],
        filas,
    )


@bp.route("/csv/conceptos/<int:proyecto_id>.csv")
def csv_conceptos(proyecto_id):
    con = db.get_db()
    filas = [
        [c["clave"], c["descripcion"], c["unidad"] or "", c["cantidad"], c["pu"], c["importe"]]
        for c in con.execute(
            """
            SELECT c.*, u.clave AS unidad FROM concepto c
              LEFT JOIN unidad u ON u.id = c.unidad_id
             WHERE c.proyecto_id = ? ORDER BY c.clave
            """,
            (proyecto_id,),
        ).fetchall()
    ]
    return _csv(f"conceptos_{proyecto_id}",
                ["Clave", "Descripción", "Unidad", "Volumen", "P.U.", "Importe"], filas)


@bp.route("/csv/insumos.csv")
def csv_insumos():
    from ..domain.costos import costo_recurso

    con = db.get_db()
    filas = [
        [r["clave"], r["descripcion"], r["tipo"], r["unidad"] or "", costo_recurso(con, r["id"])]
        for r in con.execute(
            """
            SELECT r.*, u.clave AS unidad FROM recurso r
              LEFT JOIN unidad u ON u.id = r.unidad_id WHERE r.activo = 1
             ORDER BY r.tipo, r.clave
            """
        ).fetchall()
    ]
    return _csv("catalogo_insumos", ["Clave", "Descripción", "Tipo", "Unidad", "Costo vigente"], filas)


@bp.route("/csv/matriz/<int:matriz_id>.csv")
def csv_matriz(matriz_id):
    con = db.get_db()
    filas = [
        [c["clave"], c["descripcion"], c["unidad"] or "", c["cantidad"],
         c["costo_unitario"], c["importe"]]
        for c in detalle_matriz(con, matriz_id)
    ]
    return _csv(f"matriz_{matriz_id}",
                ["Clave", "Descripción", "Unidad", "Cantidad", "Costo unitario", "Importe"], filas)


@bp.route("/csv/estimaciones/<int:proyecto_id>.csv")
def csv_estimaciones(proyecto_id):
    con = db.get_db()
    filas = [
        [e["numero"], e["periodo_inicio"], e["periodo_fin"], e["subtotal"], e["iva"],
         e["amortizacion"], e["retencion"], e["total"], e["estatus"]]
        for e in estado_de_cuenta(con, proyecto_id)["estimaciones"]
    ]
    return _csv(
        f"estimaciones_{proyecto_id}",
        ["Número", "Inicio", "Fin", "Subtotal", "IVA", "Amortización", "Retención", "Total", "Estatus"],
        filas,
    )


@bp.route("/csv/bodega/<int:almacen_id>.csv")
def csv_bodega(almacen_id):
    con = db.get_db()
    filas = [
        [i["clave"], i["descripcion"], i["unidad"] or "", i["cantidad"],
         i["costo_promedio"], i["importe"]]
        for i in existencias(con, almacen_id=almacen_id)
    ]
    return _csv(f"bodega_{almacen_id}",
                ["Clave", "Descripción", "Unidad", "Existencia", "Costo promedio", "Importe"],
                filas)


@bp.route("/csv/servicios/<int:proyecto_id>.csv")
def csv_servicios(proyecto_id):
    con = db.get_db()
    filas = [
        [s["clave"], s["descripcion"], s["tarea"] or "", s["cantidad"], s["importe"]]
        for s in estado_de_servicios(con, proyecto_id)
    ]
    return _csv(f"servicios_{proyecto_id}",
                ["Clave", "Descripción", "Tarea", "Cantidad consumida", "Importe"], filas)


# ---------------------------------------------------------------- helpers ---
def _proyecto(con, proyecto_id):
    fila = con.execute("SELECT * FROM proyecto WHERE id = ?", (proyecto_id,)).fetchone()
    if fila is None:
        abort(404)
    return fila


def _empresa(con):
    return con.execute("SELECT * FROM empresa LIMIT 1").fetchone()
