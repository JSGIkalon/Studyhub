"""Ajuste de la seleccion al texto de la pagina.

``QPdfDocument.getSelection`` solo devuelve algo cuando **ambos** puntos caen
justo dentro de la caja de un glifo. Arrastrar desde el margen izquierdo, o
soltar en el hueco entre dos lineas, devuelve una seleccion invalida: el
comportamiento que cualquiera esperaria de un visor no se obtiene gratis.

Aqui se resuelve ajustando cada punto al texto mas cercano antes de preguntar a
Qt, que es lo que hacen los visores de verdad.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtPdf import QPdfDocument

# Cuanto se mete el punto dentro de la caja al ajustarlo. Justo en el borde
# pdfium sigue considerandolo fuera.
_MARGEN_INTERIOR = 1.0


class TextoDePagina:
    """Cajas de texto de una pagina, cacheadas por pagina.

    Extraer el texto de una pagina cuesta milisegundos; hacerlo en cada
    movimiento del raton durante un arrastre seria inaceptable.
    """

    def __init__(self, documento: QPdfDocument) -> None:
        self._documento = documento
        self._cajas: dict[int, list[QRectF]] = {}

    def cajas(self, pagina: int) -> list[QRectF]:
        """Rectangulos de todos los fragmentos de texto de la pagina."""
        if (guardadas := self._cajas.get(pagina)) is not None:
            return guardadas

        seleccion = self._documento.getAllText(pagina)
        cajas = (
            [poligono.boundingRect() for poligono in seleccion.bounds()]
            if seleccion.isValid()
            else []
        )
        self._cajas[pagina] = cajas
        return cajas

    def vaciar(self) -> None:
        """Descarta el cache. Se usa al abrir otro documento."""
        self._cajas.clear()

    def ajustar(self, pagina: int, punto: QPointF) -> QPointF:
        """Devuelve el punto llevado al texto mas cercano.

        Si ya esta sobre texto se devuelve tal cual. Si no, se proyecta sobre la
        caja mas proxima, de modo que arrastrar desde el margen seleccione desde
        el principio de esa linea.
        """
        cajas = self.cajas(pagina)
        if not cajas:
            return punto

        mejor: QRectF | None = None
        menor = float("inf")
        for caja in cajas:
            if caja.contains(punto):
                return punto
            distancia = _distancia(caja, punto)
            if distancia < menor:
                mejor, menor = caja, distancia

        if mejor is None:
            return punto
        return QPointF(
            min(max(punto.x(), mejor.left() + _MARGEN_INTERIOR), mejor.right() - _MARGEN_INTERIOR),
            min(max(punto.y(), mejor.top() + _MARGEN_INTERIOR), mejor.bottom() - _MARGEN_INTERIOR),
        )


def _distancia(caja: QRectF, punto: QPointF) -> float:
    """Distancia al cuadrado entre un punto y el borde de un rectangulo.

    Se evita la raiz cuadrada porque solo se usa para comparar.
    """
    dx = max(caja.left() - punto.x(), 0.0, punto.x() - caja.right())
    dy = max(caja.top() - punto.y(), 0.0, punto.y() - caja.bottom())
    # Las lineas se recorren en vertical: penalizar mas la distancia vertical
    # evita saltar a la linea de al lado cuando se arrastra por el margen.
    return dx * dx + dy * dy * 4.0
