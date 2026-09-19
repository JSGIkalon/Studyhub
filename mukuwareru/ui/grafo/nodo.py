"""La tarjeta que representa una entidad dentro del lienzo.

Un nodo ensena lo justo: nombre, avance y estado. Todo lo demas —las notas, los
PDFs, el plan— esta a un doble clic, en la vista donde ya vivia. Saturar la
tarjeta convertiria el grafo en una tercera copia de la aplicacion.

Los colores salen de ``tokens`` y no del QSS: ver el docstring del paquete.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from mukuwareru.nucleo.modelos import DestinoNodo, EstadoNodo
from mukuwareru.nucleo.servicios import NodoResuelto
from mukuwareru.ui.tema import tokens

ANCHO_NODO = 190
ALTO_NODO = 78

_MARGEN = 10
_ALTO_BARRA = 4
_RADIO_PUERTO = 6

# Color del borde segun el estado. Es la unica senal de estado del nodo: sin
# iconos ni insignias, que en un lienzo lleno se convierten en confeti.
_BORDES: dict[EstadoNodo, str] = {
    EstadoNodo.BLOQUEADO: tokens.BORDE_SUTIL,
    EstadoNodo.DISPONIBLE: tokens.INFO,
    EstadoNodo.EN_CURSO: tokens.AVISO,
    EstadoNodo.COMPLETADO: tokens.EXITO,
}

_INICIALES: dict[DestinoNodo, str] = {
    DestinoNodo.MATERIA: "Materia",
    DestinoNodo.MODULO: "Modulo",
    DestinoNodo.HITO: "Hito",
    DestinoNodo.EVALUACION: "Examen",
}


class ItemNodo(QGraphicsObject):
    """Tarjeta movible con un puerto de salida en el borde derecho."""

    movido = Signal(int, float, float)          # nodo_id, x, y
    conexion_pedida = Signal(int, QPointF)      # nodo_id de origen, punto de escena
    abrir_pedido = Signal(int)                  # nodo_id

    def __init__(self, resuelto: NodoResuelto) -> None:
        super().__init__()
        self.resuelto = resuelto
        self.nodo_id = resuelto.nodo.id

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setPos(resuelto.nodo.x, resuelto.nodo.y)
        self.setToolTip(self._descripcion())

        self._arrastrando_puerto = False

    # -- Geometria -------------------------------------------------------------

    def boundingRect(self) -> QRectF:  # noqa: N802 (API de Qt)
        """Incluye el puerto, que sobresale por la derecha."""
        return QRectF(-2, -2, ANCHO_NODO + _RADIO_PUERTO + 4, ALTO_NODO + 4)

    def puerto(self) -> QPointF:
        """Centro del puerto de salida, en coordenadas de la escena."""
        return self.mapToScene(QPointF(ANCHO_NODO, ALTO_NODO / 2))

    def entrada(self) -> QPointF:
        """Punto por el que llegan las flechas, en coordenadas de la escena."""
        return self.mapToScene(QPointF(0, ALTO_NODO / 2))

    # -- Pintado ---------------------------------------------------------------

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Tarjeta, texto y barra de avance. Sin animaciones ni sombras."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bloqueado = self.resuelto.estado is EstadoNodo.BLOQUEADO

        cuerpo = QRectF(0, 0, ANCHO_NODO, ALTO_NODO)
        borde = QColor(_BORDES[self.resuelto.estado])
        painter.setBrush(QBrush(QColor(tokens.SUPERFICIE)))
        painter.setPen(QPen(borde, 3 if self.isSelected() else 2))
        painter.drawRoundedRect(cuerpo, tokens.RADIO, tokens.RADIO)

        # Nombre, elidido: un titulo largo no puede desbordar la tarjeta.
        titulo = QFont(tokens.FUENTE, tokens.TAM_BASE)
        titulo.setWeight(QFont.Weight.DemiBold)
        painter.setFont(titulo)
        painter.setPen(QColor(tokens.TEXTO_TENUE if bloqueado else tokens.TEXTO))
        ancho_util = ANCHO_NODO - 2 * _MARGEN
        painter.drawText(
            QRectF(_MARGEN, _MARGEN - 2, ancho_util, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            QFontMetrics(titulo).elidedText(
                self.resuelto.nombre, Qt.TextElideMode.ElideRight, int(ancho_util)
            ),
        )

        painter.setFont(QFont(tokens.FUENTE, tokens.TAM_PEQUENO))
        painter.setPen(QColor(tokens.TEXTO_TENUE if bloqueado else tokens.TEXTO_SUAVE))
        painter.drawText(
            QRectF(_MARGEN, _MARGEN + 18, ancho_util, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._subtitulo(),
        )

        painter.setPen(QColor(tokens.TEXTO_TENUE))
        painter.drawText(
            QRectF(_MARGEN, _MARGEN + 34, ancho_util, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.resuelto.estado.etiqueta,
        )

        # Barra de avance al pie. Un nodo bloqueado no la pinta: lo que importa
        # de el es que no se puede empezar todavia.
        if not bloqueado and self.resuelto.total:
            base = QRectF(
                _MARGEN, ALTO_NODO - _MARGEN, ancho_util, _ALTO_BARRA
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(tokens.SUPERFICIE_ALTA)))
            painter.drawRoundedRect(base, 2, 2)
            if self.resuelto.fraccion > 0:
                painter.setBrush(QBrush(borde))
                painter.drawRoundedRect(
                    QRectF(
                        base.x(), base.y(),
                        base.width() * min(1.0, self.resuelto.fraccion), _ALTO_BARRA,
                    ),
                    2, 2,
                )

        # Puerto de salida: de aqui arrancan las flechas.
        painter.setPen(QPen(borde, 1))
        painter.setBrush(QBrush(QColor(tokens.FONDO)))
        painter.drawEllipse(
            QPointF(ANCHO_NODO, ALTO_NODO / 2), _RADIO_PUERTO, _RADIO_PUERTO
        )

    def _subtitulo(self) -> str:
        """La cifra del nodo, en las unidades que tengan sentido para su tipo."""
        if self.resuelto.destino is DestinoNodo.MATERIA and self.resuelto.total > 1:
            return (
                f"{self.resuelto.completados} / {self.resuelto.total} modulos"
                f"  ·  {self.resuelto.porcentaje} %"
            )
        return _INICIALES[self.resuelto.destino]

    def _descripcion(self) -> str:
        """Lo que se lee al pasar el raton por encima."""
        lineas = [
            f"{_INICIALES[self.resuelto.destino]}: {self.resuelto.nombre}",
            f"Estado: {self.resuelto.estado.etiqueta}",
        ]
        if self.resuelto.prerrequisitos:
            lineas.append(f"Prerrequisitos: {len(self.resuelto.prerrequisitos)} grupo(s)")
        lineas.append("Doble clic para abrir su informacion completa")
        return "\n".join(lineas)

    # -- Raton -----------------------------------------------------------------

    def _sobre_el_puerto(self, punto: QPointF) -> bool:
        centro = QPointF(ANCHO_NODO, ALTO_NODO / 2)
        # Radio generoso: acertar en seis pixeles con el raton es un ejercicio de
        # punteria, no una interfaz.
        return (punto - centro).manhattanLength() < _RADIO_PUERTO * 3

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        """Sobre el puerto empieza una conexion; en el resto, un arrastre.

        No llamar a ``super()`` en el caso del puerto es lo que impide que el
        nodo se mueva mientras se tira de la flecha.
        """
        if event.button() is Qt.MouseButton.LeftButton and self._sobre_el_puerto(
            event.pos()
        ):
            self._arrastrando_puerto = True
            self.conexion_pedida.emit(self.nodo_id, event.scenePos())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        if self._arrastrando_puerto:
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        """Al soltar se persiste la posicion, no antes.

        Un arrastre dispara decenas de ``itemChange``; guardar en cada uno serian
        decenas de UPDATE para mover una tarjeta diez pixeles.
        """
        if self._arrastrando_puerto:
            self._arrastrando_puerto = False
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self.movido.emit(self.nodo_id, self.pos().x(), self.pos().y())

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        self.abrir_pedido.emit(self.nodo_id)
        event.accept()

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: object) -> object:  # noqa: N802
        """Avisa a las aristas cuando el nodo cambia de sitio.

        Se pregunta por los metodos y no por la clase: ``ItemArista`` importa
        este modulo, asi que importarla de vuelta seria un ciclo. El contrato es
        ``toca(nodo_id)`` y ``recalcular()``.
        """
        if change is QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            escena = self.scene()
            if escena is not None:
                for item in escena.items():
                    tocar = getattr(item, "toca", None)
                    if callable(tocar) and tocar(self.nodo_id):
                        item.recalcular()
        return super().itemChange(change, value)
