"""Avance de obra: estimaciones, pagos, consumos y estado de servicios."""
from __future__ import annotations

from .util import get, money, num, qty


# =====================================================================
#  Estimaciones
# =====================================================================
def acumulado_por_concepto(con, proyecto_id, excluir_estimacion=None) -> dict:
    """Cantidad estimada acumulada por concepto (estimaciones no canceladas)."""
    sql = """
        SELECT d.concepto_id, SUM(d.cantidad_actual) AS cantidad
          FROM estimacion_detalle d
          JOIN estimacion e ON e.id = d.estimacion_id
         WHERE e.proyecto_id = ?
           AND e.estatus IN ('autorizada', 'pagada', 'enviada')
    """
    args = [proyecto_id]
    if excluir_estimacion:
        sql += " AND e.id <> ?"
        args.append(excluir_estimacion)
    sql += " GROUP BY d.concepto_id"

    return {r["concepto_id"]: num(r, "cantidad") for r in con.execute(sql, args).fetchall()}


def preparar_detalle(con, estimacion_id) -> int:
    """Sincroniza el detalle de la estimación con los conceptos del proyecto."""
    estimacion = con.execute("SELECT * FROM estimacion WHERE id = ?", (estimacion_id,)).fetchone()
    if estimacion is None:
        return 0

    acumulados = acumulado_por_concepto(con, estimacion["proyecto_id"], estimacion_id)
    existentes = {
        r["concepto_id"]: r
        for r in con.execute(
            "SELECT * FROM estimacion_detalle WHERE estimacion_id = ?", (estimacion_id,)
        ).fetchall()
    }

    conceptos = con.execute(
        """
        SELECT c.*, u.clave AS unidad FROM concepto c
        LEFT JOIN unidad u ON u.id = c.unidad_id
        WHERE c.proyecto_id = ? ORDER BY c.orden, c.clave, c.id
        """,
        (estimacion["proyecto_id"],),
    ).fetchall()

    vistos = set()
    contador = 0
    for concepto in conceptos:
        cid = concepto["id"]
        vistos.add(cid)
        anterior = acumulados.get(cid, 0.0)
        actual = existentes.get(cid)
        cantidad_actual = num(actual, "cantidad_actual") if actual else 0.0
        datos = {
            "estimacion_id": estimacion_id,
            "concepto_id": cid,
            "clave": get(concepto, "clave", ""),
            "descripcion": get(concepto, "descripcion", ""),
            "unidad": get(concepto, "unidad", ""),
            "cantidad_anterior": qty(anterior),
            "cantidad_actual": qty(cantidad_actual),
            "cantidad_total": qty(anterior + cantidad_actual),
            "pu": num(concepto, "pu"),
            "importe": money(cantidad_actual * num(concepto, "pu")),
        }
        if actual:
            sets = ", ".join(f"{k} = ?" for k in datos)
            con.execute(
                f"UPDATE estimacion_detalle SET {sets} WHERE id = ?",
                [datos[k] for k in datos] + [actual["id"]],
            )
        else:
            cols = list(datos)
            con.execute(
                "INSERT INTO estimacion_detalle ({}) VALUES ({})".format(
                    ", ".join(cols), ", ".join("?" * len(cols))
                ),
                [datos[c] for c in cols],
            )
        contador += 1

    for cid, fila in existentes.items():
        if cid not in vistos and cid is not None:
            con.execute("DELETE FROM estimacion_detalle WHERE id = ?", (fila["id"],))

    con.commit()
    return contador


def actualizar_totales(con, estimacion_id) -> dict:
    """Recalcula importes, IVA, amortización de anticipo y retención."""
    estimacion = con.execute("SELECT * FROM estimacion WHERE id = ?", (estimacion_id,)).fetchone()
    if estimacion is None:
        return {}

    con.execute(
        "UPDATE estimacion_detalle SET cantidad_total = ROUND(cantidad_anterior + cantidad_actual, 6),"
        " importe = ROUND(cantidad_actual * pu, 2) WHERE estimacion_id = ?",
        (estimacion_id,),
    )

    subtotal = money(
        con.execute(
            "SELECT COALESCE(SUM(importe), 0) FROM estimacion_detalle WHERE estimacion_id = ?",
            (estimacion_id,),
        ).fetchone()[0]
    )

    proyecto = con.execute(
        "SELECT * FROM proyecto WHERE id = ?", (estimacion["proyecto_id"],)
    ).fetchone()
    iva_pct = num(proyecto, "pct_iva")
    amort_pct = num(proyecto, "amortizacion_pct")
    ret_pct = num(proyecto, "retencion_pct")

    iva = money(subtotal * iva_pct / 100.0)
    amortizacion = money(subtotal * amort_pct / 100.0)
    retencion = money(subtotal * ret_pct / 100.0)
    total = money(subtotal + iva - amortizacion - retencion)

    con.execute(
        "UPDATE estimacion SET subtotal = ?, iva = ?, amortizacion = ?, retencion = ?, total = ?"
        " WHERE id = ?",
        (subtotal, iva, amortizacion, retencion, total, estimacion_id),
    )
    con.commit()
    return {
        "subtotal": subtotal,
        "iva": iva,
        "amortizacion": amortizacion,
        "retencion": retencion,
        "total": total,
    }


