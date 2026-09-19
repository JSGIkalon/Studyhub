"""Servicio de estadisticas y calculo de racha."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

import pytest

from mukuwareru.nucleo.modelos import OrigenSesion, TipoSesion
from mukuwareru.nucleo.repositorios import (
    RepositorioMaterias,
    RepositorioProyectos,
    RepositorioSesiones,
)
from mukuwareru.nucleo.servicios import ServicioEstadisticas, calcular_racha

HOY = date(2026, 8, 16)  # domingo


def _dias(*desplazamientos: int) -> list[str]:
    return [(HOY - timedelta(days=d)).isoformat() for d in desplazamientos]


# --- calcular_racha: funcion pura, sin base de datos -----------------------


def test_racha_vacia() -> None:
    assert calcular_racha([], HOY) == 0


def test_racha_de_hoy_hacia_atras() -> None:
    assert calcular_racha(_dias(0, 1, 2), HOY) == 3


def test_la_racha_sobrevive_a_una_manana_sin_estudiar() -> None:
    # Solo hay registro hasta ayer: la racha no debe romperse aun.
    assert calcular_racha(_dias(1, 2, 3), HOY) == 3


def test_la_racha_se_rompe_con_dos_dias_sin_estudiar() -> None:
    assert calcular_racha(_dias(2, 3, 4), HOY) == 0


def test_la_racha_se_corta_en_el_hueco() -> None:
    assert calcular_racha(_dias(0, 1, 3, 4), HOY) == 2


def test_la_racha_tolera_dias_desordenados_y_repetidos() -> None:
    dias = _dias(2, 0, 1, 1)
    assert calcular_racha(dias, HOY) == 3


# --- ServicioEstadisticas: integrado con SQLite ----------------------------


@pytest.fixture
def proyecto_con_sesiones(conn: sqlite3.Connection) -> int:
    """Hoy 1 h en dos pomodoros, ayer 2 h, y hace diez dias 3 h."""
    proyecto = RepositorioProyectos(conn).crear("CFA")
    sesiones = RepositorioSesiones(conn)

    def registrar(dias_atras: int, segundos: int) -> None:
        momento = datetime.combine(HOY - timedelta(days=dias_atras), datetime.min.time())
        sesiones.crear(
            proyecto.id,
            tipo=TipoSesion.TRABAJO,
            origen=OrigenSesion.POMODORO,
            inicio=momento,
            duracion_seg=segundos,
        )

    registrar(0, 1800)
    registrar(0, 1800)
    registrar(1, 7200)
    registrar(10, 10800)
    return proyecto.id


def test_resumen(conn: sqlite3.Connection, proyecto_con_sesiones: int) -> None:
    resumen = ServicioEstadisticas(conn).resumen(proyecto_con_sesiones, HOY)
    assert resumen.segundos_hoy == 3600
    assert resumen.segundos_total == 3600 + 7200 + 10800
    assert resumen.pomodoros_hoy == 2
    assert resumen.racha == 2


def test_la_semana_empieza_en_lunes(
    conn: sqlite3.Connection, proyecto_con_sesiones: int
) -> None:
    # HOY es domingo, asi que la semana abarca de lunes 10 a domingo 16 e
    # incluye hoy y ayer, pero no la sesion de hace diez dias.
    resumen = ServicioEstadisticas(conn).resumen(proyecto_con_sesiones, HOY)
    assert resumen.segundos_semana == 3600 + 7200


def test_los_descansos_no_cuentan_como_tiempo_de_estudio(
    conn: sqlite3.Connection, proyecto_con_sesiones: int
) -> None:
    RepositorioSesiones(conn).crear(
        proyecto_con_sesiones,
        tipo=TipoSesion.DESCANSO_CORTO,
        origen=OrigenSesion.POMODORO,
        inicio=datetime.combine(HOY, datetime.min.time()),
        duracion_seg=300,
    )
    resumen = ServicioEstadisticas(conn).resumen(proyecto_con_sesiones, HOY)
    assert resumen.segundos_hoy == 3600
    assert resumen.pomodoros_hoy == 2


def test_por_dia_rellena_los_huecos_con_cero(
    conn: sqlite3.Connection, proyecto_con_sesiones: int
) -> None:
    serie = ServicioEstadisticas(conn).por_dia(proyecto_con_sesiones, dias=7, hoy=HOY)
    assert len(serie) == 7
    assert serie[-1] == (HOY, 3600)
    assert serie[-2] == (HOY - timedelta(days=1), 7200)
    assert serie[0] == (HOY - timedelta(days=6), 0)


def test_proyecto_sin_sesiones(conn: sqlite3.Connection) -> None:
    proyecto = RepositorioProyectos(conn).crear("Vacio")
    resumen = ServicioEstadisticas(conn).resumen(proyecto.id, HOY)
    assert (resumen.segundos_total, resumen.racha, resumen.pomodoros_hoy) == (0, 0, 0)


# --- Reparto del tiempo por materia ---------------------------------------


def test_una_sesion_con_varias_materias_reparte_su_tiempo(
    conn: sqlite3.Connection,
) -> None:
    """Las partes tienen que sumar el todo: repartir, no duplicar."""
    proyecto = RepositorioProyectos(conn).crear("CFA")
    materias = RepositorioMaterias(conn)
    fsa = materias.crear(proyecto.id, "FSA")
    equity = materias.crear(proyecto.id, "Equity")
    sesiones = RepositorioSesiones(conn)
    momento = datetime.combine(HOY, datetime.min.time())

    sesiones.crear(
        proyecto.id,
        tipo=TipoSesion.TRABAJO,
        origen=OrigenSesion.POMODORO,
        inicio=momento,
        duracion_seg=3600,
        materias=[fsa.id],
    )
    sesiones.crear(
        proyecto.id,
        tipo=TipoSesion.TRABAJO,
        origen=OrigenSesion.POMODORO,
        inicio=momento,
        duracion_seg=3600,
        materias=[fsa.id, equity.id],
    )

    por_materia = sesiones.segundos_por_materia(proyecto.id)
    assert por_materia == {fsa.id: 5400, equity.id: 1800}
    assert sum(por_materia.values()) == sesiones.segundos_trabajo(proyecto.id)


def test_el_tiempo_sin_clasificar_completa_el_total(conn: sqlite3.Connection) -> None:
    proyecto = RepositorioProyectos(conn).crear("CFA")
    fsa = RepositorioMaterias(conn).crear(proyecto.id, "FSA")
    sesiones = RepositorioSesiones(conn)
    momento = datetime.combine(HOY, datetime.min.time())

    for materias_sesion in ([fsa.id], None):
        sesiones.crear(
            proyecto.id,
            tipo=TipoSesion.TRABAJO,
            origen=OrigenSesion.POMODORO,
            inicio=momento,
            duracion_seg=1800,
            materias=materias_sesion,
        )

    total = sum(sesiones.segundos_por_materia(proyecto.id).values())
    total += sesiones.segundos_sin_clasificar(proyecto.id)
    assert total == sesiones.segundos_trabajo(proyecto.id) == 3600
