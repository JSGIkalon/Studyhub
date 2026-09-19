"""El lienzo: zoom, paneo, arrastre y creacion de conexiones.

Se usa ``QGraphicsView`` y no un ``paintEvent`` propio, al contrario que el
lector de PDF. Alli hizo falta porque ``QPdfView`` esconde el mapeo entre el
viewport y la pagina; aqui ``mapToScene`` es publico, y con el vienen gratis el
zoom bajo el cursor, la deteccion de clics, la seleccion por rectangulo y el
orden Z. Escribir todo eso a mano seria trabajo de tres modulos para tener lo
mismo peor.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QWidget,
)

from mukuwareru.nucleo.modelos import DestinoNodo
from mukuwareru.nucleo.servicios import GrafoProyecto
from mukuwareru.ui.grafo.arista import ItemArista
from mukuwareru.ui.grafo.nodo import ALTO_NODO, ANCHO_NODO, ItemNodo
from mukuwareru.ui.tema import tokens

# Formato propio y no `text/plain`: asi el lienzo no acepta cualquier texto que
# alguien arrastre desde otra aplicacion. Mismo criterio que el timeline del
# Pomodoro.
MIME_NODO = "application/x-mukuwareru-nodo-grafo"

_ZOOM_PASO = 1.15
_ZOOM_MINIMO = 0.4
_ZOOM_MAXIMO = 2.0
_MARGEN_ESCENA = 400


class LienzoGrafo(QGraphicsView):
    """Vista del grafo. No escribe en la base: avisa y la vista decide."""

    nodo_movido = Signal(int, float, float)          # nodo_id, x, y
    conexion_creada = Signal(int, int)               # destino, origen
    entidad_soltada = Signal(str, int, float, float)  # destino, objeto_id, x, y
    nodo_abierto = Signal(int)                       # nodo_id
    nodos_borrados = Signal(list)                    # [nodo_id]
    aristas_borradas = Signal(list)                  # [(destino, origen)]
    seleccion_cambiada = Signal(object)              # NodoResuelto | None
    aviso = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._escena = QGraphicsScene(self)
        self._escena.setBackgroundBrush(QColor(tokens.FONDO))
        self.setScene(self._escena)

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._items: dict[int, ItemNodo] = {}
        self._aristas: list[ItemArista] = []
        self._tirando: QGraphicsPathItem | None = None
        self._origen_tirando: int | None = None

        self._escena.selectionChanged.connect(self._al_cambiar_seleccion)

    # -- Contenido -------------------------------------------------------------

    def pintar(self, grafo: GrafoProyecto) -> None:
        """Reconstruye la escena entera a partir del grafo ya resuelto.

        Reconstruir y no actualizar en su sitio: el grafo de un proyecto son
        decenas de items, no miles, y asi no hay estado que sincronizar entre lo
        que se ve y lo que dice la base.
        """
        self._escena.clear()
        self._items.clear()
        self._aristas.clear()
        self._tirando = None

        for resuelto in grafo.nodos:
            item = ItemNodo(resuelto)
            item.movido.connect(self.nodo_movido)
            item.abrir_pedido.connect(self.nodo_abierto)
            item.conexion_pedida.connect(self._empezar_conexion)
            self._escena.addItem(item)
            self._items[resuelto.nodo.id] = item

        # Cuantas aristas hay en cada grupo: solo son alternativas las de un
        # grupo con dos o mas, y solo esas se marcan con la «o».
        tamanos: dict[tuple[int, int], int] = {}
        for arista in grafo.aristas:
            clave = (arista.destino, arista.grupo)
            tamanos[clave] = tamanos.get(clave, 0) + 1

        for arista in grafo.aristas:
            origen = self._items.get(arista.origen)
            destino = self._items.get(arista.destino)
            if origen is None or destino is None:
                continue
            item = ItemArista(origen, destino, arista.grupo)
            item.alternativa = tamanos[(arista.destino, arista.grupo)] > 1
            item.recalcular()
            self._escena.addItem(item)
            self._aristas.append(item)

        self._ajustar_escena()

    def _ajustar_escena(self) -> None:
        """Deja margen alrededor para poder arrastrar mas alla de lo que hay."""
        caja = (
            self._escena.itemsBoundingRect()
            if self._items
            else self.viewport().rect().toRectF()
        )
        self._escena.setSceneRect(
            caja.adjusted(-_MARGEN_ESCENA, -_MARGEN_ESCENA, _MARGEN_ESCENA, _MARGEN_ESCENA)
        )

    def encajar(self) -> None:
        """Encuadra todo lo que hay. El atajo de «no encuentro mi grafo»."""
        if not self._items:
            return
        self.fitInView(
            self._escena.itemsBoundingRect().adjusted(-40, -40, 40, 40),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        self._acotar_zoom()

    def restablecer_zoom(self) -> None:
        """Vuelve al 100 %."""
        self.resetTransform()

    # -- Zoom y paneo ----------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 (API de Qt)
        """La rueda hace zoom bajo el cursor, acotado."""
        factor = _ZOOM_PASO if event.angleDelta().y() > 0 else 1 / _ZOOM_PASO
        escala = self.transform().m11() * factor
        if _ZOOM_MINIMO <= escala <= _ZOOM_MAXIMO:
            self.scale(factor, factor)
        event.accept()

    def _acotar_zoom(self) -> None:
        """Recorta la escala tras un ``fitInView``, que no la respeta sola."""
        escala = self.transform().m11()
        if escala < _ZOOM_MINIMO:
            self.scale(_ZOOM_MINIMO / escala, _ZOOM_MINIMO / escala)
        elif escala > _ZOOM_MAXIMO:
            self.scale(_ZOOM_MAXIMO / escala, _ZOOM_MAXIMO / escala)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        """El boton central panea; el izquierdo selecciona o arrastra."""
        if event.button() is Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            # Qt solo panea con el boton izquierdo, asi que se le entrega un
            # evento izquierdo sintetico: es el truco habitual y evita
            # reimplementar el arrastre entero.
            falso = QMouseEvent(
                event.type(),
                event.position(),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                event.modifiers(),
            )
            super().mousePressEvent(falso)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        if self._tirando is not None:
            self._mover_tirador(self.mapToScene(event.position().toPoint()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        if self._tirando is not None:
            self._terminar_conexion(self.mapToScene(event.position().toPoint()))
            event.accept()
            return
        if event.button() is Qt.MouseButton.MiddleButton:
            super().mouseReleaseEvent(event)
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            return
        super().mouseReleaseEvent(event)

    # -- Conexiones ------------------------------------------------------------

    def _empezar_conexion(self, nodo_id: int, punto: QPointF) -> None:
        """Arranca la linea punteada que sigue al raton."""
        self._origen_tirando = nodo_id
        tirador = QGraphicsPathItem()
        tirador.setPen(QPen(QColor(tokens.TEXTO_SUAVE), 1.5, Qt.PenStyle.DashLine))
        tirador.setZValue(10)
        self._escena.addItem(tirador)
        self._tirando = tirador
        self._mover_tirador(punto)

    def _mover_tirador(self, hasta: QPointF) -> None:
        origen = self._items.get(self._origen_tirando or -1)
        if self._tirando is None or origen is None:
            return
        camino = QPainterPath(origen.puerto())
        camino.lineTo(hasta)
        self._tirando.setPath(camino)

    def _terminar_conexion(self, punto: QPointF) -> None:
        """Al soltar: si hay un nodo debajo, se pide la conexion.

        Soltar en el vacio no es un error, es cambiar de idea: se descarta la
        linea y no se dice nada.
        """
        if self._tirando is not None:
            self._escena.removeItem(self._tirando)
        self._tirando = None
        origen = self._origen_tirando
        self._origen_tirando = None
        if origen is None:
            return

        for item in self._escena.items(punto):
            if isinstance(item, ItemNodo) and item.nodo_id != origen:
                self.conexion_creada.emit(item.nodo_id, origen)
                return

    # -- Soltar entidades del panel --------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 (API de Qt)
        if event.mimeData().hasFormat(MIME_NODO):
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802 (API de Qt)
        if event.mimeData().hasFormat(MIME_NODO):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 (API de Qt)
        """Coloca la entidad donde se solto, en coordenadas de la escena.

        Lo que viaja es «que clase de cosa y cual», nunca una copia de sus
        datos: el nodo que se cree sera una referencia.
        """
        bruto = bytes(event.mimeData().data(MIME_NODO)).decode("utf-8")
        destino, _, identificador = bruto.partition("\t")
        if destino not in {d.value for d in DestinoNodo} or not identificador.isdigit():
            return

        punto = self.mapToScene(event.position().toPoint())
        # Se resta medio nodo para que la tarjeta quede centrada en el cursor y
        # no colgando de su esquina superior izquierda.
        self.entidad_soltada.emit(
            destino,
            int(identificador),
            punto.x() - ANCHO_NODO / 2,
            punto.y() - ALTO_NODO / 2,
        )
        event.acceptProposedAction()

    # -- Teclado y seleccion ---------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (API de Qt)
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._borrar_seleccion()
            event.accept()
            return
        super().keyPressEvent(event)

    def _borrar_seleccion(self) -> None:
        """Quita del grafo lo seleccionado. Nunca borra la entidad de detras."""
        nodos = [
            item.nodo_id
            for item in self._escena.selectedItems()
            if isinstance(item, ItemNodo)
        ]
        aristas = [
            (item.destino.nodo_id, item.origen.nodo_id)
            for item in self._escena.selectedItems()
            if isinstance(item, ItemArista)
        ]
        if aristas:
            self.aristas_borradas.emit(aristas)
        if nodos:
            self.nodos_borrados.emit(nodos)

    def _al_cambiar_seleccion(self) -> None:
        seleccionados = [
            item for item in self._escena.selectedItems() if isinstance(item, ItemNodo)
        ]
        uno = seleccionados[0].resuelto if len(seleccionados) == 1 else None
        self.seleccion_cambiada.emit(uno)

    def seleccion(self) -> list[ItemNodo]:
        """Nodos seleccionados ahora mismo."""
        return [
            item for item in self._escena.selectedItems() if isinstance(item, ItemNodo)
        ]
