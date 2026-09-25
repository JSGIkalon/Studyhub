"""Piezas comunes a todos los repositorios."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime


class Repositorio:
    """Base minima: guarda la conexion. Sin magia, sin metaclases."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._cx = conexion


@contextmanager
def transaccion(conexion: sqlite3.Connection) -> Iterator[None]:
    """Agrupa varias sentencias en una unidad atomica.

    La conexion se abre en autocommit (``isolation_level=None``), asi que
    ``with conexion:`` no agrupa nada. Un SAVEPOINT si: abre transaccion si no
    la hay y se anida si ya la hay, de modo que un servicio puede envolver
    varias llamadas a repositorios que a su vez usan ``transaccion``.
    """
    conexion.execute("SAVEPOINT mk")
    try:
        yield
    except BaseException:
        conexion.execute("ROLLBACK TO mk")
        conexion.execute("RELEASE mk")
        raise
    conexion.execute("RELEASE mk")


def ahora_iso() -> str:
    """Marca de tiempo ISO-8601 con desfase local."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def a_fecha(valor: str | None) -> date | None:
    """Convierte ``'YYYY-MM-DD'`` en ``date``, tolerando ``None``."""
    return date.fromisoformat(valor) if valor else None


def a_fecha_hora(valor: str | None) -> datetime | None:
    """Convierte una marca ISO-8601 en ``datetime``, tolerando ``None``."""
    return datetime.fromisoformat(valor) if valor else None
