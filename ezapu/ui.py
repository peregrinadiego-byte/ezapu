"""Motor de vistas declarativas.

Aquí se declara, en un solo lugar, cómo se lista y se captura cada tabla:
columnas, campos, referencias y comportamiento. Con eso el blueprint
``catalogos`` da de alta un CRUD completo para todas las tablas de catálogo y
las vistas especializadas reutilizan las mismas definiciones.
"""
from __future__ import annotations

from flask import request, url_for

from . import db
from .domain.costos import costo_recurso, detalle_costo_horario
from .domain.util import TIPOS_RECURSO, money, num

# ============================================================================
#  Especificación de tablas
# ============================================================================
TIPOS_TERCERO = [("cliente", "Cliente"), ("proveedor", "Proveedor"), ("contratista", "Contratista")]
TIPOS_MATRIZ = [("pu", "Precio unitario"), ("basica", "Costo básico"),
                ("auxiliar", "Auxiliar"), ("costo_horario", "Costo horario")]
TIPOS_PROYECTO = [("propuesta", "Propuesta"), ("catalogo", "Catálogo"), ("control", "Control de obra")]
TIPOS_CONTRATO = [("obra", "Obra"), ("tarea", "Tarea"), ("equipos", "Equipos"),
                  ("fletes", "Fletes"), ("suministro", "Suministro"), ("servicios", "Servicios")]
TIPOS_ESTIMACION = [("cobrar", "Por cobrar"), ("pagar", "Por pagar"), ("proforma", "Proforma")]
ESTATUS_ESTIMACION = [("borrador", "Borrador"), ("enviada", "Enviada"),
                      ("autorizada", "Autorizada"), ("pagada", "Pagada")]
TIPOS_MOVIMIENTO = [("entrada", "Entrada"), ("salida", "Salida"), ("ajuste", "Ajuste")]
ESTADOS_REQUISICION = [("solicitada", "Solicitada"), ("autorizada", "Autorizada"),
                       ("surtida", "Surtida"), ("cancelada", "Cancelada")]
ESTADOS_TAREA = [("planeado", "Planeado"), ("en_proceso", "En proceso"), ("terminado", "Terminado")]

ESPECIFICACIONES: dict[str, dict] = {}


def registrar(tabla: str, **spec) -> None:
    spec["tabla"] = tabla
    spec.setdefault("singular", spec.get("titulo", tabla).rstrip("s"))
    spec.setdefault("orden", "id")
    spec.setdefault("modulo", "m2")
    ESPECIFICACIONES[tabla] = spec


def spec_de(tabla: str) -> dict:
    if tabla not in ESPECIFICACIONES:
        raise KeyError(f"Tabla sin especificación: {tabla}")
    return ESPECIFICACIONES[tabla]


# ============================================================================
#  Referencias (llaves foráneas → etiquetas)
# ============================================================================
_REFS = {
    "unidad": "clave || ' · ' || COALESCE(nombre, '')",
    "familia": "clave || ' · ' || COALESCE(nombre, '')",
    "grupo": "clave || ' · ' || COALESCE(nombre, '')",
    "tercero": "clave || ' · ' || nombre",
    "recurso": "clave || ' · ' || descripcion",
    "matriz": "clave || ' · ' || descripcion",
    "proyecto": "clave || ' · ' || nombre",
    "partida": "COALESCE(clave, '') || ' · ' || nombre",
    "tarea": "COALESCE(clave, '') || ' · ' || nombre",
    "contrato": "COALESCE(numero, '') || ' · ' || COALESCE(descripcion, '')",
    "almacen": "clave || ' · ' || COALESCE(nombre, '')",
    "requisicion": "COALESCE(folio, '') || ' · ' || COALESCE(solicitante, '')",
    "centro_costo": "COALESCE(clave, '') || ' · ' || nombre",
    "organizacion": "COALESCE(clave, '') || ' · ' || nombre",
    "estimacion": "COALESCE(numero, '') || ' · ' || COALESCE(fecha, '')",
}


def opciones_ref(con, tabla: str, filtro: str | None = None) -> list[tuple]:
    """Lista ``(id, etiqueta)`` para poblar un ``<select>``."""
    expr = _REFS.get(tabla, "id")
    sql = f"SELECT id, {expr} AS etiqueta FROM {tabla}"
    args: list = []
    if filtro:
        sql += f" WHERE {filtro}"
    sql += " ORDER BY etiqueta"
    return [(r["id"], r["etiqueta"] or str(r["id"])) for r in con.execute(sql, args).fetchall()]


def _cache_refs(con, tablas: set) -> dict:
    cache = {}
    for tabla in tablas:
        cache[tabla] = {r["id"]: r["etiqueta"] for r in con.execute(
            f"SELECT id, {_REFS.get(tabla, 'id')} AS etiqueta FROM {tabla}"
        ).fetchall()}
    return cache


