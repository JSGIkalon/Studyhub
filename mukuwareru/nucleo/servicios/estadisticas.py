"""Estadisticas de tiempo de estudio.

Todo se calcula al vuelo con SQL sobre ``sesion``. No hay tablas de agregados,
asi que nada puede quedar desincronizado.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from mukuwareru.nucleo.repositorios import RepositorioSesiones


@dataclass(frozen=True, slots=True)
class ResumenEstudio:
    """Las cifras que necesita el Panel."""

    segundos_hoy: int
    segundos_semana: int
    segundos_total: int
    pomodoros_hoy: int
    racha: int


def calcular_racha(dias: list[str], hoy: date) -> int:
    """Dias consecutivos de estudio que terminan hoy o ayer.

    Se acepta que el ultimo dia sea ayer para que la racha no se rompa por el
    simple hecho de que aun no se ha estudiado esta manana.
    """
    if not dias:
        return 0

    fechas = {date.fromisoformat(d) for d in dias}
    if hoy in fechas:
        cursor = hoy
    elif (ayer := hoy - timedelta(days=1)) in fechas:
        cursor = ayer
    else:
        return 0

    racha = 0
    while cursor in fechas:
        racha += 1
        cursor -= timedelta(days=1)
    return racha


class ServicioEstadisticas:
    """Compone las agregaciones del repositorio en cifras presentables."""

    def __init__(self, conexion: sqlite3.Connection) -> None:
        self._sesiones = RepositorioSesiones(conexion)

    def resumen(self, proyecto_id: int, hoy: date | None = None) -> ResumenEstudio:
        """Cifras del Panel para el proyecto indicado."""
        dia = hoy or date.today()
        lunes = dia - timedelta(days=dia.weekday())

        return ResumenEstudio(
            segundos_hoy=self._sesiones.segundos_trabajo(
                proyecto_id, desde=dia.isoformat(), hasta=dia.isoformat()
            ),
            segundos_semana=self._sesiones.segundos_trabajo(
                proyecto_id, desde=lunes.isoformat(), hasta=dia.isoformat()
            ),
            segundos_total=self._sesiones.segundos_trabajo(proyecto_id),
            pomodoros_hoy=self._sesiones.contar_pomodoros(proyecto_id, fecha=dia.isoformat()),
            racha=calcular_racha(self._sesiones.dias_con_trabajo(proyecto_id), dia),
        )

    def por_dia(
        self, proyecto_id: int, dias: int = 30, hoy: date | None = None
    ) -> list[tuple[date, int]]:
        """Segundos de trabajo de cada uno de los ultimos ``dias``, sin huecos.

        Los dias sin estudio aparecen con cero: un grafico con huecos miente.
        """
        fin = hoy or date.today()
        inicio = fin - timedelta(days=dias - 1)
        registrados = self._sesiones.segundos_por_dia(
            proyecto_id, inicio.isoformat(), fin.isoformat()
        )
        return [
            (dia, registrados.get(dia.isoformat(), 0))
            for dia in (inicio + timedelta(days=n) for n in range(dias))
        ]
