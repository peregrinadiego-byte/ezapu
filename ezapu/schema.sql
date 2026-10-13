-- ============================================================================
--  EZAPU · Esquema de base de datos (SQLite)
--  Modelo inspirado en la estructura funcional de OPUS (Ecosoft):
--    M1 = Propuestas / Presupuestos   ·   M2 = Control de obra
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- empresa ---
CREATE TABLE IF NOT EXISTS empresa (
  id            INTEGER PRIMARY KEY,
  nombre        TEXT NOT NULL,
  rfc           TEXT,
  direccion     TEXT,
  telefono      TEXT,
  email         TEXT,
  moneda        TEXT DEFAULT 'MXN',
  iva_pct       REAL DEFAULT 16.0
);

-- ------------------------------------------------------------- catálogos ---
CREATE TABLE IF NOT EXISTS unidad (
  id            INTEGER PRIMARY KEY,
  clave         TEXT NOT NULL UNIQUE,
  nombre        TEXT,
  tipo          TEXT
);

CREATE TABLE IF NOT EXISTS familia (
  id            INTEGER PRIMARY KEY,
  clave         TEXT NOT NULL UNIQUE,
  nombre        TEXT,
  tipo          TEXT
);

CREATE TABLE IF NOT EXISTS grupo (
  id            INTEGER PRIMARY KEY,
  clave         TEXT NOT NULL UNIQUE,
  nombre        TEXT,
  familia_id    INTEGER REFERENCES familia(id) ON DELETE SET NULL
);

-- clientes | proveedores | contratistas
CREATE TABLE IF NOT EXISTS tercero (
  id            INTEGER PRIMARY KEY,
  clave         TEXT UNIQUE,
  nombre        TEXT NOT NULL,
  rfc           TEXT,
  tipo          TEXT NOT NULL DEFAULT 'proveedor',
  contacto      TEXT,
  telefono      TEXT,
  email         TEXT,
  direccion     TEXT,
  especialidad  TEXT,
  notas         TEXT
);

-- ------------------------------------------------------------- proyectos ---
CREATE TABLE IF NOT EXISTS proyecto (
  id                    INTEGER PRIMARY KEY,
  clave                 TEXT NOT NULL UNIQUE,
  nombre                TEXT NOT NULL,
  cliente_id            INTEGER REFERENCES tercero(id) ON DELETE SET NULL,
  tipo                  TEXT DEFAULT 'propuesta',   -- propuesta | catalogo | control
  ubicacion             TEXT,
  moneda                TEXT DEFAULT 'MXN',
  fecha_apertura        TEXT,
  fecha_cierre          TEXT,
  estado                TEXT DEFAULT 'abierto',
  -- Análisis del precio (M1 · Análisis económico)
  pct_indirectos        REAL DEFAULT 0,
  pct_utilidad          REAL DEFAULT 0,
  pct_financiamiento    REAL DEFAULT 0,
  pct_cargos_adicionales REAL DEFAULT 0,
  pct_iva               REAL DEFAULT 16,
  base_indirectos       TEXT DEFAULT 'directo',     -- directo | acumulado
  -- Condiciones de cobro (M2)
  anticipo_pct          REAL DEFAULT 0,
  retencion_pct         REAL DEFAULT 0,
  amortizacion_pct      REAL DEFAULT 100,
  notas                 TEXT
);

-- ------------------------------------------------- matrices / precios u. ---
CREATE TABLE IF NOT EXISTS matriz (
  id                 INTEGER PRIMARY KEY,
  clave              TEXT NOT NULL UNIQUE,
  descripcion        TEXT NOT NULL,
  tipo               TEXT NOT NULL DEFAULT 'pu',   -- basica | costo_horario | auxiliar | pu
  unidad_id          INTEGER REFERENCES unidad(id) ON DELETE SET NULL,
  proyecto_id        INTEGER REFERENCES proyecto(id) ON DELETE CASCADE,
  costo_directo      REAL DEFAULT 0,
  costo_indirecto_pct REAL DEFAULT 0,
  notas              TEXT
);

