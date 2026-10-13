"""Costos básicos, costos horarios de equipo, matrices y precios unitarios.

Equivalente al núcleo de cálculo de OPUS M1:

* **Costo básico de mano de obra** → salario real = ``salario base × (1 + FSR)``
* **Costo horario de equipo/herramienta** → fórmula clásica de obra pública
  (depreciación, inversión, seguros, mantenimiento, reparaciones, combustible,
  lubricantes, llantas, operador y otros)
* **Matriz de precio unitario** → sumatoria de ``cantidad × costo`` de cada
  componente, donde un componente puede ser un insumo o una matriz anidada
  (auxiliar).
"""
from __future__ import annotations

from .util import get, num, qty

# --------------------------------------------------------------------------
#  Conceptos de costo horario: etiquetas para desglose y reportes
# --------------------------------------------------------------------------
ETIQUETAS_COSTO_HORARIO = {
    "depreciacion": "Depreciación",
    "inversion": "Inversión (interés)",
    "seguros": "Seguros",
    "mantenimiento": "Mantenimiento",
    "reparaciones": "Reparaciones",
    "combustible": "Combustible",
    "lubricantes": "Lubricantes",
    "llantas": "Llantas",
    "operador": "Operador",
    "otros": "Otros",
}


# =====================================================================
#  Mano de obra
# =====================================================================
def costo_basico_mano_obra(salario_base, factor_prestaciones) -> float:
    """Salario real por turno."""
    return qty(float(salario_base or 0) * (1 + float(factor_prestaciones or 0) / 100.0))


# =====================================================================
#  Costo horario de equipo y herramienta
# =====================================================================
def detalle_costo_horario(con, fila) -> dict:
    """Desglose del costo horario por concepto, más el total.

    ``fila`` es un renglón de la tabla ``costo_horario``.
    """
    vm = num(fila, "valor_maquina")
    vr = num(fila, "valor_rescate")
    vu = num(fila, "vida_util")
    horas_anuales = num(fila, "horas_anuales")
    if horas_anuales <= 0:
        horas_anuales = 2000.0  # valor por omisión razonable

    partes: dict[str, float] = {}

    partes["depreciacion"] = (vm - vr) / vu if vu > 0 else 0.0

    base_inversion = (vm + vr) / 2.0
    partes["inversion"] = base_inversion * (num(fila, "tasa_interes") / 100.0) / horas_anuales
    partes["seguros"] = base_inversion * (num(fila, "tasa_seguro") / 100.0) / horas_anuales

    partes["mantenimiento"] = (num(fila, "coef_mantenimiento") * vm) / vu if vu > 0 else 0.0
    partes["reparaciones"] = (num(fila, "coef_reparaciones") * vm) / vu if vu > 0 else 0.0

    combustible = num(fila, "consumo_combustible") * num(fila, "precio_combustible")
    partes["combustible"] = combustible
    partes["lubricantes"] = combustible * num(fila, "pct_lubricantes") / 100.0

    vida_llantas = num(fila, "vida_llantas")
    partes["llantas"] = num(fila, "costo_llantas") / vida_llantas if vida_llantas > 0 else 0.0

    operador = 0.0
    if num(fila, "incluye_operador", 1):
        rid = get(fila, "recurso_operador_id", None)
        if rid:
            mo = con.execute("SELECT * FROM mano_obra WHERE recurso_id = ?", (rid,)).fetchone()
            if mo:
                horas = num(mo, "horas_turno", 8) or 8
                operador = num(mo, "costo_basico") / horas
        if not operador:
            operador = num(fila, "costo_operador")
    partes["operador"] = operador

    partes["otros"] = num(fila, "costo_otros")

    for clave in partes:
        partes[clave] = qty(partes[clave])

    total = qty(sum(partes.values()))
    if num(fila, "manual") and num(fila, "costo_total"):
        total = qty(num(fila, "costo_total"))

    partes["total"] = total
    return partes


# =====================================================================
#  Resolución de costos (recursiva, detecta ciclos)
# =====================================================================
class CicloError(ValueError):
    """Una matriz se contiene a sí misma de forma circular."""


def costo_recurso(con, recurso_id, _pila=None) -> float:
    """Costo unitario vigente de un insumo.

    * ``material``/``subcontrato``/``flete`` → costo base (+ merma)
    * ``mano_obra``  → salario real por turno
    * ``equipo``/``herramienta`` → costo horario total
    * ``auxiliar``   → costo de la matriz que lo respalda
    """
    fila = con.execute("SELECT * FROM recurso WHERE id = ?", (recurso_id,)).fetchone()
    if fila is None:
        return 0.0

    tipo = get(fila, "tipo", "material")

    if tipo == "mano_obra":
        mo = con.execute("SELECT * FROM mano_obra WHERE recurso_id = ?", (recurso_id,)).fetchone()
        if mo is not None:
            calculado = num(mo, "costo_basico")
            if not calculado:
                calculado = costo_basico_mano_obra(num(mo, "salario_base"), num(mo, "factor_prestaciones"))
            return qty(calculado)

    if tipo in ("equipo", "herramienta"):
        ch = con.execute("SELECT * FROM costo_horario WHERE recurso_id = ?", (recurso_id,)).fetchone()
        if ch is not None:
            return qty(detalle_costo_horario(con, ch)["total"])

    if tipo == "auxiliar":
        mid = get(fila, "matriz_id", None)
        if mid:
            return costo_matriz(con, mid, _pila)

    base = num(fila, "costo_base")
    merma = num(fila, "merma_pct")
    return qty(base * (1 + merma / 100.0))


