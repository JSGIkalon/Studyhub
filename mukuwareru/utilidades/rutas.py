"""Resolucion de rutas de la aplicacion.

La raiz de datos se calcula **una sola vez** al arrancar y se cachea. En
desarrollo vive junto al repositorio; congelada, junto al ejecutable, con
retroceso a ``%LOCALAPPDATA%`` cuando la carpeta del ejecutable es de solo
lectura (por ejemplo, instalado en *Program Files*).
"""

from __future__ import annotations

import os
import sys
from functools import cache
from pathlib import Path

NOMBRE_APP = "Mukuwareru"


def esta_congelada() -> bool:
    """Indica si la aplicacion corre empaquetada por PyInstaller."""
    return getattr(sys, "frozen", False)


def _es_escribible(carpeta: Path) -> bool:
    """Comprueba de forma real si se puede escribir en ``carpeta``."""
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        testigo = carpeta / ".escritura"
        testigo.write_text("", encoding="utf-8")
        testigo.unlink()
    except OSError:
        return False
    return True


@cache
def raiz_datos() -> Path:
    """Devuelve la carpeta raiz donde viven los datos del usuario.

    Es la carpeta que **nunca** debe tocar una actualizacion del ejecutable.
    """
    if esta_congelada():
        junto_al_exe = Path(sys.executable).resolve().parent
        if _es_escribible(junto_al_exe / "datos"):
            return junto_al_exe
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / NOMBRE_APP
    # En desarrollo: la raiz del repositorio (mukuwareru/utilidades -> ../..).
    return Path(__file__).resolve().parents[2]


def carpeta_datos() -> Path:
    """Carpeta ``datos/``: base de datos y ajustes de arranque."""
    return _asegurar(raiz_datos() / "datos")


def carpeta_biblioteca() -> Path:
    """Carpeta ``Library/``: raiz por defecto de las bibliotecas PDF."""
    return _asegurar(raiz_datos() / "Library")


def carpeta_registros() -> Path:
    """Carpeta ``logs/``."""
    return _asegurar(raiz_datos() / "logs")


def ruta_base_datos() -> Path:
    """Ruta del archivo SQLite."""
    return carpeta_datos() / "basedatos.db"


def ruta_ajustes_arranque() -> Path:
    """Ruta del JSON con lo poco que se necesita antes de abrir la BD."""
    return carpeta_datos() / "ajustes.json"


def _asegurar(carpeta: Path) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta
