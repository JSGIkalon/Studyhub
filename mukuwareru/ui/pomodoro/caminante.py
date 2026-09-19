"""El personaje que recorre el timeline.

Es la unica animacion de Mukuwareru, y esta acotada a proposito: solo cambia de
posicion. Dentro de un bloque se desliza con el progreso, una vez por segundo y
sin animar; al cambiar de bloque el salto se suaviza con una interpolacion de
320 ms. Nada mas se mueve, nada parpadea y nada pide atencion.

Si el PNG del personaje no esta —se genera con
``herramientas/preparar_personaje.py``— se pinta un marcador redondo con el color
de la fase, y el timeline sigue siendo legible.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRectF,
    Qt,
)
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from mukuwareru.ui import iconos
from mukuwareru.ui.tema import tokens

ALTO = 46
ANCHO = 34
_DURACION_MS = 320


class Caminante(QWidget):
    """Silueta con sombra que marca por donde va el recorrido."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Caminante")
        self.setFixedSize(ANCHO, ALTO)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setToolTip("Por aqui vas")

        self._color = tokens.ACENTO
        self._mapa = iconos.personaje(ALTO - 7)
        self._animacion = QPropertyAnimation(self, b"pos", self)
        self._animacion.setDuration(_DURACION_MS)
        self._animacion.setEasingCurve(QEasingCurve.Type.OutCubic)

    # -- Datos --------------------------------------------------------------

    def establecer_color(self, color: str) -> None:
        """Tine la sombra con el color de la fase en curso."""
        if color != self._color:
            self._color = color
            self.update()

    def ir_a(self, centro_x: int, base_y: int, *, suave: bool) -> None:
        """Coloca al personaje con los pies en ``base_y`` y centrado en ``centro_x``.

        ``suave`` distingue los dos movimientos: el paso de un bloque al
        siguiente se interpola; el avance dentro del bloque, que llega una vez
        por segundo, se aplica directo para que no vaya siempre un tic por detras.
        """
        destino = QPoint(centro_x - self.width() // 2, base_y - self.height())
        if destino == self.pos():
            return

        self._animacion.stop()
        if not suave or not self.isVisible():
            self.move(destino)
            return
        self._animacion.setStartValue(self.pos())
        self._animacion.setEndValue(destino)
        self._animacion.start()

    # -- Pintado ------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (API de Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self._color)

        # Sombra de contacto: sin ella la silueta parece flotar sobre el riel.
        sombra = QColor(color)
        sombra.setAlpha(70)
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(sombra)
        pintor.drawEllipse(QRectF(self.width() / 2 - 10, self.height() - 6.0, 20, 4))

        if self._mapa.isNull():
            pintor.setBrush(color)
            pintor.drawEllipse(
                QRectF(self.width() / 2 - 7, self.height() - 22.0, 14, 14)
            )
            pintor.end()
            return

        pintor.drawPixmap(
            (self.width() - self._mapa.width()) // 2,
            self.height() - self._mapa.height() - 3,
            self._mapa,
        )
        pintor.end()
