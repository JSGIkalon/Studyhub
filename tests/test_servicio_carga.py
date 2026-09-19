"""Carga declarada: horas estimadas, dedicadas, restantes y prioridad.

Los numeros son redondos a proposito para poder comprobarlos a mano.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

import pytest

from mukuwareru.nucleo.modelos import OrigenSesion, Prioridad, TipoSesion
from mukuwareru.nucleo.repositorios import (
    RepositorioMaterias,
    RepositorioModulos,
    RepositorioProyectos,
    RepositorioSesiones,
)
from mukuwareru.nucleo.servicios import ServicioCarga, ServicioPlan

DIA = date(2026, 9, 15)


@pytest.fixture
def proyecto_id(conn: sqlite3.Connection) -> int:
    """Proyecto con dos materias, la primera con cuatro modulos."""
    proyecto = RepositorioProyectos(conn).crear("MSc")
    materias = RepositorioMaterias(conn)
    probabilidad = materias.crear(proyecto.id, "Probability", orden=0)
    materias.crear(proyecto.id, "Linear Algebra", orden=1)

    modulos = RepositorioModulos(conn)
    for i in range(4):
        modulos.crear(probabilidad.id, f"LM {i}", orden=i)
    return proyecto.id


@pytest.fixture
def servicio(conn: sqlite3.Connection) -> ServicioCarga:
    return ServicioCarga(conn)


def probabilidad(conn: sqlite3.Connection, proyecto_id: int) -> int:
    return RepositorioMaterias(conn).listar(proyecto_id)[0].id


def estudiar(conn: sqlite3.Connection, proyecto_id: int, materia_id: int, horas: float) -> None:
    """Registra una sesion de trabajo atribuida a una materia."""
    RepositorioSesiones(conn).crear(
        proyecto_id,
        tipo=TipoSesion.TRABAJO,
        origen=OrigenSesion.MANUAL,
        inicio=datetime(2026, 9, 1, 10, 0),
        duracion_seg=int(horas * 3600),
        materias=[materia_id],
    )


# --- Sin declarar nada -------------------------------------------------------


def test_sin_horas_no_hay_estimacion(servicio: ServicioCarga, proyecto_id: int) -> None:
    """Un proyecto que no declara horas se comporta como antes de la v1.1."""
    cargas = servicio.resumen(proyecto_id)
    assert len(cargas) == 2
    assert all(not c.estimada for c in cargas)
    assert all(c.horas_restantes == 0 for c in cargas)
    assert servicio.horas_restantes(proyecto_id) is None


def test_prioridad_por_defecto_es_media(servicio: ServicioCarga, proyecto_id: int) -> None:
    assert all(c.prioridad is Prioridad.MEDIA for c in servicio.resumen(proyecto_id))


# --- Horas de la materia -----------------------------------------------------


def test_restantes_son_estimadas_menos_dedicadas(
    conn: sqlite3.Connection, servicio: ServicioCarga, proyecto_id: int
) -> None:
    """40 estimadas, 15 dedicadas -> 25 restantes. El ejemplo del enunciado."""
    materia_id = probabilidad(conn, proyecto_id)
    servicio.fijar(
        materia_id,
        horas_estimadas=40,
        horas_restantes_manual=None,
        prioridad=Prioridad.ALTA,
        fecha_limite=date(2026, 10, 15),
    )
    estudiar(conn, proyecto_id, materia_id, 15)

    carga = servicio.resumen(proyecto_id)[0]
    assert carga.horas_estimadas == 40
    assert carga.horas_dedicadas == 15
    assert carga.horas_restantes == 25
    assert not carga.sobrescrita
    assert carga.prioridad is Prioridad.ALTA
    assert carga.dias_para_limite(DIA) == 30


def test_restantes_nunca_negativas(
    conn: sqlite3.Connection, servicio: ServicioCarga, proyecto_id: int
) -> None:
    """Pasarse de la estimacion significa que se quedo corta, no que sobren horas."""
    materia_id = probabilidad(conn, proyecto_id)
    servicio.fijar(
        materia_id,
        horas_estimadas=10,
        horas_restantes_manual=None,
        prioridad=Prioridad.MEDIA,
        fecha_limite=None,
    )
    estudiar(conn, proyecto_id, materia_id, 30)
    assert servicio.resumen(proyecto_id)[0].horas_restantes == 0


def test_sobrescritura_manda_sobre_el_calculo(
    conn: sqlite3.Connection, servicio: ServicioCarga, proyecto_id: int
) -> None:
    materia_id = probabilidad(conn, proyecto_id)
    servicio.fijar(
        materia_id,
        horas_estimadas=40,
        horas_restantes_manual=8,
        prioridad=Prioridad.MEDIA,
        fecha_limite=None,
    )
    estudiar(conn, proyecto_id, materia_id, 15)

    carga = servicio.resumen(proyecto_id)[0]
    assert carga.horas_restantes == 8
    assert carga.sobrescrita
    # La estimacion y el historial siguen intactos: corregir el resultado no
    # puede obligar a falsear los datos de partida.
    assert carga.horas_estimadas == 40
    assert carga.horas_dedicadas == 15


def test_horas_negativas_se_guardan_como_sin_dato(
    conn: sqlite3.Connection, servicio: ServicioCarga, proyecto_id: int
) -> None:
    materia_id = probabilidad(conn, proyecto_id)
    servicio.fijar(
        materia_id,
        horas_estimadas=-5,
        horas_restantes_manual=-1,
        prioridad=Prioridad.MEDIA,
        fecha_limite=None,
    )
    carga = servicio.resumen(proyecto_id)[0]
    assert carga.horas_estimadas is None
    assert carga.horas_restantes_manual is None


# --- Horas desglosadas por modulo --------------------------------------------


def test_el_desglose_por_modulos_manda(
    conn: sqlite3.Connection, servicio: ServicioCarga, proyecto_id: int
) -> None:
    """Cuatro modulos de 3 h, uno hecho -> 12 estimadas y 9 restantes."""
    materia_id = probabilidad(conn, proyecto_id)
    servicio.fijar(
        materia_id,
        horas_estimadas=100,     # se ignora: el desglose es mas fino
        horas_restantes_manual=None,
        prioridad=Prioridad.MEDIA,
        fecha_limite=None,
    )
    modulos = RepositorioModulos(conn)
    listados = modulos.listar(materia_id)
    for modulo in listados:
        servicio.fijar_horas_modulo(modulo.id, 3)
    modulos.marcar(listados[0].id, True)

    carga = servicio.resumen(proyecto_id)[0]
    assert carga.desglosada
    assert carga.horas_estimadas == 12
    assert carga.horas_restantes == 9


def test_total_del_proyecto_suma_las_materias_estimadas(
    conn: sqlite3.Connection, servicio: ServicioCarga, proyecto_id: int
) -> None:
    materias = RepositorioMaterias(conn).listar(proyecto_id)
    servicio.fijar(
        materias[0].id,
        horas_estimadas=40,
        horas_restantes_manual=None,
        prioridad=Prioridad.MEDIA,
        fecha_limite=None,
    )
    servicio.fijar(
        materias[1].id,
        horas_estimadas=10,
        horas_restantes_manual=None,
        prioridad=Prioridad.MEDIA,
        fecha_limite=None,
    )
    assert servicio.horas_restantes(proyecto_id) == 50


# --- Urgencia ----------------------------------------------------------------


def test_urgentes_ordena_por_fecha_y_luego_por_prioridad(
    conn: sqlite3.Connection, servicio: ServicioCarga, proyecto_id: int
) -> None:
    materias = RepositorioMaterias(conn).listar(proyecto_id)
    servicio.fijar(
        materias[0].id,
        horas_estimadas=10,
        horas_restantes_manual=None,
        prioridad=Prioridad.BAJA,
        fecha_limite=date(2026, 9, 20),      # antes
    )
    servicio.fijar(
        materias[1].id,
        horas_estimadas=10,
        horas_restantes_manual=None,
        prioridad=Prioridad.CRITICA,
        fecha_limite=date(2026, 12, 1),      # despues, aunque sea critica
    )
    urgentes = servicio.urgentes(proyecto_id, DIA)
    assert [c.nombre for c in urgentes] == ["Probability", "Linear Algebra"]


# --- Integracion con el planificador existente -------------------------------


def test_el_diagnostico_usa_las_horas_declaradas(
    conn: sqlite3.Connection, servicio: ServicioCarga, proyecto_id: int
) -> None:
    """Con horas declaradas, el ritmo deja de ser una extrapolacion."""
    from mukuwareru.nucleo.repositorios import RepositorioHitos

    materia_id = probabilidad(conn, proyecto_id)
    servicio.fijar(
        materia_id,
        horas_estimadas=28,
        horas_restantes_manual=None,
        prioridad=Prioridad.MEDIA,
        fecha_limite=None,
    )
    RepositorioHitos(conn).crear(proyecto_id, "Examen", date(2026, 10, 13))

    diagnostico = ServicioPlan(conn).diagnostico(proyecto_id, DIA)
    assert diagnostico.declarado
    assert diagnostico.horas_restantes_declaradas == 28
    # 28 h en 28 dias son cuatro semanas justas: 7 h por semana.
    assert diagnostico.horas_por_semana_necesarias == pytest.approx(7.0)


def test_sin_horas_declaradas_el_diagnostico_no_cambia(
    conn: sqlite3.Connection, proyecto_id: int
) -> None:
    """El comportamiento anterior a la v1.1 se conserva intacto."""
    from mukuwareru.nucleo.repositorios import RepositorioHitos

    RepositorioHitos(conn).crear(proyecto_id, "Examen", date(2026, 10, 13))
    diagnostico = ServicioPlan(conn).diagnostico(proyecto_id, DIA)
    assert not diagnostico.declarado
    assert diagnostico.horas_restantes_declaradas is None
    # Cuatro modulos pendientes, una hora cada uno por defecto, cuatro semanas.
    assert diagnostico.horas_por_semana_necesarias == pytest.approx(1.0)
