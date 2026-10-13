# EZAPU

Herramienta web para **presupuestos de obra (M1)** y **control de obra (M2)**,
hecha con **Python + Flask + SQLite + HTML/CSS**, sin dependencias de *frontend*.

Reproduce, con software libre, el flujo de trabajo del sistema de:
catálogo de insumos → costos básicos y horarios → matrices de precios unitarios →
presupuesto → explosión de insumos → programa de obra → estimaciones, bodega y
valor ganado.

> Proyecto independiente.
---

## Módulos

### M1 · Propuestas y presupuestos

| Grupo | Vistas |
|---|---|
| Catálogos de insumos | Todos los insumos, Materiales, Mano de obra, Equipo, Herramienta, Auxiliares, Subcontratos, Fletes, Familias, Grupos, Unidades |
| Costos básicos | Salarios de mano de obra, Costos horarios de equipo, Matrices de costo unitario |
| Presupuesto | Proyectos y propuestas, Partidas, Catálogo de conceptos, Volúmenes y generadores, Explosión de insumos, Programa de suministros, Análisis del precio, Escalatorias |
| Reportes | Formatos imprimibles y exportación a Excel/CSV |

### M2 · Control de obra

| Grupo | Vistas |
|---|---|
| Planeación | Estructura de trabajos (Gantt), Listado de trabajos, Explosión de insumos, Programa de suministros, Contratos, Planeación de equipo |
| Catálogos | Recursos, Materiales, Mano de obra, Equipo, Matrices, Fletes, Subcontratos, Contratistas y proveedores, Equipo en obra |
| Avance | Órdenes de trabajo, Estimaciones, Registro de consumo, Estado de servicios, Pagos, Conceptos a estimar, Requisiciones |
| Bodega | Estado, Movimientos, Almacenes |
| Administración de proyectos | Estructura de costos, Estructura de organización, Valor ganado y curva S |

---

## Puesta en marcha

Requisitos: **Python 3.10 o superior** (probado en 3.12). No se necesita Node ni base de datos externa.

```bash
git clone https://github.com/<tu-usuario>/ezapu.git
cd ezapu

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

flask --app run init-db          # crea ezapu.db y carga la obra de ejemplo
python run.py                    # http://127.0.0.1:5000
```

`python run.py` crea la base automáticamente si no existe, así que basta con
ejecutarlo. Variables de entorno opcionales (ver `.env.example`):

| Variable | Descripción | Default |
|---|---|---|
| `EZAPU_DB` | ruta del archivo SQLite | `ezapu.db` en la raíz |
| `HOST` / `PORT` | dirección y puerto del servidor | `127.0.0.1` / `5000` |
| `SECRET_KEY` | clave para mensajes de sesión | valor de desarrollo |
| `FLASK_DEBUG` | `1` recarga en caliente | `1` |

### Comandos útiles

```bash
flask --app run init-db      # crea la base (no hace nada si ya existe)
flask --app run reset-db     # borra y recrea con datos de ejemplo
flask --app run sembrar      # carga la semilla si la base está vacía
python -m unittest discover -s tests   # 23 pruebas del dominio de cálculo
```

---

## Uso y publicación

### En tu computadora

```bash
git clone https://github.com/peregrinadiego-byte/ezapu.git
cd ezapu
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py                    # http://127.0.0.1:5000
```

`ezapu.db` se genera en tu máquina y **no se sube al repositorio** (está en
`.gitignore`).

### GitHub Codespaces

Abre el repositorio → *Code* → *Codespaces* → *Create*. La terminal ya incluye
Python: ejecuta `pip install -r requirements.txt && python run.py` y abre el
puerto 5000 cuando Codespaces te lo ofrezca.

### Docker (local o servidor)

```bash
docker build -t ezapu .
docker run --rm -p 5000:5000 -v ezapu-datos:/datos ezapu
```

### Publicar la aplicación en internet

El repositorio ya trae la configuración lista para los servicios que sí ejecutan Python:

| Servicio | Archivo | Notas |
|---|---|---|
| **Render** | `render.yaml` | *New +* → *Blueprint* → conecta el repositorio. Plan gratuito; su disco es efímero, así que la base se recrea en cada despliegue (para conservar los datos, agrega un disco y descomenta el bloque del `render.yaml`). |
| **Railway** | `Procfile` | Detecta `web: gunicorn wsgi:app …` sin configuración extra. |
| **Fly.io** | `Dockerfile` | `fly launch` y sigue el asistente. |
| **PythonAnywhere** | `wsgi.py` | Crea una *Web app* WSGI apuntando a `wsgi.py`. |
| **VPS propio** | `wsgi.py` | `gunicorn wsgi:app --bind 0.0.0.0:8000` detrás de Nginx. |

`wsgi.py` **crea y siembra la base automáticamente** si no existe, de modo que el
primer arranque en un servidor nuevo funcione sin pasos manuales.


