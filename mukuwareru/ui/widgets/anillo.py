"""Anillo de progreso dibujado con QPainter."""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from mukuwareru.ui.tema import tokens


def pintar_arco(
    pintor: QPainter, caja: QRect, grosor: int, fraccion: float, color: str, *, holgura: int = 1
) -> None:
    """Pista completa y, encima, el arco de ``fraccion`` (0 a 1) desde arriba.

    Es lo comun a los dos anillos, el de progreso y el del reloj: cada uno
    pinta despues su propio texto en el centro.
    """
    margen = grosor / 2 + holgura
    area = QRectF(caja).adjusted(margen, margen, -margen, -margen)

    pista = QPen(QColor(tokens.SUPERFICIE_ALTA), grosor)
    pista.setCapStyle(Qt.PenCapStyle.FlatCap)
    pintor.setPen(pista)
    pintor.drawArc(area, 0, 360 * 16)

    if fraccion > 0:
        arco = QPen(QColor(color), grosor)
        arco.setCapStyle(Qt.PenCapStyle.RoundCap)
        pintor.setPen(arco)
        # Arranca arriba (90 grados) y avanza en sentido horario.
        pintor.drawArc(area, 90 * 16, -int(360 * 16 * fraccion))


class AnilloProgreso(QWidget):
    """Donut con el porcentaje en el centro.

    No se anima: el valor se pinta directamente. La prioridad es la velocidad.
    """

    def __init__(
        self,
        diametro: int = 168,
        grosor: int = 14,
        color: str = tokens.EXITO,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._porcentaje = 0
        self._grosor = grosor
        self._color = color
        self.setFixedSize(diametro, diametro)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def establecer(self, porcentaje: int, color: str | None = None) -> None:
        """Fija el valor (0-100) y, opcionalmente, el color del arco."""
        self._porcentaje = max(0, min(100, porcentaje))
        if color is not None:
            self._color = color
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (API de Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)

        pintar_arco(pintor, self.rect(), self._grosor, self._porcentaje / 100, self._color)

        pintor.setPen(QColor(tokens.TEXTO))
        fuente = QFont(tokens.FUENTE, 30)
        fuente.setWeight(QFont.Weight.DemiBold)
        pintor.setFont(fuente)
        pintor.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self._porcentaje}%")
        pintor.end()
