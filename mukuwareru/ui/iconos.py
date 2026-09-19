"""Carga de iconos SVG con tinte.

Los SVG llevan ``stroke="{{COLOR}}"``, que se sustituye antes de rasterizar.
Un unico archivo por icono sirve entonces para todos los estados (normal,
hover, activo) sin duplicar recursos.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from mukuwareru.ui.tema import tokens

_TAMANO = 18

# Tamanos que Windows pide del icono de la aplicacion (barra de tareas, Alt+Tab,
# escritorio, notificaciones).
_LADOS_APP = (16, 24, 32, 48, 64, 128, 256)


@lru_cache(maxsize=128)
def _fuente_svg(nombre: str) -> str:
    recurso = resources.files("mukuwareru.recursos.iconos").joinpath(f"{nombre}.svg")
    return recurso.read_text(encoding="utf-8")


@lru_cache(maxsize=256)
def pixmap(nombre: str, color: str, tamano: int = _TAMANO) -> QPixmap:
    """Rasteriza un icono al color y tamano pedidos."""
    svg = _fuente_svg(nombre).replace("{{COLOR}}", color)
    renderizador = QSvgRenderer(svg.encode("utf-8"))

    imagen = QImage(tamano, tamano, QImage.Format.Format_ARGB32_Premultiplied)
    imagen.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(imagen)
    renderizador.render(pintor, QRectF(0, 0, tamano, tamano))
    pintor.end()
    return QPixmap.fromImage(imagen)


@lru_cache(maxsize=256)
def icono(nombre: str, color: str = tokens.TEXTO_SUAVE, tamano: int = _TAMANO) -> QIcon:
    """Devuelve un ``QIcon`` cacheado; ante un nombre desconocido, vacio."""
    try:
        return QIcon(pixmap(nombre, color, tamano))
    except (FileNotFoundError, ModuleNotFoundError):
        return QIcon()


@lru_cache(maxsize=8)
def personaje(altura: int) -> QPixmap:
    """Silueta del caminante del timeline, escalada a la altura pedida.

    Se lee con ``importlib.resources`` como los iconos, y no por ruta de disco:
    es lo que hace que siga cargando dentro del ejecutable congelado. Si el PNG
    no esta —se genera con ``herramientas/preparar_personaje.py``— se devuelve un
    mapa vacio y el timeline pinta un marcador simple en su lugar.
    """
    recurso = resources.files("mukuwareru.recursos").joinpath("personaje.png")
    try:
        mapa = QPixmap()
        if not mapa.loadFromData(recurso.read_bytes()) or mapa.isNull():
            return QPixmap()
    except (FileNotFoundError, ModuleNotFoundError):
        return QPixmap()
    return mapa.scaledToHeight(altura, Qt.TransformationMode.SmoothTransformation)


@lru_cache(maxsize=1)
def icono_aplicacion() -> QIcon:
    """Icono de la ventana, la barra de tareas y los avisos del sistema.

    Un ``logo.png`` en ``mukuwareru/recursos`` tiene prioridad sobre el vectorial:
    es la via para poner un logotipo dibujado fuera sin tocar codigo. El SVG
    queda como respaldo.
    """
    png = resources.files("mukuwareru.recursos").joinpath("logo.png")
    try:
        mapa = QPixmap()
        if mapa.loadFromData(png.read_bytes()) and not mapa.isNull():
            # Se registran los tamanos pequenos ya escalados. Con un unico mapa
            # de 1254 px, Qt reduce a 16 px de golpe y el trazo se ensucia.
            resultado = QIcon()
            for lado in _LADOS_APP:
                resultado.addPixmap(
                    mapa.scaled(
                        lado,
                        lado,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            return resultado
    except (FileNotFoundError, ModuleNotFoundError):
        pass

    svg = resources.files("mukuwareru.recursos").joinpath("mukuwareru.svg")
    try:
        fuente = svg.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        return QIcon()

    renderizador = QSvgRenderer(fuente.encode("utf-8"))
    resultado = QIcon()
    for lado in _LADOS_APP:
        imagen = QImage(lado, lado, QImage.Format.Format_ARGB32_Premultiplied)
        imagen.fill(Qt.GlobalColor.transparent)
        pintor = QPainter(imagen)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderizador.render(pintor, QRectF(0, 0, lado, lado))
        pintor.end()
        resultado.addPixmap(QPixmap.fromImage(imagen))
    return resultado
