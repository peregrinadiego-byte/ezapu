"""M2 · Planeación: estructura de trabajos y programa de obra (Gantt)."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import db
from ..domain import estructura_trabajos, gantt
from ..domain.planeacion import avance_ponderado, importe_por_tarea
from ..domain.util import parse_date

bp = Blueprint("planeacion", __name__, url_prefix="/m2")


def _proyectos(con):
    return [dict(p) for p in con.execute("SELECT * FROM proyecto ORDER BY clave").fetchall()]


@bp.route("/planeacion/")
def indice():
    con = db.get_db()
    proyectos = _proyectos(con)
    for p in proyectos:
        p["avance"] = avance_ponderado(con, p["id"])
        p["tareas"] = con.execute(
            "SELECT COUNT(*) FROM tarea WHERE proyecto_id = ?", (p["id"],)
        ).fetchone()[0]
    return render_template("planeacion/seleccion.html", proyectos=proyectos)


@bp.route("/proyectos/<int:proyecto_id>/planeacion/")
def programa(proyecto_id):
    con = db.get_db()
    proyecto = con.execute("SELECT * FROM proyecto WHERE id = ?", (proyecto_id,)).fetchone()
    if proyecto is None:
        abort(404)

    estructura = estructura_trabajos(con, proyecto_id)
    diagrama = gantt(con, proyecto_id)

    tareas = [dict(t) for t in con.execute(
        """
        SELECT t.*, p.nombre AS partida, t2.nombre AS predecesora
          FROM tarea t
          LEFT JOIN partida p ON p.id = t.partida_id
          LEFT JOIN tarea   t2 ON t2.id = t.predecesora_id
         WHERE t.proyecto_id = ?
         ORDER BY COALESCE(t.inicio, ''), t.orden, t.clave
        """,
        (proyecto_id,),
    ).fetchall()]

    return render_template(
        "planeacion/programa.html",
        proyecto=proyecto,
        estructura=estructura,
        gantt=diagrama,
        tareas=tareas,
        importes=importe_por_tarea(con, proyecto_id),
        avance=avance_ponderado(con, proyecto_id),
    )


@bp.route("/tareas/<int:tarea_id>/avance", methods=["POST"])
def actualizar_avance(tarea_id):
    con = db.get_db()
    tarea = con.execute("SELECT * FROM tarea WHERE id = ?", (tarea_id,)).fetchone()
    if tarea is None:
        abort(404)

    avance = float(request.form.get("avance") or 0)
    avance = max(0.0, min(100.0, avance))
    estado = request.form.get("estado")
    if not estado:
        estado = "terminado" if avance >= 100 else ("en_proceso" if avance > 0 else "planeado")

    con.execute("UPDATE tarea SET avance = ?, estado = ? WHERE id = ?", (avance, estado, tarea_id))
    con.commit()
    flash(f"Avance de «{tarea['nombre']}» actualizado a {avance:g} %.", "ok")
    return redirect(request.form.get("_volver")
                    or url_for("planeacion.programa", proyecto_id=tarea["proyecto_id"]))


@bp.route("/proyectos/<int:proyecto_id>/tareas/nueva", methods=["POST"])
def nueva_tarea(proyecto_id):
    con = db.get_db()
    inicio = parse_date(request.form.get("inicio"))
    fin = parse_date(request.form.get("fin"))
    duracion = (fin - inicio).days + 1 if inicio and fin else 0
    con.execute(
        """
        INSERT INTO tarea (proyecto_id, parent_id, partida_id, clave, nombre, inicio, fin,
                           duracion, avance, peso, responsable, estado, orden)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 'planeado',
                (SELECT COALESCE(MAX(orden), 0) + 10 FROM tarea WHERE proyecto_id = ?))
        """,
        (
            proyecto_id,
            request.form.get("parent_id") or None,
            request.form.get("partida_id") or None,
            request.form.get("clave"),
            request.form.get("nombre"),
            request.form.get("inicio") or None,
            request.form.get("fin") or None,
            duracion,
            float(request.form.get("peso") or 1),
            request.form.get("responsable"),
            proyecto_id,
        ),
    )
    con.commit()
    flash("Tarea agregada a la estructura de trabajos.", "ok")
    return redirect(url_for("planeacion.programa", proyecto_id=proyecto_id))
