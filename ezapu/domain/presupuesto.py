"""Presupuesto: hoja de conceptos, análisis del precio y desglose por partidas.

El «análisis del precio» replica el esquema de OPUS M1: los porcentajes de
indirectos, utilidad, financiamiento y cargos adicionales se aplican sobre el
costo directo o sobre el acumulado, según ``proyecto.base_indirectos``.
"""
from __future__ import annotations

from .costos import precio_matriz
from .trees import build_tree, flatten, rollup
from .util import get, money, num, qty


def totales(con, proyecto_id) -> dict:
    """Resumen económico del presupuesto."""
    proyecto = con.execute("SELECT * FROM proyecto WHERE id = ?", (proyecto_id,)).fetchone()
    if proyecto is None:
        return {}

    directo = money(
        con.execute(
            "SELECT COALESCE(SUM(importe), 0) FROM concepto WHERE proyecto_id = ?", (proyecto_id,)
        ).fetchone()[0]
    )

    base_modo = get(proyecto, "base_indirectos", "directo") or "directo"

    def pct(clave):
        return num(proyecto, clave) / 100.0

    indirectos = money(directo * pct("pct_indirectos"))
    acumulado = directo + indirectos

    base_utilidad = directo if base_modo == "directo" else acumulado
    utilidad = money(base_utilidad * pct("pct_utilidad"))
    acumulado += utilidad

    base_fin = directo if base_modo == "directo" else acumulado
    financiamiento = money(base_fin * pct("pct_financiamiento"))
    acumulado += financiamiento

    base_cargos = directo if base_modo == "directo" else acumulado
    cargos = money(base_cargos * pct("pct_cargos_adicionales"))

    subtotal = money(directo + indirectos + utilidad + financiamiento + cargos)
    iva = money(subtotal * pct("pct_iva"))

    return {
        "costo_directo": directo,
        "indirectos": indirectos,
        "utilidad": utilidad,
        "financiamiento": financiamiento,
        "cargos_adicionales": cargos,
        "subtotal": subtotal,
        "iva": iva,
        "total": money(subtotal + iva),
        "base": base_modo,
        "pct_indirectos": num(proyecto, "pct_indirectos"),
        "pct_utilidad": num(proyecto, "pct_utilidad"),
        "pct_financiamiento": num(proyecto, "pct_financiamiento"),
        "pct_cargos_adicionales": num(proyecto, "pct_cargos_adicionales"),
        "pct_iva": num(proyecto, "pct_iva"),
        "anticipo_pct": num(proyecto, "anticipo_pct"),
        "anticipo": money(subtotal * pct("anticipo_pct")),
    }


def hoja(con, proyecto_id) -> list[dict]:
    """Hoja de presupuesto ordenada: partidas (con subtotales) y conceptos."""
    partidas = con.execute(
        "SELECT * FROM partida WHERE proyecto_id = ? ORDER BY orden, clave, id", (proyecto_id,)
    ).fetchall()
    conceptos = con.execute(
        """
        SELECT c.*, u.clave AS unidad, m.clave AS matriz_clave
          FROM concepto c
          LEFT JOIN unidad u ON u.id = c.unidad_id
          LEFT JOIN matriz m ON m.id = c.matriz_id
         WHERE c.proyecto_id = ?
         ORDER BY c.orden, c.clave, c.id
        """,
        (proyecto_id,),
    ).fetchall()

    nodos = [dict(p) for p in partidas]
    raices, indice = build_tree(
        nodos, sort_key=lambda n: (num(n, "orden"), str(n.get("clave") or ""))
    )

    for concepto in conceptos:
        item = dict(concepto)
        item["es_concepto"] = True
        item["importe"] = money(num(item, "cantidad") * num(item, "pu"))
        item["hijos"] = []          # los conceptos son hojas del árbol
        padre = indice.get(get(concepto, "partida_id", None))
        if padre is not None:
            padre["hijos"].append(item)
        else:
            raices.append(item)

    rollup(raices, "importe", "total")

    return list(flatten(raices))


def desglose_concepto(con, concepto_id) -> dict:
    """Desglose de un concepto: matriz, componentes y su costo."""
    from .costos import detalle_matriz

    concepto = con.execute(
        """
        SELECT c.*, m.clave AS matriz_clave, m.descripcion AS matriz_descripcion,
               m.costo_indirecto_pct, u.clave AS unidad
          FROM concepto c
          LEFT JOIN matriz m ON m.id = c.matriz_id
          LEFT JOIN unidad u ON u.id = c.unidad_id
         WHERE c.id = ?
        """,
        (concepto_id,),
    ).fetchone()
    if concepto is None:
        return {}
    info = dict(concepto)
    mid = get(concepto, "matriz_id", None)
    info["componentes"] = detalle_matriz(con, mid) if mid else []
    info["costo_directo"] = sum(c["importe"] for c in info["componentes"])
    info["pu"] = precio_matriz(con, mid) if mid else num(concepto, "pu")
    info["importe"] = money(num(concepto, "cantidad") * info["pu"])
    return info


def recalcular_conceptos(con, proyecto_id) -> int:
    """Reaplica el precio de la matriz a cada concepto y recalcula importes."""
    filas = con.execute("SELECT * FROM concepto WHERE proyecto_id = ?", (proyecto_id,)).fetchall()
    for concepto in filas:
        mid = get(concepto, "matriz_id", None)
        if mid:
            con.execute(
                "UPDATE concepto SET pu = ? WHERE id = ?", (precio_matriz(con, mid), concepto["id"])
            )
        con.execute(
            "UPDATE concepto SET importe = ROUND(cantidad * pu, 2) WHERE id = ?", (concepto["id"],)
        )
    con.commit()
    return len(filas)


def generadores(con, concepto_id) -> list[dict]:
    filas = []
    for g in con.execute(
        "SELECT * FROM generador WHERE concepto_id = ? ORDER BY orden, id", (concepto_id,)
    ).fetchall():
        item = dict(g)
        item["total"] = qty(
            num(item, "veces") * num(item, "largo") * num(item, "ancho") * num(item, "alto")
        )
        filas.append(item)
    return filas


def recalcular_volumen(con, concepto_id):
    """El volumen del concepto puede alimentarse de sus números generadores."""
    total = con.execute(
        "SELECT COALESCE(SUM(veces * largo * ancho * alto), 0) FROM generador WHERE concepto_id = ?",
        (concepto_id,),
    ).fetchone()[0]
    con.execute("UPDATE concepto SET cantidad = ? WHERE id = ?", (qty(total), concepto_id))
    con.execute("UPDATE concepto SET importe = ROUND(cantidad * pu, 2) WHERE id = ?", (concepto_id,))
    con.commit()


def escalatorias(con, proyecto_id) -> list[dict]:
    filas = []
    for e in con.execute(
        "SELECT * FROM escalatoria WHERE proyecto_id = ? ORDER BY periodo", (proyecto_id,)
    ).fetchall():
        item = dict(e)
        item["factor"] = num(item, "factor", 1)
        filas.append(item)
    return filas