# ============================================================================
#  Lectura y escritura genéricas
# ============================================================================
def _normaliza_fila(con, spec: dict, fila: dict, cache: dict) -> dict:
    """Convierte una fila cruda en fila lista para la plantilla."""
    salida = dict(fila)
    for columna in spec["columnas"]:
        clave = columna["clave"]
        tipo = columna.get("tipo", "text")
        valor = salida.get(clave)
        if tipo == "ref":
            tabla_ref = columna["ref"]
            salida[f"_{clave}"] = cache.get(tabla_ref, {}).get(valor, "")
        elif tipo == "calc":
            salida[clave] = columna["fn"](con, fila)
        elif tipo == "badge":
            opciones = dict(columna.get("opciones") or [])
            salida[f"_{clave}"] = opciones.get(valor, valor)
        elif tipo == "money":
            salida[clave] = money(valor)
        elif tipo == "num":
            try:
                salida[clave] = float(valor or 0)
            except (TypeError, ValueError):
                salida[clave] = 0.0
    salida["_id"] = fila.get("id")
    return salida


def listar(con, spec: dict, filtros: dict | None = None, buscar: str | None = None) -> list[dict]:
    tabla = spec["tabla"]
    where, args = [], []

    for campo, valor in (filtros or {}).items():
        if valor in (None, "", "todos"):
            continue
        where.append(f"{campo} = ?")
        args.append(valor)

    if buscar and spec.get("buscar_en"):
        trozos = [f"{c} LIKE ?" for c in spec["buscar_en"]]
        where.append("(" + " OR ".join(trozos) + ")")
        args.extend([f"%{buscar}%"] * len(spec["buscar_en"]))

    sql = f"SELECT * FROM {tabla}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {spec.get('orden', 'id')}"

    filas = [dict(r) for r in con.execute(sql, args).fetchall()]

    tablas_ref = {c["ref"] for c in spec["columnas"] if c.get("tipo") == "ref"}
    tablas_ref |= {f["ref"] for f in spec.get("campos", []) if f.get("ref")}
    cache = _cache_refs(con, tablas_ref) if tablas_ref else {}

    return [_normaliza_fila(con, spec, fila, cache) for fila in filas]


def obtener(con, tabla: str, row_id: int) -> dict | None:
    fila = con.execute(f"SELECT * FROM {tabla} WHERE id = ?", (row_id,)).fetchone()
    return dict(fila) if fila else None


def _coercionar(campo: dict, valor):
    tipo = campo.get("tipo", "text")
    if tipo in ("number", "money", "qty"):
        if valor in ("", None):
            return 0.0 if tipo != "number" else 0
        texto = str(valor).replace(",", "").strip()
        try:
            return float(texto) if "." in texto else int(texto)
        except ValueError:
            return 0
    if tipo == "checkbox":
        return 1 if valor in ("1", "on", "true", "True") else 0
    if tipo == "select":
        if valor in ("", None):
            return None
        if campo.get("ref"):
            return int(valor)
        return valor
    if valor == "" and campo.get("nulo", True) and campo.get("tipo") == "date":
        return None
    if valor is None:
        return None
    return str(valor).strip()


def datos_del_formulario(spec: dict, formulario) -> dict:
    datos = {}
    for campo in spec.get("campos", []):
        if campo.get("solo_lectura"):
            continue
        if campo["clave"] not in formulario:
            if campo.get("tipo") == "checkbox":
                datos[campo["clave"]] = 0
            continue
        datos[campo["clave"]] = _coercionar(campo, formulario.get(campo["clave"]))
    return datos


def guardar(con, spec: dict, datos: dict, row_id: int | None = None) -> int:
    tabla = spec["tabla"]
    if row_id:
        if not datos:
            return row_id
        sets = ", ".join(f"{c} = ?" for c in datos)
        con.execute(f"UPDATE {tabla} SET {sets} WHERE id = ?", list(datos.values()) + [row_id])
        con.commit()
        return row_id
    cols = list(datos)
    cur = con.execute(
        "INSERT INTO {} ({}) VALUES ({})".format(
            tabla, ", ".join(cols), ", ".join("?" * len(cols))
        ),
        list(datos.values()),
    )
    con.commit()
    return cur.lastrowid


# ============================================================================
#  Navegación (réplica de la estructura de menús de OPUS)
# ============================================================================
def _u(endpoint: str, **params) -> str:
    return url_for(endpoint, **params)


def _cat(tabla: str, params: dict | None = None) -> str:
    return url_for("catalogos.lista", tabla=tabla, **(params or {}))


