"""Almacenamiento de resultados de examenes y su desglose por asignatura."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from mukuwareru.nucleo.modelos import LineaEvaluacion
from mukuwareru.nucleo.repositorios import (
    RepositorioEvaluaciones,
    RepositorioHitos,
    RepositorioMaterias,
    RepositorioProyectos,
)

DIA = date(2026, 9, 14)


@pytest.fixture
def proyecto_id(conn: sqlite3.Connection) -> int:
    proyecto = RepositorioProyectos(conn).crear("CFA")
    materias = RepositorioMaterias(conn)
    materias.crear(proyecto.id, "Ethics", orden=0, peso=17.1)
    materias.crear(proyecto.id, "Derivatives", orden=1, peso=6.3)
    return proyecto.id


@pytest.fixture
def repo(conn: sqlite3.Connection) -> RepositorioEvaluaciones:
    return RepositorioEvaluaciones(conn)


def materias_de(conn: sqlite3.Connection, proyecto_id: int) -> list[int]:
    return [m.id for m in RepositorioMaterias(conn).listar(proyecto_id)]


# --- Alta y lectura --------------------------------------------------------


def test_crear_devuelve_la_evaluacion_con_id_y_desglose(
    conn: sqlite3.Connection, repo: RepositorioEvaluaciones, proyecto_id: int
) -> None:
    ethics, derivatives = materias_de(conn, proyecto_id)
    creada = repo.crear(
        proyecto_id,
        "Mock 1",
        DIA,
        38,
        50,
        materias=[
            LineaEvaluacion(ethics, 20, 25),
            LineaEvaluacion(derivatives, 18, 25),
        ],
    )

    assert creada.id > 0
    assert creada.porcentaje == 76
    assert len(creada.materias) == 2
    assert creada.peso == 1.0          # el defecto, distinto de `materia.peso`


def test_una_evaluacion_sin_desglose_tiene_materias_vacio(
    repo: RepositorioEvaluaciones, proyecto_id: int
) -> None:
    creada = repo.crear(proyecto_id, "Parcial", DIA, 8.5, 10)
    assert creada.materias == []
    assert creada.porcentaje == 85


def test_listar_va_de_mas_reciente_a_mas_antigua(
    repo: RepositorioEvaluaciones, proyecto_id: int
) -> None:
    repo.crear(proyecto_id, "Viejo", date(2026, 1, 1), 10, 20)
    repo.crear(proyecto_id, "Nuevo", date(2026, 8, 1), 15, 20)

    assert [e.titulo for e in repo.listar(proyecto_id)] == ["Nuevo", "Viejo"]


def test_las_evaluaciones_no_saltan_de_proyecto(
    conn: sqlite3.Connection, repo: RepositorioEvaluaciones, proyecto_id: int
) -> None:
    ajeno = RepositorioProyectos(conn).crear("MSc")
    repo.crear(proyecto_id, "Del CFA", DIA, 10, 20)

    assert repo.listar(ajeno.id) == []
    assert repo.conteo(ajeno.id) == 0


def test_decimales_no_enteros(repo: RepositorioEvaluaciones, proyecto_id: int) -> None:
    """La escala es la del examen: 8,5 sobre 10 se guarda tal cual."""
    creada = repo.crear(proyecto_id, "Parcial", DIA, 8.5, 10)
    leida = repo.obtener(creada.id)
    assert leida is not None
    assert (leida.puntos_obtenidos, leida.puntos_posibles) == (8.5, 10.0)


# --- Desglose --------------------------------------------------------------


def test_desglosar_reemplaza_el_desglose_entero(
    conn: sqlite3.Connection, repo: RepositorioEvaluaciones, proyecto_id: int
) -> None:
    ethics, derivatives = materias_de(conn, proyecto_id)
    creada = repo.crear(
        proyecto_id, "Mock", DIA, 38, 50, materias=[LineaEvaluacion(ethics, 20, 25)]
    )

    repo.desglosar(creada.id, [LineaEvaluacion(derivatives, 18, 25)])
    lineas = repo.desglose_de(creada.id)
    assert [linea.materia_id for linea in lineas] == [derivatives]


def test_desglosar_con_secuencia_vacia_deja_solo_la_nota_global(
    conn: sqlite3.Connection, repo: RepositorioEvaluaciones, proyecto_id: int
) -> None:
    ethics, _ = materias_de(conn, proyecto_id)
    creada = repo.crear(
        proyecto_id, "Mock", DIA, 38, 50, materias=[LineaEvaluacion(ethics, 20, 25)]
    )

    repo.desglosar(creada.id, [])
    leida = repo.obtener(creada.id)
    assert leida is not None and leida.materias == []
    assert leida.porcentaje == 76


def test_actualizar_no_toca_el_desglose(
    conn: sqlite3.Connection, repo: RepositorioEvaluaciones, proyecto_id: int
) -> None:
    ethics, _ = materias_de(conn, proyecto_id)
    creada = repo.crear(
        proyecto_id, "Mock", DIA, 38, 50, materias=[LineaEvaluacion(ethics, 20, 25)]
    )

    creada.titulo = "Mock 1 (corregido)"
    repo.actualizar(creada)

    leida = repo.obtener(creada.id)
    assert leida is not None
    assert leida.titulo == "Mock 1 (corregido)"
    assert len(leida.materias) == 1


def test_eliminar_arrastra_el_desglose(
    conn: sqlite3.Connection, repo: RepositorioEvaluaciones, proyecto_id: int
) -> None:
    ethics, _ = materias_de(conn, proyecto_id)
    creada = repo.crear(
        proyecto_id, "Mock", DIA, 38, 50, materias=[LineaEvaluacion(ethics, 20, 25)]
    )

    repo.eliminar(creada.id)
    assert repo.obtener(creada.id) is None
    restantes = conn.execute("SELECT COUNT(*) FROM evaluacion_materia").fetchone()[0]
    assert restantes == 0


def test_borrar_la_materia_quita_su_linea_y_no_la_evaluacion(
    conn: sqlite3.Connection, repo: RepositorioEvaluaciones, proyecto_id: int
) -> None:
    ethics, derivatives = materias_de(conn, proyecto_id)
    creada = repo.crear(
        proyecto_id,
        "Mock",
        DIA,
        38,
        50,
        materias=[LineaEvaluacion(ethics, 20, 25), LineaEvaluacion(derivatives, 18, 25)],
    )

    RepositorioMaterias(conn).eliminar(ethics)
    leida = repo.obtener(creada.id)
    assert leida is not None
    assert [linea.materia_id for linea in leida.materias] == [derivatives]


# --- Enlace con el calendario ----------------------------------------------


def test_borrar_el_hito_deja_la_evaluacion_con_hito_nulo(
    conn: sqlite3.Connection, repo: RepositorioEvaluaciones, proyecto_id: int
) -> None:
    """SET NULL y no CASCADE: borrar la fecha prevista no borra la nota."""
    hitos = RepositorioHitos(conn)
    hito = hitos.crear(proyecto_id, "Mock 2", DIA)
    creada = repo.crear(proyecto_id, "Mock 2", DIA, 38, 50, hito_id=hito.id)

    hitos.eliminar(hito.id)
    leida = repo.obtener(creada.id)
    assert leida is not None
    assert leida.hito_id is None
    assert leida.porcentaje == 76


def test_por_hito_encuentra_el_resultado(
    conn: sqlite3.Connection, repo: RepositorioEvaluaciones, proyecto_id: int
) -> None:
    hito = RepositorioHitos(conn).crear(proyecto_id, "Mock 2", DIA)
    repo.crear(proyecto_id, "Mock 2", DIA, 38, 50, hito_id=hito.id)

    encontrada = repo.por_hito(hito.id)
    assert encontrada is not None and encontrada.titulo == "Mock 2"


def test_no_caben_dos_evaluaciones_en_el_mismo_hito(
    conn: sqlite3.Connection, repo: RepositorioEvaluaciones, proyecto_id: int
) -> None:
    hito = RepositorioHitos(conn).crear(proyecto_id, "Mock 2", DIA)
    repo.crear(proyecto_id, "Mock 2", DIA, 38, 50, hito_id=hito.id)

    with pytest.raises(sqlite3.IntegrityError):
        repo.crear(proyecto_id, "Otro", DIA, 10, 20, hito_id=hito.id)


def test_varias_evaluaciones_sin_hito_conviven(
    repo: RepositorioEvaluaciones, proyecto_id: int
) -> None:
    """El indice unico es parcial: `hito_id` nulo es el caso corriente."""
    repo.crear(proyecto_id, "Uno", DIA, 10, 20)
    repo.crear(proyecto_id, "Dos", DIA, 12, 20)
    assert repo.conteo(proyecto_id) == 2


# --- Restricciones ---------------------------------------------------------


def test_puntos_posibles_cero_es_rechazado(
    repo: RepositorioEvaluaciones, proyecto_id: int
) -> None:
    """Un examen sobre cero puntos seria una division por cero al pintarlo."""
    with pytest.raises(sqlite3.IntegrityError):
        repo.crear(proyecto_id, "Imposible", DIA, 0, 0)


def test_puntos_obtenidos_negativos_son_rechazados(
    repo: RepositorioEvaluaciones, proyecto_id: int
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        repo.crear(proyecto_id, "Imposible", DIA, -1, 20)


# --- Consulta para el servicio ---------------------------------------------


def test_lineas_por_materia_trae_los_dos_pesos(
    conn: sqlite3.Connection, repo: RepositorioEvaluaciones, proyecto_id: int
) -> None:
    ethics, _ = materias_de(conn, proyecto_id)
    repo.crear(
        proyecto_id,
        "Mock",
        DIA,
        38,
        50,
        peso=3.0,
        materias=[LineaEvaluacion(ethics, 20, 25)],
    )

    lineas = repo.lineas_por_materia(proyecto_id)
    assert len(lineas) == 1
    assert lineas[0].nombre == "Ethics"
    assert lineas[0].peso_materia == 17.1
    assert lineas[0].peso_evaluacion == 3.0
    assert lineas[0].fraccion == 0.8
