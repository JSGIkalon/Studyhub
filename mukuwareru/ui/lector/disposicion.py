"""Disposicion de las paginas dentro del visor.

Calcula, para un zoom dado, donde cae cada pagina en el lienzo virtual y como
traducir entre coordenadas del lienzo y coordenadas de pagina en **puntos PDF**.

Ese mapeo es el motivo de que el visor sea propio: ``QPdfView`` no lo expone y
sin el no hay seleccion de texto, ni resaltados, ni anclaje de anotaciones.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSizeF

MARGEN = 16.0      # margen exterior del lienzo, en pixeles
SEPARACION = 14.0  # hueco entre paginas, en pixeles


@dataclass(frozen=True, slots=True)
class Ubicacion:
    """Donde esta una pagina dentro del lienzo, en pixeles."""

    indice: int
    rect: QRectF


class Disposicion:
    """Coloca las paginas en una sola columna con scroll continuo."""

    def __init__(self, tamanos: list[QSizeF], zoom: float = 1.0) -> None:
        self._tamanos = tamanos
        self._zoom = zoom
        self._ubicaciones: list[Ubicacion] = []
        self._ancho = 0.0
        self._alto = 0.0
        self._recalcular()

    # -- Estado ------------------------------------------------------------

    @property
    def zoom(self) -> float:
        """Factor de escala vigente."""
        return self._zoom

    @property
    def paginas(self) -> int:
        """Numero de paginas del documento."""
        return len(self._tamanos)

    @property
    def ancho(self) -> float:
        """Ancho total del lienzo, margenes incluidos."""
        return self._ancho

    @property
    def alto(self) -> float:
        """Alto total del lienzo, margenes incluidos."""
        return self._alto

    def establecer_zoom(self, zoom: float) -> None:
        """Cambia el zoom y recalcula las posiciones."""
        if abs(zoom - self._zoom) < 1e-6:
            return
        self._zoom = zoom
        self._recalcular()

    def tamano_puntos(self, indice: int) -> QSizeF:
        """Tamano de la pagina en puntos PDF, sin escalar."""
        return self._tamanos[indice]

    def rect(self, indice: int) -> QRectF:
        """Rectangulo de una pagina dentro del lienzo, en pixeles."""
        return self._ubicaciones[indice].rect

    # -- Consultas ---------------------------------------------------------

    def visibles(self, area: QRectF, margen_paginas: int = 1) -> list[Ubicacion]:
        """Paginas que intersecan el area visible, mas ``margen_paginas`` a cada lado.

        Renderizar una pagina de mas por arriba y por abajo hace que el scroll
        no muestre huecos en blanco.
        """
        indices = [u.indice for u in self._ubicaciones if u.rect.intersects(area)]
        if not indices:
            return [self._ubicaciones[self.pagina_en(area.center().y())]]

        primero = max(0, min(indices) - margen_paginas)
        ultimo = min(self.paginas - 1, max(indices) + margen_paginas)
        return self._ubicaciones[primero : ultimo + 1]

    def pagina_en(self, y: float) -> int:
        """Indice de la pagina que ocupa esa altura del lienzo."""
        for ubicacion in self._ubicaciones:
            if y < ubicacion.rect.bottom() + SEPARACION / 2:
                return ubicacion.indice
        return max(0, self.paginas - 1)

    def pagina_dominante(self, area: QRectF) -> int:
        """Pagina que ocupa mas superficie del area visible.

        Es la que debe considerarse «la pagina actual»: al recordar la posicion
        de lectura interesa la que se esta mirando, no la que asoma por el borde.
        """
        mejor, mayor = 0, -1.0
        for ubicacion in self._ubicaciones:
            interseccion = ubicacion.rect.intersected(area)
            superficie = interseccion.width() * interseccion.height()
            if superficie > mayor:
                mejor, mayor = ubicacion.indice, superficie
        return mejor

    # -- Conversion de coordenadas ------------------------------------------

    def a_puntos(self, indice: int, punto_lienzo: QPointF) -> QPointF:
        """Convierte un punto del lienzo a puntos PDF dentro de esa pagina."""
        rect = self.rect(indice)
        return QPointF(
            (punto_lienzo.x() - rect.x()) / self._zoom,
            (punto_lienzo.y() - rect.y()) / self._zoom,
        )

    def a_lienzo(self, indice: int, punto_pdf: QPointF) -> QPointF:
        """Convierte un punto en puntos PDF a coordenadas del lienzo."""
        rect = self.rect(indice)
        return QPointF(
            rect.x() + punto_pdf.x() * self._zoom,
            rect.y() + punto_pdf.y() * self._zoom,
        )

    def rect_a_lienzo(self, indice: int, rect_pdf: QRectF) -> QRectF:
        """Convierte un rectangulo en puntos PDF a coordenadas del lienzo."""
        origen = self.a_lienzo(indice, rect_pdf.topLeft())
        return QRectF(
            origen.x(),
            origen.y(),
            rect_pdf.width() * self._zoom,
            rect_pdf.height() * self._zoom,
        )

    def zoom_para_ancho(self, ancho_disponible: float) -> float:
        """Zoom que hace caber la pagina mas ancha en el ancho dado."""
        if not self._tamanos:
            return 1.0
        maximo = max(t.width() for t in self._tamanos)
        return max(0.1, (ancho_disponible - 2 * MARGEN) / maximo)

    def zoom_para_pagina(self, ancho: float, alto: float) -> float:
        """Zoom que hace caber una pagina entera en el area dada."""
        if not self._tamanos:
            return 1.0
        ancho_max = max(t.width() for t in self._tamanos)
        alto_max = max(t.height() for t in self._tamanos)
        return max(
            0.1,
            min(
                (ancho - 2 * MARGEN) / ancho_max,
                (alto - 2 * MARGEN) / alto_max,
            ),
        )

    # -- Interno -----------------------------------------------------------

    def _recalcular(self) -> None:
        self._ubicaciones = []
        ancho_max = max((t.width() for t in self._tamanos), default=0.0) * self._zoom
        self._ancho = ancho_max + 2 * MARGEN

        y = MARGEN
        for indice, tamano in enumerate(self._tamanos):
            ancho = tamano.width() * self._zoom
            alto = tamano.height() * self._zoom
            # Centradas horizontalmente: las paginas apaisadas no deben saltar.
            x = (self._ancho - ancho) / 2
            self._ubicaciones.append(Ubicacion(indice, QRectF(x, y, ancho, alto)))
            y += alto + SEPARACION

        self._alto = y - SEPARACION + MARGEN if self._ubicaciones else 0.0