def construir_nav() -> list[dict]:
    """Devuelve los dos módulos con sus grupos y vistas."""
    activo_tabla = request.view_args.get("tabla") if request.view_args else None
    endpoint = request.endpoint or ""

    def item(texto, url, clave=None):
        activo = False
        if endpoint.startswith("catalogos."):
            activo = clave == activo_tabla
        else:
            activo = request.path == url.split("?")[0]
        return {"texto": texto, "url": url, "activo": activo}

    m1 = {
        "clave": "m1",
        "titulo": "M1 · Propuestas y presupuestos",
        "grupos": [
            ("Catálogos de insumos", [
                item("Todos los insumos", _cat("recurso")),
                item("Materiales", _cat("recurso", {"tipo": "material"}), "recurso"),
                item("Mano de obra", _cat("recurso", {"tipo": "mano_obra"})),
                item("Equipo", _cat("recurso", {"tipo": "equipo"})),
                item("Herramienta", _cat("recurso", {"tipo": "herramienta"})),
                item("Auxiliares (matrices)", _cat("recurso", {"tipo": "auxiliar"})),
                item("Subcontratos", _cat("recurso", {"tipo": "subcontrato"})),
                item("Fletes", _cat("recurso", {"tipo": "flete"})),
                item("Familias", _cat("familia")),
                item("Grupos", _cat("grupo")),
                item("Unidades de medida", _cat("unidad")),
            ]),
            ("Costos básicos", [
                item("Salarios de mano de obra", _cat("mano_obra")),
                item("Costos horarios de equipo", _cat("costo_horario")),
                item("Matrices de costo unitario", _cat("matriz")),
            ]),
            ("Presupuesto", [
                item("Proyectos y propuestas", _cat("proyecto")),
                item("Partidas", _cat("partida")),
                item("Catálogo de conceptos", _cat("concepto")),
                item("Volúmenes y generadores", _u("presupuesto.generadores_indice")),
                item("Explosión de insumos", _u("presupuesto.explosion_indice")),
                item("Programa de suministros", _u("presupuesto.suministros_indice")),
                item("Análisis del precio", _u("presupuesto.analisis_indice")),
                item("Escalatorias", _cat("escalatoria")),
            ]),
            ("Reportes", [
                item("Formatos e impresión", _u("reportes.indice")),
            ]),
        ],
    }

    m2 = {
        "clave": "m2",
        "titulo": "M2 · Control de obra",
        "grupos": [
            ("Planeación", [
                item("Estructura de trabajos", _u("planeacion.indice")),
                item("Listado de trabajos", _cat("tarea")),
                item("Explosión de insumos", _u("presupuesto.explosion_indice")),
                item("Programa de suministros", _u("presupuesto.suministros_indice")),
                item("Contratos", _cat("contrato")),
                item("Planeación de equipo", _cat("equipo_en_obra")),
            ]),
            ("Catálogos", [
                item("Recursos", _cat("recurso")),
                item("Materiales", _cat("recurso", {"tipo": "material"})),
                item("Mano de obra", _cat("recurso", {"tipo": "mano_obra"})),
                item("Equipo", _cat("recurso", {"tipo": "equipo"})),
                item("Matrices", _cat("matriz")),
                item("Fletes", _cat("recurso", {"tipo": "flete"})),
                item("Subcontratos", _cat("recurso", {"tipo": "subcontrato"})),
                item("Contratistas y proveedores", _cat("tercero")),
                item("Equipo en obra", _cat("equipo_en_obra")),
            ]),
            ("Avance", [
                item("Órdenes de trabajo", _cat("orden_trabajo")),
                item("Estimaciones", _u("control.estimaciones_indice")),
                item("Registro de consumo", _cat("consumo")),
                item("Estado de servicios", _u("control.servicios_indice")),
                item("Pagos", _cat("pago")),
                item("Conceptos a estimar", _cat("concepto")),
                item("Requisiciones", _cat("requisicion")),
            ]),
            ("Bodega", [
                item("Estado de la bodega", _u("control.bodega_indice")),
                item("Movimientos", _cat("movimiento_bodega")),
                item("Almacenes", _cat("almacen")),
            ]),
            ("Administración de proyectos", [
                item("Estructura de costos", _cat("centro_costo")),
                item("Estructura de organización", _cat("organizacion")),
                item("Valor ganado y curva S", _u("administracion.valor_ganado_indice")),
            ]),
        ],
    }

    return [m1, m2]


# ============================================================================
#  Columnas / campos reutilizables
# ============================================================================
def col(clave, etiqueta, tipo="text", **extra):
    return {"clave": clave, "etiqueta": etiqueta, "tipo": tipo, **extra}


def fld(clave, etiqueta, tipo="text", **extra):
    campo = {"clave": clave, "etiqueta": etiqueta, "tipo": tipo}
    campo.update(extra)
    return campo


COL_EMPRESA = [col("nombre", "Empresa"), col("rfc", "RFC")]


# ============================================================================
#  Registro de especificaciones
# ============================================================================
registrar(
    "unidad",
    titulo="Unidades de medida",
    singular="Unidad",
    modulo="m1",
    descripcion="Unidades con las que se miden los insumos y los conceptos.",
    orden="clave",
    buscar_en=["clave", "nombre"],
    columnas=[col("clave", "Clave"), col("nombre", "Nombre"), col("tipo", "Tipo")],
    campos=[fld("clave", "Clave", requerido=True), fld("nombre", "Nombre"), fld("tipo", "Tipo")],
)

registrar(
    "familia",
    titulo="Familias de insumos",
    singular="Familia",
    modulo="m1",
    orden="clave",
    buscar_en=["clave", "nombre"],
    columnas=[col("clave", "Clave"), col("nombre", "Nombre"), col("tipo", "Tipo")],
    campos=[fld("clave", "Clave", requerido=True), fld("nombre", "Nombre"), fld("tipo", "Tipo")],
)

registrar(
    "grupo",
    titulo="Grupos de insumos",
    singular="Grupo",
    modulo="m1",
    orden="clave",
    buscar_en=["clave", "nombre"],
    columnas=[col("clave", "Clave"), col("nombre", "Nombre"), col("familia_id", "Familia", "ref", ref="familia")],
    campos=[fld("clave", "Clave", requerido=True), fld("nombre", "Nombre"),
            fld("familia_id", "Familia", "select", ref="familia")],
)

