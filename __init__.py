"""Registro central de blueprints."""
from __future__ import annotations


def registrar_blueprints(app) -> None:
    from .. import auth
    from . import (
        administracion,
        catalogos,
        control,
        main,
        matrices,
        planeacion,
        presupuesto,
        reportes,
    )

    app.register_blueprint(main.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(catalogos.bp)
    app.register_blueprint(matrices.bp)
    app.register_blueprint(presupuesto.bp)
    app.register_blueprint(planeacion.bp)
    app.register_blueprint(control.bp)
    app.register_blueprint(administracion.bp)
    app.register_blueprint(reportes.bp)
