"""Horas dedicadas a una materia frente al peso que deberia llevarse.

No reutiliza ``BarraMateria`` porque aquella pinta **una** magnitud y aqui hacen
falta dos comparables en el mismo eje mas el signo de la diferencia. Anadirle un
tercer modo de pintado a un widget del que dependen a la vez el Panel, Progreso
y Resultados seria pagar en riesgo lo que aqui cuesta cuarenta lineas.

La lectura es inmediata: la barra es lo que le dedicas, la marca vertical es lo
que le tocaria. Barra por debajo de la marca, materia desatendida.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from mukuwareru.ui.tema import tokens

# Las mismas medidas que `BarraMateria`, para que las dos tarjetas de la fila
# inferior de Estadisticas queden alineadas.
_ANCHO_NOMBRE = 168
_ANCHO_CIFRAS = 92
_ALTO_BARRA = 7
_ALTO_MARCA = 15


class BarraAtencion(QWidget):
    """Una linea del bloque «Atencion por materia»."""

    def __init__(
        self,
        nombre: str,
        real: float,
        objetivo: float,
        color: str,
        *,
        escala: float = 100.0,
        desatendida: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._nombre = nombre
        self._real = real
        self._objetivo = objetivo
        self._color = color
        # La escala la fija la vista y es comun a todas las filas: con una
        # escala por fila, dos materias con reparto muy distinto se pintarian
        # igual de largas y la comparacion entre ellas seria falsa.
        self._escala = max(escala, 1.0)
        self._desatendida = desatendida
        self.setFixedHeight(26)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (API de Qt)
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        alto = self.height()

        pintor.setPen(QColor(tokens.TEXTO_SUAVE))
        nombre = pintor.fontMetrics().elidedText(
            self._nombre, Qt.TextElideMode.ElideRight, _ANCHO_NOMBRE
        )
        pintor.drawText(
            QRectF(0, 0, _ANCHO_NOMBRE, alto),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            nombre,
        )

        x = _ANCHO_NOMBRE + tokens.ESPACIO_PEQUENO
        ancho = self.width() - x - _ANCHO_CIFRAS - tokens.ESPACIO_PEQUENO
        if ancho <= 0:
            pintor.end()
            return

        y = (alto - _ALTO_BARRA) / 2
        radio = _ALTO_BARRA / 2

        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor(tokens.SUPERFICIE_ALTA))
        pintor.drawRoundedRect(QRectF(x, y, ancho, _ALTO_BARRA), radio, radio)

        if self._real > 0:
            # Nunca menos de un alto de barra: un 1 % debe seguir viendose.
            relleno = max(_ALTO_BARRA, ancho * min(self._real, self._escala) / self._escala)
            pintor.setBrush(QColor(tokens.AVISO if self._desatendida else self._color))
            pintor.drawRoundedRect(QRectF(x, y, relleno, _ALTO_BARRA), radio, radio)

        # La marca del objetivo, mas alta que la barra para que se vea aunque la
        # barra la sobrepase.
        marca = x + ancho * min(self._objetivo, self._escala) / self._escala
        pintor.setBrush(QColor(tokens.TEXTO))
        pintor.drawRect(QRectF(marca - 1, (alto - _ALTO_MARCA) / 2, 2, _ALTO_MARCA))

        pintor.setPen(QColor(tokens.AVISO if self._desatendida else tokens.TEXTO_SUAVE))
        pintor.drawText(
            QRectF(self.width() - _ANCHO_CIFRAS, 0, _ANCHO_CIFRAS, alto),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{self._real:.0f}% / {self._objetivo:.0f}%",
        )
        pintor.end()
