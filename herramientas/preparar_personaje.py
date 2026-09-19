"""Convierte la foto del personaje en el PNG con transparencia que usa el timeline.

La imagen de origen es una foto de estudio: figura oscura sobre fondo blanco. Se
recorta ese fondo, se ajusta al rectangulo util y se guarda a una altura fija.

Se ejecuta a mano y el resultado se versiona: la aplicacion no lleva conversores
de imagen dentro. Solo hay que volver a pasarla si cambia la foto de origen.

    python herramientas/preparar_personaje.py [origen.jpg]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QGuiApplication, QImage, qAlpha, qBlue, qGreen, qRed, qRgba

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "Imagen.jpg"
DESTINO = RAIZ / "mukuwareru" / "recursos" / "personaje.png"

# Rampa del fondo: por encima de OPACO_HASTA todo es figura, por debajo de
# TRANSPARENTE_DESDE todo es fondo. En medio se interpola el alfa, que es lo que
# evita el halo blanco alrededor de la silueta.
TRANSPARENTE_DESDE = 244
OPACO_HASTA = 216

ALTURA = 256
MARGEN = 2


def _luminancia(pixel: int) -> int:
    """Gris perceptual del pixel, 0 negro y 255 blanco."""
    return (qRed(pixel) * 299 + qGreen(pixel) * 587 + qBlue(pixel) * 114) // 1000


def _alfa(pixel: int) -> int:
    """Opacidad que le toca al pixel segun lo cerca que este del blanco."""
    luz = _luminancia(pixel)
    if luz >= TRANSPARENTE_DESDE:
        return 0
    if luz <= OPACO_HASTA:
        return qAlpha(pixel)
    tramo = TRANSPARENTE_DESDE - OPACO_HASTA
    return int(255 * (TRANSPARENTE_DESDE - luz) / tramo)


def quitar_fondo(imagen: QImage) -> QImage:
    """Devuelve la imagen con el fondo claro convertido en transparencia."""
    salida = imagen.convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(salida.height()):
        for x in range(salida.width()):
            pixel = salida.pixel(x, y)
            alfa = _alfa(pixel)
            if alfa == qAlpha(pixel):
                continue
            salida.setPixel(x, y, qRgba(qRed(pixel), qGreen(pixel), qBlue(pixel), alfa))
    return salida


def recortar(imagen: QImage) -> QImage:
    """Ajusta la imagen al rectangulo que de verdad tiene contenido."""
    izquierda, derecha = imagen.width(), 0
    arriba, abajo = imagen.height(), 0
    for y in range(imagen.height()):
        for x in range(imagen.width()):
            if qAlpha(imagen.pixel(x, y)) < 12:
                continue
            izquierda, derecha = min(izquierda, x), max(derecha, x)
            arriba, abajo = min(arriba, y), max(abajo, y)

    if derecha <= izquierda or abajo <= arriba:
        return imagen

    izquierda = max(0, izquierda - MARGEN)
    arriba = max(0, arriba - MARGEN)
    derecha = min(imagen.width() - 1, derecha + MARGEN)
    abajo = min(imagen.height() - 1, abajo + MARGEN)
    return imagen.copy(izquierda, arriba, derecha - izquierda + 1, abajo - arriba + 1)


def preparar(origen: Path, destino: Path) -> int:
    """Lee, limpia, recorta, escala y guarda. Devuelve el codigo de salida."""
    if not origen.exists():
        print(f"No se encuentra la imagen de origen:\n  {origen}")
        return 1

    imagen = QImage(str(origen))
    if imagen.isNull():
        print(f"Qt no pudo leer la imagen:\n  {origen}")
        return 1

    print(f"Origen: {imagen.width()}x{imagen.height()} px")
    limpia = recortar(quitar_fondo(imagen))
    escalada = limpia.scaledToHeight(
        ALTURA, Qt.TransformationMode.SmoothTransformation
    )

    destino.parent.mkdir(parents=True, exist_ok=True)
    if not escalada.save(str(destino), "PNG"):
        print(f"No se pudo escribir:\n  {destino}")
        return 1

    print(f"Escrito: {destino}  ({escalada.width()}x{escalada.height()} px)")
    return 0


def main() -> int:
    """Punto de entrada de la herramienta."""
    # QImage necesita una aplicacion Qt viva para los plugins de imagen, pero no
    # una ventana: basta la de consola.
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_PluginApplication, False)
    aplicacion = QGuiApplication(sys.argv)
    origen = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ORIGEN
    codigo = preparar(origen, DESTINO)
    del aplicacion
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
