"""Rutas que comparten las herramientas.

Hay **dos** bases de datos en esta maquina: la del repositorio (la que usa
``python -m mukuwareru`` en desarrollo) y la de la aplicacion instalada, que es
la que tiene los datos del usuario. Toda herramienta que lee o escribe datos
reales apunta por defecto a la instalada, y la calcula aqui: cuando cada guion
la calculaba a su manera, unos escribian en una base y otros en la otra sin que
nada avisara.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from mukuwareru.utilidades.rutas import NOMBRE_APP  # noqa: E402


def carpeta_instalacion() -> Path:
    """Carpeta de instalacion habitual para una aplicacion de un solo usuario."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Programs" / NOMBRE_APP


def base_instalada() -> Path:
    """La base que usa de verdad el ejecutable instalado."""
    return carpeta_instalacion() / "datos" / "basedatos.db"
