"""Fila de progreso de una materia: nombre, barra y porcentaje."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from mukuwareru.ui.tema import tokens

_ANCHO_NOMBRE = 168
_ANCHO_PORCENTAJE = 46
_ANCHO_CUOTA = 44
_ALTO_BARRA = 7


class BarraMateria(QWidget):
    """Una linea del bloque «Modulos por tema».

    Se pinta entera con QPainter en lugar de componer tres widgets: es una fila
    que se repite diez veces y asi el bloque cuesta un solo paintEvent.

    ``cuota`` es el peso de la asignatura en porcentaje del proyecto. Cuando se
    pasa aparece en una columna propia entre el nombre y la barra, y no dentro
    del nombre: el nombre se recorta cuando no cabe, y el peso es justo el dato
    que no puede perderse al recortar.
    """

    def __init__(
        self,
        nombre: str,
        completados: int,
        total: int,
        color: str,
        parent: QWidget | None = None,
        *,
        cuota: float | None = None,
    ) -> None:
        super().__init__(parent)
        self._nombre = nombre
        self._completados = completados
        self._total = total
        self._color = color
        self._cuota = cuota
        self.setFixedHeight(26)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        detalle = f"{nombre}: {completados} de {total} modulos"
        if cuota is not None:
            detalle += f"  ·  peso {cuota:.1f} % del proyecto"
        self.setToolTip(detalle)

    @property
    def _porcentaje(self) -> int:
        return round(self._completados * 100 / self._total) if self._total else 0

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
        if self._cuota is not None:
            pintor.setPen(QColor(tokens.TEXTO_TENUE))
            pintor.drawText(
                QRectF(x, 0, _ANCHO_CUOTA, alto),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{self._cuota:.1f}%",
            )
            x += _ANCHO_CUOTA + tokens.ESPACIO_PEQUENO

        # El espacio extra evita que la barra al 100 % toque el porcentaje.
        ancho = self.width() - x - _ANCHO_PORCENTAJE - tokens.ESPACIO_PEQUENO
        y = (alto - _ALTO_BARRA) / 2
        radio = _ALTO_BARRA / 2

        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QColor(tokens.SUPERFICIE_ALTA))
        pintor.drawRoundedRect(QRectF(x, y, ancho, _ALTO_BARRA), radio, radio)

        if self._porcentaje > 0:
            # Nunca menos de un alto de barra: un 1 % debe seguir viendose.
            relleno = max(_ALTO_BARRA, ancho * self._porcentaje / 100)
            pintor.setBrush(QColor(self._color))
            pintor.drawRoundedRect(QRectF(x, y, relleno, _ALTO_BARRA), radio, radio)

        pintor.setPen(QColor(tokens.TEXTO if self._porcentaje else tokens.TEXTO_TENUE))
        pintor.drawText(
            QRectF(self.width() - _ANCHO_PORCENTAJE, 0, _ANCHO_PORCENTAJE, alto),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{self._porcentaje}%",
        )
        pintor.end()
