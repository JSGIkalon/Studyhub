"""Tarjeta de metrica: una sola cifra, grande y legible de un vistazo."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from mukuwareru.ui import iconos
from mukuwareru.ui.tema import tokens
from mukuwareru.ui.widgets.contenedor import contenedor, vaciar
from mukuwareru.ui.widgets.tarjeta import Tarjeta


class TarjetaMetrica(Tarjeta):
    """Icono y titulo arriba, cifra grande en medio, aclaracion abajo."""

    def __init__(
        self,
        titulo: str,
        icono: str,
        color: str = tokens.ACENTO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._color = color
        self.setMinimumWidth(178)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._construir(titulo, icono)

    def _construir(self, titulo: str, nombre_icono: str) -> None:
        cabecera = QHBoxLayout()
        cabecera.setSpacing(tokens.ESPACIO_PEQUENO)

        simbolo = QLabel()
        simbolo.setPixmap(iconos.pixmap(nombre_icono, self._color, 18))
        cabecera.addWidget(simbolo)

        etiqueta = QLabel(titulo)
        etiqueta.setObjectName("TextoSuave")
        cabecera.addWidget(etiqueta)
        cabecera.addStretch(1)

        self.contenido.addWidget(contenedor(cabecera))

        self._valor = QLabel("—")
        fuente = QFont(tokens.FUENTE, tokens.TAM_METRICA)
        fuente.setWeight(QFont.Weight.Bold)
        self._valor.setFont(fuente)
        self.contenido.addWidget(self._valor)

        self._aclaracion = QLabel("")
        self._aclaracion.setObjectName("TextoTenue")
        self.contenido.addWidget(self._aclaracion)

    def establecer(self, valor: str, aclaracion: str = "", color: str | None = None) -> None:
        """Actualiza la cifra y su aclaracion."""
        self._valor.setText(valor)
        self._valor.setStyleSheet(f"color: {color};" if color else "")
        self._aclaracion.setText(aclaracion)


class ListaResumen(Tarjeta):
    """Tarjeta con una lista corta de dos columnas y su estado vacio.

    Con ``pista`` las filas son clicables y emiten ``elegido`` con su indice.
    """

    elegido = Signal(int)

    def __init__(
        self, titulo: str, vacio: str, parent: QWidget | None = None, *, pista: str = ""
    ) -> None:
        super().__init__(titulo, parent)
        self._vacio = vacio
        self._pista = pista
        self._filas = QVBoxLayout()
        self._filas.setSpacing(2)
        self.contenido.addWidget(contenedor(self._filas))
        self.contenido.addStretch(1)

    def establecer(self, elementos: list[tuple[str, str]]) -> None:
        """Reemplaza el contenido. Una lista vacia muestra el mensaje de vacio."""
        vaciar(self._filas)

        if not elementos:
            aviso = QLabel(self._vacio)
            aviso.setObjectName("TextoTenue")
            aviso.setWordWrap(True)
            self._filas.addWidget(aviso)
            return

        for indice, (izquierda, derecha) in enumerate(elementos):
            fila = _fila(izquierda, derecha)
            if self._pista:
                fila.setCursor(Qt.CursorShape.PointingHandCursor)
                fila.setToolTip(self._pista)
                fila.pulsada.connect(lambda i=indice: self.elegido.emit(i))
            self._filas.addWidget(fila)


class _Fila(QWidget):
    """Fila de ``ListaResumen``; emite ``pulsada`` al hacer clic."""

    pulsada = Signal()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        if event.button() is Qt.MouseButton.LeftButton:
            self.pulsada.emit()
        super().mouseReleaseEvent(event)


def _fila(izquierda: str, derecha: str) -> _Fila:
    caja = QHBoxLayout()
    caja.setContentsMargins(0, 3, 0, 3)
    caja.setSpacing(tokens.ESPACIO_PEQUENO)

    principal = QLabel(izquierda)
    principal.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    principal.setWordWrap(False)
    caja.addWidget(principal, 1)

    secundario = QLabel(derecha)
    secundario.setObjectName("TextoTenue")
    caja.addWidget(secundario, 0, Qt.AlignmentFlag.AlignRight)

    fila = _Fila()
    fila.setObjectName("Transparente")  # como `contenedor`: sin fondo propio
    fila.setLayout(caja)
    return fila
