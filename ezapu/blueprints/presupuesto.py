"""M1 · Presupuesto: hoja, desglose, generadores, explosión y análisis del precio."""
from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for

from .. import db
from ..domain import (
    desglose_concepto,
    explosion_proyecto,
    generadores,
    hoja,
    money,
    programa_suministros,
    recalcular_conceptos,
    recalcular_todo,
    recalcular_volumen,
    resumen_por_tipo,
    totales,
)
from ..domain.avance import estado_de_cuenta
from ..domain.planeacion import avance_ponderado

bp = Blueprint("presupuesto", __name__, url_prefix="/m1")


def _proyecto(con, proyecto_id):
    fila = con.execute("SELECT * FROM proyecto WHERE id = ?", (proyecto_id,)).fetchone()
    if fila is None:
        abort(404)
    return fila


def _proyectos(con):
    return [dict(p) for p in con.execute("SELECT * FROM proyecto ORDER BY clave").fetchall()]


# ------------------------------------------------------------ selectores ----
@bp.route("/explosion/")
def explosion_indice():
    return render_template(
        "seleccion.html", proyectos=_proyectos(db.get_db()),
        titulo="Explosión de insumos",
        descripcion="Abre el presupuesto hasta sus insumos básicos: materiales, mano de obra, "
                    "equipo, herramienta, subcontratos y fletes.",
        destino="presupuesto.explosion",
    )


@bp.route("/suministros/")
def suministros_indice():
    return render_template(
        "seleccion.html", proyectos=_proyectos(db.get_db()),
        titulo="Programa de suministros",
        descripcion="Distribuye la explosión de insumos entre las tareas de la obra.",
        destino="presupuesto.suministros",
    )


@bp.route("/analisis/")
def analisis_indice():
    return render_template(
        "seleccion.html", proyectos=_proyectos(db.get_db()),
        titulo="Análisis del precio",
        descripcion="Indirectos, utilidad, financiamiento, cargos adicionales y anticipo.",
        destino="presupuesto.analisis",
    )


@bp.route("/generadores/")
def generadores_indice():
    return render_template(
        "seleccion.html", proyectos=_proyectos(db.get_db()),
        titulo="Volúmenes y generadores",
        descripcion="Números generadores que respaldan el volumen de cada concepto.",
        destino="presupuesto.hoja_presupuesto",
    )


# --------------------------------------------------------------- hoja -------
@bp.route("/proyectos/<int:proyecto_id>/presupuesto/")
def hoja_presupuesto(proyecto_id):
    con = db.get_db()
    proyecto = _proyecto(con, proyecto_id)
    return render_template(
        "presupuesto/hoja.html",
        proyecto=proyecto,
        filas=hoja(con, proyecto_id),
        resumen=totales(con, proyecto_id),
        avance=avance_ponderado(con, proyecto_id),
        cuenta=estado_de_cuenta(con, proyecto_id),
    )


@bp.route("/proyectos/<int:proyecto_id>/recalcular", methods=["POST"])
def recalcular(proyecto_id):
    con = db.get_db()
    _proyecto(con, proyecto_id)
    recalcular_todo(con)
    n = recalcular_conceptos(con, proyecto_id)
    flash(f"Se recalcularon {n} conceptos con el precio vigente de sus matrices.", "ok")
    return redirect(url_for("presupuesto.hoja_presupuesto", proyecto_id=proyecto_id))


# ------------------------------------------------------------- generadores --
@bp.route("/conceptos/<int:concepto_id>/generadores/")
def concepto_generadores(concepto_id):
    con = db.get_db()
    concepto = con.execute(
        """
        SELECT c.*, u.clave AS unidad, p.nombre AS proyecto_nombre, p.id AS pid,
               m.clave AS matriz
          FROM concepto c
          LEFT JOIN unidad u ON u.id = c.unidad_id
          LEFT JOIN matriz m ON m.id = c.matriz_id
          LEFT JOIN proyecto p ON p.id = c.proyecto_id
         WHERE c.id = ?
        """,
        (concepto_id,),
    ).fetchone()
    if concepto is None:
        abort(404)
    filas = generadores(con, concepto_id)
    return render_template(
        "presupuesto/generadores.html",
        concepto=concepto,
        generadores=filas,
        suma=sum(f["total"] for f in filas),
    )


