"""Fábrica de la aplicación EZAPU."""
from __future__ import annotations

import datetime as _dt

from flask import Flask, render_template, request, session, redirect, url_for
from jinja2 import StrictUndefined

from . import db
from .config import Config
from .domain.util import TIPOS_RECURSO

__version__ = "1.0.0"


# ---------------------------------------------------------------- filtros ---
def _fmt_num(valor, decimales=2):
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        return valor
    texto = f"{numero:,.{decimales}f}"
    return texto


def _fmt_qty(valor):
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        return valor
    if numero == int(numero):
        return f"{int(numero):,}"
    return f"{numero:,.4f}".rstrip("0").rstrip(".")


def _fmt_fecha(valor, formato="%d/%m/%Y"):
    if not valor:
        return ""
    texto = str(valor)[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return _dt.datetime.strptime(texto, fmt).strftime(formato)
        except ValueError:
            continue
    return texto


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.jinja_env.undefined = StrictUndefined
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    app.jinja_env.filters["money"] = _fmt_num
    app.jinja_env.filters["num"] = _fmt_num
    app.jinja_env.filters["qty"] = _fmt_qty
    app.jinja_env.filters["fecha"] = _fmt_fecha
    app.jinja_env.globals["TIPOS_RECURSO"] = TIPOS_RECURSO

    db.register(app)

    from .auth import init_auth
    init_auth(app)

    from .blueprints import registrar_blueprints
    from .ui import construir_nav

    registrar_blueprints(app)

    @app.before_request
    def _requiere_login():
        if request.endpoint and (request.endpoint.startswith("auth.") or
                                 request.endpoint == "static"):
            return None
        if "user_id" not in session:
            return redirect(url_for("auth.google_login"))
        return None

    @app.context_processor
    def _contexto():
        return {
            "nav": construir_nav(),
            "version_app": __version__,
            "fecha_generacion": _dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
            "proyecto_activo": request.args.get("proyecto_id", type=int),
        }

    @app.errorhandler(404)
    def _no_encontrado(_e):
        return render_template("error.html", codigo=404,
                               mensaje="No se encontró el recurso solicitado."), 404

    @app.errorhandler(500)
    def _error_interno(_e):
        return render_template("error.html", codigo=500,
                               mensaje="Ocurrió un error inesperado."), 500

    return app
