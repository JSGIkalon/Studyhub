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

        hoy_seg, semana_seg, total_seg = self._sesiones.segundos_hoy_semana_total(
            proyecto_id, dia.isoformat(), lunes.isoformat()
        )
        return ResumenEstudio(
            segundos_hoy=hoy_seg,
            segundos_semana=semana_seg,
            segundos_total=total_seg,
            pomodoros_hoy=self._sesiones.contar_pomodoros(proyecto_id, fecha=dia.isoformat()),
            racha=calcular_racha(self._sesiones.dias_con_trabajo(proyecto_id), dia),
        )

    def resumen_varios(
        self, proyecto_ids: list[int], hoy: date | None = None
    ) -> ResumenEstudio:
        """Cifras consolidadas de varios proyectos.

        Las horas y los pomodoros se suman; la racha es de dias seguidos con
        estudio en **cualquiera** de ellos, no la suma de las rachas.
        """
        dia = hoy or date.today()
        parciales = [self.resumen(pid, dia) for pid in proyecto_ids]
        dias = sorted(
            {d for pid in proyecto_ids for d in self._sesiones.dias_con_trabajo(pid)}
        )
        return ResumenEstudio(
            segundos_hoy=sum(p.segundos_hoy for p in parciales),
            segundos_semana=sum(p.segundos_semana for p in parciales),
            segundos_total=sum(p.segundos_total for p in parciales),
            pomodoros_hoy=sum(p.pomodoros_hoy for p in parciales),
            racha=calcular_racha(dias, dia),
        )

    def segundos_por_dia_varios(
        self, proyecto_ids: list[int], desde: str, hasta: str
    ) -> dict[str, int]:
        """``segundos_por_dia`` sumado sobre varios proyectos."""
        total: dict[str, int] = {}
        for pid in proyecto_ids:
            for fecha, segundos in self._sesiones.segundos_por_dia(pid, desde, hasta).items():
                total[fecha] = total.get(fecha, 0) + segundos
        return total

    def segundos_por_periodo_varios(
        self, proyecto_ids: list[int], desde: str, hasta: str, formato: str
    ) -> dict[str, int]:
        """``segundos_por_periodo`` sumado sobre varios proyectos."""
        total: dict[str, int] = {}
        for pid in proyecto_ids:
            parcial = self._sesiones.segundos_por_periodo(pid, desde, hasta, formato)
            for clave, segundos in parcial.items():
                total[clave] = total.get(clave, 0) + segundos
        return total

    def pomodoros_varios(self, proyecto_ids: list[int]) -> int:
        """Pomodoros completados, sumados sobre varios proyectos."""
        return sum(self._sesiones.contar_pomodoros(pid) for pid in proyecto_ids)

    def por_dia(
        self, proyecto_id: int, dias: int = 30, hoy: date | None = None
    ) -> list[tuple[date, int]]:
        """Segundos de trabajo de cada uno de los ultimos ``dias``, sin huecos.

        Los dias sin estudio aparecen con cero: un grafico con huecos miente.
        """
        return self.por_dia_varios([proyecto_id], dias, hoy)

    def por_dia_varios(
        self, proyecto_ids: list[int], dias: int = 30, hoy: date | None = None
    ) -> list[tuple[date, int]]:
        """``por_dia`` sumado sobre varios proyectos."""
        fin = hoy or date.today()
        inicio = fin - timedelta(days=dias - 1)
        registrados = self.segundos_por_dia_varios(
            proyecto_ids, inicio.isoformat(), fin.isoformat()
        )
        return [
            (dia, registrados.get(dia.isoformat(), 0))
            for dia in (inicio + timedelta(days=n) for n in range(dias))
        ]