@bp.route("/conceptos/<int:concepto_id>/generadores/nuevo", methods=["POST"])
def generador_nuevo(concepto_id):
    con = db.get_db()
    datos = request.form
    veces = float(datos.get("veces") or 1)
    largo = float(datos.get("largo") or 0)
    ancho = float(datos.get("ancho") or 0)
    alto = float(datos.get("alto") or 0)
    con.execute(
        "INSERT INTO generador (concepto_id, descripcion, veces, largo, ancho, alto, total, orden)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            concepto_id,
            datos.get("descripcion"),
            veces,
            largo,
            ancho,
            alto,
            round(veces * largo * ancho * alto, 6),
            con.execute(
                "SELECT COALESCE(MAX(orden), 0) + 10 FROM generador WHERE concepto_id = ?",
                (concepto_id,),
            ).fetchone()[0],
        ),
    )
    con.commit()
    if datos.get("aplicar") in ("1", "on", "si", "sí"):
        recalcular_volumen(con, concepto_id)
        flash("Generadores guardados y volumen del concepto actualizado.", "ok")
    else:
        flash("Generador agregado.", "ok")
    return redirect(url_for("presupuesto.concepto_generadores", concepto_id=concepto_id))


@bp.route("/generadores/<int:generador_id>/eliminar", methods=["POST"])
def generador_eliminar(generador_id):
    con = db.get_db()
    fila = con.execute("SELECT * FROM generador WHERE id = ?", (generador_id,)).fetchone()
    if fila is None:
        abort(404)
    con.execute("DELETE FROM generador WHERE id = ?", (generador_id,))
    con.commit()
    recalcular_volumen(con, fila["concepto_id"])
    flash("Generador eliminado.", "ok")
    return redirect(url_for("presupuesto.concepto_generadores", concepto_id=fila["concepto_id"]))


@bp.route("/proyectos/<int:proyecto_id>/aplicar-generadores", methods=["POST"])
def aplicar_generadores(proyecto_id):
    con = db.get_db()
    aplicados = 0
    for concepto in con.execute(
        "SELECT id FROM concepto WHERE proyecto_id = ?", (proyecto_id,)
    ).fetchall():
        tiene = con.execute(
            "SELECT COUNT(*) FROM generador WHERE concepto_id = ?", (concepto["id"],)
        ).fetchone()[0]
        if tiene:
            recalcular_volumen(con, concepto["id"])
            aplicados += 1
    flash(f"Volúmenes actualizados desde generadores en {aplicados} conceptos.", "ok")
    return redirect(url_for("presupuesto.hoja_presupuesto", proyecto_id=proyecto_id))


# -------------------------------------------------------------- desglose ----
@bp.route("/conceptos/<int:concepto_id>/desglose/")
def concepto_desglose(concepto_id):
    con = db.get_db()
    info = desglose_concepto(con, concepto_id)
    if not info:
        abort(404)
    return render_template("presupuesto/desglose.html", info=info)


# ------------------------------------------------------------ explosión -----
@bp.route("/proyectos/<int:proyecto_id>/explosion/")
def explosion(proyecto_id):
    con = db.get_db()
    proyecto = _proyecto(con, proyecto_id)
    filas = explosion_proyecto(con, proyecto_id)
    return render_template(
        "presupuesto/explosion.html",
        proyecto=proyecto,
        filas=filas,
        resumen=resumen_por_tipo(filas),
        total=sum(f["importe"] for f in filas),
    )


