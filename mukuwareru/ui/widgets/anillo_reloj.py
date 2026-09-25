"""Anillo de cuenta atras del Pomodoro."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from mukuwareru.ui.tema import tokens
from mukuwareru.ui.widgets.anillo import pintar_arco
from mukuwareru.utilidades import formato


class AnilloReloj(QWidget):
    """Cuenta atras circular con el tiempo restante y la fase en el centro.

    Se repinta una vez por segundo, solo cuando el texto cambia.
    """

    def __init__(
        self, diametro: int = 260, grosor: int = 12, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._progreso = 0.0
        self._restante = 0
        self._fase = ""
        self._color = tokens.ACENTO
        self._grosor = grosor
        # La tipografia se escala con el diametro: el anillo se usa a 260 px en
        # solitario y a 132 px al lado del timeline, y un tamano fijo se sale.
        self._tamano_reloj = max(14, int(diametro * 0.177))
        self._separacion = int(diametro * 0.2)
        self.setFixedSize(diametro, diametro)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def establecer(self, restante_seg: int, progreso: float, fase: str, color: str) -> None:
        """Actualiza el estado mostrado y repinta."""
        self._restante = restante_seg
        self._progreso = max(0.0, min(1.0, progreso))
        self._fase = fase
        self._color = color
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (API de Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)

        pintar_arco(pintor, self.rect(), self._grosor, self._progreso, self._color, holgura=2)

        desplazamiento = self._separacion // 4
        centro = self.rect().adjusted(0, -desplazamiento, 0, -desplazamiento)
        pintor.setPen(QColor(tokens.TEXTO))
        fuente = QFont(tokens.FUENTE, self._tamano_reloj)
        fuente.setWeight(QFont.Weight.Light)
        pintor.setFont(fuente)
        pintor.drawText(
            centro, Qt.AlignmentFlag.AlignCenter, formato.duracion_reloj(self._restante)
        )

        etiqueta = self.rect().adjusted(0, self._separacion, 0, self._separacion)
        pintor.setPen(QColor(self._color))
        pintor.setFont(QFont(tokens.FUENTE, tokens.TAM_BASE))
        pintor.drawText(etiqueta, Qt.AlignmentFlag.AlignCenter, self._fase)
        pintor.end()