registrar(
    "tercero",
    titulo="Clientes, proveedores y contratistas",
    singular="Tercero",
    modulo="m2",
    orden="clave",
    buscar_en=["clave", "nombre", "rfc"],
    descripcion="Padrón de terceros: clientes, proveedores y contratistas.",
    columnas=[col("clave", "Clave"), col("nombre", "Nombre"),
              col("tipo", "Tipo", "badge", opciones=TIPOS_TERCERO),
              col("especialidad", "Especialidad"), col("telefono", "Teléfono")],
    campos=[fld("clave", "Clave", requerido=True), fld("nombre", "Nombre / razón social", requerido=True),
            fld("tipo", "Tipo", "select", opciones=TIPOS_TERCERO),
            fld("rfc", "RFC"), fld("contacto", "Contacto"), fld("telefono", "Teléfono"),
            fld("email", "Correo"), fld("especialidad", "Especialidad / categoría"),
            fld("direccion", "Dirección", "textarea"), fld("notas", "Notas", "textarea")],
)

registrar(
    "recurso",
    titulo="Catálogo de insumos",
    singular="Insumo",
    modulo="m1",
    orden="clave",
    recalcular=True,
    buscar_en=["clave", "descripcion"],
    descripcion="Materiales, mano de obra, equipo, herramienta, subcontratos, fletes "
                "y auxiliares (conceptos). El costo vigente se calcula solo.",
    columnas=[
        col("clave", "Clave"),
        col("descripcion", "Descripción"),
        col("tipo", "Tipo", "badge", opciones=list(TIPOS_RECURSO.items())),
        col("unidad_id", "Unidad", "ref", ref="unidad"),
        col("familia_id", "Familia", "ref", ref="familia"),
        col("costo_vigente", "Costo vigente", "calc",
            fn=lambda con, fila: costo_recurso(con, fila["id"]), formato="money", alinear="der"),
    ],
    campos=[
        fld("clave", "Clave", requerido=True),
        fld("descripcion", "Descripción", requerido=True),
        fld("tipo", "Tipo", "select", opciones=list(TIPOS_RECURSO.items())),
        fld("unidad_id", "Unidad", "select", ref="unidad"),
        fld("familia_id", "Familia", "select", ref="familia"),
        fld("grupo_id", "Grupo", "select", ref="grupo"),
        fld("proveedor_id", "Proveedor", "select", ref="tercero",
            ref_filtro="tipo = 'proveedor'"),
        fld("costo_base", "Costo base / precio unitario", "money",
            ayuda="Se ignora en mano de obra, equipo y auxiliares: su costo se calcula."),
        fld("merma_pct", "Merma (%)", "money"),
        fld("matriz_id", "Matriz (solo auxiliares)", "select", ref="matriz"),
        fld("fecha_precio", "Fecha del precio", "date"),
        fld("notas", "Notas", "textarea"),
        fld("activo", "Activo", "checkbox", default=1),
    ],
)

registrar(
    "mano_obra",
    titulo="Salarios de mano de obra",
    singular="Salario",
    modulo="m1",
    orden="id",
    recalcular=True,
    descripcion="Costo básico = salario base × (1 + factor de prestaciones).",
    columnas=[
        col("recurso_id", "Insumo", "ref", ref="recurso"),
        col("salario_base", "Salario base", "money", alinear="der"),
        col("factor_prestaciones", "FSR %", "num", alinear="der"),
        col("horas_turno", "Horas/turno", "num", alinear="der"),
        col("costo_basico", "Salario real", "money", alinear="der"),
    ],
    campos=[
        fld("recurso_id", "Insumo de mano de obra", "select", ref="recurso",
            ref_filtro="tipo = 'mano_obra'", requerido=True),
        fld("salario_base", "Salario base por turno", "money"),
        fld("factor_prestaciones", "Factor de prestaciones (%)", "money"),
        fld("horas_turno", "Horas por turno", "money", default=8),
        fld("cuadrilla", "Cuadrilla"),
        fld("notas", "Notas", "textarea"),
    ],
)