@bp.route("/proyectos/<int:proyecto_id>/suministros/")
def suministros(proyecto_id):
    con = db.get_db()
    proyecto = _proyecto(con, proyecto_id)
    filas = programa_suministros(con, proyecto_id)
    return render_template(
        "presupuesto/suministros.html",
        proyecto=proyecto,
        filas=filas,
        total=sum(f["importe"] for f in filas),
    )


# ----------------------------------------------------------- análisis -------
@bp.route("/proyectos/<int:proyecto_id>/analisis/", methods=["GET", "POST"])
def analisis(proyecto_id):
    con = db.get_db()
    proyecto = _proyecto(con, proyecto_id)

    if request.method == "POST":
        valores = {
            "pct_indirectos": float(request.form.get("pct_indirectos") or 0),
            "pct_utilidad": float(request.form.get("pct_utilidad") or 0),
            "pct_financiamiento": float(request.form.get("pct_financiamiento") or 0),
            "pct_cargos_adicionales": float(request.form.get("pct_cargos_adicionales") or 0),
            "pct_iva": float(request.form.get("pct_iva") or 0),
            "anticipo_pct": float(request.form.get("anticipo_pct") or 0),
            "retencion_pct": float(request.form.get("retencion_pct") or 0),
            "amortizacion_pct": float(request.form.get("amortizacion_pct") or 0),
            "base_indirectos": request.form.get("base_indirectos") or "directo",
        }
        sets = ", ".join(f"{c} = ?" for c in valores)
        con.execute(f"UPDATE proyecto SET {sets} WHERE id = ?", list(valores.values()) + [proyecto_id])
        con.commit()
        flash("Parámetros del análisis actualizados.", "ok")
        return redirect(url_for("presupuesto.analisis", proyecto_id=proyecto_id))

    return render_template(
        "presupuesto/analisis.html",
        proyecto=proyecto,
        resumen=totales(con, proyecto_id),
        partidas=[
            dict(p)
            for p in con.execute(
                "SELECT p.*, (SELECT COALESCE(SUM(c.importe), 0) FROM concepto c"
                " WHERE c.partida_id = p.id) AS directo"
                "  FROM partida p WHERE p.proyecto_id = ? ORDER BY p.orden, p.clave",
                (proyecto_id,),
            ).fetchall()
        ],
        escalatorias=[
            dict(e)
            for e in con.execute(
                "SELECT * FROM escalatoria WHERE proyecto_id = ? ORDER BY periodo", (proyecto_id,)
            ).fetchall()
        ],
    )


# ---------------------------------------------------------------- CSV -------
def _respuesta_csv(nombre, encabezados, filas):
    buffer = io.StringIO()
    buffer.write("\ufeff")            # BOM para que Excel lo abra con acentos
    escritor = csv.writer(buffer)
    escritor.writerow(encabezados)
    escritor.writerows(filas)
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={nombre}.csv"},
    )


@bp.route("/proyectos/<int:proyecto_id>/explosion.csv")
def explosion_csv(proyecto_id):
    con = db.get_db()
    filas = explosion_proyecto(con, proyecto_id)
    return _respuesta_csv(
        f"explosion_{proyecto_id}",
        ["Tipo", "Clave", "Descripción", "Unidad", "Cantidad", "Costo unitario", "Importe"],
        [
            [f["tipo"], f["clave"], f["descripcion"], f["unidad"], f["cantidad"],
             f["costo_unitario"], money(f["importe"])]
            for f in filas
        ],
    )


@bp.route("/proyectos/<int:proyecto_id>/suministros.csv")
def suministros_csv(proyecto_id):
    con = db.get_db()
    filas = programa_suministros(con, proyecto_id)
    return _respuesta_csv(
        f"suministros_{proyecto_id}",
        ["Tarea", "Inicio", "Fin", "Clave", "Descripción", "Unidad", "Cantidad",
         "Costo unitario", "Importe"],
        [
            [f["tarea"], f["inicio"], f["fin"], f["clave"], f["descripcion"], f["unidad"],
             f["cantidad"], f["costo_unitario"], money(f["importe"])]
            for f in filas
        ],
    )
