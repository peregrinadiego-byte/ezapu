"""Construcción de estructuras jerárquicas (partidas, tareas, centros de costo)."""
from __future__ import annotations

from .util import num


def build_tree(rows, id_key="id", parent_key="parent_id", children_key="hijos", sort_key=None):
    """Convierte una lista plana en árbol.

    Devuelve ``(raices, indice)`` donde ``indice`` mapea id → nodo.
    """
    nodos: dict = {}
    for fila in rows:
        nodo = dict(fila)
        nodo[children_key] = []
        nodos[nodo[id_key]] = nodo

    raices = []
    for nodo in nodos.values():
        padre = nodo.get(parent_key)
        if padre in nodos and padre != nodo[id_key]:
            nodos[padre][children_key].append(nodo)
        else:
            raices.append(nodo)

    orden = sort_key or (lambda n: (num(n, "orden"), str(n.get("clave") or "")))

    def _sort(items):
        items.sort(key=orden)
        for item in items:
            _sort(item[children_key])

    _sort(raices)
    return raices, nodos


def rollup(nodos, total_key="importe", out_key="total", children_key="hijos"):
    """Suma recursiva de un campo hacia los nodos padre."""
    acumulado = 0.0
    for nodo in nodos:
        propio = num(nodo, total_key)
        hijos = rollup(nodo[children_key], total_key, out_key, children_key)
        nodo[out_key] = propio + hijos
        acumulado += nodo[out_key]
    return acumulado


def flatten(nodos, depth=0, children_key="hijos"):
    """Recorre el árbol en profundidad, anotando ``nivel_calc``."""
    for nodo in nodos:
        nodo["nivel_calc"] = depth
        yield nodo
        yield from flatten(nodo[children_key], depth + 1, children_key)