registrar(
    "costo_horario",
    titulo="Costos horarios de equipo y herramienta",
    singular="Costo horario",
    modulo="m1",
    orden="id",
    recalcular=True,
    descripcion="Fórmula de costo horario: depreciación, inversión, seguros, mantenimiento, "
                "reparaciones, combustible, lubricantes, llantas y operador.",
    columnas=[
        col("recurso_id", "Equipo", "ref", ref="recurso"),
        col("valor_maquina", "Valor máquina", "money", alinear="der"),
        col("vida_util", "Vida útil (h)", "num", alinear="der"),
        col("costo_total", "Costo horario", "money", alinear="der"),
    ],
    campos=[
        fld("recurso_id", "Equipo o herramienta", "select", ref="recurso",
            ref_filtro="tipo IN ('equipo','herramienta')", requerido=True),
        fld("valor_maquina", "Valor de la máquina (VM)", "money"),
        fld("valor_rescate", "Valor de rescate (VR)", "money"),
        fld("vida_util", "Vida útil (horas)", "money"),
        fld("horas_anuales", "Horas de uso por año", "money"),
        fld("tasa_interes", "Tasa de interés (%)", "money"),
        fld("tasa_seguro", "Tasa de seguros (%)", "money"),
        fld("coef_mantenimiento", "Coeficiente de mantenimiento", "money"),
        fld("coef_reparaciones", "Coeficiente de reparaciones", "money"),
        fld("consumo_combustible", "Consumo de combustible (l/h)", "money"),
        fld("precio_combustible", "Precio del combustible ($/l)", "money"),
        fld("pct_lubricantes", "Lubricantes (% del combustible)", "money"),
        fld("costo_llantas", "Costo de llantas", "money"),
        fld("vida_llantas", "Vida de las llantas (h)", "money"),
        fld("recurso_operador_id", "Operador (insumo de mano de obra)", "select", ref="recurso",
            ref_filtro="tipo = 'mano_obra'"),
        fld("incluye_operador", "Incluye operador", "checkbox", default=1),
        fld("costo_otros", "Otros cargos por hora", "money"),
        fld("manual", "Capturar el costo total manualmente", "checkbox"),
        fld("costo_total", "Costo horario total (manual)", "money"),
    ],
)

registrar(
    "matriz",
    titulo="Matrices de costo unitario",
    singular="Matriz",
    modulo="m1",
    orden="clave",
    recalcular=True,
    buscar_en=["clave", "descripcion"],
    descripcion="Análisis de precio unitario: se arma con insumos y con submatrices "
                "(auxiliares). El costo directo se calcula solo.",
    columnas=[
        col("clave", "Clave"), col("descripcion", "Descripción"),
        col("tipo", "Tipo", "badge", opciones=TIPOS_MATRIZ),
        col("unidad_id", "Unidad", "ref", ref="unidad"),
        col("costo_directo", "Costo directo", "money", alinear="der"),
        col("costo_indirecto_pct", "Indirectos %", "num", alinear="der"),
    ],
    detalle="matriz_detalle",
    campos=[
        fld("clave", "Clave", requerido=True),
        fld("descripcion", "Descripción", requerido=True),
        fld("tipo", "Tipo", "select", opciones=TIPOS_MATRIZ),
        fld("unidad_id", "Unidad", "select", ref="unidad"),
        fld("costo_indirecto_pct", "Indirectos propios (%)", "money"),
        fld("proyecto_id", "Proyecto (opcional)", "select", ref="proyecto"),
        fld("notas", "Notas", "textarea"),
    ],
)

registrar(
    "proyecto",
    titulo="Proyectos y propuestas",
    singular="Proyecto",
    modulo="m1",
    orden="clave",
    buscar_en=["clave", "nombre"],
    descripcion="Cada proyecto concentra partidas, conceptos, matrices y su análisis del precio.",
    columnas=[
        col("clave", "Clave"), col("nombre", "Nombre"),
        col("tipo", "Tipo", "badge", opciones=TIPOS_PROYECTO),
        col("cliente_id", "Cliente", "ref", ref="tercero"),
        col("ubicacion", "Ubicación"),
        col("estado", "Estado", "badge"),
    ],
    campos=[
        fld("clave", "Clave", requerido=True), fld("nombre", "Nombre", requerido=True),
        fld("cliente_id", "Cliente", "select", ref="tercero", ref_filtro="tipo = 'cliente'"),
        fld("tipo", "Tipo", "select", opciones=TIPOS_PROYECTO),
        fld("ubicacion", "Ubicación"), fld("moneda", "Moneda", default="MXN"),
        fld("fecha_apertura", "Fecha de apertura", "date"),
        fld("fecha_cierre", "Fecha de cierre", "date"),
        fld("estado", "Estado"),
        fld("pct_indirectos", "Indirectos (%)", "money"),
        fld("pct_utilidad", "Utilidad (%)", "money"),
        fld("pct_financiamiento", "Financiamiento (%)", "money"),
        fld("pct_cargos_adicionales", "Cargos adicionales (%)", "money"),
        fld("pct_iva", "IVA (%)", "money"),
        fld("base_indirectos", "Base de aplicación", "select",
            opciones=[("directo", "Sobre el costo directo"), ("acumulado", "Sobre el acumulado")]),
        fld("anticipo_pct", "Anticipo (%)", "money"),
        fld("retencion_pct", "Retención (%)", "money"),
        fld("amortizacion_pct", "Amortización de anticipo (%)", "money"),
        fld("notas", "Notas", "textarea"),
    ],
)

registrar(
    "partida",
    titulo="Partidas del presupuesto",
    singular="Partida",
    modulo="m1",
    orden="clave",
    buscar_en=["clave", "nombre"],
    columnas=[col("clave", "Clave"), col("nombre", "Nombre"),
              col("proyecto_id", "Proyecto", "ref", ref="proyecto"),
              col("parent_id", "Partida padre", "ref", ref="partida")],
    campos=[fld("proyecto_id", "Proyecto", "select", ref="proyecto", requerido=True),
            fld("parent_id", "Partida padre", "select", ref="partida"),
            fld("clave", "Clave", requerido=True), fld("nombre", "Nombre", requerido=True),
            fld("orden", "Orden", "number"), fld("notas", "Notas", "textarea")],
)

