"""Genera el instalador distribuible de Mukuwareru.

    python herramientas/construir.py      # compila
    python herramientas/empaquetar.py     # produce Mukuwareru-Setup-X.Y.Z.exe

El resultado es un unico ``.exe`` que se puede llevar a cualquier Windows 10 u
11 de 64 bits: el paquete ya incluye Python y Qt, asi que en el equipo de
destino no hace falta instalar nada previo.

Requiere Inno Setup 6 (``winget install JRSoftware.InnoSetup``). Se busca su
compilador en las rutas habituales de instalacion por usuario y por maquina.

Diferencia con ``instalar.py``: aquel actualiza *esta* maquina copiando archivos
y es lo que conviene durante el desarrollo; este produce el instalador para
*otras* maquinas y tarda bastante mas, porque comprime 144 MB.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from construir import COMPILADO as ORIGEN  # una sola definicion de la ruta

from mukuwareru import __version__

RAIZ = Path(__file__).resolve().parent.parent
GUION = RAIZ / "herramientas" / "mukuwareru.iss"
ICONO = RAIZ / "mukuwareru" / "recursos" / "mukuwareru.ico"

# Dentro de herramientas, junto al script que lo genera: se sincroniza con
# OneDrive como el resto del proyecto y se encuentra sin tener que buscarlo.
SALIDA = RAIZ / "herramientas" / "Instalador"

_CANDIDATOS_ISCC = (
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("PROGRAMFILES", "")) / "Inno Setup 6" / "ISCC.exe",
)


def buscar_compilador() -> Path | None:
    """Localiza ``ISCC.exe``, el compilador de Inno Setup."""
    for ruta in _CANDIDATOS_ISCC:
        if ruta.is_file():
            return ruta
    return None


def main() -> int:
    """Compila el guion de Inno Setup contra la ultima compilacion."""
    if not (ORIGEN / "Mukuwareru.exe").exists():
        print(f"No hay compilacion en {ORIGEN}.\nEjecuta antes:  python herramientas/construir.py")
        return 1

    iscc = buscar_compilador()
    if iscc is None:
        print(
            "No se encuentra Inno Setup 6.\n"
            "Instalalo con:  winget install --id JRSoftware.InnoSetup"
        )
        return 1

    SALIDA.mkdir(parents=True, exist_ok=True)
    print(f"Empaquetando {__version__} con {iscc.name}…")
    print("Comprimir 144 MB lleva un par de minutos.\n")

    resultado = subprocess.run(
        [
            str(iscc),
            f"/DVersion={__version__}",
            f"/DOrigen={ORIGEN}",
            f"/DSalida={SALIDA}",
            f"/DIcono={ICONO}",
            "/Qp",  # solo avisos y errores: la lista de 500 archivos no aporta
            str(GUION),
        ],
        cwd=RAIZ,
        check=False,
    )
    if resultado.returncode != 0:
        return resultado.returncode

    instalador = SALIDA / f"Mukuwareru-Setup-{__version__}.exe"
    tamano = instalador.stat().st_size / 1024 / 1024
    print(f"\nInstalador listo ({tamano:.0f} MB):\n  {instalador}")
    print(
        "\nCopialo a cualquier Windows 10/11 de 64 bits y ejecutalo.\n"
        "No pide permisos de administrador y no necesita Python instalado."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
