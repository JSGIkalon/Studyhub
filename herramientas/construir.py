"""Compila Mukuwareru.

    python herramientas/construir.py

**Nada de la compilacion ocurre dentro del proyecto.** Tanto los archivos
intermedios como el resultado se generan bajo el directorio temporal del
sistema, porque el proyecto vive en OneDrive y eso trae dos problemas reales:

1. La sincronizacion mantiene abiertos los archivos que acaba de subir, y
   PyInstaller falla con ``PermissionError`` al vaciar su carpeta de salida.
2. Cada compilacion subiria ~130 MB de artefactos a la nube sin ninguna razon.

El resultado se estrena con ``herramientas/instalar.py``, que copia el
ejecutable a la carpeta de uso diario conservando ``datos/``.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent

_TEMP = Path(tempfile.gettempdir())
TRABAJO = _TEMP / "mukuwareru-build"      # archivos intermedios de PyInstaller
SALIDA = _TEMP / "mukuwareru-dist"        # carpeta que PyInstaller vacia y rellena
COMPILADO = SALIDA / "Mukuwareru"         # el resultado en si


def main() -> int:
    """Ejecuta PyInstaller y deja la compilacion lista para instalar."""
    borrar(TRABAJO)
    borrar(SALIDA)

    resultado = subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            str(RAIZ / "herramientas" / "mukuwareru.spec"),
            "--noconfirm",
            "--distpath", str(SALIDA),
            "--workpath", str(TRABAJO),
        ],
        cwd=RAIZ,
        check=False,
    )
    if resultado.returncode != 0:
        return resultado.returncode

    borrar(TRABAJO)
    tamano = sum(f.stat().st_size for f in COMPILADO.rglob("*") if f.is_file())
    print(f"\nCompilado en: {COMPILADO}")
    print(f"Tamano: {tamano / 1024 / 1024:.0f} MB")
    print("\nSiguiente paso:  python herramientas/instalar.py")
    return 0


def borrar(ruta: Path) -> None:
    """Borra un archivo o arbol, sorteando bloqueos de solo lectura."""
    if not ruta.exists():
        return
    if ruta.is_file():
        ruta.unlink(missing_ok=True)
        return
    shutil.rmtree(ruta, onexc=_forzar_borrado)


def _forzar_borrado(funcion: Any, ruta: Any, _error: BaseException) -> None:
    """Quita el atributo de solo lectura y reintenta una vez."""
    try:
        Path(ruta).chmod(stat.S_IWRITE)
        funcion(ruta)
    except OSError as fallo:
        print(f"  aviso: no se pudo borrar {ruta} ({fallo.strerror})")


if __name__ == "__main__":
    sys.exit(main())
