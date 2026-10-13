"""Administración de proyectos: valor ganado, curva S y desviaciones."""
from __future__ import annotations

import datetime as _dt

from .avance import costo_real_insumos
from .planeacion import importe_por_tarea
from .presupuesto import totales
from .util import get, money, num, parse_date


def _fraccion_planeada(tarea, fecha: _dt.date) -> float:
    inicio = parse_date(get(tarea, "inicio"))
    fin = parse_date(get(tarea, "fin"))
    if not inicio or not fin:
        return 1.0 if get(tarea, "estado") == "terminado" else 0.0
    if fecha <= inicio:
        return 0.0
    if fecha >= fin:
        return 1.0
    total = (fin - inicio).days or 1
    return (fecha - inicio).days / total


def valor_ganado(con, proyecto_id, hasta=None, puntos=24) -> dict:
    """Indicadores EVM (PV, EV, AC, SPI, CPI) y serie de curva S."""
    proyecto = con.execute("SELECT * FROM proyecto WHERE id = ?", (proyecto_id,)).fetchone()
    if proyecto is None:
        return {}

    resumen = totales(con, proyecto_id)
    bac = resumen.get("subtotal", 0.0)      # presupuesto base (sin IVA)
    if not bac:
        return {"bac": 0.0, "sin_presupuesto": True, "serie": []}

    tareas = [dict(t) for t in con.execute(
        "SELECT * FROM tarea WHERE proyecto_id = ?", (proyecto_id,)
    ).fetchall()]
    importes = importe_por_tarea(con, proyecto_id)

    fechas = [d for d in (parse_date(get(t, "inicio")) for t in tareas) if d] + [
        d for d in (parse_date(get(t, "fin")) for t in tareas) if d
    ]
    hoy = hasta or _dt.date.today()
    if fechas:
        inicio, fin = min(fechas), max(fechas)
    else:
        inicio = parse_date(get(proyecto, "fecha_apertura")) or hoy
        fin = hoy

    ev = money(sum(importes.get(t["id"], 0.0) * num(t, "avance") / 100.0 for t in tareas))
    ac = costo_real_insumos(con, proyecto_id)

    def pv_en(fecha):
        return money(sum(importes.get(t["id"], 0.0) * _fraccion_planeada(t, fecha) for t in tareas))

    pv = pv_en(hoy)

    # Serie para la curva S
    consumos = [
        (parse_date(get(c, "fecha")), num(c, "costo"))
        for c in con.execute(
            "SELECT fecha, costo FROM consumo WHERE proyecto_id = ?", (proyecto_id,)
        ).fetchall()
    ]

    serie = []
    if fin > inicio:
        paso = max(1, ((fin - inicio).days + 1) // max(1, puntos))
        cursor = inicio
        while cursor <= fin:
            ac_cursor = money(
                sum(monto for fecha, monto in consumos if fecha and fecha <= cursor)
            )
            serie.append(
                {
                    "fecha": cursor.isoformat(),
                    "etiqueta": cursor.strftime("%b %y"),
                    "pv": pv_en(cursor),
                    "ev": money(
                        sum(
                            importes.get(t["id"], 0.0)
                            * num(t, "avance")
                            / 100.0
                            * min(1.0, _fraccion_planeada(t, cursor) or 1.0)
                            for t in tareas
                        )
                    ),
                    "ac": ac_cursor,
                }
            )
            cursor += _dt.timedelta(days=paso)

    spi = (ev / pv) if pv else 0.0
    cpi = (ev / ac) if ac else 0.0
    eac = (bac / cpi) if cpi else bac

    return {
        "bac": money(bac),
        "pv": pv,
        "ev": ev,
        "ac": ac,
        "sv": money(ev - pv),
        "cv": money(ev - ac),
        "spi": round(spi, 4),
        "cpi": round(cpi, 4),
        "eac": money(eac),
        "etc": money(max(0.0, eac - ac)),
        "vac": money(bac - eac),
        "avance_fisico": round((ev / bac * 100.0) if bac else 0.0, 2),
        "avance_planeado": round((pv / bac * 100.0) if bac else 0.0, 2),
        "inicio": inicio.isoformat(),
        "fin": fin.isoformat(),
        "serie": serie,
        "sin_presupuesto": False,
    }


def estructura_costos(con, proyecto_id) -> list[dict]:
    """Árbol de centros de costo con su presupuesto."""
    from .trees import build_tree, flatten, rollup

    filas = [
        dict(r)
        for r in con.execute(
            "SELECT * FROM centro_costo WHERE proyecto_id = ? ORDER BY clave, id", (proyecto_id,)
        ).fetchall()
    ]
    for f in filas:
        f.setdefault("orden", 0)
    raices, _ = build_tree(filas, sort_key=lambda n: (num(n, "orden"), str(n.get("clave") or "")))
    for n in raices:
        n["presupuesto"] = num(n, "presupuesto")
    rollup(raices, "presupuesto", "presupuesto_total")
    return list(flatten(raices))


def estructura_organizacion(con, proyecto_id) -> list[dict]:
    from .trees import build_tree, flatten

    filas = [dict(r) for r in con.execute(
        "SELECT * FROM organizacion WHERE proyecto_id = ? ORDER BY clave, id", (proyecto_id,)
    ).fetchall()]
    for f in filas:
        f.setdefault("orden", 0)
    raices, _ = build_tree(filas, sort_key=lambda n: (num(n, "orden"), str(n.get("clave") or "")))
    return list(flatten(raices))
