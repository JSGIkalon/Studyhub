"""Instala o actualiza Mukuwareru en la carpeta de uso diario.

    python herramientas/instalar.py [carpeta]

Copia ``Mukuwareru.exe`` y ``_internal/`` desde la compilacion (ver ``construir.py``) a la
carpeta de instalacion y **nunca toca** ``datos/``, ``Library/`` ni ``logs/``. Ese es
exactamente el requisito de poder actualizar el ejecutable sin perder la
informacion del usuario.

Por defecto instala en ``%LOCALAPPDATA%\\Programs\\Mukuwareru``, deliberadamente
fuera de OneDrive: una carpeta de 130 MB que se sincroniza en cada compilacion
es una molestia, y la sincronizacion puede corromper una base SQLite abierta.

Si encuentra una instalacion de la epoca en que la aplicacion se llamaba
StudyHub, se trae sus datos antes de nada. Ver ``_migrar_desde_studyhub``.

Al terminar crea un acceso directo en el Escritorio.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from construir import COMPILADO as ORIGEN  # una sola definicion de la ruta

from herramientas._comun import carpeta_instalacion

GENERADO = ("Mukuwareru.exe", "_internal")
DEL_USUARIO = ("datos", "Library", "logs")

# La aplicacion se llamo StudyHub hasta la version 1.0.0.
NOMBRE_ANTERIOR = "StudyHub"


def _migrar_desde_studyhub(destino: Path) -> None:
    """Trae los datos de la instalacion anterior, cuando se llamaba StudyHub.

    Cambiar el nombre cambia la carpeta de instalacion, y con ella la ruta donde
    vive la base de datos. Sin esto, renombrar la aplicacion equivaldria a
    empezar de cero: progreso, sesiones, anotaciones y biblioteca perdidos.

    Se **copia**, no se mueve: si algo saliera mal, la carpeta antigua sigue
    intacta. Solo se copia lo que aun no existe en el destino, asi que ejecutarlo
    dos veces no pisa nada de lo nuevo.
    """
    anterior = destino.parent / NOMBRE_ANTERIOR
    if not anterior.is_dir() or anterior == destino:
        return

    pendientes = [
        c for c in DEL_USUARIO if (anterior / c).exists() and not (destino / c).exists()
    ]
    if not pendientes:
        return

    print(f"  se encontro una instalacion anterior en {anterior}")
    destino.mkdir(parents=True, exist_ok=True)
    for nombre in pendientes:
        origen = anterior / nombre
        shutil.copytree(origen, destino / nombre)
        cuantos = sum(1 for f in (destino / nombre).rglob("*") if f.is_file())
        print(f"  migrado: {nombre} ({cuantos} archivos)")
    print(f"  la carpeta anterior no se ha tocado; puedes borrarla: {anterior}")


def main(destino: Path) -> int:
    """Copia la compilacion sobre la carpeta de instalacion."""
    if not (ORIGEN / "Mukuwareru.exe").exists():
        print(f"No hay compilacion en {ORIGEN}. Ejecuta antes construir.py")
        return 1

    actualizacion = (destino / "Mukuwareru.exe").exists()
    destino.mkdir(parents=True, exist_ok=True)
    print(("Actualizando" if actualizacion else "Instalando") + f" en {destino}")

    _migrar_desde_studyhub(destino)

    conservados = [c for c in DEL_USUARIO if (destino / c).exists()]
    if conservados:
        print(f"  se conservan: {', '.join(conservados)}")

    for nombre in GENERADO:
        origen = ORIGEN / nombre
        objetivo = destino / nombre
        if objetivo.is_dir():
            shutil.rmtree(objetivo, ignore_errors=True)
        elif objetivo.exists():
            objetivo.unlink()

        if origen.is_dir():
            shutil.copytree(origen, objetivo)
        else:
            shutil.copy2(origen, objetivo)
        print(f"  copiado: {nombre}")

    (destino / "Library").mkdir(exist_ok=True)

    if (base := destino / "datos" / "basedatos.db").exists():
        print(f"  base de datos intacta: {base.stat().st_size // 1024} KB")

    _crear_acceso_directo(destino / "Mukuwareru.exe")
    print(f"\nListo. Abre Mukuwareru con doble clic en:\n  {destino / 'Mukuwareru.exe'}")
    return 0


def _crear_acceso_directo(exe: Path) -> None:
    """Crea un acceso directo en el Escritorio mediante WScript.Shell."""
    if sys.platform != "win32":
        return
    guion = (
        "$w = New-Object -ComObject WScript.Shell; "
        "$a = $w.CreateShortcut("
        "[System.IO.Path]::Combine($w.SpecialFolders('Desktop'), 'Mukuwareru.lnk')); "
        f"$a.TargetPath = '{exe}'; "
        f"$a.WorkingDirectory = '{exe.parent}'; "
        f"$a.IconLocation = '{exe}'; "
        "$a.Description = 'Mukuwareru - centro de estudio'; "
        "$a.Save()"
    )
    resultado = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", guion],
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode == 0:
        print("  acceso directo creado en el Escritorio")
    else:
        print(f"  aviso: no se pudo crear el acceso directo ({resultado.stderr.strip()})")


if __name__ == "__main__":
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else carpeta_instalacion()
    sys.exit(main(ruta))
