"""Datos de ejemplo: obra «OBRA DEMO» con catálogos, matrices y avance.

Se ejecuta con ``python -m ezapu.seed`` o al inicializar la base con
``flask --app run init-db``.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

from .domain.costos import recalcular_todo
from .domain.util import UNIDADES_BASE

# --- calendario del ejemplo -------------------------------------------------
# La obra de demostración se sitúa alrededor de la fecha en que se ejecuta la
# semilla, para que el Gantt, las estimaciones y la curva S tengan sentido.
HOY = _dt.date.today()
INICIO = HOY - _dt.timedelta(days=88)     # ~55 % del programa de 161 días


def d(dias: int) -> str:
    """Fecha ISO a ``dias`` del inicio de la obra."""
    return (INICIO + _dt.timedelta(days=dias)).isoformat()


def mes(desplazamiento: int, formato: str = "%Y-%m") -> str:
    """Etiqueta del mes desplazado ``desplazamiento`` meses desde el inicio."""
    total = INICIO.month - 1 + desplazamiento
    return f"{INICIO.year + total // 12}-{total % 12 + 1:02d}" if formato == "%Y-%m" else ""


def fin_de_mes(desplazamiento: int) -> str:
    """Último día del mes desplazado."""
    total = INICIO.month - 1 + desplazamiento + 1
    primero_siguiente = _dt.date(INICIO.year + total // 12, total % 12 + 1, 1)
    return (primero_siguiente - _dt.timedelta(days=1)).isoformat()


# ------------------------------------------------------------------ helpers --
def ins(con, table: str, **datos) -> int:
    cols = list(datos)
    cur = con.execute(
        "INSERT INTO {} ({}) VALUES ({})".format(
            table, ", ".join(cols), ", ".join("?" * len(cols))
        ),
        [datos[c] for c in cols],
    )
    return cur.lastrowid


def _wipe(con) -> None:
    con.execute("PRAGMA foreign_keys = OFF")
    tablas = [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    for tabla in tablas:
        con.execute(f"DELETE FROM {tabla}")
    con.execute("PRAGMA foreign_keys = ON")
    con.commit()


# --------------------------------------------------------------------- seed --
def seed(con, reset: bool = False) -> bool:
    """Carga el juego de datos de ejemplo. Devuelve True si insertó algo."""
    if reset:
        _wipe(con)

    if con.execute("SELECT COUNT(*) FROM empresa").fetchone()[0]:
        return False

    # ---- empresa -----------------------------------------------------------
    ins(
        con,
        "empresa",
        nombre="Constructora del Pacífico, S.A. de C.V.",
        rfc="CPA950101H45",
        direccion="Av. Reforma 1234, Col. Centro, Culiacán, Sinaloa",
        telefono="667 123 4567",
        email="licitaciones@constructora-pacifico.mx",
        moneda="MXN",
        iva_pct=16.0,
    )

    # ---- unidades ----------------------------------------------------------
    unidades = {}
    for clave, nombre, tipo in UNIDADES_BASE:
        unidades[clave] = ins(con, "unidad", clave=clave, nombre=nombre, tipo=tipo)

    # ---- familias y grupos -------------------------------------------------
    fam = {}
    for clave, nombre in [
        ("MAT", "Materiales"),
        ("MO", "Mano de obra"),
        ("EQP", "Equipo y herramienta"),
        ("SUB", "Subcontratos"),
        ("FLE", "Fletes"),
        ("AUX", "Auxiliares"),
    ]:
        fam[clave] = ins(con, "familia", clave=clave, nombre=nombre, tipo="insumo")

    grupos = {}
    for clave, nombre, familia in [
        ("CEM", "Cementantes", "MAT"),
        ("AGR", "Agregados", "MAT"),
        ("ACE", "Aceros", "MAT"),
        ("MAM", "Mampostería", "MAT"),
        ("ACA", "Acabados", "MAT"),
        ("BAS", "Básicos", "MO"),
        ("MAQ", "Maquinaria", "EQP"),
        ("HERR", "Herramienta", "EQP"),
    ]:
        grupos[clave] = ins(con, "grupo", clave=clave, nombre=nombre, familia_id=fam[familia])

    # ---- terceros ----------------------------------------------------------
    ter = {}
    for clave, nombre, tipo, extra in [
        ("CLI-01", "Constructora del Pacífico, S.A. de C.V.", "cliente",
         {"contacto": "Ing. Laura Medina", "email": "lmedina@constructora-pacifico.mx"}),
        ("PRO-01", "Cementos Mexicanos, S.A.", "proveedor", {"telefono": "667 200 1010"}),
        ("PRO-02", "Aceros del Norte, S.A. de C.V.", "proveedor", {"telefono": "667 200 2020"}),
        ("PRO-03", "Materiales Rivera", "proveedor", {"telefono": "667 200 3030"}),
        ("CON-01", "Excavaciones Hernández", "contratista",
         {"especialidad": "Movimiento de tierras"}),
        ("CON-02", "Transportes Gutiérrez", "contratista", {"especialidad": "Fletes y acarreos"}),
        ("CON-03", "Renta de Maquinaria del Valle", "contratista",
         {"especialidad": "Renta de equipo"}),
    ]:
        ter[clave] = ins(con, "tercero", clave=clave, nombre=nombre, tipo=tipo, **extra)

    # ---- recursos básicos --------------------------------------------------
    rec = {}

    def recurso(clave, descripcion, tipo, unidad, familia, grupo, costo, **extra):
        rec[clave] = ins(
            con,
            "recurso",
            clave=clave,
            descripcion=descripcion,
            tipo=tipo,
            unidad_id=unidades[unidad],
            familia_id=fam[familia],
            grupo_id=grupos.get(grupo, grupos.get("BAS")),
            costo_base=costo,
            proveedor_id=extra.pop("proveedor_id", None),
            merma_pct=extra.pop("merma_pct", 0),
            notas=extra.pop("notas", None),
        )
        return rec[clave]

    materiales = [
        # clave, descripción, unidad, costo, merma %, proveedor, grupo
        ("M-01", "Cemento Portland CPC 30R", "kg", 3.20, 2.0, "PRO-01", "CEM"),
        ("M-02", "Arena cribada puesta en obra", "m3", 320.00, 0, "PRO-03", "AGR"),
        ("M-03", 'Grava triturada de 3/4"', "m3", 380.00, 0, "PRO-03", "AGR"),
        ("M-04", "Concreto premezclado f'c=200 kg/cm²", "m3", 2400.00, 0, "PRO-01", "CEM"),
        ("M-05", "Concreto premezclado f'c=250 kg/cm²", "m3", 2650.00, 0, "PRO-01", "CEM"),
        ("M-06", 'Varilla corrugada 3/8"', "kg", 22.50, 5.0, "PRO-02", "ACE"),
        ("M-07", 'Varilla corrugada 1/2"', "kg", 22.00, 5.0, "PRO-02", "ACE"),
        ("M-08", "Alambre recocido #18", "kg", 32.00, 0, "PRO-02", "ACE"),
        ("M-09", "Block de concreto 15x20x40 cm", "pza", 14.50, 3.0, "PRO-03", "MAM"),
        ("M-10", "Agua potable para mezclas", "m3", 45.00, 0, None, "AGR"),
        ("M-11", 'Madera de pino de 3ª en polín 3x3"', "pza", 210.00, 0, "PRO-03", "MAM"),
        ("M-12", 'Clavo de acero 2 1/2"', "kg", 30.00, 0, "PRO-03", "MAM"),
        ("M-13", "Desmoldante para cimbra", "l", 45.00, 0, "PRO-03", "ACA"),
        ("M-14", "Pintura vinílica para interiores", "l", 78.00, 0, "PRO-03", "ACA"),
        ("M-15", "Sellador acrílico para muros", "l", 62.00, 0, "PRO-03", "ACA"),
    ]
    for clave, desc, unidad, costo, merma, prov, grupo in materiales:
        recurso(
            clave, desc, "material", unidad, "MAT", grupo, costo,
            merma_pct=merma, proveedor_id=ter.get(prov) if prov else None,
        )

    mano = [
        ("MO-01", "Peón", 320.00),
        ("MO-02", "Ayudante general", 360.00),
        ("MO-03", "Oficial albañil", 520.00),
        ("MO-04", "Oficial fierrero", 520.00),
        ("MO-05", "Cabo de oficios", 620.00),
        ("MO-06", "Oficial pintor", 480.00),
        ("MO-07", "Operador de maquinaria pesada", 580.00),
    ]
    for clave, desc, salario in mano:
        recurso(clave, desc, "mano_obra", "jorn", "MO", "BAS", 0)
        ins(
            con,
            "mano_obra",
            recurso_id=rec[clave],
            salario_base=salario,
            factor_prestaciones=78.0,
            horas_turno=8.0,
            cuadrilla=None,
        )

    equipos = [
        # clave, desc, VM, VR, vida útil, horas/año, %mat, %rep, l/h, $/l, %lub, llantas, vida llantas, operador, otros
        ("EQ-01", "Revolvedora de concreto de 1 saco", 65000, 6500, 10000, 1200,
         0.60, 0.20, 3.5, 24.50, 15, 0, 0, None, 0),
        ("EQ-02", "Camión de volteo de 7 m³", 1250000, 125000, 12000, 1600,
         0.55, 0.25, 14.0, 24.50, 12, 45000, 2500, "MO-07", 0),
        ("EQ-03", "Retroexcavadora sobre orugas 1.0 m³", 1450000, 145000, 12000, 1600,
         0.60, 0.25, 11.0, 24.50, 12, 38000, 2000, "MO-07", 0),
        ("EQ-04", "Vibrador de concreto de chicote", 18000, 1800, 6000, 1000,
         0.60, 0.25, 1.2, 24.50, 10, 0, 0, None, 0),
        ("EQ-05", "Estación total con tripié", 320000, 32000, 8000, 1000,
         0.40, 0.15, 0, 0, 0, 0, 0, None, 0),
        ("EQ-06", "Bailarina (plancha vibratoria)", 42000, 4200, 5000, 900,
         0.60, 0.25, 1.5, 24.50, 10, 0, 0, None, 0),
    ]
    for (clave, desc, vm, vr, vu, ha, mat, rep, comb, pcomb, club, llantas, vll, oper, otros) in equipos:
        recurso(clave, desc, "equipo", "hr", "EQP", "MAQ", 0)
        ins(
            con,
            "costo_horario",
            recurso_id=rec[clave],
            valor_maquina=vm,
            valor_rescate=vr,
            vida_util=vu,
            horas_anuales=ha,
            tasa_interes=12.0,
            tasa_seguro=3.0,
            coef_mantenimiento=mat,
            coef_reparaciones=rep,
            consumo_combustible=comb,
            precio_combustible=pcomb,
            pct_lubricantes=club,
            costo_llantas=llantas,
            vida_llantas=vll,
            recurso_operador_id=rec.get(oper) if oper else None,
            incluye_operador=1 if oper else 0,
            costo_otros=otros,
            manual=0,
        )

    recurso("HER-01", "Herramienta menor de mano", "herramienta", "hr", "EQP", "HERR", 4.50,
            notas="Cargo por hora de uso de herramienta menor.")

    # ---- matrices auxiliares (auxiliares de costo) -------------------------
    def matriz(clave, descripcion, tipo, unidad, **extra):
        return ins(
            con,
            "matriz",
            clave=clave,
            descripcion=descripcion,
            tipo=tipo,
            unidad_id=unidades.get(unidad),
            proyecto_id=extra.pop("proyecto_id", None),
            costo_indirecto_pct=extra.pop("costo_indirecto_pct", 0),
            notas=extra.pop("notas", None),
        )

    def detalle(matriz_id, cantidad, recurso_clave=None, submatriz_id=None, notas=None):
        ins(
            con,
            "matriz_detalle",
            matriz_id=matriz_id,
            recurso_id=rec.get(recurso_clave) if recurso_clave else None,
            submatriz_id=submatriz_id,
            cantidad=cantidad,
            notas=notas,
        )

    aux_concreto = matriz("AUX-01", "Concreto hecho en obra f'c=200 kg/cm²", "auxiliar", "m3")
    detalle(aux_concreto, 0.350, "M-01")     # cemento (ton → 350 kg)
    detalle(aux_concreto, 0.550, "M-02")     # arena
    detalle(aux_concreto, 0.650, "M-03")     # grava
    detalle(aux_concreto, 0.190, "M-10")     # agua
    detalle(aux_concreto, 0.450, "EQ-01")    # revolvedora
    detalle(aux_concreto, 0.500, "MO-02")    # ayudante
    detalle(aux_concreto, 0.060, "MO-03")    # oficial
    detalle(aux_concreto, 0.400, "HER-01")

    aux_acero = matriz("AUX-02", "Acero de refuerzo habilitado y armado", "auxiliar", "kg")
    detalle(aux_acero, 1.000, "M-06")
    detalle(aux_acero, 0.020, "M-08")
    detalle(aux_acero, 0.020, "MO-04")
    detalle(aux_acero, 0.010, "MO-01")
    detalle(aux_acero, 0.020, "HER-01")

    aux_cimbra = matriz("AUX-03", "Cimbra acabado común (m² de contacto)", "auxiliar", "m2")
    detalle(aux_cimbra, 1.200, "M-11")
    detalle(aux_cimbra, 0.150, "M-12")
    detalle(aux_cimbra, 0.050, "M-13")
    detalle(aux_cimbra, 0.120, "MO-03")
    detalle(aux_cimbra, 0.080, "MO-01")

    aux_mortero = matriz("AUX-04", "Mortero cemento-arena 1:4", "auxiliar", "m3")
    detalle(aux_mortero, 0.420, "M-01")
    detalle(aux_mortero, 1.100, "M-02")
    detalle(aux_mortero, 0.250, "M-10")
    detalle(aux_mortero, 0.400, "EQ-01")
    detalle(aux_mortero, 0.400, "MO-01")

    for clave, desc, unidad, matriz_id in [
        ("A-01", "Concreto hecho en obra f'c=200 kg/cm²", "m3", aux_concreto),
        ("A-02", "Acero de refuerzo habilitado", "kg", aux_acero),
        ("A-03", "Cimbra acabada común", "m2", aux_cimbra),
        ("A-04", "Mortero cemento-arena 1:4", "m3", aux_mortero),
    ]:
        rec[clave] = ins(
            con,
            "recurso",
            clave=clave,
            descripcion=desc,
            tipo="auxiliar",
            unidad_id=unidades[unidad],
            familia_id=fam["AUX"],
            costo_base=0,
            matriz_id=matriz_id,
        )

    # ---- matrices de precio unitario ---------------------------------------
    pu = {}
    pu["P-01"] = matriz("P-01", "Trazo y nivelación con estación total", "pu", "m2")
    detalle(pu["P-01"], 0.005, "MO-05")
    detalle(pu["P-01"], 0.010, "MO-03")
    detalle(pu["P-01"], 0.020, "MO-01")
    detalle(pu["P-01"], 0.015, "EQ-05")
    detalle(pu["P-01"], 0.040, "HER-01")

    pu["P-02"] = matriz("P-02", "Excavación a cielo abierto en material tipo I", "pu", "m3")
    detalle(pu["P-02"], 0.020, "EQ-03")
    detalle(pu["P-02"], 0.050, "MO-01")
    detalle(pu["P-02"], 0.030, "HER-01")

    pu["P-03"] = matriz("P-03", "Plantilla de concreto f'c=100, e=5 cm", "pu", "m2")
    detalle(pu["P-03"], 0.050, "A-01")
    detalle(pu["P-03"], 0.050, "MO-03")
    detalle(pu["P-03"], 0.080, "MO-01")

    pu["P-04"] = matriz("P-04", "Zapata de concreto armado f'c=250, 15 cm de espesor", "pu", "m3")
    detalle(pu["P-04"], 1.030, "M-05")
    detalle(pu["P-04"], 90.000, "A-02")
    detalle(pu["P-04"], 4.500, "A-03")
    detalle(pu["P-04"], 0.120, "EQ-04")
    detalle(pu["P-04"], 0.500, "MO-03")
    detalle(pu["P-04"], 1.600, "MO-01")
    detalle(pu["P-04"], 0.300, "HER-01")

    pu["P-05"] = matriz("P-05", "Muro de block de concreto 15x20x40 cm", "pu", "m2")
    detalle(pu["P-05"], 12.500, "M-09")
    detalle(pu["P-05"], 0.020, "A-04")
    detalle(pu["P-05"], 0.150, "MO-03")
    detalle(pu["P-05"], 0.200, "MO-01")
    detalle(pu["P-05"], 0.250, "HER-01")

    pu["P-06"] = matriz("P-06", "Castillo de concreto f'c=200 de 15x15 cm", "pu", "m")
    detalle(pu["P-06"], 0.025, "M-04")
    detalle(pu["P-06"], 4.200, "A-02")
    detalle(pu["P-06"], 0.100, "A-03")
    detalle(pu["P-06"], 0.080, "MO-03")
    detalle(pu["P-06"], 0.120, "MO-01")
    detalle(pu["P-06"], 0.100, "HER-01")

    pu["P-07"] = matriz("P-07", "Losa de azotea de concreto armado f'c=250, e=12 cm", "pu", "m2")
    detalle(pu["P-07"], 0.130, "M-05")
    detalle(pu["P-07"], 12.500, "A-02")
    detalle(pu["P-07"], 1.150, "A-03")
    detalle(pu["P-07"], 0.080, "EQ-04")
    detalle(pu["P-07"], 0.150, "MO-03")
    detalle(pu["P-07"], 0.250, "MO-01")
    detalle(pu["P-07"], 0.200, "HER-01")

    pu["P-08"] = matriz("P-08", "Aplanado de mortero cemento-arena 1:4 a plomo y regla", "pu", "m2")
    detalle(pu["P-08"], 0.022, "A-04")
    detalle(pu["P-08"], 0.200, "MO-03")
    detalle(pu["P-08"], 0.250, "MO-01")
    detalle(pu["P-08"], 0.150, "HER-01")

    pu["P-09"] = matriz("P-09", "Pintura vinílica a dos manos sobre muro", "pu", "m2")
    detalle(pu["P-09"], 0.350, "M-14")
    detalle(pu["P-09"], 0.150, "M-15")
    detalle(pu["P-09"], 0.060, "MO-06")
    detalle(pu["P-09"], 0.020, "MO-01")
    detalle(pu["P-09"], 0.030, "HER-01")

    # ---- proyecto, partidas y conceptos ------------------------------------
    proyecto = ins(
        con,
        "proyecto",
        clave="OBRA DEMO",
        nombre="Casa habitación unifamiliar · Obra demostrativa",
        cliente_id=ter["CLI-01"],
        tipo="control",
        ubicacion="Culiacán, Sinaloa",
        moneda="MXN",
        fecha_apertura=d(0),
        fecha_cierre=d(161),
        estado="en_proceso",
        pct_indirectos=12.0,
        pct_utilidad=10.0,
        pct_financiamiento=2.0,
        pct_cargos_adicionales=0.0,
        pct_iva=16.0,
        base_indirectos="directo",
        anticipo_pct=20.0,
        retencion_pct=5.0,
        amortizacion_pct=20.0,
        notas="Proyecto de demostración con catálogos, matrices y avance cargado.",
    )

    partidas = {}
    for clave, nombre, orden in [
        ("01", "Preliminares", 1),
        ("02", "Cimentación", 2),
        ("03", "Estructura y albañilería", 3),
        ("04", "Acabados", 4),
    ]:
        partidas[clave] = ins(
            con, "partida", proyecto_id=proyecto, clave=clave, nombre=nombre, nivel=1, orden=orden
        )

    conceptos = [
        ("01.01", "Trazo y nivelación con estación total", "m2", "P-01", 420.0, "01"),
        ("02.01", "Excavación a cielo abierto en material tipo I", "m3", "P-02", 180.0, "02"),
        ("02.02", "Plantilla de concreto f'c=100, e=5 cm", "m2", "P-03", 96.0, "02"),
        ("02.03", "Zapata de concreto armado f'c=250, 15 cm", "m3", "P-04", 42.0, "02"),
        ("03.01", "Muro de block de concreto 15x20x40 cm", "m2", "P-05", 320.0, "03"),
        ("03.02", "Castillo de concreto f'c=200 de 15x15 cm", "m", "P-06", 210.0, "03"),
        ("03.03", "Losa de azotea de concreto armado f'c=250, e=12 cm", "m2", "P-07", 240.0, "03"),
        ("04.01", "Aplanado de mortero cemento-arena 1:4 a plomo y regla", "m2", "P-08", 520.0, "04"),
        ("04.02", "Pintura vinílica a dos manos sobre muro", "m2", "P-09", 520.0, "04"),
    ]
    conceptos_id = {}
    for clave, desc, unidad, matriz_clave, cantidad, partida_clave in conceptos:
        conceptos_id[clave] = ins(
            con,
            "concepto",
            proyecto_id=proyecto,
            partida_id=partidas[partida_clave],
            clave=clave,
            descripcion=desc,
            unidad_id=unidades[unidad],
            matriz_id=pu[matriz_clave],
            cantidad=cantidad,
            pu=0,
            importe=0,
        )

    # ---- números generadores (volúmenes) -----------------------------------
    for concepto_clave, renglones in {
        "01.01": [("Frente del terreno", 1, 30.0, 14.0, 1)],
        "02.01": [("Cepas para zapatas y contratrabes", 12, 2.5, 2.0, 3.0)],
        "03.03": [("Losa de azotea", 1, 15.0, 16.0, 1)],
    }.items():
        for descripcion, veces, largo, ancho, alto in renglones:
            ins(
                con,
                "generador",
                concepto_id=conceptos_id[concepto_clave],
                descripcion=descripcion,
                veces=veces,
                largo=largo,
                ancho=ancho,
                alto=alto,
                total=round(veces * largo * ancho * alto, 6),
            )

    # ---- estructura de trabajos -------------------------------------------
    tareas = {}
    for clave, nombre, padre, partida_clave, inicio, fin, avance, peso in [
        ("1", "Preliminares", None, None, d(0), d(15), 100, 1),
        ("1.1", "Trazo y nivelación", "1", "01", d(0), d(5), 100, 1),
        ("2", "Cimentación", None, None, d(3), d(43), 68, 1),
        ("2.1", "Excavación", "2", "02", d(3), d(20), 100, 1),
        ("2.2", "Plantillas de concreto", "2", "02", d(15), d(31), 80, 1),
        ("2.3", "Zapatas de concreto armado", "2", "02", d(27), d(43), 45, 1),
        ("3", "Estructura y albañilería", None, None, d(36), d(116), 12, 1),
        ("3.1", "Muros de block", "3", "03", d(36), d(75), 25, 1),
        ("3.2", "Castillos y dalas", "3", "03", d(55), d(91), 10, 1),
        ("3.3", "Losa de azotea", "3", "03", d(86), d(116), 0, 1),
        ("4", "Acabados", None, None, d(105), d(161), 0, 1),
        ("4.1", "Aplanados", "4", "04", d(105), d(140), 0, 1),
        ("4.2", "Pintura", "4", "04", d(140), d(161), 0, 1),
    ]:
        tareas[clave] = ins(
            con,
            "tarea",
            proyecto_id=proyecto,
            parent_id=tareas.get(padre),
            partida_id=partidas.get(partida_clave) if partida_clave else None,
            clave=clave,
            nombre=nombre,
            inicio=inicio,
            fin=fin,
            duracion=0,
            avance=avance,
            peso=peso,
            responsable="Residente de obra",
            estado="terminado" if avance >= 100 else ("en_proceso" if avance else "planeado"),
        )

    # ---- contratos ---------------------------------------------------------
    contrato_excavacion = ins(
        con,
        "contrato",
        proyecto_id=proyecto,
        tercero_id=ter["CON-01"],
        numero="CT-2026-001",
        tipo="obra",
        descripcion="Excavación a cielo abierto para cimentación",
        fecha=d(1),
        anticipo_pct=20.0,
        retencion_pct=5.0,
        estatus="abierto",
    )
    ins(
        con,
        "contrato_concepto",
        contrato_id=contrato_excavacion,
        concepto_id=conceptos_id["02.01"],
        clave="02.01",
        descripcion="Excavación a cielo abierto en material tipo I",
        unidad_id=unidades["m3"],
        cantidad=180.0,
        pu=0,
        importe=0,
    )

    contrato_equipo = ins(
        con,
        "contrato",
        proyecto_id=proyecto,
        tercero_id=ter["CON-03"],
        numero="CT-2026-002",
        tipo="equipos",
        descripcion="Renta de retroexcavadora y camión de volteo",
        fecha=d(1),
        anticipo_pct=0.0,
        retencion_pct=0.0,
        estatus="abierto",
    )
    contrato_flete = ins(
        con,
        "contrato",
        proyecto_id=proyecto,
        tercero_id=ter["CON-02"],
        numero="CT-2026-003",
        tipo="fletes",
        descripcion="Acarreo de material producto de excavación",
        fecha=d(1),
        estatus="abierto",
    )

    ins(
        con,
        "orden_trabajo",
        proyecto_id=proyecto,
        contrato_id=contrato_excavacion,
        tarea_id=tareas["2.1"],
        folio="OT-0001",
        fecha=d(3),
        descripcion="Inicio de excavación en cepas y contratrabes",
        monto=0,
        estado="cerrada",
    )
    ins(
        con,
        "orden_trabajo",
        proyecto_id=proyecto,
        contrato_id=contrato_equipo,
        tarea_id=tareas["2.3"],
        folio="OT-0002",
        fecha=d(27),
        descripcion="Suministro de retroexcavadora para excavación de zapatas",
        monto=0,
        estado="en_proceso",
    )

    # ---- bodega ------------------------------------------------------------
    almacen = ins(
        con,
        "almacen",
        clave="ALM-01",
        nombre="Bodega de obra",
        proyecto_id=proyecto,
        ubicacion="Frente de obra, acceso norte",
        responsable="Ing. Almacén",
    )
    movimientos = [
        ("entrada", d(2), "M-01", 6.0, 3100.00, "FAC-1001", ter["PRO-01"]),
        ("entrada", d(2), "M-09", 4500.0, 14.20, "FAC-1002", ter["PRO-03"]),
        ("entrada", d(4), "M-02", 40.0, 300.00, "FAC-1003", ter["PRO-03"]),
        ("entrada", d(4), "M-03", 35.0, 360.00, "FAC-1004", ter["PRO-03"]),
        ("entrada", d(7), "M-06", 3800.0, 22.00, "FAC-1005", ter["PRO-02"]),
        ("entrada", d(7), "M-08", 120.0, 31.00, "FAC-1006", ter["PRO-02"]),
        ("entrada", d(29), "M-05", 60.0, 2620.00, "FAC-1007", ter["PRO-01"]),
        ("salida", d(10), "M-01", 1.5, 3100.00, "REQ-0001-S", None),
        ("salida", d(13), "M-09", 1200.0, 14.20, "REQ-0002-S", None),
        ("salida", d(17), "M-02", 12.0, 300.00, "REQ-0003-S", None),
        ("salida", d(23), "M-06", 900.0, 22.00, "REQ-0004-S", None),
        ("salida", d(31), "M-05", 22.0, 2620.00, "REQ-0005-S", None),
        ("salida", d(36), "M-03", 8.0, 360.00, "REQ-0006-S", None),
    ]
    for tipo_mov, fecha, recurso_clave, cantidad, costo, documento, proveedor in movimientos:
        ins(
            con,
            "movimiento_bodega",
            almacen_id=almacen,
            recurso_id=rec[recurso_clave],
            tipo=tipo_mov,
            fecha=fecha,
            cantidad=cantidad,
            costo_unitario=costo,
            documento=documento,
            tercero_id=proveedor,
        )

    # ---- consumos en obra (estado de servicios) ----------------------------
    consumos = [
        (d(5), tareas["1.1"], "MO-01", 16.0, "01.01"),
        (d(5), tareas["1.1"], "MO-03", 8.0, "01.01"),
        (d(10), tareas["2.1"], "EQ-03", 34.0, "02.01"),
        (d(10), tareas["2.1"], "MO-01", 60.0, "02.01"),
        (d(20), tareas["2.1"], "EQ-02", 24.0, "02.01"),
        (d(17), tareas["2.2"], "A-01", 5.2, "02.02"),
        (d(17), tareas["2.2"], "MO-01", 32.0, "02.02"),
        (d(31), tareas["2.3"], "M-05", 22.0, "02.03"),
        (d(31), tareas["2.3"], "A-02", 3600.0, "02.03"),
        (d(31), tareas["2.3"], "A-03", 180.0, "02.03"),
        (d(31), tareas["2.3"], "MO-03", 60.0, "02.03"),
        (d(38), tareas["3.1"], "M-09", 1200.0, "03.01"),
        (d(38), tareas["3.1"], "A-04", 6.0, "03.01"),
    ]
    from .domain.costos import costo_recurso

    for fecha, tarea_id, recurso_clave, cantidad, concepto_clave in consumos:
        unitario = costo_recurso(con, rec[recurso_clave])
        ins(
            con,
            "consumo",
            proyecto_id=proyecto,
            tarea_id=tarea_id,
            recurso_id=rec[recurso_clave],
            fecha=fecha,
            cantidad=cantidad,
            costo_unitario=unitario,
            costo=round(cantidad * unitario, 2),
            documento=concepto_clave,
        )

    # ---- requisiciones -----------------------------------------------------
    requisicion1 = ins(
        con, "requisicion", proyecto_id=proyecto, folio="REQ-0001", fecha=d(9),
        solicitante="Ing. Residente", estado="surtida",
    )
    ins(con, "requisicion_detalle", requisicion_id=requisicion1, recurso_id=rec["M-01"],
        cantidad=1.5, cantidad_surtida=1.5, unidad="ton")
    ins(con, "requisicion_detalle", requisicion_id=requisicion1, recurso_id=rec["M-02"],
        cantidad=12.0, cantidad_surtida=12.0, unidad="m3")

    requisicion2 = ins(
        con, "requisicion", proyecto_id=proyecto, folio="REQ-0002", fecha=d(28),
        solicitante="Ing. Residente", estado="autorizada",
    )
    ins(con, "requisicion_detalle", requisicion_id=requisicion2, recurso_id=rec["M-05"],
        cantidad=40.0, cantidad_surtida=0, unidad="m3")
    ins(con, "requisicion_detalle", requisicion_id=requisicion2, recurso_id=rec["A-02"],
        cantidad=4200.0, cantidad_surtida=0, unidad="kg")

    # Precio unitario definitivo de cada concepto antes de estimar
    recalcular_todo(con)

    # ---- estimaciones ------------------------------------------------------
    from .domain.avance import actualizar_totales

    acumulados = {"01.01": 1.00, "02.01": 1.00, "02.02": 0.80, "02.03": 0.45,
                  "03.01": 0.15, "03.02": 0.05, "03.03": 0.0, "04.01": 0.0, "04.02": 0.0}
    acumulados_2 = {"01.01": 1.00, "02.01": 1.00, "02.02": 1.00, "02.03": 0.85,
                    "03.01": 0.35, "03.02": 0.12, "03.03": 0.0, "04.01": 0.0, "04.02": 0.0}

    anteriores: dict = {}
    for numero, periodo, fecha, avance, tipo in [
        ("EST-01", (d(0), d(26)), d(26), acumulados, "cobrar"),
        ("EST-02", (d(27), d(54)), d(54), acumulados_2, "cobrar"),
    ]:
        estimacion = ins(
            con,
            "estimacion",
            proyecto_id=proyecto,
            contrato_id=None,
            numero=numero,
            tipo=tipo,
            periodo_inicio=periodo[0],
            periodo_fin=periodo[1],
            fecha=fecha,
            estatus="pagada" if numero == "EST-01" else "autorizada",
        )
        for clave, cantidad_presupuesto in [(c[0], c[4]) for c in conceptos]:
            factor = avance.get(clave, 0.0)
            anterior = anteriores.get(clave, 0.0)
            acumulado = round(cantidad_presupuesto * factor, 4)
            actual = round(max(0.0, acumulado - anterior), 4)
            anteriores[clave] = acumulado
            concepto_fila = con.execute(
                "SELECT c.*, u.clave AS unidad FROM concepto c LEFT JOIN unidad u ON u.id = c.unidad_id"
                " WHERE c.id = ?",
                (conceptos_id[clave],),
            ).fetchone()
            ins(
                con,
                "estimacion_detalle",
                estimacion_id=estimacion,
                concepto_id=conceptos_id[clave],
                clave=clave,
                descripcion=concepto_fila["descripcion"],
                unidad=concepto_fila["unidad"],
                cantidad_anterior=anterior,
                cantidad_actual=actual,
                cantidad_total=acumulado,
                pu=concepto_fila["pu"],
                importe=0,
            )
        actualizar_totales(con, estimacion)
        if numero == "EST-01":
            total = con.execute("SELECT total FROM estimacion WHERE id = ?", (estimacion,)).fetchone()[0]
            ins(
                con,
                "pago",
                estimacion_id=estimacion,
                proyecto_id=proyecto,
                fecha=d(38),
                monto=round(total, 2),
                referencia="TRF-889201",
                medio="transferencia",
                notas="Pago de la estimación 1 menos amortización y retención.",
            )

    # ---- administración de proyectos ---------------------------------------
    cc_obra = ins(con, "centro_costo", proyecto_id=proyecto, clave="CC-01",
                  nombre="Obra civil", nivel=1, presupuesto=0)
    for clave, nombre, presupuesto in [
        ("CC-01.1", "Cimentación", 0),
        ("CC-01.2", "Estructura", 0),
        ("CC-01.3", "Acabados", 0),
    ]:
        ins(con, "centro_costo", proyecto_id=proyecto, parent_id=cc_obra, clave=clave,
            nombre=nombre, nivel=2, presupuesto=presupuesto)

    org = ins(con, "organizacion", proyecto_id=proyecto, clave="ORG-01",
              nombre="Residencia de obra", responsable="Ing. Laura Medina", nivel=1)
    ins(con, "organizacion", proyecto_id=proyecto, parent_id=org, clave="ORG-01.1",
        nombre="Supervisión técnica", responsable="Ing. Superintendente", nivel=2)
    ins(con, "organizacion", proyecto_id=proyecto, parent_id=org, clave="ORG-01.2",
        nombre="Almacén y control de insumos", responsable="Encargado de almacén", nivel=2)

    for recurso_clave, tarea_clave, inicio, fin, planeadas, reales in [
        ("EQ-03", "2.1", d(3), d(20), 32.0, 34.0),
        ("EQ-02", "2.1", d(5), d(23), 20.0, 24.0),
        ("EQ-01", "2.2", d(15), d(31), 40.0, 26.0),
        ("EQ-04", "2.3", d(27), d(43), 12.0, 6.0),
    ]:
        ins(
            con,
            "equipo_en_obra",
            proyecto_id=proyecto,
            recurso_id=rec[recurso_clave],
            tarea_id=tareas[tarea_clave],
            tercero_id=ter["CON-03"],
            fecha_inicio=inicio,
            fecha_fin=fin,
            horas_planeadas=planeadas,
            horas_reales=reales,
            costo_hora=0,
        )

    for periodo, factor in [(mes(0), 1.000), (mes(1), 1.012),
                            (mes(2), 1.028), (mes(3), 1.035)]:
        ins(con, "escalatoria", proyecto_id=proyecto, periodo=periodo, factor=factor)

    con.commit()

    # ---- recálculo global (matrices, PU, auxiliares) -----------------------
    recalcular_todo(con)
    return True


def main() -> None:
    from . import db

    ruta = sys.argv[1] if len(sys.argv) > 1 else "ezapu.db"
    if not Path(ruta).exists():
        print(f"No existe «{ruta}». Créalo con: flask --app run init-db")
        raise SystemExit(1)
    con = db.connect(ruta)
    creado = seed(con, reset=True)
    con.close()
    print(f"Semilla aplicada en {ruta} (nuevo = {creado})")


if __name__ == "__main__":
    main()