## Modelo de datos

Un solo archivo SQLite con 25 tablas. Grupos principales:

* **Catálogos**: `unidad`, `familia`, `grupo`, `tercero`, `recurso`, `mano_obra`, `costo_horario`
* **Costos**: `matriz`, `matriz_detalle` (componentes: insumo o submatriz)
* **Presupuesto**: `proyecto`, `partida`, `concepto`, `generador`, `escalatoria`
* **Planeación y avance**: `tarea`, `contrato`, `contrato_concepto`, `orden_trabajo`,
  `estimacion`, `estimacion_detalle`, `pago`, `consumo`, `requisicion`, `requisicion_detalle`
* **Bodega**: `almacen`, `movimiento_bodega`
* **Administración**: `centro_costo`, `organizacion`, `equipo_en_obra`, `empresa`

Los precios **no se capturan dos veces**: el costo vigente de un insumo, el precio
unitario de una matriz y el importe de un concepto se calculan y se recalculan al
guardar cualquier cambio (`recalcular_todo`).

---

## Fórmulas implementadas

**Costo básico de mano de obra**

```
salario real = salario base × (1 + factor de prestaciones)
```

**Costo horario de equipo y herramienta**

```
depreciación  = (VM − VR) / vida útil
inversión     = ((VM + VR) / 2) × tasa de interés / horas por año
seguros       = ((VM + VR) / 2) × tasa de seguro / horas por año
mantenimiento = coeficiente de mantenimiento × VM / vida útil
reparaciones  = coeficiente de reparaciones × VM / vida útil
combustible   = consumo (l/h) × precio del combustible
lubricantes   = combustible × % de lubricantes
llantas       = costo de llantas / vida de las llantas
operador      = salario real del operador / horas del turno
costo horario = suma de todos los conceptos
```

**Matriz de precio unitario**

```
costo directo = Σ (rendimiento × costo del componente)
precio        = costo directo × (1 + indirectos propios)
```
Un componente puede ser un insumo o **otra matriz** (auxiliar), con detección de
referencias circulares.

**Análisis del precio del presupuesto**

```
indirectos, utilidad, financiamiento y cargos adicionales
  → sobre el costo directo (por omisión) o en cascada sobre el acumulado
subtotal = directo + indirectos + utilidad + financiamiento + cargos
total    = subtotal × (1 + IVA)
```

**Explosión de insumos**: abre recursivamente cada matriz del presupuesto y acumula
solo los insumos básicos (materiales, mano de obra, equipo, herramienta,
subcontratos y fletes) multiplicados por el volumen del concepto.

**Estimaciones**

```
importe          = cantidad de esta estimación × precio unitario
subtotal         = Σ importes
total            = subtotal + IVA − amortización de anticipo − retención
cantidad total   = cantidad anterior acumulada + cantidad de esta estimación
```

**Valor ganado**: PV, EV, AC, SV, CV, SPI, CPI, EAC, ETC, VAC y curva S, tomando el
importe de cada tarea como reparto del importe de su partida según su peso.

---

## Reportes

Todos los formatos se generan como HTML imprimible (botón *Imprimir / Guardar PDF*
del navegador, con hoja de estilo `@media print`) y además pueden exportarse a
CSV/Excel (llevan BOM UTF-8 para que Excel respete los acentos):

* Presupuesto de obra, catálogo de conceptos, explosión de insumos
* Análisis de precio unitario por matriz
* Estimación de obra con firmas, estado de cuenta
* Catálogo de insumos, inventario de bodega, reporte de valor ganado

---

## Pruebas

`tests/test_dominio.py` cubre el núcleo de cálculo con 23 casos: salario real,
partes del costo horario, merma de materiales, matrices anidadas, detección de
ciclos, sumatoria del presupuesto, indirectos sobre directo y sobre acumulado,
explosión de insumos, acumulados de estimaciones, existencias y costo promedio de
bodega, y los indicadores de valor ganado.

```bash
python -m unittest discover -s tests -v
```

---

## Alcance y siguientes pasos

Implementado: catálogos, costos básicos y horarios, matrices anidadas, presupuesto,
generadores, análisis del precio, explosión, programa de suministros, EDT con Gantt,
contratos, estimaciones con amortización y retención, pagos, consumos, requisiciones,
bodega con kardex y costo promedio, estructuras de costo y organización, valor ganado.

Ideas para extender:

* Usuarios y permisos, bitácora de cambios por obra.
* Importación/exportación de OPUS, Neodata y hojas de cálculo.
* Catálogos generales compartidos entre proyectos (catálogo universal).
* Programación con dependencias y ruta crítica (CPM) más allá del Gantt simple.
* Costos paramétricos de indirectos por personal y oficina central.
* Escalatorias aplicadas al importe de cada estimación.

## Licencia

MIT. Ver `LICENSE`.
