"""Piezas comunes a todos los repositorios."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime


class Repositorio:
    """Base minima: guarda la conexion. Sin magia, sin metaclases."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._cx = conexion


def ahora_iso() -> str:
    """Marca de tiempo ISO-8601 con desfase local."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def hoy_iso() -> str:
    """Fecha local en formato ``YYYY-MM-DD``."""
    return date.today().isoformat()


def a_fecha(valor: str | None) -> date | None:
    """Convierte ``'YYYY-MM-DD'`` en ``date``, tolerando ``None``."""
    return date.fromisoformat(valor) if valor else None


def a_fecha_hora(valor: str | None) -> datetime | None:
    """Convierte una marca ISO-8601 en ``datetime``, tolerando ``None``."""
    return datetime.fromisoformat(valor) if valor else None
