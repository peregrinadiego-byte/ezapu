"""Planeación: estructura de trabajos y programa de obra (Gantt)."""
from __future__ import annotations

import datetime as _dt

from .trees import build_tree, flatten, rollup
from .util import get, num, parse_date, qty


def estructura_trabajos(con, proyecto_id) -> list[dict]:
    """Árbol de tareas con importes y avance ponderado."""
    tareas = [dict(t) for t in con.execute(
        "SELECT * FROM tarea WHERE proyecto_id = ? ORDER BY orden, clave, id", (proyecto_id,)
    ).fetchall()]

    importes = importe_por_tarea(con, proyecto_id)
    raices, nodos = build_tree(
        tareas, sort_key=lambda n: (num(n, "orden"), str(n.get("clave") or ""))
    )

    for t in nodos.values():
        t["importe"] = importes.get(t["id"], 0.0)
        t["avance_pct"] = num(t, "avance")
        t["importe_ganado"] = t["importe"] * t["avance_pct"] / 100.0

    rollup([n for n in raices], "importe", "importe_total")
    return list(flatten(raices))


def importe_por_tarea(con, proyecto_id) -> dict:
    """Reparte el importe de cada partida entre sus tareas según el peso."""
    filas = con.execute(
        """
        SELECT c.partida_id, COALESCE(SUM(c.importe), 0) AS importe
          FROM concepto c WHERE c.proyecto_id = ?
         GROUP BY c.partida_id
        """,
        (proyecto_id,),
    ).fetchall()
    por_partida = {r["partida_id"]: num(r, "importe") for r in filas}

    tareas = con.execute("SELECT * FROM tarea WHERE proyecto_id = ?", (proyecto_id,)).fetchall()
    agrupadas: dict = {}
    for t in tareas:
        agrupadas.setdefault(get(t, "partida_id", None), []).append(t)

    resultado: dict = {}
    for partida_id, grupo in agrupadas.items():
        total_peso = sum((num(t, "peso", 1) or 1) for t in grupo)
        importe = por_partida.get(partida_id, 0.0)
        for t in grupo:
            resultado[t["id"]] = importe * ((num(t, "peso", 1) or 1) / total_peso)
    return resultado


def gantt(con, proyecto_id) -> dict:
    """Datos para dibujar la barra de cada tarea con CSS (offset/duración en %)."""
    tareas = [
        dict(t)
        for t in con.execute(
            """
            SELECT t.*, p.nombre AS partida
              FROM tarea t LEFT JOIN partida p ON p.id = t.partida_id
             WHERE t.proyecto_id = ? ORDER BY t.inicio, t.orden, t.clave
            """,
            (proyecto_id,),
        ).fetchall()
    ]

    fechas = []
    for t in tareas:
        ini, fin = parse_date(get(t, "inicio")), parse_date(get(t, "fin"))
        if ini:
            fechas.append(ini)
        if fin:
            fechas.append(fin)
    if not fechas:
        return {"inicio": None, "fin": None, "dias": 0, "filas": [], "meses": []}

    inicio, fin = min(fechas), max(fechas)
    if fin <= inicio:
        fin = inicio + _dt.timedelta(days=1)
    total_dias = (fin - inicio).days + 1

    filas = []
    for t in tareas:
        ini = parse_date(get(t, "inicio")) or inicio
        fin_t = parse_date(get(t, "fin")) or ini
        offset = max(0, (ini - inicio).days)
        duracion = max(1, (fin_t - ini).days + 1)
        t["offset_pct"] = round(offset / total_dias * 100, 4)
        t["ancho_pct"] = round(duracion / total_dias * 100, 4)
        t["inicio_txt"] = ini.isoformat()
        t["fin_txt"] = fin_t.isoformat()
        if get(t, "duracion"):
            t["dias"] = num(t, "duracion")
        else:
            t["dias"] = duracion
            con.execute("UPDATE tarea SET duracion = ? WHERE id = ?", (duracion, t["id"]))
        filas.append(t)
    con.commit()

    meses = []
    cursor = _dt.date(inicio.year, inicio.month, 1)
    while cursor <= fin:
        offset = (max(cursor, inicio) - inicio).days
        ancho = (
            (_dt.date(cursor.year + (cursor.month == 12), (cursor.month % 12) + 1, 1) - max(cursor, inicio))
            .days
        )
        meses.append(
            {
                "etiqueta": cursor.strftime("%b %Y"),
                "offset_pct": round(offset / total_dias * 100, 4),
                "ancho_pct": round(min(ancho, total_dias) / total_dias * 100, 4),
            }
        )
        cursor = _dt.date(cursor.year + (cursor.month == 12), (cursor.month % 12) + 1, 1)

    return {
        "inicio": inicio.isoformat(),
        "fin": fin.isoformat(),
        "dias": total_dias,
        "filas": filas,
        "meses": meses,
    }


def avance_ponderado(con, proyecto_id) -> float:
    """Avance físico de la obra ponderado por importe."""
    importes = importe_por_tarea(con, proyecto_id)
    total = sum(importes.values())
    if not total:
        return 0.0
    ganado = 0.0
    for t in con.execute("SELECT * FROM tarea WHERE proyecto_id = ?", (proyecto_id,)).fetchall():
        ganado += importes.get(t["id"], 0.0) * num(t, "avance") / 100.0
    return qty(ganado / total * 100.0)
