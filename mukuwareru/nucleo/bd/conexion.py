"""Apertura y configuracion de la conexion SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from mukuwareru.nucleo.bd.migrador import migrar


def abrir(ruta: Path | str) -> sqlite3.Connection:
    """Abre la base de datos, la configura y la deja migrada al dia.

    Acepta ``':memory:'`` para los tests.
    """
    en_memoria = str(ruta) == ":memory:"
    if not en_memoria:
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)

    conexion = sqlite3.connect(str(ruta), isolation_level=None)
    conexion.row_factory = sqlite3.Row

    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA synchronous = NORMAL")
    if not en_memoria:
        # WAL no aporta nada en memoria y falla en algunas plataformas.
        conexion.execute("PRAGMA journal_mode = WAL")

    migrar(conexion, None if en_memoria else Path(ruta))
    return conexion