def costo_matriz(con, matriz_id, _pila=None) -> float:
    """Costo directo de una matriz (sumatoria recursiva de sus componentes)."""
    pila = set(_pila or ())
    if matriz_id in pila:
        raise CicloError(f"La matriz {matriz_id} forma un ciclo con una submatriz suya.")
    pila.add(matriz_id)

    total = 0.0
    filas = con.execute(
        "SELECT * FROM matriz_detalle WHERE matriz_id = ? ORDER BY orden, id", (matriz_id,)
    ).fetchall()
    for d in filas:
        cantidad = num(d, "cantidad")
        sub = get(d, "submatriz_id", None)
        if sub:
            componente = costo_matriz(con, sub, pila)
        else:
            componente = costo_recurso(con, get(d, "recurso_id", None))
        total += cantidad * componente

    pila.discard(matriz_id)
    return qty(total)


def precio_matriz(con, matriz_id) -> float:
    """Precio unitario de la matriz = costo directo + indirectos propios."""
    fila = con.execute(
        "SELECT costo_directo, costo_indirecto_pct FROM matriz WHERE id = ?", (matriz_id,)
    ).fetchone()
    if fila is None:
        return 0.0
    cd = costo_matriz(con, matriz_id)
    return qty(cd * (1 + num(fila, "costo_indirecto_pct") / 100.0))


# =====================================================================
#  Recálculo en lote (se ejecuta al guardar catálogos, matrices, etc.)
# =====================================================================
def recalcular_todo(con) -> dict:
    """Recalcula salarios reales, costos horarios, matrices y precios unitarios.

    Devuelve un resumen de lo actualizado.
    """
    resumen = {"mano_obra": 0, "costo_horario": 0, "recursos_auxiliares": 0,
               "matrices": 0, "conceptos": 0}

    # 1 · salarios reales
    for mo in con.execute("SELECT * FROM mano_obra").fetchall():
        valor = costo_basico_mano_obra(num(mo, "salario_base"), num(mo, "factor_prestaciones"))
        con.execute("UPDATE mano_obra SET costo_basico = ? WHERE id = ?", (valor, mo["id"]))
        resumen["mano_obra"] += 1

    # 2 · costos horarios
    for ch in con.execute("SELECT * FROM costo_horario").fetchall():
        total = detalle_costo_horario(con, ch)["total"]
        con.execute("UPDATE costo_horario SET costo_total = ? WHERE id = ?", (total, ch["id"]))
        resumen["costo_horario"] += 1

    # 3 · recursos auxiliares (su costo es el de la matriz que los respalda)
    for rec in con.execute(
        "SELECT * FROM recurso WHERE tipo = 'auxiliar' AND matriz_id IS NOT NULL"
    ).fetchall():
        con.execute(
            "UPDATE recurso SET costo_base = ? WHERE id = ?",
            (precio_matriz(con, rec["matriz_id"]), rec["id"]),
        )
        resumen["recursos_auxiliares"] += 1

    # 4 · matrices
    for mat in con.execute("SELECT * FROM matriz").fetchall():
        cd = costo_matriz(con, mat["id"])
        con.execute("UPDATE matriz SET costo_directo = ? WHERE id = ?", (cd, mat["id"]))
        resumen["matrices"] += 1

    # 5 · precios unitarios de los conceptos del presupuesto
    for concepto in con.execute("SELECT * FROM concepto").fetchall():
        mid = get(concepto, "matriz_id", None)
        if mid:
            pu = precio_matriz(con, mid)
            con.execute("UPDATE concepto SET pu = ? WHERE id = ?", (pu, concepto["id"]))
        con.execute(
            "UPDATE concepto SET importe = ROUND(cantidad * pu, 2) WHERE id = ?",
            (concepto["id"],),
        )
        resumen["conceptos"] += 1

    con.commit()
    return resumen


def detalle_matriz(con, matriz_id) -> list[dict]:
    """Filas de la matriz con el costo calculado de cada componente."""
    filas = []
    for d in con.execute(
        """
        SELECT d.*,
               COALESCE(r.clave, m2.clave)       AS clave,
               COALESCE(r.descripcion, m2.descripcion) AS descripcion,
               COALESCE(u.clave, u2.clave)       AS unidad
          FROM matriz_detalle d
          LEFT JOIN recurso r ON r.id = d.recurso_id
          LEFT JOIN matriz  m2 ON m2.id = d.submatriz_id
          LEFT JOIN unidad  u  ON u.id = r.unidad_id
          LEFT JOIN unidad  u2 ON u2.id = m2.unidad_id
         WHERE d.matriz_id = ?
         ORDER BY d.orden, d.id
        """,
        (matriz_id,),
    ).fetchall():
        item = dict(d)
        if item.get("submatriz_id"):
            item["costo_unitario"] = costo_matriz(con, item["submatriz_id"])
            item["es_auxiliar"] = True
        else:
            item["costo_unitario"] = costo_recurso(con, item.get("recurso_id"))
            item["es_auxiliar"] = False
        item["importe"] = qty(num(item, "cantidad") * item["costo_unitario"])
        filas.append(item)
    return filas