registrar(
    "concepto",
    titulo="Catálogo de conceptos",
    singular="Concepto",
    modulo="m1",
    orden="clave",
    recalcular=True,
    buscar_en=["clave", "descripcion"],
    descripcion="Conceptos de obra con su volumen, precio unitario e importe.",
    columnas=[
        col("clave", "Clave"), col("descripcion", "Descripción"),
        col("proyecto_id", "Proyecto", "ref", ref="proyecto"),
        col("unidad_id", "Unidad", "ref", ref="unidad"),
        col("matriz_id", "Matriz", "ref", ref="matriz"),
        col("cantidad", "Volumen", "qty", alinear="der"),
        col("pu", "P.U.", "money", alinear="der"),
        col("importe", "Importe", "money", alinear="der"),
    ],
    campos=[
        fld("proyecto_id", "Proyecto", "select", ref="proyecto", requerido=True),
        fld("partida_id", "Partida", "select", ref="partida"),
        fld("clave", "Clave", requerido=True),
        fld("descripcion", "Descripción", requerido=True),
        fld("unidad_id", "Unidad", "select", ref="unidad"),
        fld("matriz_id", "Matriz de precio unitario", "select", ref="matriz"),
        fld("cantidad", "Volumen", "qty"),
        fld("pu", "Precio unitario", "money"),
        fld("orden", "Orden", "number"),
        fld("notas", "Notas", "textarea"),
    ],
)

registrar(
    "tarea",
    titulo="Estructura de trabajos",
    singular="Tarea",
    modulo="m2",
    orden="clave",
    buscar_en=["clave", "nombre"],
    descripcion="Estructura de desglose de trabajos (EDT) con fechas y avance.",
    columnas=[
        col("clave", "Clave"), col("nombre", "Nombre"),
        col("proyecto_id", "Proyecto", "ref", ref="proyecto"),
        col("partida_id", "Partida", "ref", ref="partida"),
        col("inicio", "Inicio", "date"), col("fin", "Fin", "date"),
        col("avance", "Avance %", "num", alinear="der"),
        col("estado", "Estado", "badge", opciones=ESTADOS_TAREA),
    ],
    campos=[
        fld("proyecto_id", "Proyecto", "select", ref="proyecto", requerido=True),
        fld("parent_id", "Tarea padre", "select", ref="tarea"),
        fld("partida_id", "Partida ligada", "select", ref="partida"),
        fld("clave", "Clave"), fld("nombre", "Nombre", requerido=True),
        fld("inicio", "Inicio", "date"), fld("fin", "Fin", "date"),
        fld("duracion", "Duración (días)", "money"),
        fld("avance", "Avance (%)", "money"),
        fld("peso", "Peso relativo", "money", default=1),
        fld("responsable", "Responsable"),
        fld("estado", "Estado", "select", opciones=ESTADOS_TAREA),
        fld("notas", "Notas", "textarea"),
    ],
)

registrar(
    "contrato",
    titulo="Contratos",
    singular="Contrato",
    modulo="m2",
    orden="numero",
    buscar_en=["numero", "descripcion"],
    descripcion="Contratos de obra, renta de equipo, fletes, suministro y servicios.",
    columnas=[
        col("numero", "Número"), col("descripcion", "Descripción"),
        col("proyecto_id", "Proyecto", "ref", ref="proyecto"),
        col("tercero_id", "Contratista", "ref", ref="tercero"),
        col("tipo", "Tipo", "badge", opciones=TIPOS_CONTRATO),
        col("fecha", "Fecha", "date"),
        col("monto", "Monto", "money", alinear="der"),
        col("estatus", "Estatus", "badge"),
    ],
    campos=[
        fld("proyecto_id", "Proyecto", "select", ref="proyecto", requerido=True),
        fld("tercero_id", "Contratista", "select", ref="tercero",
            ref_filtro="tipo IN ('contratista','proveedor')"),
        fld("numero", "Número de contrato", requerido=True),
        fld("tipo", "Tipo", "select", opciones=TIPOS_CONTRATO),
        fld("descripcion", "Descripción", "textarea"),
        fld("fecha", "Fecha", "date"),
        fld("monto", "Monto", "money"),
        fld("anticipo_pct", "Anticipo (%)", "money"),
        fld("retencion_pct", "Retención (%)", "money"),
        fld("estatus", "Estatus"),
        fld("notas", "Notas", "textarea"),
    ],
)

registrar(
    "contrato_concepto",
    titulo="Conceptos del contrato",
    singular="Concepto de contrato",
    modulo="m2",
    orden="id",
    columnas=[col("contrato_id", "Contrato", "ref", ref="contrato"),
              col("clave", "Clave"), col("descripcion", "Descripción"),
              col("cantidad", "Cantidad", "qty", alinear="der"),
              col("pu", "P.U.", "money", alinear="der"),
              col("importe", "Importe", "money", alinear="der")],
    campos=[fld("contrato_id", "Contrato", "select", ref="contrato", requerido=True),
            fld("concepto_id", "Concepto del presupuesto", "select", ref="concepto"),
            fld("clave", "Clave"), fld("descripcion", "Descripción"),
            fld("cantidad", "Cantidad", "qty"), fld("pu", "Precio unitario", "money")],
)