-- --------------------------------------------------------- catálogo insumos
CREATE TABLE IF NOT EXISTS recurso (
  id            INTEGER PRIMARY KEY,
  clave         TEXT NOT NULL UNIQUE,
  descripcion   TEXT NOT NULL,
  tipo          TEXT NOT NULL DEFAULT 'material',
                -- material | mano_obra | equipo | herramienta | subcontrato | flete | auxiliar
  unidad_id     INTEGER REFERENCES unidad(id) ON DELETE SET NULL,
  familia_id    INTEGER REFERENCES familia(id) ON DELETE SET NULL,
  grupo_id      INTEGER REFERENCES grupo(id) ON DELETE SET NULL,
  proveedor_id  INTEGER REFERENCES tercero(id) ON DELETE SET NULL,
  costo_base    REAL DEFAULT 0,
  moneda        TEXT DEFAULT 'MXN',
  merma_pct     REAL DEFAULT 0,
  matriz_id     INTEGER REFERENCES matriz(id) ON DELETE SET NULL,  -- solo 'auxiliar'
  fecha_precio  TEXT,
  notas         TEXT,
  activo        INTEGER DEFAULT 1
);

-- Costo básico de mano de obra: salario real = salario base x (1 + FSR)
CREATE TABLE IF NOT EXISTS mano_obra (
  id                  INTEGER PRIMARY KEY,
  recurso_id          INTEGER NOT NULL UNIQUE REFERENCES recurso(id) ON DELETE CASCADE,
  salario_base        REAL DEFAULT 0,
  factor_prestaciones REAL DEFAULT 0,
  horas_turno         REAL DEFAULT 8,
  cuadrilla           TEXT,
  costo_basico        REAL DEFAULT 0,
  notas               TEXT
);

