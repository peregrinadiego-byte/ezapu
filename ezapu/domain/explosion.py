"""Explosión de insumos: abre el presupuesto hasta sus insumos básicos."""
from __future__ import annotations

from .costos import costo_recurso
from .util import TIPOS_BASICOS, get, num, qty


def explosion_matriz(con, matriz_id, factor=1.0, acumulado=None, _pila=None) -> dict:
    """Acumula cantidades por insumo básico para una matriz.

    Los recursos de tipo ``auxiliar`` se abren hacia su propia matriz.
    """
    acumulado = {} if acumulado is None else acumulado
    _pila = set(_pila or ())
    if matriz_id in _pila:
        return acumulado
    _pila.add(matriz_id)

    for d in con.execute(
        "SELECT * FROM matriz_detalle WHERE matriz_id = ? ORDER BY orden, id", (matriz_id,)
    ).fetchall():
        cantidad = num(d, "cantidad") * float(factor or 0)
        sub = get(d, "submatriz_id", None)
        if sub:
            explosion_matriz(con, sub, cantidad, acumulado, _pila)
            continue

        rid = get(d, "recurso_id", None)
        if not rid:
            continue
        rec = con.execute("SELECT * FROM recurso WHERE id = ?", (rid,)).fetchone()
        if rec is None:
            continue
        tipo = get(rec, "tipo", "material")
        if tipo == "auxiliar" and get(rec, "matriz_id", None):
            explosion_matriz(con, get(rec, "matriz_id"), cantidad, acumulado, _pila)
        else:
            acumulado[rid] = acumulado.get(rid, 0.0) + cantidad

    _pila.discard(matriz_id)
    return acumulado


def explosion_proyecto(con, proyecto_id, solo_partida=None) -> list[dict]:
    """Explosión completa del presupuesto, ordenada por tipo y clave."""
    acumulado: dict[int, float] = {}

    sql = """
        SELECT c.*, m.clave AS matriz_clave
          FROM concepto c
          LEFT JOIN matriz m ON m.id = c.matriz_id
         WHERE c.proyecto_id = ?
    """
    args: list = [proyecto_id]
    if solo_partida:
        sql += " AND c.partida_id = ?"
        args.append(solo_partida)

    for concepto in con.execute(sql, args).fetchall():
        mid = get(concepto, "matriz_id", None)
        if not mid:
            continue
        explosion_matriz(con, mid, num(concepto, "cantidad"), acumulado)

    filas = []
    for rid, cantidad in acumulado.items():
        rec = con.execute(
            """
            SELECT r.*, u.clave AS unidad, u.nombre AS unidad_nombre,
                   f.nombre AS familia, g.nombre AS grupo
              FROM recurso r
              LEFT JOIN unidad  u ON u.id = r.unidad_id
              LEFT JOIN familia f ON f.id = r.familia_id
              LEFT JOIN grupo   g ON g.id = r.grupo_id
             WHERE r.id = ?
            """,
            (rid,),
        ).fetchone()
        if rec is None:
            continue
        costo = costo_recurso(con, rid)
        filas.append(
            {
                "recurso_id": rid,
                "clave": get(rec, "clave", ""),
                "descripcion": get(rec, "descripcion", ""),
                "tipo": get(rec, "tipo", "material"),
                "unidad": get(rec, "unidad", ""),
                "familia": get(rec, "familia", ""),
                "grupo": get(rec, "grupo", ""),
                "cantidad": qty(cantidad),
                "costo_unitario": costo,
                "importe": qty(cantidad * costo),
            }
        )

    orden = {t: i for i, t in enumerate(TIPOS_BASICOS)}
    filas.sort(key=lambda f: (orden.get(f["tipo"], 99), f["clave"]))
    return filas


def resumen_por_tipo(filas: list[dict]) -> list[dict]:
    """Subtotales de la explosión agrupados por tipo de insumo."""
    acc: dict[str, dict] = {}
    for f in filas:
        item = acc.setdefault(f["tipo"], {"tipo": f["tipo"], "importe": 0.0, "partidas": 0})
        item["importe"] += f["importe"]
        item["partidas"] += 1
    return sorted(acc.values(), key=lambda i: -i["importe"])


def programa_suministros(con, proyecto_id) -> list[dict]:
    """Reparte la explosión de insumos entre las tareas de la obra.

    Un concepto pertenece a una partida; las tareas ligadas a esa partida
    absorben el insumo en proporción a su ``peso``. Los insumos de conceptos
    sin partida se agrupan en un renglón «sin asignar».
    """
    explosiones: dict[tuple, float] = {}        # (tarea_id, recurso_id) -> cantidad
    tareas_por_partida: dict = {}
    for t in con.execute("SELECT * FROM tarea WHERE proyecto_id = ?", (proyecto_id,)).fetchall():
        tareas_por_partida.setdefault(get(t, "partida_id", None), []).append(t)

    sin_asignar: dict[int, float] = {}

    for concepto in con.execute(
        "SELECT * FROM concepto WHERE proyecto_id = ?", (proyecto_id,)
    ).fetchall():
        mid = get(concepto, "matriz_id", None)
        if not mid:
            continue
        cantidades = explosion_matriz(con, mid, num(concepto, "cantidad"))
        tareas = tareas_por_partida.get(get(concepto, "partida_id", None), [])
        total_peso = sum((num(t, "peso", 1) or 1) for t in tareas) if tareas else 0
        for rid, cantidad in cantidades.items():
            if tareas:
                for t in tareas:
                    proporcion = (num(t, "peso", 1) or 1) / total_peso
                    clave = (t["id"], rid)
                    explosiones[clave] = explosiones.get(clave, 0.0) + cantidad * proporcion
            else:
                sin_asignar[rid] = sin_asignar.get(rid, 0.0) + cantidad

    filas = []

    def agregar(tarea_row, rid, cantidad):
        rec = con.execute(
            """
            SELECT r.clave, r.descripcion, r.tipo, r.costo_base, r.merma_pct,
                   u.clave AS unidad
              FROM recurso r LEFT JOIN unidad u ON u.id = r.unidad_id
             WHERE r.id = ?
            """,
            (rid,),
        ).fetchone()
        if rec is None:
            return
        costo = costo_recurso(con, rid)
        filas.append(
            {
                "tarea_id": get(tarea_row, "id", None) if tarea_row else None,
                "tarea": (
                    (get(tarea_row, "clave", "") + " " + get(tarea_row, "nombre", "")).strip()
                    if tarea_row
                    else "— sin asignar —"
                ),
                "inicio": get(tarea_row, "inicio", "") if tarea_row else "",
                "fin": get(tarea_row, "fin", "") if tarea_row else "",
                "recurso_id": rid,
                "clave": get(rec, "clave", ""),
                "descripcion": get(rec, "descripcion", ""),
                "tipo": get(rec, "tipo", ""),
                "unidad": get(rec, "unidad", ""),
                "cantidad": qty(cantidad),
                "costo_unitario": costo,
                "importe": qty(cantidad * costo),
            }
        )

    for (tarea_id, rid), cantidad in explosiones.items():
        tarea = con.execute("SELECT * FROM tarea WHERE id = ?", (tarea_id,)).fetchone()
        agregar(tarea, rid, cantidad)

    for rid, cantidad in sin_asignar.items():
        agregar(None, rid, cantidad)

    filas.sort(key=lambda f: (f["inicio"] or "9999", f["clave"]))
    return filas
