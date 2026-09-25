"""La prueba de humo de la interfaz, dentro de pytest.

``herramientas/humo.py`` recorre la aplicacion de verdad —ventana, vistas,
atajos, lector, Pomodoro— sobre una base temporal. Sus secciones dependen unas
de otras (el estado que deja una lo usa la siguiente), asi que se ejecuta entera
y en su propio proceso: con su ``QApplication`` y sin compartir nada con el
resto de los tests. Asi un solo ``pytest`` lo comprueba todo.

Se salta con ``pytest -m "not ui"`` cuando solo interesa el nucleo.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


@pytest.mark.ui
def test_la_interfaz_pasa_la_prueba_de_humo() -> None:
    entorno = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONIOENCODING": "utf-8"}
    resultado = subprocess.run(
        [sys.executable, str(RAIZ / "herramientas" / "humo.py")],
        cwd=RAIZ,
        env=entorno,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    fallos = [linea for linea in resultado.stdout.splitlines() if "FALLA" in linea]
    assert resultado.returncode == 0, (
        "\n".join(fallos) or (resultado.stdout[-3000:] + resultado.stderr[-3000:])
    )
