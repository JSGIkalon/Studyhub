"""Copia de seguridad de la base de datos, fuera del disco de trabajo.

    python herramientas/respaldar.py
    python herramientas/respaldar.py --destino D:\\Copias --conservar 30
    python herramientas/respaldar.py --base "C:\\otra\\basedatos.db"

**No es una funcion de la aplicacion y no debe serlo.** Es una herramienta de
fuera, como `sincronizar_temario.py`: la aplicacion se dedica a estudiar.

Por que hace falta
------------------
La base vive en `%LOCALAPPDATA%\\Programs\\Mukuwareru\\datos`, deliberadamente
fuera de OneDrive (ver §7 de PROJECT.md): sincronizar un SQLite **abierto** puede
corromperlo, porque el archivo y su WAL cambian a la vez y el sincronizador
puede subir uno sin el otro.

Un respaldo no tiene ese problema y por eso si va a OneDrive: es un archivo
**cerrado, consolidado y que nadie vuelve a abrir**. La distincion es la clave de
toda esta herramienta.

Lo unico que respaldaba algo hasta ahora era el migrador, que vuelca una copia al
subir de version de esquema... **en la misma carpeta que el original**. Sirve
para deshacer una migracion, no para sobrevivir a un disco que falla.

Como copia
----------
Con `sqlite3.backup()`, no copiando el archivo. Es lo mismo que hace
`copiar_datos.py` y por la misma razon: consolida el WAL y deja un destino
consistente aunque la base estuviera abierta en ese momento. Copiar el `.db` a
pelo mientras la aplicacion corre produce una copia que puede faltarle las
ultimas transacciones, o directamente no abrir.

Cada copia se verifica antes de darla por buena (`PRAGMA integrity_check` y un
recuento de filas): un respaldo que no se comprueba es una suposicion.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

NOMBRE_APP = "Mukuwareru"
CARPETA_RESPALDOS = f"{NOMBRE_APP}-Respaldos"
CONSERVAR_POR_DEFECTO = 14

RAIZ = Path(__file__).resolve().parent.parent


def base_instalada() -> Path:
    """La base que usa de verdad el ejecutable instalado.

    Es el origen por defecto a proposito. Hay dos bases —la del repositorio y la
    de la instalacion— y respaldar la equivocada es el fallo silencioso mas facil
    de cometer aqui; la que tiene los datos del usuario es la instalada.
    """
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Programs" / NOMBRE_APP / "datos" / "basedatos.db"


def destino_por_defecto() -> Path:
    """Carpeta de respaldos dentro de OneDrive, si lo hay.

    Sin OneDrive cae a la carpeta del usuario: una copia en el mismo disco sigue
    protegiendo del error humano —borrar un proyecto sin querer— aunque no de un
    fallo de hardware. Es peor que OneDrive y mucho mejor que nada.
    """
    # En mayusculas porque `os.environ` de Windows no distingue: es la misma
    # variable que el sistema expone como `OneDrive`.
    nube = os.environ.get("ONEDRIVECOMMERCIAL") or os.environ.get("ONEDRIVE")
    raiz = Path(nube) if nube else Path.home()
    return raiz / CARPETA_RESPALDOS


def respaldar(origen: Path, destino: Path) -> Path:
    """Escribe una copia consistente con marca de tiempo. Devuelve su ruta."""
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / f"basedatos-{datetime.now():%Y%m%d-%H%M%S}.db"

    conexion_origen = sqlite3.connect(f"file:{origen}?mode=ro", uri=True)
    copia = sqlite3.connect(str(archivo))
    try:
        conexion_origen.backup(copia)
        # La copia hereda el `journal_mode = WAL` del original, y entonces deja
        # un `-wal` y un `-shm` a su lado que OneDrive sincronizaria como si
        # fueran respaldos. Un respaldo tiene que ser **un** archivo que se
        # pueda copiar solo; en modo DELETE no hay laterales que olvidar.
        copia.execute("PRAGMA journal_mode = DELETE")
    finally:
        copia.close()
        conexion_origen.close()
    return archivo


def verificar(archivo: Path) -> tuple[bool, str]:
    """Comprueba que la copia abre, esta integra y trae datos."""
    conexion = sqlite3.connect(f"file:{archivo}?mode=ro", uri=True)
    try:
        integridad = conexion.execute("PRAGMA integrity_check").fetchone()[0]
        if integridad != "ok":
            return False, f"integrity_check dice «{integridad}»"

        proyectos = conexion.execute("SELECT COUNT(*) FROM proyecto").fetchone()[0]
        modulos, completados = conexion.execute(
            "SELECT COUNT(*), COALESCE(SUM(completado), 0) FROM modulo"
        ).fetchone()
        sesiones = conexion.execute("SELECT COUNT(*) FROM sesion").fetchone()[0]
        version = conexion.execute("SELECT MAX(version) FROM esquema_version").fetchone()[0]
    except sqlite3.DatabaseError as error:
        return False, f"no se puede leer: {error}"
    finally:
        conexion.close()

    if not proyectos:
        # Una copia sin proyectos casi siempre significa que se respaldo la base
        # equivocada, no que el usuario borrara todo.
        return False, "la copia no tiene ningun proyecto: ¿es la base correcta?"

    return True, (
        f"esquema v{version}  ·  {proyectos} proyectos  ·  "
        f"{completados} / {modulos} modulos completados  ·  {sesiones} sesiones"
    )


def podar(destino: Path, conservar: int) -> list[Path]:
    """Borra las copias mas viejas y devuelve las que se han borrado.

    Solo toca archivos con el patron que genera esta herramienta: cualquier otra
    cosa que el usuario haya dejado en la carpeta se queda donde esta.
    """
    copias = sorted(destino.glob("basedatos-*.db"), key=lambda p: p.name)
    sobrantes = copias[:-conservar] if conservar > 0 else []
    for vieja in sobrantes:
        vieja.unlink()
        # Por si la copia la dejo una version anterior de esta herramienta, que
        # todavia guardaba en modo WAL.
        for lateral in ("-wal", "-shm"):
            vieja.with_name(vieja.name + lateral).unlink(missing_ok=True)
    return sobrantes


def main() -> int:
    """Punto de entrada. Devuelve 0 solo si la copia queda verificada."""
    analizador = argparse.ArgumentParser(
        description="Copia de seguridad verificada de la base de Mukuwareru."
    )
    analizador.add_argument(
        "--base", type=Path, default=None, help="base de datos de origen"
    )
    analizador.add_argument(
        "--destino", type=Path, default=None, help="carpeta donde dejar las copias"
    )
    analizador.add_argument(
        "--conservar",
        type=int,
        default=CONSERVAR_POR_DEFECTO,
        help=f"cuantas copias mantener (0 = todas; por defecto {CONSERVAR_POR_DEFECTO})",
    )
    argumentos = analizador.parse_args()

    origen = argumentos.base or base_instalada()
    destino = argumentos.destino or destino_por_defecto()

    if not origen.exists():
        print(f"No existe la base de datos: {origen}")
        print("Usa --base para indicar otra.")
        return 1

    print(f"Origen  : {origen}")
    print(f"Destino : {destino}")

    try:
        archivo = respaldar(origen, destino)
    except (OSError, sqlite3.Error) as error:
        print(f"FALLO al copiar: {error}")
        return 1

    correcta, detalle = verificar(archivo)
    if not correcta:
        # La copia mala se borra: dejarla ahi es peor que no tenerla, porque
        # cuenta como respaldo y no lo es.
        archivo.unlink(missing_ok=True)
        print(f"FALLO la verificacion: {detalle}")
        return 1

    print(f"Copia   : {archivo.name}  ({archivo.stat().st_size / 1024:.0f} KB)")
    print(f"          {detalle}")

    borradas = podar(destino, argumentos.conservar)
    if borradas:
        print(f"Podadas : {len(borradas)} copias antiguas")
    quedan = len(sorted(destino.glob("basedatos-*.db")))
    print(f"Guardadas: {quedan} copias en total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
