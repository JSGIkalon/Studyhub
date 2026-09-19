"""La flecha que une dos nodos: «esto hace falta antes que aquello».

La curva sale del puerto derecho del origen y entra por el lado izquierdo del
destino. Es una Bezier y no una recta porque con varios prerrequisitos las
rectas se superponen y no se sabe cual va a donde.

Las aristas del mismo grupo —las alternativas de un O— comparten color y llevan
una «o» en el medio. Sin esa marca, «A Y B» y «A O B» se dibujarian igual.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from mukuwareru.ui.grafo.nodo import ItemNodo
from mukuwareru.ui.tema import tokens

_PUNTA = 9.0
_CURVATURA = 60.0


class ItemArista(QGraphicsPathItem):
    """Curva dirigida entre dos ``ItemNodo``."""

    def __init__(self, origen: ItemNodo, destino: ItemNodo, grupo: int) -> None:
        super().__init__()
        self.origen = origen
        self.destino = destino
        self.grupo = grupo
        # Un solo prerrequisito no es una alternativa de nada, asi que no se
        # marca; solo los grupos con dos o mas se pintan como un O.
        self.alternativa = False

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(-1)          # siempre por debajo de las tarjetas
        self.recalcular()

    # -- Contrato que `ItemNodo.itemChange` usa --------------------------------

    def toca(self, nodo_id: int) -> bool:
        """Si esta arista cuelga de ese nodo."""
        return nodo_id in (self.origen.nodo_id, self.destino.nodo_id)

    def recalcular(self) -> None:
        """Rehace la curva a partir de donde estan ahora los dos nodos."""
        desde = self.origen.puerto()
        hasta = self.destino.entrada()
        tiron = min(_CURVATURA, max(20.0, abs(hasta.x() - desde.x()) / 2))

        camino = QPainterPath(desde)
        camino.cubicTo(
            QPointF(desde.x() + tiron, desde.y()),
            QPointF(hasta.x() - tiron, hasta.y()),
            hasta,
        )
        self.setPath(camino)
        self.setToolTip(
            f"{self.origen.resuelto.nombre} → {self.destino.resuelto.nombre}"
            + ("  ·  alternativa (O)" if self.alternativa else "")
        )

    def color(self) -> QColor:
        """Color de la arista. Las de un mismo grupo comparten el suyo."""
        if not self.alternativa:
            return QColor(tokens.BORDE)
        # El grupo empieza en 1; la serie en 0.
        return QColor(tokens.color_serie(self.grupo - 1))

    # -- Pintado ---------------------------------------------------------------

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(tokens.ACENTO) if self.isSelected() else self.color()

        painter.setPen(QPen(color, 2.5 if self.isSelected() else 1.8))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())

        self._punta(painter, color)
        if self.alternativa:
            self._marca_o(painter, color)

    def _punta(self, painter: QPainter, color: QColor) -> None:
        """Triangulo en el extremo, orientado segun la tangente de la curva."""
        camino = self.path()
        final = camino.pointAtPercent(1.0)
        angulo = math.radians(camino.angleAtPercent(1.0))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPolygon(
            QPolygonF([
                final,
                final + QPointF(
                    -_PUNTA * math.cos(angulo - math.pi / 7),
                    _PUNTA * math.sin(angulo - math.pi / 7),
                ),
                final + QPointF(
                    -_PUNTA * math.cos(angulo + math.pi / 7),
                    _PUNTA * math.sin(angulo + math.pi / 7),
                ),
            ])
        )

    def _marca_o(self, painter: QPainter, color: QColor) -> None:
        """Una «o» en el punto medio: esta arista es una alternativa."""
        centro = self.path().pointAtPercent(0.5)
        caja = QRectF(centro.x() - 8, centro.y() - 8, 16, 16)

        painter.setPen(QPen(color, 1.2))
        painter.setBrush(QBrush(QColor(tokens.FONDO)))
        painter.drawEllipse(caja)

        painter.setFont(QFont(tokens.FUENTE, tokens.TAM_PEQUENO))
        painter.setPen(color)
        painter.drawText(caja, Qt.AlignmentFlag.AlignCenter, "o")