registrar(
    "orden_trabajo",
    titulo="Órdenes de trabajo",
    singular="Orden de trabajo",
    modulo="m2",
    orden="folio",
    columnas=[col("folio", "Folio"), col("fecha", "Fecha", "date"),
              col("descripcion", "Descripción"),
              col("proyecto_id", "Proyecto", "ref", ref="proyecto"),
              col("contrato_id", "Contrato", "ref", ref="contrato"),
              col("monto", "Monto", "money", alinear="der"),
              col("estado", "Estado", "badge")],
    campos=[fld("proyecto_id", "Proyecto", "select", ref="proyecto", requerido=True),
            fld("contrato_id", "Contrato", "select", ref="contrato"),
            fld("tarea_id", "Tarea", "select", ref="tarea"),
            fld("folio", "Folio", requerido=True), fld("fecha", "Fecha", "date"),
            fld("descripcion", "Descripción", "textarea"),
            fld("monto", "Monto", "money"),
            fld("estado", "Estado", "select",
                opciones=[("abierta", "Abierta"), ("en_proceso", "En proceso"), ("cerrada", "Cerrada")]),
            fld("notas", "Notas", "textarea")],
)

registrar(
    "consumo",
    titulo="Registro de consumo",
    singular="Consumo",
    modulo="m2",
    orden="fecha",
    descripcion="Insumos realmente consumidos en la obra (base del estado de servicios).",
    columnas=[col("fecha", "Fecha", "date"),
              col("proyecto_id", "Proyecto", "ref", ref="proyecto"),
              col("recurso_id", "Insumo", "ref", ref="recurso"),
              col("tarea_id", "Tarea", "ref", ref="tarea"),
              col("cantidad", "Cantidad", "qty", alinear="der"),
              col("costo_unitario", "Costo unitario", "money", alinear="der"),
              col("costo", "Importe", "money", alinear="der")],
    campos=[fld("proyecto_id", "Proyecto", "select", ref="proyecto", requerido=True),
            fld("tarea_id", "Tarea", "select", ref="tarea"),
            fld("recurso_id", "Insumo", "select", ref="recurso", requerido=True),
            fld("fecha", "Fecha", "date"),
            fld("cantidad", "Cantidad", "qty"),
            fld("costo_unitario", "Costo unitario", "money"),
            fld("documento", "Documento"), fld("notas", "Notas", "textarea")],
)

registrar(
    "requisicion",
    titulo="Requisiciones de material",
    singular="Requisición",
    modulo="m2",
    orden="folio",
    columnas=[col("folio", "Folio"), col("fecha", "Fecha", "date"),
              col("proyecto_id", "Proyecto", "ref", ref="proyecto"),
              col("solicitante", "Solicitante"),
              col("estado", "Estado", "badge", opciones=ESTADOS_REQUISICION)],
    campos=[fld("proyecto_id", "Proyecto", "select", ref="proyecto", requerido=True),
            fld("folio", "Folio", requerido=True), fld("fecha", "Fecha", "date"),
            fld("solicitante", "Solicitante"),
            fld("estado", "Estado", "select", opciones=ESTADOS_REQUISICION),
            fld("notas", "Notas", "textarea")],
)

registrar(
    "requisicion_detalle",
    titulo="Renglones de requisición",
    singular="Renglón",
    modulo="m2",
    orden="id",
    columnas=[col("requisicion_id", "Requisición", "ref", ref="requisicion"),
              col("recurso_id", "Insumo", "ref", ref="recurso"),
              col("cantidad", "Cantidad", "qty", alinear="der"),
              col("cantidad_surtida", "Surtida", "qty", alinear="der")],
    campos=[fld("requisicion_id", "Requisición", "select", ref="requisicion", requerido=True),
            fld("recurso_id", "Insumo", "select", ref="recurso", requerido=True),
            fld("cantidad", "Cantidad", "qty"),
            fld("cantidad_surtida", "Cantidad surtida", "qty"),
            fld("unidad", "Unidad"), fld("notas", "Notas", "textarea")],
)

registrar(
    "almacen",
    titulo="Almacenes",
    singular="Almacén",
    modulo="m2",
    orden="clave",
    columnas=[col("clave", "Clave"), col("nombre", "Nombre"),
              col("proyecto_id", "Proyecto", "ref", ref="proyecto"),
              col("responsable", "Responsable")],
    campos=[fld("clave", "Clave", requerido=True), fld("nombre", "Nombre"),
            fld("proyecto_id", "Proyecto", "select", ref="proyecto"),
            fld("ubicacion", "Ubicación"), fld("responsable", "Responsable"),
            fld("activo", "Activo", "checkbox", default=1)],
)