def resumen_estimacion(con, estimacion_id) -> dict:
    estimacion = con.execute(
        """
        SELECT e.*, t.nombre AS contratista, p.nombre AS proyecto,
               p.pct_iva, p.amortizacion_pct, p.retencion_pct
          FROM estimacion e
          JOIN proyecto p ON p.id = e.proyecto_id
          LEFT JOIN contrato c ON c.id = e.contrato_id
          LEFT JOIN tercero t ON t.id = c.tercero_id
         WHERE e.id = ?
        """,
        (estimacion_id,),
    ).fetchone()
    if estimacion is None:
        return {}
    info = dict(estimacion)
    info["detalle"] = [
        dict(r)
        for r in con.execute(
            "SELECT * FROM estimacion_detalle WHERE estimacion_id = ? ORDER BY id", (estimacion_id,)
        ).fetchall()
    ]
    info["pagos"] = [
        dict(r)
        for r in con.execute(
            "SELECT * FROM pago WHERE estimacion_id = ? ORDER BY fecha, id", (estimacion_id,)
        ).fetchall()
    ]
    info["pagado"] = money(sum(num(p, "monto") for p in info["pagos"]))
    info["saldo"] = money(num(info, "total") - info["pagado"])
    return info


def estado_de_cuenta(con, proyecto_id) -> dict:
    filas = [
        dict(r)
        for r in con.execute(
            """
            SELECT e.*, t.nombre AS contratista
              FROM estimacion e
              LEFT JOIN contrato c ON c.id = e.contrato_id
              LEFT JOIN tercero t ON t.id = c.tercero_id
             WHERE e.proyecto_id = ?
             ORDER BY COALESCE(e.fecha, ''), e.id
            """,
            (proyecto_id,),
        ).fetchall()
    ]

    for f in filas:
        f["pagado"] = money(
            con.execute(
                "SELECT COALESCE(SUM(monto), 0) FROM pago WHERE estimacion_id = ?", (f["id"],)
            ).fetchone()[0]
        )
        f["saldo"] = money(num(f, "total") - f["pagado"])

    return {
        "estimaciones": filas,
        "total_estimado": money(sum(num(f, "subtotal") for f in filas)),
        "total_pagado": money(sum(f["pagado"] for f in filas)),
        "total_pendiente": money(sum(f["saldo"] for f in filas)),
    }


# =====================================================================
#  Consumos · «Estado de servicios»
# =====================================================================
def estado_de_servicios(con, proyecto_id) -> list[dict]:
    """Insumos realmente consumidos en obra, por tarea y recurso."""
    return [
        dict(r)
        for r in con.execute(
            """
            SELECT c.recurso_id, r.clave, r.descripcion, r.tipo,
                   u.clave AS unidad,
                   t.clave AS tarea_clave, t.nombre AS tarea,
                   SUM(c.cantidad) AS cantidad,
                   SUM(c.costo)    AS importe
              FROM consumo c
              JOIN recurso r ON r.id = c.recurso_id
              LEFT JOIN unidad u ON u.id = r.unidad_id
              LEFT JOIN tarea  t ON t.id = c.tarea_id
             WHERE c.proyecto_id = ?
             GROUP BY c.recurso_id, c.tarea_id
             ORDER BY r.clave
            """,
            (proyecto_id,),
        ).fetchall()
    ]


def costo_real_insumos(con, proyecto_id) -> float:
    return money(
        con.execute(
            "SELECT COALESCE(SUM(costo), 0) FROM consumo WHERE proyecto_id = ?", (proyecto_id,)
        ).fetchone()[0]
    )


def requisiciones(con, proyecto_id) -> list[dict]:
    return [
        dict(r)
        for r in con.execute(
            """
            SELECT q.*,
                   (SELECT COUNT(*) FROM requisicion_detalle d WHERE d.requisicion_id = q.id)
                     AS renglones,
                   (SELECT COALESCE(SUM(d.cantidad), 0) FROM requisicion_detalle d
                     WHERE d.requisicion_id = q.id) AS cantidad_total
              FROM requisicion q
             WHERE q.proyecto_id = ?
             ORDER BY COALESCE(q.fecha, ''), q.id
            """,
            (proyecto_id,),
        ).fetchall()
    ]
