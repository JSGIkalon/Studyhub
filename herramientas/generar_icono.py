"""Genera el icono del ejecutable a partir del logotipo de la aplicacion.

    python herramientas/generar_icono.py

Acepta dos fuentes, y prefiere la primera que encuentre:

1. ``mukuwareru/recursos/logo.png`` — un logotipo de mapa de bits. Es el camino
   para un logo dibujado fuera: basta con dejar el archivo ahi.
2. ``mukuwareru/recursos/mukuwareru.svg`` — el vectorial de respaldo.

Escribe ``mukuwareru.ico`` (para el ejecutable y el instalador) y, si la fuente es
PNG, tambien ``logo.png`` normalizado, que es lo que carga la interfaz en
caliente. Ambos se versionan para que compilar no dependa de este paso.

El ICO lleva varios tamanos dentro: Windows escoge el que necesita en cada sitio
(barra de tareas, Alt+Tab, escritorio) y escalar uno solo se ve mal en todos.
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

RAIZ = Path(__file__).resolve().parent.parent
RECURSOS = RAIZ / "mukuwareru" / "recursos"
ORIGEN_PNG = RECURSOS / "logo.png"
ORIGEN_SVG = RECURSOS / "mukuwareru.svg"
DESTINO = RECURSOS / "mukuwareru.ico"

LADOS = (16, 24, 32, 48, 64, 128, 256)


def _desde_svg(lado: int) -> QImage:
    renderizador = QSvgRenderer(ORIGEN_SVG.read_bytes())
    imagen = QImage(lado, lado, QImage.Format.Format_ARGB32)
    imagen.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(imagen)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderizador.render(pintor, QRectF(0, 0, lado, lado))
    pintor.end()
    return imagen


def _desde_png(fuente: QImage, lado: int) -> QImage:
    return fuente.scaled(
        lado,
        lado,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _a_png(imagen: QImage) -> bytes:
    """Serializa una imagen como PNG en memoria."""
    bufer = QBuffer()
    bufer.open(QIODevice.OpenModeFlag.WriteOnly)
    imagen.save(bufer, "PNG")
    return bytes(bufer.data())


def _escribir_ico(imagenes: list[QImage], destino: Path) -> None:
    """Ensambla un ICO multi-tamano con las imagenes comprimidas en PNG.

    Se hace a mano porque ``QImage.save`` escribe un ICO de **un solo** tamano y
    sin comprimir: un 256x256 salia por encima de 1 MB, y a partir de ahi el
    compilador de Inno Setup lo rechaza con «File is too large». Guardar cada
    tamano como PNG deja el archivo en decenas de KB. Windows admite entradas
    PNG dentro de un ICO desde Vista.
    """
    datos = [_a_png(imagen) for imagen in imagenes]
    cabecera = struct.pack("<HHH", 0, 1, len(datos))  # reservado, tipo ICO, numero

    desplazamiento = len(cabecera) + 16 * len(datos)
    entradas = b""
    for imagen, bloque in zip(imagenes, datos, strict=True):
        # Un 256 se codifica como 0: el campo es de un solo byte.
        lado = 0 if imagen.width() >= 256 else imagen.width()
        entradas += struct.pack(
            "<BBBBHHII", lado, lado, 0, 0, 1, 32, len(bloque), desplazamiento
        )
        desplazamiento += len(bloque)

    destino.write_bytes(cabecera + entradas + b"".join(datos))


def main() -> int:
    """Rasteriza el logotipo a todos los tamanos y lo guarda como ICO."""
    QGuiApplication(sys.argv)

    if ORIGEN_PNG.exists():
        fuente = QImage(str(ORIGEN_PNG))
        if fuente.isNull():
            print(f"No se pudo leer {ORIGEN_PNG}")
            return 1
        print(f"Fuente: {ORIGEN_PNG.name} ({fuente.width()}x{fuente.height()})")
        imagenes = [_desde_png(fuente, lado) for lado in LADOS]
    elif ORIGEN_SVG.exists():
        print(f"Fuente: {ORIGEN_SVG.name}")
        imagenes = [_desde_svg(lado) for lado in LADOS]
    else:
        print(f"No hay logotipo. Deja un PNG en {ORIGEN_PNG}")
        return 1

    _escribir_ico(imagenes, DESTINO)
    tamanos = " ".join(f"{i.width()}" for i in imagenes)
    print(f"Icono generado: {DESTINO.name} ({DESTINO.stat().st_size // 1024} KB)")
    print(f"Tamanos incluidos: {tamanos}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
