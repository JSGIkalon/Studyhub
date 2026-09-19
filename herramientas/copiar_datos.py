"""Copia la base de datos de desarrollo a la carpeta del ejecutable.

    python herramientas/copiar_datos.py [destino]

Usa la API de respaldo de SQLite en lugar de copiar archivos: asi el WAL se
consolida y el destino queda consistente aunque el origen estuviera abierto.

Sirve para estrenar una version compilada sin perder lo ya registrado. En el uso
normal no hace falta: el ejecutable conserva su propio ``datos/`` entre
actualizaciones.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ORIGEN = RAIZ / "datos" / "basedatos.db"
DESTINO_POR_DEFECTO = RAIZ / "dist" / "Mukuwareru" / "datos" / "basedatos.db"


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

    comprobacion = sqlite3.connect(str(destino))
    try:
        proyectos = comprobacion.execute("SELECT COUNT(*) FROM proyecto").fetchone()[0]
        modulos = comprobacion.execute(
            "SELECT COUNT(*), COALESCE(SUM(completado), 0) FROM modulo"
        ).fetchone()
        sesiones = comprobacion.execute("SELECT COUNT(*) FROM sesion").fetchone()[0]
    finally:
        comprobacion.close()

    print(f"Copiado a {destino}")
    print(f"  proyectos: {proyectos}")
    print(f"  modulos:   {modulos[1]} / {modulos[0]} completados")
    print(f"  sesiones:  {sesiones}")
    return 0


if __name__ == "__main__":
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else DESTINO_POR_DEFECTO
    sys.exit(main(ruta))
