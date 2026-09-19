"""Huella rapida de un archivo.

Identifica un PDF aunque se renombre o se mueva de carpeta, sin leerlo entero:
un temario de 40 MB no puede releerse en cada escaneo de la biblioteca.

Combina el tamano con el MD5 de los primeros y ultimos 64 KB. Para PDFs, cuyas
cabeceras y tablas de referencias cruzadas son practicamente unicas, la
probabilidad de colision es despreciable. No es una huella criptografica y no
pretende serlo.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_BLOQUE = 64 * 1024


def calcular(ruta: Path) -> str:
    """Devuelve la huella de un archivo como ``<tamano>-<md5parcial>``."""
    tamano = ruta.stat().st_size
    resumen = hashlib.md5(usedforsecurity=False)
    resumen.update(str(tamano).encode())

    with ruta.open("rb") as archivo:
        resumen.update(archivo.read(_BLOQUE))
        if tamano > _BLOQUE * 2:
            archivo.seek(-_BLOQUE, 2)
            resumen.update(archivo.read(_BLOQUE))

    return f"{tamano}-{resumen.hexdigest()[:16]}"
