"""Copia la base de datos de desarrollo sobre la de una instalacion.

    python herramientas/copiar_datos.py <destino\\basedatos.db>

Usa la API de respaldo de SQLite en lugar de copiar archivos: asi el WAL se
consolida y el destino queda consistente aunque el origen estuviera abierto.

Sirve para estrenar una instalacion con lo ya registrado en desarrollo. En el
uso normal no hace falta: el ejecutable conserva su propio ``datos/`` entre
actualizaciones.

El destino es **obligatorio** a proposito: esto sobrescribe una base entera, y
un valor por defecto haria que ejecutarlo sin pensar pisara los datos reales.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from herramientas.respaldar import verificar  # noqa: E402

ORIGEN = RAIZ / "datos" / "basedatos.db"


def main(destino: Path) -> int:
    """Respalda la base de datos de desarrollo sobre ``destino``."""
    if not ORIGEN.exists():
        print(f"No existe {ORIGEN}")
        return 1

    destino.parent.mkdir(parents=True, exist_ok=True)
    for residuo in (
        destino,
        destino.with_name(destino.name + "-wal"),
        destino.with_name(destino.name + "-shm"),
    ):
        residuo.unlink(missing_ok=True)

    origen = sqlite3.connect(str(ORIGEN))
    copia = sqlite3.connect(str(destino))
    try:
        origen.backup(copia)
    finally:
        copia.close()
        origen.close()

    correcta, detalle = verificar(destino)
    print(f"Copiado a {destino}")
    print(f"  {detalle}")
    return 0 if correcta else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
