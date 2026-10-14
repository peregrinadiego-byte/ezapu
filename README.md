# EZAPU

Aplicación web para elaborar presupuestos y llevar el control de obras. Usa
Python, Flask y SQLite. No requiere Node.js ni una base de datos externa.

Proyecto independiente, sin relación con Ecosoft ni con OPUS.

## Elige cómo usarlo

- **En tu computadora:** instala Python y abre EZAPU en
  `http://127.0.0.1:5000`.
- **En internet:** publica el repositorio en Render y obtén una dirección
  pública para abrirlo desde cualquier navegador.
- **Con Docker:** ejecuta la aplicación en un contenedor local o en un servidor.

## Ejecutarlo en tu computadora

### Requisitos

- Python 3.10 o posterior; se recomienda Python 3.12.
- Git, o descargar el repositorio como ZIP.

### Linux o macOS

```bash
git clone https://github.com/peregrinadiego-byte/ezapu.git
cd ezapu
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

Abre <http://127.0.0.1:5000>.

### Windows PowerShell

```powershell
git clone https://github.com/peregrinadiego-byte/ezapu.git
cd ezapu
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

Abre <http://127.0.0.1:5000>.

Si PowerShell no permite activar el entorno, ejecuta directamente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

La primera ejecución crea `ezapu.db` y carga una obra de ejemplo. Para detener
el servidor presiona `Ctrl+C` en la terminal.

## Ejecutarlo con Docker

Requiere Docker instalado:

```bash
git clone https://github.com/peregrinadiego-byte/ezapu.git
cd ezapu
docker build -t ezapu .
docker run --rm -p 5000:5000 -v ezapu-datos:/datos ezapu
```

Abre <http://127.0.0.1:5000>. El volumen `ezapu-datos` conserva la base aunque
se detenga o se elimine el contenedor.

## Publicarlo en internet con Render

El repositorio ya incluye `render.yaml`, que configura la instalación y el
arranque de la aplicación.

1. Crea una cuenta en <https://render.com>.
2. Selecciona **New + → Blueprint**.
3. Conecta GitHub y elige `peregrinadiego-byte/ezapu`.
4. Confirma el servicio definido por `render.yaml`.
5. Espera a que termine el despliegue.
6. Abre la dirección `.onrender.com` que Render muestre para el servicio.

No necesitas ejecutar comandos en Render: se instalan las dependencias, se crea
la base si no existe y se inicia EZAPU automáticamente.

### Persistencia de datos en Render

Con el plan gratuito, el almacenamiento es efímero. La aplicación funciona,
pero los datos pueden reiniciarse después de un despliegue o reinicio. Para
datos reales, configura un disco persistente y conserva respaldos de `ezapu.db`.

## Qué incluye EZAPU

- Catálogos de materiales, mano de obra, equipo, proveedores y unidades.
- Costos básicos, costos horarios y matrices de precios unitarios.
- Proyectos, partidas, conceptos, generadores y presupuestos.
- Explosión de insumos y programa de suministros.
- Planeación, avance, contratos, estimaciones y pagos.
- Almacenes, movimientos y kardex.
- Valor ganado, reportes imprimibles y exportaciones CSV.

La aplicación inicia con datos demostrativos: proyecto, recursos, matrices,
conceptos, tareas, estimaciones y movimientos de bodega.

## Comandos administrativos

Con el entorno virtual activado:

```bash
flask --app run init-db   # crea la base si no existe
flask --app run sembrar   # carga datos si la base está vacía
flask --app run reset-db  # reemplaza la base con datos de ejemplo
```

`reset-db` reemplaza los datos actuales. Úsalo solo para reiniciar la
información.

## Configuración opcional

| Variable | Función | Predeterminado |
|---|---|---|
| `EZAPU_DB` | Ruta del archivo SQLite | `ezapu.db` |
| `HOST` | Dirección de escucha | `127.0.0.1` |
| `PORT` | Puerto | `5000` |
| `SECRET_KEY` | Clave de sesión | clave de desarrollo |
| `FLASK_DEBUG` | Recarga automática | `1` |

Para acceder desde otros dispositivos de tu red local:

```bash
HOST=0.0.0.0 python run.py
```

No expongas esta modalidad directamente a internet sin configurar seguridad y
un servidor de producción.

Si el puerto 5000 está ocupado:

```bash
PORT=5050 python run.py
```

En Windows PowerShell:

```powershell
$env:PORT=5050
python run.py
```

## Solución de problemas

**`python` no existe:** en Linux/macOS usa `python3`; en Windows usa `py`.

**Render falla:** revisa los registros. Debe instalar `requirements.txt` y
arrancar con `gunicorn wsgi:app`.

**Quiero comenzar de cero:** ejecuta `flask --app run reset-db`. Esto reemplaza
los datos actuales.

## Estructura principal

```text
run.py                 entrada para desarrollo local
wsgi.py                entrada para Render y Gunicorn
requirements.txt       dependencias de Python
Dockerfile             imagen Docker
render.yaml            configuración de Render
ezapu/
  __init__.py          creación de la aplicación Flask
  db.py                conexión e inicialización de SQLite
  schema.sql           estructura de la base
  seed.py              datos de ejemplo
  domain/              cálculos de costos y control
  blueprints/          rutas de la aplicación
  templates/           páginas HTML
  static/              estilos y JavaScript
```

## Licencia

MIT. Consulta [LICENSE](LICENSE).