-- Costo horario de equipo y herramienta
CREATE TABLE IF NOT EXISTS costo_horario (
  id                    INTEGER PRIMARY KEY,
  recurso_id            INTEGER NOT NULL UNIQUE REFERENCES recurso(id) ON DELETE CASCADE,
  valor_maquina         REAL DEFAULT 0,     -- VM
  valor_rescate         REAL DEFAULT 0,     -- VR
  vida_util             REAL DEFAULT 0,     -- horas
  horas_anuales         REAL DEFAULT 0,
  tasa_interes          REAL DEFAULT 0,     -- %
  tasa_seguro           REAL DEFAULT 0,     -- %
  coef_mantenimiento    REAL DEFAULT 0,     -- fracción de VM / vida útil
  coef_reparaciones     REAL DEFAULT 0,     -- fracción de VM / vida útil
  consumo_combustible   REAL DEFAULT 0,     -- l/h
  precio_combustible    REAL DEFAULT 0,
  pct_lubricantes       REAL DEFAULT 0,     -- % del combustible
  costo_llantas         REAL DEFAULT 0,
  vida_llantas          REAL DEFAULT 0,     -- horas
  recurso_operador_id   INTEGER REFERENCES recurso(id) ON DELETE SET NULL,
  costo_operador        REAL DEFAULT 0,     -- $/h (si no se liga un recurso)
  incluye_operador      INTEGER DEFAULT 1,
  costo_otros           REAL DEFAULT 0,
  manual                INTEGER DEFAULT 0,  -- 1 = usar costo_total tal cual
  costo_total           REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS matriz_detalle (
  id            INTEGER PRIMARY KEY,
  matriz_id     INTEGER NOT NULL REFERENCES matriz(id) ON DELETE CASCADE,
  recurso_id    INTEGER REFERENCES recurso(id) ON DELETE CASCADE,
  submatriz_id  INTEGER REFERENCES matriz(id) ON DELETE CASCADE,
  cantidad      REAL NOT NULL DEFAULT 1,    -- rendimiento por unidad
  orden         INTEGER DEFAULT 0,
  notas         TEXT
);

-- ----------------------------------------------------------- presupuesto ---
CREATE TABLE IF NOT EXISTS partida (
  id            INTEGER PRIMARY KEY,
  proyecto_id   INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
  parent_id     INTEGER REFERENCES partida(id) ON DELETE CASCADE,
  clave         TEXT,
  nombre        TEXT NOT NULL,
  nivel         INTEGER DEFAULT 1,
  orden         INTEGER DEFAULT 0,
  notas         TEXT
);

CREATE TABLE IF NOT EXISTS concepto (
  id            INTEGER PRIMARY KEY,
  proyecto_id   INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
  partida_id    INTEGER REFERENCES partida(id) ON DELETE SET NULL,
  clave         TEXT,
  descripcion   TEXT NOT NULL,
  unidad_id     INTEGER REFERENCES unidad(id) ON DELETE SET NULL,
  matriz_id     INTEGER REFERENCES matriz(id) ON DELETE SET NULL,
  cantidad      REAL DEFAULT 0,
  pu            REAL DEFAULT 0,
  importe       REAL DEFAULT 0,
  orden         INTEGER DEFAULT 0,
  notas         TEXT
);

-- Números generadores de volumen
CREATE TABLE IF NOT EXISTS generador (
  id            INTEGER PRIMARY KEY,
  concepto_id   INTEGER NOT NULL REFERENCES concepto(id) ON DELETE CASCADE,
  descripcion   TEXT,
  veces         REAL DEFAULT 1,
  largo         REAL DEFAULT 0,
  ancho         REAL DEFAULT 0,
  alto          REAL DEFAULT 0,
  total         REAL DEFAULT 0,
  orden         INTEGER DEFAULT 0
);

-- ---------------------------------------------- M2 · planeación / tareas ---
CREATE TABLE IF NOT EXISTS tarea (
  id            INTEGER PRIMARY KEY,
  proyecto_id   INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
  parent_id     INTEGER REFERENCES tarea(id) ON DELETE CASCADE,
  partida_id    INTEGER REFERENCES partida(id) ON DELETE SET NULL,
  clave         TEXT,
  nombre        TEXT NOT NULL,
  nivel         INTEGER DEFAULT 1,
  inicio        TEXT,
  fin           TEXT,
  duracion      REAL DEFAULT 0,
  predecesora_id INTEGER REFERENCES tarea(id) ON DELETE SET NULL,
  avance        REAL DEFAULT 0,       -- %
  peso          REAL DEFAULT 1,
  responsable   TEXT,
  estado        TEXT DEFAULT 'planeado',
  orden         INTEGER DEFAULT 0,
  notas         TEXT
);

-- ------------------------------------------------ M2 · contratos / OT -----
CREATE TABLE IF NOT EXISTS contrato (
  id            INTEGER PRIMARY KEY,
  proyecto_id   INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
  tercero_id    INTEGER REFERENCES tercero(id) ON DELETE SET NULL,
  numero        TEXT,
  tipo          TEXT DEFAULT 'obra',   -- obra|tarea|equipos|fletes|suministro|servicios
  descripcion   TEXT,
  fecha         TEXT,
  monto         REAL DEFAULT 0,
  anticipo_pct  REAL DEFAULT 0,
  retencion_pct REAL DEFAULT 0,
  moneda        TEXT DEFAULT 'MXN',
  estatus       TEXT DEFAULT 'abierto',
  notas         TEXT
);

CREATE TABLE IF NOT EXISTS contrato_concepto (
  id            INTEGER PRIMARY KEY,
  contrato_id   INTEGER NOT NULL REFERENCES contrato(id) ON DELETE CASCADE,
  concepto_id   INTEGER REFERENCES concepto(id) ON DELETE SET NULL,
  clave         TEXT,
  descripcion   TEXT,
  unidad_id     INTEGER REFERENCES unidad(id) ON DELETE SET NULL,
  cantidad      REAL DEFAULT 0,
  pu            REAL DEFAULT 0,
  importe       REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orden_trabajo (
  id            INTEGER PRIMARY KEY,
  proyecto_id   INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
  contrato_id   INTEGER REFERENCES contrato(id) ON DELETE SET NULL,
  tarea_id      INTEGER REFERENCES tarea(id) ON DELETE SET NULL,
  folio         TEXT,
  fecha         TEXT,
  descripcion   TEXT,
  monto         REAL DEFAULT 0,
  estado        TEXT DEFAULT 'abierta',   -- abierta|en_proceso|cerrada
  notas         TEXT
);

-- ------------------------------------------------------ M2 · avance -------
CREATE TABLE IF NOT EXISTS estimacion (
  id                 INTEGER PRIMARY KEY,
  proyecto_id        INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
  contrato_id        INTEGER REFERENCES contrato(id) ON DELETE SET NULL,
  numero             TEXT,
  tipo               TEXT DEFAULT 'cobrar',   -- cobrar | pagar | proforma
  periodo_inicio     TEXT,
  periodo_fin        TEXT,
  fecha              TEXT,
  subtotal           REAL DEFAULT 0,
  iva                REAL DEFAULT 0,
  amortizacion       REAL DEFAULT 0,
  retencion          REAL DEFAULT 0,
  total              REAL DEFAULT 0,
  estatus            TEXT DEFAULT 'borrador',  -- borrador|enviada|autorizada|pagada
  notas              TEXT
);

CREATE TABLE IF NOT EXISTS estimacion_detalle (
  id                INTEGER PRIMARY KEY,
  estimacion_id     INTEGER NOT NULL REFERENCES estimacion(id) ON DELETE CASCADE,
  concepto_id       INTEGER REFERENCES concepto(id) ON DELETE CASCADE,
  clave             TEXT,
  descripcion       TEXT,
  unidad            TEXT,
  cantidad_anterior REAL DEFAULT 0,
  cantidad_actual   REAL DEFAULT 0,
  cantidad_total    REAL DEFAULT 0,
  pu                REAL DEFAULT 0,
  importe           REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pago (
  id            INTEGER PRIMARY KEY,
  estimacion_id INTEGER REFERENCES estimacion(id) ON DELETE CASCADE,
  proyecto_id   INTEGER REFERENCES proyecto(id) ON DELETE CASCADE,
  fecha         TEXT,
  monto         REAL DEFAULT 0,
  referencia    TEXT,
  medio         TEXT DEFAULT 'transferencia',
  notas         TEXT
);

-- Registro de consumo de insumos en obra  → "Estado de servicios"
CREATE TABLE IF NOT EXISTS consumo (
  id            INTEGER PRIMARY KEY,
  proyecto_id   INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
  tarea_id      INTEGER REFERENCES tarea(id) ON DELETE SET NULL,
  recurso_id    INTEGER REFERENCES recurso(id) ON DELETE SET NULL,
  fecha         TEXT,
  cantidad      REAL DEFAULT 0,
  costo_unitario REAL DEFAULT 0,
  costo         REAL DEFAULT 0,
  documento     TEXT,
  notas         TEXT
);

CREATE TABLE IF NOT EXISTS requisicion (
  id            INTEGER PRIMARY KEY,
  proyecto_id   INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
  folio         TEXT,
  fecha         TEXT,
  solicitante   TEXT,
  estado        TEXT DEFAULT 'solicitada',  -- solicitada|autorizada|surtida|cancelada
  notas         TEXT
);

CREATE TABLE IF NOT EXISTS requisicion_detalle (
  id            INTEGER PRIMARY KEY,
  requisicion_id INTEGER NOT NULL REFERENCES requisicion(id) ON DELETE CASCADE,
  recurso_id    INTEGER REFERENCES recurso(id) ON DELETE SET NULL,
  cantidad      REAL DEFAULT 0,
  cantidad_surtida REAL DEFAULT 0,
  unidad        TEXT,
  notas         TEXT
);

-- ------------------------------------------------------ M2 · bodega -------
CREATE TABLE IF NOT EXISTS almacen (
  id            INTEGER PRIMARY KEY,
  clave         TEXT NOT NULL UNIQUE,
  nombre        TEXT,
  proyecto_id   INTEGER REFERENCES proyecto(id) ON DELETE CASCADE,
  ubicacion     TEXT,
  responsable   TEXT,
  activo        INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS movimiento_bodega (
  id            INTEGER PRIMARY KEY,
  almacen_id    INTEGER NOT NULL REFERENCES almacen(id) ON DELETE CASCADE,
  recurso_id    INTEGER NOT NULL REFERENCES recurso(id) ON DELETE CASCADE,
  tipo          TEXT NOT NULL DEFAULT 'entrada',  -- entrada|salida|ajuste
  fecha         TEXT,
  cantidad      REAL DEFAULT 0,
  costo_unitario REAL DEFAULT 0,
  documento     TEXT,
  tercero_id    INTEGER REFERENCES tercero(id) ON DELETE SET NULL,
  tarea_id      INTEGER REFERENCES tarea(id) ON DELETE SET NULL,
  notas         TEXT
);

-- ------------------------------------- M2 · administración de proyectos ---
CREATE TABLE IF NOT EXISTS centro_costo (
  id            INTEGER PRIMARY KEY,
  proyecto_id   INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
  parent_id     INTEGER REFERENCES centro_costo(id) ON DELETE CASCADE,
  clave         TEXT,
  nombre        TEXT NOT NULL,
  nivel         INTEGER DEFAULT 1,
  presupuesto   REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS organizacion (
  id            INTEGER PRIMARY KEY,
  proyecto_id   INTEGER REFERENCES proyecto(id) ON DELETE CASCADE,
  parent_id     INTEGER REFERENCES organizacion(id) ON DELETE CASCADE,
  clave         TEXT,
  nombre        TEXT NOT NULL,
  responsable   TEXT,
  nivel         INTEGER DEFAULT 1
);

-- Planeación de equipo en obra
CREATE TABLE IF NOT EXISTS equipo_en_obra (
  id               INTEGER PRIMARY KEY,
  proyecto_id      INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
  recurso_id       INTEGER REFERENCES recurso(id) ON DELETE SET NULL,
  tarea_id         INTEGER REFERENCES tarea(id) ON DELETE SET NULL,
  tercero_id       INTEGER REFERENCES tercero(id) ON DELETE SET NULL,
  fecha_inicio     TEXT,
  fecha_fin        TEXT,
  horas_planeadas  REAL DEFAULT 0,
  horas_reales     REAL DEFAULT 0,
  costo_hora       REAL DEFAULT 0,
  notas            TEXT
);

-- Escalatorias / ajustes de costos por periodo
CREATE TABLE IF NOT EXISTS escalatoria (
  id            INTEGER PRIMARY KEY,
  proyecto_id   INTEGER NOT NULL REFERENCES proyecto(id) ON DELETE CASCADE,
  periodo       TEXT,
  factor        REAL DEFAULT 1,
  notas         TEXT
);

-- ------------------------------------------------------------------ índices -
CREATE INDEX IF NOT EXISTS ix_recurso_tipo    ON recurso(tipo);
CREATE INDEX IF NOT EXISTS ix_matriz_det_mat   ON matriz_detalle(matriz_id);
CREATE INDEX IF NOT EXISTS ix_concepto_proy    ON concepto(proyecto_id);
CREATE INDEX IF NOT EXISTS ix_concepto_matriz  ON concepto(matriz_id);
CREATE INDEX IF NOT EXISTS ix_tarea_proy       ON tarea(proyecto_id);
CREATE INDEX IF NOT EXISTS ix_est_proy         ON estimacion(proyecto_id);
CREATE INDEX IF NOT EXISTS ix_estdet_est       ON estimacion_detalle(estimacion_id);
CREATE INDEX IF NOT EXISTS ix_mov_alm          ON movimiento_bodega(almacen_id, recurso_id);
