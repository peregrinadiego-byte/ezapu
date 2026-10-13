"""CRUD genérico para todas las tablas de catálogo declaradas en ``ui``."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, request, url_for

from .. import db
from ..domain.costos import costo_recurso, recalcular_todo
from ..ui import (
    ESPECIFICACIONES,
    datos_del_formulario,
    guardar,
    listar,
    obtener,
    opciones_ref,
    spec_de,
)

bp = Blueprint("catalogos", __name__, url_prefix="/c")

TABLAS_SIN_ALTA = {"contrato_concepto"}


# ------------------------------------------------------------------ ganchos --
def _hook_consumo(con, datos, row_id):
    if not datos.get("costo_unitario"):
        datos["costo_unitario"] = costo_recurso(con, datos.get("recurso_id"))
    datos["costo"] = round(float(datos.get("cantidad") or 0) * float(datos["costo_unitario"] or 0), 2)


def _hook_movimiento_bodega(con, datos, row_id):
    if not datos.get("costo_unitario"):
        datos["costo_unitario"] = costo_recurso(con, datos.get("recurso_id"))


def _hook_contrato_concepto(con, datos, row_id):
    datos["importe"] = round(float(datos.get("cantidad") or 0) * float(datos.get("pu") or 0), 2)


GANCHOS = {
    "consumo": _hook_consumo,
    "movimiento_bodega": _hook_movimiento_bodega,
    "contrato_concepto": _hook_contrato_concepto,
}


# ------------------------------------------------------------------- rutas ---
def _spec(tabla):
    if tabla not in ESPECIFICACIONES:
        abort(404)
    return spec_de(tabla)


def _columnas_tabla(con, tabla):
    return {r["name"] for r in con.execute(f"PRAGMA table_info({tabla})").fetchall()}


def _opciones_campos(con, spec):
    campos = []
    for campo in spec.get("campos", []):
        campo = dict(campo)
        if campo.get("ref"):
            campo["opciones"] = opciones_ref(con, campo["ref"], campo.get("ref_filtro"))
        campos.append(campo)
    return campos


@bp.route("/<tabla>/")
def lista(tabla):
    spec = _spec(tabla)
    con = db.get_db()
    columnas = _columnas_tabla(con, tabla)
    filtros = {
        clave: valor
        for clave, valor in request.args.items()
        if clave in columnas and valor not in ("", "todos")
    }
    filas = listar(con, spec, filtros, request.args.get("q"))
    return _render(spec, filas, filtros, con)


def _render(spec, filas, filtros, con):
    from flask import render_template

    totales = {}
    for columna in spec["columnas"]:
        if columna.get("tipo") in ("money", "num", "qty") and columna.get("totalizar"):
            totales[columna["clave"]] = sum(
                float(f.get(columna["clave"]) or 0) for f in filas
            )
    return render_template(
        "catalogos/lista.html",
        spec=spec,
        filas=filas,
        filtros=filtros,
        buscar=request.args.get("q", ""),
        totales=totales,
        opciones=opciones_ref(con, spec["tabla"]),
    )


@bp.route("/<tabla>/nuevo", methods=["GET", "POST"])
def nuevo(tabla):
    spec = _spec(tabla)
    if tabla in TABLAS_SIN_ALTA:
        abort(404)
    con = db.get_db()

    if request.method == "POST":
        datos = datos_del_formulario(spec, request.form)
        if spec["tabla"] in GANCHOS:
            GANCHOS[spec["tabla"]](con, datos, None)
        nuevo_id = guardar(con, spec, datos)
        if spec.get("recalcular"):
            recalcular_todo(con)
        flash(f"{spec['singular']} guardado correctamente.", "ok")
        destino = request.form.get("_volver")
        return redirect(destino or url_for("catalogos.lista", tabla=tabla))

    valores = {campo["clave"]: campo.get("default") for campo in spec.get("campos", [])}
    for clave, valor in request.args.items():
        if clave in valores or clave in _columnas_tabla(con, tabla):
            valores[clave] = valor
    return _formulario(spec, valores, con, nuevo=True)


def _formulario(spec, valores, con, nuevo):
    from flask import render_template

    return render_template(
        "catalogos/formulario.html",
        spec=spec,
        valores=valores,
        campos=_opciones_campos(con, spec),
        nuevo=nuevo,
        volver=request.args.get("volver") or request.form.get("_volver"),
    )


@bp.route("/<tabla>/<int:row_id>/editar", methods=["GET", "POST"])
def editar(tabla, row_id):
    spec = _spec(tabla)
    con = db.get_db()
    fila = obtener(con, tabla, row_id)
    if fila is None:
        abort(404)

    if request.method == "POST":
        datos = datos_del_formulario(spec, request.form)
        if tabla in GANCHOS:
            GANCHOS[tabla](con, datos, row_id)
        guardar(con, spec, datos, row_id)
        if spec.get("recalcular"):
            recalcular_todo(con)
        flash(f"{spec['singular']} actualizado.", "ok")
        destino = request.form.get("_volver")
        return redirect(destino or url_for("catalogos.lista", tabla=tabla))

    return _formulario(spec, {**fila, **{k: v for k, v in request.args.items()}}, con, nuevo=False)


@bp.route("/<tabla>/<int:row_id>/eliminar", methods=["POST"])
def eliminar(tabla, row_id):
    spec = _spec(tabla)
    con = db.get_db()
    try:
        con.execute(f"DELETE FROM {tabla} WHERE id = ?", (row_id,))
        con.commit()
        if spec.get("recalcular"):
            recalcular_todo(con)
        flash(f"{spec['singular']} eliminado.", "ok")
    except Exception as exc:  # noqa: BLE001
        flash(f"No se pudo eliminar: {exc}", "error")
    return redirect(request.form.get("_volver") or url_for("catalogos.lista", tabla=tabla))