registrar(
    "movimiento_bodega",
    titulo="Movimientos de bodega",
    singular="Movimiento",
    modulo="m2",
    orden="fecha",
    descripcion="Entradas, salidas y ajustes de insumos en almacén.",
    columnas=[col("fecha", "Fecha", "date"),
              col("almacen_id", "Almacén", "ref", ref="almacen"),
              col("recurso_id", "Insumo", "ref", ref="recurso"),
              col("tipo", "Tipo", "badge", opciones=TIPOS_MOVIMIENTO),
              col("cantidad", "Cantidad", "qty", alinear="der"),
              col("costo_unitario", "Costo unitario", "money", alinear="der"),
              col("documento", "Documento")],
    campos=[fld("almacen_id", "Almacén", "select", ref="almacen", requerido=True),
            fld("recurso_id", "Insumo", "select", ref="recurso", requerido=True),
            fld("tipo", "Tipo", "select", opciones=TIPOS_MOVIMIENTO),
            fld("fecha", "Fecha", "date"),
            fld("cantidad", "Cantidad", "qty"),
            fld("costo_unitario", "Costo unitario", "money"),
            fld("documento", "Documento"),
            fld("tercero_id", "Proveedor / contratista", "select", ref="tercero"),
            fld("tarea_id", "Tarea destino", "select", ref="tarea"),
            fld("notas", "Notas", "textarea")],
)

registrar(
    "pago",
    titulo="Pagos",
    singular="Pago",
    modulo="m2",
    orden="fecha",
    columnas=[col("fecha", "Fecha", "date"),
              col("estimacion_id", "Estimación", "ref", ref="estimacion"),
              col("proyecto_id", "Proyecto", "ref", ref="proyecto"),
              col("monto", "Monto", "money", alinear="der"),
              col("referencia", "Referencia"), col("medio", "Medio")],
    campos=[fld("estimacion_id", "Estimación", "select", ref="estimacion"),
            fld("proyecto_id", "Proyecto", "select", ref="proyecto", requerido=True),
            fld("fecha", "Fecha", "date"), fld("monto", "Monto", "money"),
            fld("referencia", "Referencia"), fld("medio", "Medio"),
            fld("notas", "Notas", "textarea")],
)

registrar(
    "centro_costo",
    titulo="Estructura de costos",
    singular="Centro de costo",
    modulo="m2",
    orden="clave",
    columnas=[col("clave", "Clave"), col("nombre", "Nombre"),
              col("proyecto_id", "Proyecto", "ref", ref="proyecto"),
              col("parent_id", "Centro padre", "ref", ref="centro_costo"),
              col("presupuesto", "Presupuesto", "money", alinear="der")],
    campos=[fld("proyecto_id", "Proyecto", "select", ref="proyecto", requerido=True),
            fld("parent_id", "Centro padre", "select", ref="centro_costo"),
            fld("clave", "Clave"), fld("nombre", "Nombre", requerido=True),
            fld("presupuesto", "Presupuesto", "money")],
)

registrar(
    "organizacion",
    titulo="Estructura de organización",
    singular="Unidad orgánica",
    modulo="m2",
    orden="clave",
    columnas=[col("clave", "Clave"), col("nombre", "Nombre"),
              col("proyecto_id", "Proyecto", "ref", ref="proyecto"),
              col("parent_id", "Depende de", "ref", ref="organizacion"),
              col("responsable", "Responsable")],
    campos=[fld("proyecto_id", "Proyecto", "select", ref="proyecto"),
            fld("parent_id", "Depende de", "select", ref="organizacion"),
            fld("clave", "Clave"), fld("nombre", "Nombre", requerido=True),
            fld("responsable", "Responsable")],
)

registrar(
    "equipo_en_obra",
    titulo="Planeación de equipo",
    singular="Equipo en obra",
    modulo="m2",
    orden="fecha_inicio",
    columnas=[col("recurso_id", "Equipo", "ref", ref="recurso"),
              col("proyecto_id", "Proyecto", "ref", ref="proyecto"),
              col("tarea_id", "Tarea", "ref", ref="tarea"),
              col("tercero_id", "Proveedor", "ref", ref="tercero"),
              col("fecha_inicio", "Inicio", "date"), col("fecha_fin", "Fin", "date"),
              col("horas_planeadas", "Horas planeadas", "num", alinear="der"),
              col("horas_reales", "Horas reales", "num", alinear="der")],
    campos=[fld("proyecto_id", "Proyecto", "select", ref="proyecto", requerido=True),
            fld("recurso_id", "Equipo", "select", ref="recurso",
                ref_filtro="tipo IN ('equipo','herramienta')", requerido=True),
            fld("tarea_id", "Tarea", "select", ref="tarea"),
            fld("tercero_id", "Proveedor / arrendador", "select", ref="tercero"),
            fld("fecha_inicio", "Inicio", "date"), fld("fecha_fin", "Fin", "date"),
            fld("horas_planeadas", "Horas planeadas", "money"),
            fld("horas_reales", "Horas reales", "money"),
            fld("costo_hora", "Costo por hora", "money"),
            fld("notas", "Notas", "textarea")],
)

registrar(
    "escalatoria",
    titulo="Escalatorias",
    singular="Escalatoria",
    modulo="m1",
    orden="periodo",
    descripcion="Factores de ajuste de costos por periodo.",
    columnas=[col("periodo", "Periodo"),
              col("proyecto_id", "Proyecto", "ref", ref="proyecto"),
              col("factor", "Factor", "num", alinear="der")],
    campos=[fld("proyecto_id", "Proyecto", "select", ref="proyecto", requerido=True),
            fld("periodo", "Periodo (AAAA-MM)", requerido=True),
            fld("factor", "Factor", "money", default=1),
            fld("notas", "Notas", "textarea")],
)
