"""Dominio de cálculo de EZAPU.

Módulos:

* ``costos``      · costo básico de mano de obra, costo horario, matrices y PU
* ``explosion``   · explosión de insumos y programa de suministros
* ``presupuesto`` · hoja de presupuesto, análisis del precio, generadores
* ``avance``      · estimaciones, pagos, consumos y estado de servicios
* ``bodega``      · existencias, kardex y costo promedio
* ``planeacion``  · estructura de trabajos, Gantt y avance ponderado
* ``valor_ganado``· EVM, curva S y estructuras de costo/organización
* ``trees``       · utilidades de jerarquías
* ``util``        · helpers numéricos y catálogos base
"""
from .avance import (  # noqa: F401
    acumulado_por_concepto,
    actualizar_totales,
    costo_real_insumos,
    estado_de_cuenta,
    estado_de_servicios,
    preparar_detalle,
    requisiciones,
    resumen_estimacion,
)
from .bodega import existencias, kardex  # noqa: F401
from .costos import (  # noqa: F401
    CicloError,
    ETIQUETAS_COSTO_HORARIO,
    costo_basico_mano_obra,
    costo_matriz,
    costo_recurso,
    detalle_costo_horario,
    detalle_matriz,
    precio_matriz,
    recalcular_todo,
)
from .explosion import (  # noqa: F401
    explosion_matriz,
    explosion_proyecto,
    programa_suministros,
    resumen_por_tipo,
)
from .planeacion import (  # noqa: F401
    avance_ponderado,
    estructura_trabajos,
    gantt,
    importe_por_tarea,
)
from .presupuesto import (  # noqa: F401
    desglose_concepto,
    escalatorias,
    generadores,
    hoja,
    recalcular_conceptos,
    recalcular_volumen,
    totales,
)
from .util import TIPOS_BASICOS, TIPOS_RECURSO, UNIDADES_BASE, money, num, qty  # noqa: F401
from .valor_ganado import (  # noqa: F401
    estructura_costos,
    estructura_organizacion,
    valor_ganado,
)

__all__ = [
    "acumulado_por_concepto", "actualizar_totales", "avance_ponderado", "costo_basico_mano_obra",
    "costo_matriz", "costo_real_insumos", "costo_recurso", "desglose_concepto",
    "detalle_costo_horario", "detalle_matriz", "escalatorias", "estado_de_cuenta",
    "estado_de_servicios", "estructura_costos", "estructura_organizacion",
    "estructura_trabajos", "existencias", "explosion_matriz", "explosion_proyecto", "gantt",
    "generadores", "hoja", "importe_por_tarea", "kardex", "money", "num", "precio_matriz",
    "preparar_detalle", "programa_suministros", "qty", "recalcular_conceptos",
    "recalcular_todo", "recalcular_volumen", "requisiciones", "resumen_estimacion",
    "resumen_por_tipo", "totales", "valor_ganado",
]
