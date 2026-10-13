"""Editor de matrices de costo unitario (análisis de precio unitario)."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import db
from ..domain.costos import (
    CicloError,
    detalle_matriz,
    precio_matriz,
    recalcular_todo,
)
from ..ui import opciones_ref

bp = Blueprint("matrices", __name__, url_prefix="/m1/matrices")


def _matriz_o_404(con, matriz_id):
    fila = con.execute(
        """
        SELECT m.*, u.clave AS unidad, p.clave AS proyecto
          FROM matriz m
          LEFT JOIN unidad u ON u.id = m.unidad_id
          LEFT JOIN proyecto p ON p.id = m.proyecto_id
         WHERE m.id = ?
        """,
        (matriz_id,),
    ).fetchone()
    if fila is None:
        abort(404)
    return fila


@bp.route("/<int:matriz_id>/")
def editor(matriz_id):
    con = db.get_db()
    matriz = _matriz_o_404(con, matriz_id)
    try:
        componentes = detalle_matriz(con, matriz_id)
        error = None
    except CicloError as exc:
        componentes, error = [], str(exc)

    submatrices = [
        dict(r)
        for r in con.execute(
            "SELECT id, clave, descripcion FROM matriz WHERE id <> ? ORDER BY clave", (matriz_id,)
        ).fetchall()
    ]

    return render_template(
        "matrices/editor.html",
        matriz=matriz,
        componentes=componentes,
        costo_directo=sum(c["importe"] for c in componentes),
        precio=precio_matriz(con, matriz_id) if not error else 0,
        error=error,
        recursos=opciones_ref(con, "recurso"),
        matrices=submatrices,
    )


@bp.route("/<int:matriz_id>/componentes/nuevo", methods=["POST"])
def agregar_componente(matriz_id):
    con = db.get_db()
    _matriz_o_404(con, matriz_id)

    submatriz_id = request.form.get("submatriz_id") or None
    recurso_id = request.form.get("recurso_id") or None
    if not submatriz_id and not recurso_id:
        flash("Selecciona un insumo o una submatriz.", "error")
        return redirect(url_for("matrices.editor", matriz_id=matriz_id))
    if submatriz_id and int(submatriz_id) == matriz_id:
        flash("Una matriz no puede contenerse a sí misma.", "error")
        return redirect(url_for("matrices.editor", matriz_id=matriz_id))

    siguiente = con.execute(
        "SELECT COALESCE(MAX(orden), 0) + 10 FROM matriz_detalle WHERE matriz_id = ?", (matriz_id,)
    ).fetchone()[0]

    con.execute(
        "INSERT INTO matriz_detalle (matriz_id, recurso_id, submatriz_id, cantidad, orden, notas)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            matriz_id,
            int(recurso_id) if recurso_id else None,
            int(submatriz_id) if submatriz_id else None,
            float(request.form.get("cantidad") or 0),
            siguiente,
            request.form.get("notas") or None,
        ),
    )
    con.commit()
    recalcular_todo(con)
    flash("Componente agregado.", "ok")
    return redirect(url_for("matrices.editor", matriz_id=matriz_id))


@bp.route("/<int:matriz_id>/componentes/<int:detalle_id>", methods=["POST"])
def actualizar_componente(matriz_id, detalle_id):
    con = db.get_db()
    con.execute(
        "UPDATE matriz_detalle SET cantidad = ?, notas = ? WHERE id = ? AND matriz_id = ?",
        (
            float(request.form.get("cantidad") or 0),
            request.form.get("notas") or None,
            detalle_id,
            matriz_id,
        ),
    )
    con.commit()
    recalcular_todo(con)
    flash("Rendimiento actualizado.", "ok")
    return redirect(url_for("matrices.editor", matriz_id=matriz_id))


@bp.route("/<int:matriz_id>/componentes/<int:detalle_id>/eliminar", methods=["POST"])
def eliminar_componente(matriz_id, detalle_id):
    con = db.get_db()
    con.execute("DELETE FROM matriz_detalle WHERE id = ? AND matriz_id = ?", (detalle_id, matriz_id))
    con.commit()
    recalcular_todo(con)
    flash("Componente eliminado.", "ok")
    return redirect(url_for("matrices.editor", matriz_id=matriz_id))
