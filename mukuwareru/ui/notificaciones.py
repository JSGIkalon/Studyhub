"""Avisos del sistema.

Se apoya en ``QSystemTrayIcon``, que en Windows produce una notificacion nativa
sin dependencias ni conexion. La bandeja es el unico camino que ofrece Qt para
avisar cuando la ventana esta minimizada, que es justo cuando hace falta.

Todo el modulo esta escrito para no estorbar: si el escritorio no tiene bandeja
(sesion remota, algunos escritorios de Linux) las llamadas no hacen nada y la
aplicacion sigue funcionando igual.
"""

from __future__ import annotations

from PySide6.QtWidgets import QSystemTrayIcon, QWidget

from mukuwareru.ui import iconos
from mukuwareru.utilidades.registro import obtener

_log = obtener(__name__)
_DURACION_MS = 6000


class Notificador:
    """Envia avisos del sistema, o los ignora si no hay bandeja."""

    def __init__(self, parent: QWidget | None = None) -> None:
        self._bandeja: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            _log.info("Sin bandeja del sistema: no habra notificaciones")
            return

        self._bandeja = QSystemTrayIcon(iconos.icono_aplicacion(), parent)
        self._bandeja.setToolTip("Mukuwareru")
        self._bandeja.show()

    @property
    def disponible(self) -> bool:
        """Si el escritorio admite notificaciones."""
        return self._bandeja is not None

    def notificar(self, titulo: str, mensaje: str) -> None:
        """Muestra un aviso del sistema. Sin bandeja, no hace nada."""
        if self._bandeja is None:
            return
        self._bandeja.showMessage(
            titulo, mensaje, iconos.icono_aplicacion(), _DURACION_MS
        )
        _log.info("Aviso: %s - %s", titulo, mensaje)

    def cerrar(self) -> None:
        """Retira el icono de la bandeja al salir."""
        if self._bandeja is not None:
            self._bandeja.hide()
            self._bandeja = None
