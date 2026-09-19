"""Lienzo del visor: renderiza las paginas, gestiona el scroll y la seleccion.

Es el corazon del lector y el unico motivo por el que no se usa ``QPdfView``:
Qt aporta el motor de rasterizado y de busqueda, pero no expone el mapeo entre
el viewport y las coordenadas de pagina, sin el cual no hay seleccion de texto
ni resaltados anclados.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, QPointF, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions
from PySide6.QtWidgets import QAbstractScrollArea, QWidget

from mukuwareru.ui.lector.cache import CachePaginas
from mukuwareru.ui.lector.disposicion import MARGEN, Disposicion
from mukuwareru.ui.lector.seleccion import TextoDePagina
from mukuwareru.ui.tema import tokens

ZOOM_MINIMO = 0.2
ZOOM_MAXIMO = 6.0
_PASOS_ZOOM = (0.25, 0.33, 0.5, 0.67, 0.8, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 6.0)


@dataclass(frozen=True, slots=True)
class Resaltado:
    """Un rectangulo a pintar sobre una pagina, en puntos PDF."""

    pagina: int
    rect: QRectF
    color: str


class VistaPaginas(QAbstractScrollArea):
    """Scroll continuo de una columna con seleccion de texto."""

    pagina_cambiada = Signal(int)
    zoom_cambiado = Signal(float)
    seleccion_cambiada = Signal(str)
    menu_pedido = Signal(QPoint)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._documento: QPdfDocument | None = None
        self._disposicion = Disposicion([])
        self._cache = CachePaginas()
        self._texto: TextoDePagina | None = None
        self._modo_ajuste = "ancho"

        self._resaltados: list[Resaltado] = []
        self._hallazgos: list[Resaltado] = []
        self._seleccion: list[Resaltado] = []
        self._texto_seleccionado = ""
        self._pagina_seleccion = -1
        self._rango_seleccion: tuple[QPointF, QPointF] | None = None
        self._arrastrando = False
        self._pagina_actual = 0

        self.setFrameShape(QAbstractScrollArea.Shape.NoFrame)
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        self.viewport().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.viewport().customContextMenuRequested.connect(self.menu_pedido.emit)
        self.verticalScrollBar().valueChanged.connect(self._al_desplazar)
        self.horizontalScrollBar().valueChanged.connect(lambda _: self.viewport().update())

    # -- Documento ---------------------------------------------------------

    def establecer_documento(self, documento: QPdfDocument) -> None:
        """Carga un documento ya abierto y prepara la disposicion."""
        self._documento = documento
        self._cache.vaciar()
        self._texto = TextoDePagina(documento)
        self._limpiar_seleccion()
        self._resaltados = []
        self._hallazgos = []

        tamanos = [
            QSizeF(documento.pagePointSize(i)) for i in range(max(0, documento.pageCount()))
        ]
        self._disposicion = Disposicion(tamanos, self._disposicion.zoom)
        self._aplicar_ajuste()
        self._actualizar_barras()
        self.viewport().update()

    @property
    def paginas(self) -> int:
        """Numero de paginas del documento cargado."""
        return self._disposicion.paginas

    @property
    def pagina_actual(self) -> int:
        """Pagina que ocupa mas superficie del area visible."""
        return self._pagina_actual

    @property
    def zoom(self) -> float:
        """Factor de escala vigente."""
        return self._disposicion.zoom

    @property
    def texto_seleccionado(self) -> str:
        """Texto de la seleccion actual, o cadena vacia."""
        return self._texto_seleccionado

    @property
    def pagina_seleccion(self) -> int:
        """Pagina donde vive la seleccion actual, o ``-1``."""
        return self._pagina_seleccion

    def rects_seleccion(self) -> list[QRectF]:
        """Rectangulos de la seleccion, en puntos PDF y listos para persistir."""
        return [r.rect for r in self._seleccion]

    # -- Navegacion --------------------------------------------------------

    def ir_a_pagina(self, indice: int, desplazamiento_y: float = 0.0) -> None:
        """Desplaza el lienzo hasta el inicio de una pagina."""
        if not self.paginas:
            return
        indice = max(0, min(self.paginas - 1, indice))
        rect = self._disposicion.rect(indice)
        self.verticalScrollBar().setValue(int(rect.y() - MARGEN + desplazamiento_y))

    def desplazamiento_en_pagina(self) -> float:
        """Cuanto se ha bajado dentro de la pagina actual, en pixeles."""
        rect = self._disposicion.rect(self._pagina_actual) if self.paginas else QRectF()
        return max(0.0, self.verticalScrollBar().value() - rect.y() + MARGEN)

    def establecer_zoom(self, zoom: float, *, modo: str = "manual") -> None:
        """Cambia el zoom conservando la pagina que se estaba mirando."""
        zoom = max(ZOOM_MINIMO, min(ZOOM_MAXIMO, zoom))
        if abs(zoom - self._disposicion.zoom) < 1e-6:
            return

        pagina = self._pagina_actual
        dentro = self.desplazamiento_en_pagina() / max(self._disposicion.zoom, 1e-6)

        self._modo_ajuste = modo
        self._disposicion.establecer_zoom(zoom)
        self._cache.descartar_otros_zooms(zoom, self.devicePixelRatioF())
        self._actualizar_barras()
        self.ir_a_pagina(pagina, dentro * zoom)
        self.zoom_cambiado.emit(zoom)
        self.viewport().update()

    def acercar(self) -> None:
        """Sube al siguiente paso de zoom."""
        actual = self._disposicion.zoom
        siguiente = next((p for p in _PASOS_ZOOM if p > actual + 1e-6), ZOOM_MAXIMO)
        self.establecer_zoom(siguiente)

    def alejar(self) -> None:
        """Baja al paso de zoom anterior."""
        actual = self._disposicion.zoom
        previo = next((p for p in reversed(_PASOS_ZOOM) if p < actual - 1e-6), ZOOM_MINIMO)
        self.establecer_zoom(previo)

    def ajustar_ancho(self) -> None:
        """Encaja el ancho de la pagina en el viewport."""
        self.establecer_zoom(
            self._disposicion.zoom_para_ancho(self.viewport().width()), modo="ancho"
        )

    def ajustar_pagina(self) -> None:
        """Encaja una pagina entera en el viewport."""
        self.establecer_zoom(
            self._disposicion.zoom_para_pagina(
                self.viewport().width(), self.viewport().height()
            ),
            modo="pagina",
        )

    # -- Capas superpuestas ------------------------------------------------

    def establecer_resaltados(self, resaltados: list[Resaltado]) -> None:
        """Fija los resaltados guardados que deben pintarse."""
        self._resaltados = resaltados
        self.viewport().update()

    def establecer_hallazgos(self, hallazgos: list[Resaltado]) -> None:
        """Fija los resultados de busqueda a resaltar."""
        self._hallazgos = hallazgos
        self.viewport().update()

    def limpiar_seleccion(self) -> None:
        """Descarta la seleccion actual."""
        self._limpiar_seleccion()
        self.viewport().update()

    # -- Eventos de Qt -----------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (API de Qt)
        pintor = QPainter(self.viewport())
        pintor.fillRect(self.viewport().rect(), QColor(tokens.FONDO))
        if self._documento is None or not self.paginas:
            pintor.end()
            return

        area = self._area_visible()
        desplazamiento = QPointF(-area.x(), -area.y())
        dpr = self.devicePixelRatioF()

        for ubicacion in self._disposicion.visibles(area):
            destino = ubicacion.rect.translated(desplazamiento)
            pintor.fillRect(destino, QColor("#FFFFFF"))
            if (imagen := self._imagen(ubicacion.indice, dpr)) is not None:
                pintor.drawImage(destino, imagen)

            self._pintar_capa(pintor, ubicacion.indice, desplazamiento, self._resaltados, 90)
            self._pintar_capa(pintor, ubicacion.indice, desplazamiento, self._hallazgos, 110)
            self._pintar_capa(pintor, ubicacion.indice, desplazamiento, self._seleccion, 80)
        pintor.end()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (API de Qt)
        super().resizeEvent(event)
        self._aplicar_ajuste()
        self._actualizar_barras()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 (API de Qt)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.acercar()
            else:
                self.alejar()
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        if event.button() is not Qt.MouseButton.LeftButton or self._documento is None:
            super().mousePressEvent(event)
            return

        ubicacion = self._pagina_bajo(event.position())
        if ubicacion is None:
            self.limpiar_seleccion()
            return

        indice, punto = ubicacion
        self._pagina_seleccion = indice
        self._rango_seleccion = (punto, punto)
        self._arrastrando = True
        self._seleccion = []
        self._texto_seleccionado = ""
        self.viewport().update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        if not self._arrastrando or self._rango_seleccion is None:
            super().mouseMoveEvent(event)
            return
        # La seleccion se ancla a la pagina donde empezo: arrastrar hacia otra
        # pagina extiende la seleccion dentro de la primera, no salta de pagina.
        punto = self._a_puntos_en(self._pagina_seleccion, event.position())
        self._rango_seleccion = (self._rango_seleccion[0], punto)
        self._recalcular_seleccion()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (API de Qt)
        if self._arrastrando:
            self._arrastrando = False
            self._recalcular_seleccion()
            self.seleccion_cambiada.emit(self._texto_seleccionado)
        super().mouseReleaseEvent(event)

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802 (API de Qt)
        super().scrollContentsBy(dx, dy)
        self.viewport().update()

    # -- Interno -----------------------------------------------------------

    def _area_visible(self) -> QRectF:
        return QRectF(
            self.horizontalScrollBar().value(),
            self.verticalScrollBar().value(),
            self.viewport().width(),
            self.viewport().height(),
        )

    def _actualizar_barras(self) -> None:
        vertical = self.verticalScrollBar()
        horizontal = self.horizontalScrollBar()
        vertical.setPageStep(self.viewport().height())
        vertical.setSingleStep(48)
        vertical.setRange(0, max(0, int(self._disposicion.alto - self.viewport().height())))
        horizontal.setPageStep(self.viewport().width())
        horizontal.setSingleStep(48)
        horizontal.setRange(0, max(0, int(self._disposicion.ancho - self.viewport().width())))

    def _aplicar_ajuste(self) -> None:
        """Reaplica el modo de ajuste al cambiar el tamano del viewport."""
        if not self.paginas or self._modo_ajuste == "manual":
            return
        if self._modo_ajuste == "ancho":
            nuevo = self._disposicion.zoom_para_ancho(self.viewport().width())
        else:
            nuevo = self._disposicion.zoom_para_pagina(
                self.viewport().width(), self.viewport().height()
            )
        if abs(nuevo - self._disposicion.zoom) > 1e-3:
            self._disposicion.establecer_zoom(max(ZOOM_MINIMO, min(ZOOM_MAXIMO, nuevo)))
            self._cache.descartar_otros_zooms(self._disposicion.zoom, self.devicePixelRatioF())
            self.zoom_cambiado.emit(self._disposicion.zoom)

    def _al_desplazar(self, _valor: int) -> None:
        if not self.paginas:
            return
        pagina = self._disposicion.pagina_dominante(self._area_visible())
        if pagina != self._pagina_actual:
            self._pagina_actual = pagina
            self.pagina_cambiada.emit(pagina)
        self.viewport().update()

    def _imagen(self, indice: int, dpr: float) -> QImage | None:
        """Imagen rasterizada de una pagina, del cache o recien generada."""
        if self._documento is None:
            return None
        clave = CachePaginas.clave(indice, self._disposicion.zoom, dpr)
        if (imagen := self._cache.obtener(clave)) is not None:
            return imagen

        rect = self._disposicion.rect(indice)
        tamano = (rect.size() * dpr).toSize()
        if tamano.isEmpty():
            return None

        opciones = QPdfDocumentRenderOptions()
        imagen = self._documento.render(indice, tamano, opciones)
        if imagen.isNull():
            return None
        imagen.setDevicePixelRatio(dpr)
        self._cache.guardar(clave, imagen)
        return imagen

    def _pintar_capa(
        self,
        pintor: QPainter,
        indice: int,
        desplazamiento: QPointF,
        capa: list[Resaltado],
        alfa: int,
    ) -> None:
        pintor.setPen(Qt.PenStyle.NoPen)
        for marca in capa:
            if marca.pagina != indice:
                continue
            color = QColor(marca.color)
            color.setAlpha(alfa)
            pintor.setBrush(color)
            pintor.drawRect(
                self._disposicion.rect_a_lienzo(indice, marca.rect).translated(desplazamiento)
            )

    def _pagina_bajo(self, posicion: QPointF) -> tuple[int, QPointF] | None:
        """Pagina y punto PDF bajo una posicion del viewport."""
        if not self.paginas:
            return None
        area = self._area_visible()
        lienzo = QPointF(posicion.x() + area.x(), posicion.y() + area.y())
        indice = self._disposicion.pagina_en(lienzo.y())
        return indice, self._disposicion.a_puntos(indice, lienzo)

    def _a_puntos_en(self, indice: int, posicion: QPointF) -> QPointF:
        area = self._area_visible()
        lienzo = QPointF(posicion.x() + area.x(), posicion.y() + area.y())
        return self._disposicion.a_puntos(indice, lienzo)

    def _recalcular_seleccion(self) -> None:
        """Pide a Qt el texto entre los dos extremos y guarda sus rectangulos."""
        if self._documento is None or self._rango_seleccion is None or self._texto is None:
            return

        pagina = self._pagina_seleccion
        inicio, fin = self._rango_seleccion
        # Sin este ajuste, arrastrar desde el margen no seleccionaria nada.
        inicio = self._texto.ajustar(pagina, inicio)
        fin = self._texto.ajustar(pagina, fin)
        seleccion = self._documento.getSelection(pagina, inicio, fin)

        if not seleccion.isValid() or not seleccion.text():
            self._seleccion = []
            self._texto_seleccionado = ""
            self.viewport().update()
            return

        self._texto_seleccionado = seleccion.text()
        self._seleccion = [
            Resaltado(pagina, poligono.boundingRect(), tokens.INFO)
            for poligono in seleccion.bounds()
        ]
        self.viewport().update()

    def _limpiar_seleccion(self) -> None:
        self._seleccion = []
        self._texto_seleccionado = ""
        self._pagina_seleccion = -1
        self._rango_seleccion = None
        self._arrastrando = False
