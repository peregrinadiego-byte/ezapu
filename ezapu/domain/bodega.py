"""Bodega de obra: existencias, kardex y costo promedio ponderado."""
from __future__ import annotations

from .costos import costo_recurso
from .util import get, money, num, qty


def existencias(con, almacen_id=None, proyecto_id=None) -> list[dict]:
    """Existencia por insumo con costo promedio ponderado de las entradas."""
    filtros, args = [], []
    if almacen_id:
        filtros.append("m.almacen_id = ?")
        args.append(almacen_id)
    if proyecto_id:
        filtros.append("a.proyecto_id = ?")
        args.append(proyecto_id)
    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""

    filas = con.execute(
        f"""
        SELECT m.recurso_id,
               r.clave, r.descripcion, r.tipo,
               u.clave AS unidad,
               SUM(CASE WHEN m.tipo = 'entrada' THEN m.cantidad
                        WHEN m.tipo = 'salida'  THEN -m.cantidad
                        ELSE m.cantidad END)                       AS cantidad,
               SUM(CASE WHEN m.tipo = 'entrada' THEN m.cantidad * m.costo_unitario ELSE 0 END)
                                                                   AS base_costo,
               SUM(CASE WHEN m.tipo = 'entrada' THEN m.cantidad ELSE 0 END) AS base_cantidad
          FROM movimiento_bodega m
          JOIN almacen a ON a.id = m.almacen_id
          JOIN recurso r ON r.id = m.recurso_id
          LEFT JOIN unidad u ON u.id = r.unidad_id
          {where}
         GROUP BY m.recurso_id
         ORDER BY r.clave
        """,
        args,
    ).fetchall()

    resultado = []
    for f in filas:
        item = dict(f)
        cantidad = num(item, "cantidad")
        base_cantidad = num(item, "base_cantidad")
        if base_cantidad:
            promedio = num(item, "base_costo") / base_cantidad
        else:
            promedio = costo_recurso(con, item["recurso_id"])
        item["cantidad"] = qty(cantidad)
        item["costo_promedio"] = money(promedio)
        item["costo_reposicion"] = money(costo_recurso(con, item["recurso_id"]))
        item["importe"] = money(cantidad * promedio)
        resultado.append(item)
    return resultado


def kardex(con, almacen_id, recurso_id) -> list[dict]:
    """Movimientos de un insumo con saldo acumulado."""
    saldo = 0.0
    filas = []
    for m in con.execute(
        """
        SELECT m.*, a.clave AS almacen, t.nombre AS tercero
          FROM movimiento_bodega m
          JOIN almacen a ON a.id = m.almacen_id
          LEFT JOIN tercero t ON t.id = m.tercero_id
         WHERE m.almacen_id = ? AND m.recurso_id = ?
         ORDER BY COALESCE(m.fecha, ''), m.id
        """,
        (almacen_id, recurso_id),
    ).fetchall():
        item = dict(m)
        cantidad = num(item, "cantidad")
        if get(item, "tipo") == "salida":
            saldo -= cantidad
        else:
            saldo += cantidad
        item["saldo"] = qty(saldo)
        filas.append(item)
    return filas
