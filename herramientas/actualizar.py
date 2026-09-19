"""Deja al dia el ejecutable y el instalador tras un cambio de codigo.

    python herramientas/actualizar.py            # todo
    python herramientas/actualizar.py --rapido   # sin instalador (mas veloz)

Encadena los tres pasos que hay que dar siempre despues de tocar el codigo:

1. ``construir.py``   compila el paquete
2. ``instalar.py``    lo estrena en esta maquina, conservando ``datos/``
3. ``empaquetar.py``  regenera ``Mukuwareru-Setup-X.Y.Z.exe``

Existe por una razon aprendida a base de fallos: **cambiar el codigo no cambia la
aplicacion instalada**. Mas de una vez un arreglo estaba hecho y el fallo seguia
a la vista porque el ``.exe`` era el anterior. Un solo comando quita la excusa.

Antes de compilar pasa las comprobaciones. Si alguna falla, no se compila nada:
publicar un ejecutable roto es peor que no publicarlo.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
HERRAMIENTAS = RAIZ / "herramientas"

_COMPROBACIONES = (
    ("ruff", [sys.executable, "-m", "ruff", "check", "."]),
    ("mypy", [sys.executable, "-m", "mypy", "mukuwareru/nucleo"]),
    ("pytest", [sys.executable, "-m", "pytest", "-q"]),
    ("humo", [sys.executable, str(HERRAMIENTAS / "humo.py")]),
)


def _ejecutar(titulo: str, orden: list[str]) -> bool:
    """Lanza un paso y cuenta si salio bien."""
    print(f"\n=== {titulo} " + "=" * max(0, 60 - len(titulo)))
    return subprocess.run(orden, cwd=RAIZ, check=False).returncode == 0


def main(rapido: bool) -> int:
    """Comprueba, compila, instala y empaqueta."""
    for titulo, orden in _COMPROBACIONES:
        if not _ejecutar(titulo, orden):
            print(f"\nFALLA {titulo}. No se compila nada.")
            return 1

    pasos = [("construir", "construir.py"), ("instalar", "instalar.py")]
    if not rapido:
        pasos.append(("empaquetar", "empaquetar.py"))

    for titulo, guion in pasos:
        if not _ejecutar(titulo, [sys.executable, str(HERRAMIENTAS / guion)]):
            print(f"\nFALLA {titulo}.")
            return 1

    print("\n" + "=" * 68)
    print("Ejecutable instalado y al dia.")
    if rapido:
        print("Instalador NO regenerado (--rapido). Para publicarlo:")
        print("  python herramientas/empaquetar.py")
    else:
        print("Instalador regenerado.")
    print("Cierra Mukuwareru y vuelve a abrirlo para ver los cambios.")
    return 0


if __name__ == "__main__":
    sys.exit(main(rapido="--rapido" in sys.argv))
