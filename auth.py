"""Autenticación Google y creación de bases privadas por usuario."""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from authlib.integrations.flask_client import OAuth
from flask import Blueprint, current_app, redirect, render_template, session, url_for

bp = Blueprint("auth", __name__, url_prefix="/auth")
oauth = OAuth()


def init_auth(app) -> None:
    oauth.init_app(app)
    if app.config.get("GOOGLE_CLIENT_ID") and app.config.get("GOOGLE_CLIENT_SECRET"):
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    Path(app.config["AUTH_DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(app.config["AUTH_DATABASE"]) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS usuario (
            id INTEGER PRIMARY KEY, google_sub TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE, nombre TEXT NOT NULL,
            foto TEXT, creado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")


def create_user_database(path: Path, template: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        shutil.copy2(template, path)


@bp.route("/google")
def google_login():
    client = oauth.create_client("google")
    if client is None:
        return render_template("error.html", codigo=503,
                               mensaje="Google Login no está configurado."), 503
    return client.authorize_redirect(url_for("auth.google_callback", _external=True))


@bp.route("/google/callback")
def google_callback():
    client = oauth.create_client("google")
    token = client.authorize_access_token()
    userinfo = token.get("userinfo") or client.userinfo()
    with sqlite3.connect(current_app.config["AUTH_DATABASE"]) as con:
        row = con.execute("SELECT id FROM usuario WHERE google_sub = ?", (userinfo["sub"],)).fetchone()
        if row is None:
            cur = con.execute("INSERT INTO usuario (google_sub, email, nombre, foto) VALUES (?, ?, ?, ?)",
                              (userinfo["sub"], userinfo["email"], userinfo.get("name", userinfo["email"]), userinfo.get("picture")))
            user_id = cur.lastrowid
        else:
            user_id = row[0]
    session.clear()
    session["user_id"] = user_id
    session["user_email"] = userinfo["email"]
    session["user_name"] = userinfo.get("name", userinfo["email"])
    return redirect(url_for("main.inicio"))


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.inicio"))
