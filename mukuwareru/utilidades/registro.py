"""Configuracion del registro (logging) de la aplicacion."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from mukuwareru.utilidades import rutas

_FORMATO = "%(asctime)s  %(levelname)-7s  %(name)-28s  %(message)s"
_configurado = False


def configurar(nivel: int = logging.INFO) -> None:
    """Instala los manejadores de registro. Idempotente."""
    global _configurado
    if _configurado:
        return

    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    formato = logging.Formatter(_FORMATO, datefmt="%Y-%m-%d %H:%M:%S")

    archivo = RotatingFileHandler(
        rutas.carpeta_registros() / "mukuwareru.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    archivo.setFormatter(formato)
    raiz.addHandler(archivo)

    # Sin consola cuando esta congelada: no hay terminal donde escribir.
    if not rutas.esta_congelada():
        consola = logging.StreamHandler(sys.stderr)
        consola.setFormatter(formato)
        raiz.addHandler(consola)

    _configurado = True


def obtener(nombre: str) -> logging.Logger:
    """Atajo para pedir un logger con el nombre del modulo."""
    return logging.getLogger(nombre)
