"""Arranque de Mukuwareru.

Secuencia: registro -> base de datos migrada -> tema -> contexto -> ventana.
Nada mas ocurre antes de que la ventana sea visible, para que la aplicacion
abra rapido.

**No hay siembra de proyectos.** Una instalacion nueva arranca vacia y muestra
la bienvenida (``ui/vistas/bienvenida.py``), que invita a crear el primero. Los
proyectos de ejemplo que hubo aqui obligaban a todo el mundo a heredar el
temario de otra persona y a borrarlo a mano.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from mukuwareru.contexto import Contexto
from mukuwareru.nucleo.bd import conexion as bd
from mukuwareru.ui import iconos
from mukuwareru.ui.tema import aplicar as aplicar_tema
from mukuwareru.ui.ventana_principal import VentanaPrincipal
from mukuwareru.utilidades import registro, rutas

_log = registro.obtener(__name__)


def main() -> int:
    """Punto de entrada. Devuelve el codigo de salida del proceso."""
    registro.configurar()
    _log.info("Mukuwareru arrancando (datos en %s)", rutas.raiz_datos())

    conn = bd.abrir(rutas.ruta_base_datos())

    app = QApplication(sys.argv)
    app.setApplicationName("Mukuwareru")
    app.setOrganizationName("Mukuwareru")
    app.setWindowIcon(iconos.icono_aplicacion())
    aplicar_tema(app)

    ventana = VentanaPrincipal(Contexto(conn))
    ventana.show()
    return app.exec()
