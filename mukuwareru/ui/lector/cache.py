"""Cache de paginas rasterizadas.

Rasterizar una pagina A4 al 150 % cuesta decenas de milisegundos: hacerlo en
cada ``paintEvent`` haria el scroll inusable. Este cache guarda las imagenes ya
generadas y las descarta por orden de uso menos reciente.

La clave incluye el zoom porque una pagina al 80 % y la misma al 150 % son
imagenes distintas. El zoom se redondea a dos decimales para que un ajuste
continuo no genere una entrada nueva por cada pixel de diferencia.
"""

from __future__ import annotations

from collections import OrderedDict

from PySide6.QtGui import QImage

_MAXIMO_POR_DEFECTO = 24


class CachePaginas:
    """Cache LRU de imagenes de pagina."""

    def __init__(self, maximo: int = _MAXIMO_POR_DEFECTO) -> None:
        self._maximo = maximo
        self._entradas: OrderedDict[tuple[int, int, int], QImage] = OrderedDict()

    @staticmethod
    def clave(pagina: int, zoom: float, dpr: float) -> tuple[int, int, int]:
        """Clave estable para una pagina a un zoom y densidad de pixeles dados."""
        return (pagina, round(zoom * 100), round(dpr * 100))

    def obtener(self, clave: tuple[int, int, int]) -> QImage | None:
        """Devuelve la imagen si esta cacheada y la marca como recien usada."""
        imagen = self._entradas.get(clave)
        if imagen is None:
            return None
        self._entradas.move_to_end(clave)
        return imagen

    def guardar(self, clave: tuple[int, int, int], imagen: QImage) -> None:
        """Guarda una imagen, descartando la mas antigua si hace falta."""
        self._entradas[clave] = imagen
        self._entradas.move_to_end(clave)
        while len(self._entradas) > self._maximo:
            self._entradas.popitem(last=False)

    def descartar_otros_zooms(self, zoom: float, dpr: float) -> None:
        """Suelta las imagenes de zooms que ya no se van a mostrar.

        Tras varios cambios de zoom el cache se llena de tamanos obsoletos que
        ocupan memoria sin volver a usarse nunca.
        """
        actual = (round(zoom * 100), round(dpr * 100))
        for clave in [c for c in self._entradas if (c[1], c[2]) != actual]:
            del self._entradas[clave]

    def vaciar(self) -> None:
        """Descarta todo. Se usa al abrir otro documento."""
        self._entradas.clear()

    def __len__(self) -> int:
        return len(self._entradas)
