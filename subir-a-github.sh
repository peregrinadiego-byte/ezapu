#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# subir-a-github.sh · publica EZAPU en tu repositorio de GitHub
#
# Uso:
#   ./subir-a-github.sh https://github.com/<usuario>/ezapu.git
#
# Qué hace:
#   1 · comprueba que exista una identidad de Git (te la pide si falta y
#       reatribuye el commit inicial a tu nombre)
#   2 · registra el remoto "origin"
#   3 · asegura la rama "main" y muestra lo que se va a subir
#   4 · ejecuta git push -u origin main
# ---------------------------------------------------------------------------
set -euo pipefail

URL="${1:-}"
if [[ -z "$URL" ]]; then
  cat <<'AYUDA'
Falta la URL del repositorio.

  1. Crea en GitHub un repositorio VACÍO llamado "ezapu"
     (sin README, sin .gitignore, sin licencia).
  2. Ejecuta:

       ./subir-a-github.sh https://github.com/<tu-usuario>/ezapu.git

AYUDA
  exit 1
fi

if [[ ! -d .git ]]; then
  echo "Este directorio no es un repositorio Git. Ejecuta el script desde la raíz de EZAPU."
  exit 1
fi

# --- 1 · identidad ----------------------------------------------------------
NOMBRE="$(git config user.name || true)"
CORREO="$(git config user.email || true)"

if [[ -z "$NOMBRE" || -z "$CORREO" ]]; then
  echo "No hay identidad de Git configurada (ni global ni en este repositorio)."
  read -r -p "Tu nombre para los commits: " NOMBRE
  read -r -p "Tu correo de GitHub: " CORREO
  git config user.name "$NOMBRE"
  git config user.email "$CORREO"
  if git rev-parse HEAD >/dev/null 2>&1; then
    git commit --amend --reset-author --no-edit
    echo "Commit inicial reatribuido a $NOMBRE <$CORREO>."
  fi
else
  echo "Identidad de Git: $NOMBRE <$CORREO>"
fi

# --- 2 · remoto -------------------------------------------------------------
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$URL"
  echo "Remoto origin actualizado → $URL"
else
  git remote add origin "$URL"
  echo "Remoto origin agregado → $URL"
fi

# --- 3 · rama y revisión ----------------------------------------------------
git branch -M main
echo
echo "Rama: main · commits por subir:"
git log --oneline
echo
echo "Estado del árbol de trabajo:"
git status --short
echo

# --- 4 · push ---------------------------------------------------------------
git push -u origin main

echo
echo "Listo. Repositorio publicado en $URL"
