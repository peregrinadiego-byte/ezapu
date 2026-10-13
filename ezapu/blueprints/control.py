"""M2 · Avance y bodega: estimaciones, pagos, consumos, estado de servicios y almacén."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import db
from ..domain import existencias, kardex, money
from ..domain.avance import (
    actualizar_totales,
    costo_real_insumos,
    estado_de_cuenta,
    estado_de_servicios,
    preparar_detalle,
    requisiciones,
    resumen_estimacion,
)
from ..domain.explosion import explosion_proyecto
from ..domain.util import num, qty, today

bp = Blueprint("control", __name__, url_prefix="/m2")


def _proyecto(con, proyecto_id):
    fila = con.execute("SELECT * FROM proyecto WHERE id = ?", (proyecto_id,)).fetchone()
    if fila is None:
        abort(404)
    return fila


def _proyectos(con):
    return [dict(p) for p in con.execute("SELECT * FROM proyecto ORDER BY clave").fetchall()]


# ============================================================ estimaciones ==
@bp.route("/estimaciones/")
def estimaciones_indice():
    con = db.get_db()
    proyectos = _proyectos(con)
    for p in proyectos:
        cuenta = estado_de_cuenta(con, p["id"])
        p["estimado"] = cuenta["total_estimado"]
        p["pagado"] = cuenta["total_pagado"]
        p["pendiente"] = cuenta["total_pendiente"]
        p["estimaciones"] = len(cuenta["estimaciones"])
    return render_template("control/estimaciones_seleccion.html", proyectos=proyectos)


@bp.route("/proyectos/<int:proyecto_id>/estimaciones/")
def estimaciones(proyecto_id):
    con = db.get_db()
    proyecto = _proyecto(con, proyecto_id)
    cuenta = estado_de_cuenta(con, proyecto_id)
    return render_template(
        "control/estimaciones.html", proyecto=proyecto, cuenta=cuenta,
        resumen_presupuesto=con.execute(
            "SELECT COALESCE(SUM(importe), 0) FROM concepto WHERE proyecto_id = ?", (proyecto_id,)
        ).fetchone()[0],
    )


@bp.route("/proyectos/<int:proyecto_id>/estimaciones/nueva", methods=["POST"])
def estimacion_nueva(proyecto_id):
    con = db.get_db()
    _proyecto(con, proyecto_id)
    consecutivo = con.execute(
        "SELECT COUNT(*) + 1 FROM estimacion WHERE proyecto_id = ?", (proyecto_id,)
    ).fetchone()[0]
    numero = request.form.get("numero") or f"EST-{consecutivo:02d}"
    estimacion_id = con.execute(
        """
        INSERT INTO estimacion (proyecto_id, contrato_id, numero, tipo, periodo_inicio,
                                periodo_fin, fecha, estatus)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'borrador')
        """,
        (
            proyecto_id,
            request.form.get("contrato_id") or None,
            numero,
            request.form.get("tipo") or "cobrar",
            request.form.get("periodo_inicio") or None,
            request.form.get("periodo_fin") or None,
            request.form.get("fecha") or today(),
        ),
    ).lastrowid
    con.commit()
    preparar_detalle(con, estimacion_id)
    actualizar_totales(con, estimacion_id)
    flash(f"Estimación {numero} creada y sincronizada con el catálogo de conceptos.", "ok")
    return redirect(url_for("control.estimacion", estimacion_id=estimacion_id))


@bp.route("/estimaciones/<int:estimacion_id>/")
def estimacion(estimacion_id):
    con = db.get_db()
    info = resumen_estimacion(con, estimacion_id)
    if not info:
        abort(404)
    return render_template(
        "control/estimacion.html",
        estimacion=info,
        proyecto=con.execute(
            "SELECT * FROM proyecto WHERE id = ?", (info["proyecto_id"],)
        ).fetchone(),
    )


@bp.route("/estimaciones/<int:estimacion_id>/cantidades", methods=["POST"])
def estimacion_cantidades(estimacion_id):
    con = db.get_db()
    info = resumen_estimacion(con, estimacion_id)
    if not info:
        abort(404)

    for fila in info["detalle"]:
        clave = f"cantidad_{fila['id']}"
        if clave in request.form:
            con.execute(
                "UPDATE estimacion_detalle SET cantidad_actual = ? WHERE id = ?",
                (float(request.form.get(clave) or 0), fila["id"]),
            )

    estatus = request.form.get("estatus")
    if estatus:
        con.execute("UPDATE estimacion SET estatus = ? WHERE id = ?", (estatus, estimacion_id))

    con.commit()
    totales = actualizar_totales(con, estimacion_id)
    flash(f"Cantidades guardadas. Importe de la estimación: {money(totales['total']):,.2f}.", "ok")
    return redirect(url_for("control.estimacion", estimacion_id=estimacion_id))


@bp.route("/estimaciones/<int:estimacion_id>/sincronizar", methods=["POST"])
def estimacion_sincronizar(estimacion_id):
    con = db.get_db()
    filas = preparar_detalle(con, estimacion_id)
    actualizar_totales(con, estimacion_id)
    flash(f"Detalle sincronizado con {filas} conceptos del presupuesto.", "ok")
    return redirect(url_for("control.estimacion", estimacion_id=estimacion_id))


@bp.route("/estimaciones/<int:estimacion_id>/pago", methods=["POST"])
def estimacion_pago(estimacion_id):
    con = db.get_db()
    info = resumen_estimacion(con, estimacion_id)
    if not info:
        abort(404)
    monto = float(request.form.get("monto") or 0) or info["saldo"]
    con.execute(
        "INSERT INTO pago (estimacion_id, proyecto_id, fecha, monto, referencia, medio, notas)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            estimacion_id,
            info["proyecto_id"],
            request.form.get("fecha") or today(),
            round(monto, 2),
            request.form.get("referencia"),
            request.form.get("medio") or "transferencia",
            request.form.get("notas"),
        ),
    )
    con.commit()
    flash(f"Pago registrado por {money(monto):,.2f}.", "ok")
    return redirect(url_for("control.estimacion", estimacion_id=estimacion_id))


@bp.route("/estimaciones/<int:estimacion_id>/eliminar", methods=["POST"])
def estimacion_eliminar(estimacion_id):
    con = db.get_db()
    fila = con.execute("SELECT * FROM estimacion WHERE id = ?", (estimacion_id,)).fetchone()
    if fila is None:
        abort(404)
    con.execute("DELETE FROM estimacion WHERE id = ?", (estimacion_id,))
    con.commit()
    flash("Estimación eliminada.", "ok")
    return redirect(url_for("control.estimaciones", proyecto_id=fila["proyecto_id"]))


# ==================================================== estado de servicios ==
@bp.route("/servicios/")
def servicios_indice():
    return render_template(
        "seleccion.html", proyectos=_proyectos(db.get_db()),
        titulo="Estado de servicios",
        descripcion="Compara los insumos requeridos por el presupuesto contra los realmente "
                    "consumidos en obra, con su costo.",
        destino="control.servicios",
    )


@bp.route("/proyectos/<int:proyecto_id>/servicios/")
def servicios(proyecto_id):
    con = db.get_db()
    proyecto = _proyecto(con, proyecto_id)

    consumidos = estado_de_servicios(con, proyecto_id)
    requeridos = {f["recurso_id"]: f for f in explosion_proyecto(con, proyecto_id)}

    detalle = []
    for fila in consumidos:
        requerido = requeridos.get(fila["recurso_id"], {})
        cantidad_requerida = num(requerido, "cantidad")
        cantidad_consumida = num(fila, "cantidad")
        detalle.append(
            {
                "recurso_id": fila["recurso_id"],
                "clave": fila["clave"],
                "descripcion": fila["descripcion"],
                "unidad": fila["unidad"],
                "tarea": fila["tarea"] or "—",
                "cantidad_requerida": qty(cantidad_requerida),
                "cantidad_consumida": qty(cantidad_consumida),
                "diferencia": qty(cantidad_requerida - cantidad_consumida),
                "avance_pct": round(
                    (cantidad_consumida / cantidad_requerida * 100.0) if cantidad_requerida else 0.0, 1
                ),
                "importe": money(fila["importe"]),
                "costo_requerido": money(num(requerido, "importe")),
            }
        )

    consumo_por_tarea = [
        dict(r)
        for r in con.execute(
            """
            SELECT t.clave AS tarea_clave, t.nombre AS tarea, COUNT(*) AS partidas,
                   SUM(c.costo) AS importe
              FROM consumo c LEFT JOIN tarea t ON t.id = c.tarea_id
             WHERE c.proyecto_id = ?
             GROUP BY c.tarea_id ORDER BY importe DESC
            """,
            (proyecto_id,),
        ).fetchall()
    ]

    return render_template(
        "control/servicios.html",
        proyecto=proyecto,
        detalle=detalle,
        costo_real=costo_real_insumos(con, proyecto_id),
        costo_presupuestado=sum(f["importe"] for f in requeridos.values()),
        por_tarea=consumo_por_tarea,
        requisiciones=requisiciones(con, proyecto_id),
    )


# ================================================================ bodega ====
@bp.route("/bodega/")
def bodega_indice():
    con = db.get_db()
    almacenes = [dict(a) for a in con.execute(
        """
        SELECT a.*, p.clave AS proyecto, p.nombre AS proyecto_nombre
          FROM almacen a LEFT JOIN proyecto p ON p.id = a.proyecto_id
         ORDER BY a.clave
        """
    ).fetchall()]
    for a in almacenes:
        inventario = existencias(con, almacen_id=a["id"])
        a["partidas"] = len(inventario)
        a["valor"] = money(sum(i["importe"] for i in inventario))
    return render_template("control/bodega_seleccion.html", almacenes=almacenes)


@bp.route("/almacenes/<int:almacen_id>/bodega/")
def bodega(almacen_id):
    con = db.get_db()
    almacen = con.execute(
        """
        SELECT a.*, p.clave AS proyecto, p.nombre AS proyecto_nombre
          FROM almacen a LEFT JOIN proyecto p ON p.id = a.proyecto_id
         WHERE a.id = ?
        """,
        (almacen_id,),
    ).fetchone()
    if almacen is None:
        abort(404)

    inventario = existencias(con, almacen_id=almacen_id)
    movimientos = [
        dict(m)
        for m in con.execute(
            """
            SELECT m.*, r.clave AS insumo, r.descripcion, t.nombre AS tercero
              FROM movimiento_bodega m
              JOIN recurso r ON r.id = m.recurso_id
              LEFT JOIN tercero t ON t.id = m.tercero_id
             WHERE m.almacen_id = ?
             ORDER BY COALESCE(m.fecha, '') DESC, m.id DESC
             LIMIT 40
            """,
            (almacen_id,),
        ).fetchall()
    ]

    return render_template(
        "control/bodega.html",
        almacen=almacen,
        inventario=inventario,
        valor=money(sum(i["importe"] for i in inventario)),
        movimientos=movimientos,
    )


@bp.route("/almacenes/<int:almacen_id>/kardex/<int:recurso_id>/")
def kardex_insumo(almacen_id, recurso_id):
    con = db.get_db()
    almacen = con.execute("SELECT * FROM almacen WHERE id = ?", (almacen_id,)).fetchone()
    recurso = con.execute("SELECT * FROM recurso WHERE id = ?", (recurso_id,)).fetchone()
    if almacen is None or recurso is None:
        abort(404)
    return render_template(
        "control/kardex.html",
        almacen=almacen,
        recurso=recurso,
        movimientos=kardex(con, almacen_id, recurso_id),
    )
