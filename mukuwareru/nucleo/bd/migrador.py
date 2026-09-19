"""Aplicacion de migraciones de esquema.

Cada archivo ``NNN_descripcion.sql`` de ``migraciones/`` se aplica en orden
numerico, dentro de una transaccion, cuando ``NNN`` supera la version
registrada en ``esquema_version``. Esto es lo que permite reemplazar el
ejecutable sin perder los datos del usuario.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from mukuwareru.utilidades.registro import obtener

_log = obtener(__name__)
_PATRON = re.compile(r"^(\d{3})_.+\.sql$")


@dataclass(frozen=True, slots=True)
class Migracion:
    """Una migracion pendiente o aplicada."""

    version: int
    nombre: str
    sql: str


def migraciones_disponibles() -> list[Migracion]:
    """Lee del paquete todas las migraciones, ordenadas por version."""
    encontradas: list[Migracion] = []
    for recurso in resources.files("mukuwareru.nucleo.bd.migraciones").iterdir():
        coincidencia = _PATRON.match(recurso.name)
        if coincidencia is None:
            continue
        encontradas.append(
            Migracion(
                version=int(coincidencia.group(1)),
                nombre=recurso.name,
                sql=recurso.read_text(encoding="utf-8"),
            )
        )
    return sorted(encontradas, key=lambda m: m.version)


def version_actual(conexion: sqlite3.Connection) -> int:
    """Version de esquema de la base de datos. Cero si esta vacia."""
    conexion.execute("CREATE TABLE IF NOT EXISTS esquema_version (version INTEGER NOT NULL)")
    fila = conexion.execute("SELECT MAX(version) FROM esquema_version").fetchone()
    return int(fila[0]) if fila and fila[0] is not None else 0


def migrar(conexion: sqlite3.Connection, ruta_bd: Path | None = None) -> int:
    """Aplica las migraciones pendientes y devuelve la version resultante.

    Antes de la primera migracion sobre una base de datos existente se guarda
    una copia de seguridad junto al archivo original.
    """
    version = version_actual(conexion)
    pendientes = [m for m in migraciones_disponibles() if m.version > version]
    if not pendientes:
        return version

    if ruta_bd is not None and version > 0 and ruta_bd.exists():
        respaldo = ruta_bd.with_suffix(f".v{version}.respaldo.db")
        shutil.copy2(ruta_bd, respaldo)
        _log.info("Copia de seguridad creada en %s", respaldo.name)

    for migracion in pendientes:
        _log.info("Aplicando migracion %s", migracion.nombre)
        # Las claves foraneas se desactivan durante el DDL y se reactivan al
        # terminar: evita que un ALTER intermedio dispare comprobaciones.
        conexion.execute("PRAGMA foreign_keys = OFF")
        try:
            with conexion:
                conexion.executescript(migracion.sql)
                conexion.execute(
                    "INSERT INTO esquema_version (version) VALUES (?)", (migracion.version,)
                )
        finally:
            conexion.execute("PRAGMA foreign_keys = ON")
        version = migracion.version

    _log.info("Esquema en version %d", version)
    return version
