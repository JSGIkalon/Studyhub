"""Orden y color de las materias.

Las materias se quedaron sin reordenar cuando los modulos si lo tenian, y
`materia.color` existia en el esquema desde el principio sin que nadie lo
escribiera. Estas pruebas cubren las dos cosas, calcando
`test_repositorio_modulos.py`.
"""

from __future__ import annotations

import sqlite3

import pytest

from mukuwareru.nucleo.repositorios import RepositorioMaterias, RepositorioProyectos

NOMBRES = ("Ethics", "Quantitative Methods", "Economics", "Derivatives")


@pytest.fixture
def proyecto_id(conn: sqlite3.Connection) -> int:
    """Proyecto con cuatro materias en un orden deliberadamente no alfabetico."""
    proyecto = RepositorioProyectos(conn).crear("CFA")
    materias = RepositorioMaterias(conn)
    for posicion, nombre in enumerate(NOMBRES):
        materias.crear(proyecto.id, nombre, orden=posicion)
    return proyecto.id


@pytest.fixture
def repo(conn: sqlite3.Connection) -> RepositorioMaterias:
    return RepositorioMaterias(conn)


def orden_de(repo: RepositorioMaterias, proyecto_id: int) -> list[str]:
    return [m.nombre for m in repo.listar(proyecto_id)]


# --- Mover -----------------------------------------------------------------


def test_subir_intercambia_con_la_anterior(
    repo: RepositorioMaterias, proyecto_id: int
) -> None:
    tercera = repo.listar(proyecto_id)[2]
    assert repo.mover(tercera.id, -1)
    assert orden_de(repo, proyecto_id) == [
        "Ethics", "Economics", "Quantitative Methods", "Derivatives"
    ]


def test_bajar_intercambia_con_la_siguiente(
    repo: RepositorioMaterias, proyecto_id: int
) -> None:
    primera = repo.listar(proyecto_id)[0]
    assert repo.mover(primera.id, 1)
    assert orden_de(repo, proyecto_id) == [
        "Quantitative Methods", "Ethics", "Economics", "Derivatives"
    ]


def test_no_se_puede_subir_la_primera(
    repo: RepositorioMaterias, proyecto_id: int
) -> None:
    primera = repo.listar(proyecto_id)[0]
    assert not repo.mover(primera.id, -1)
    assert orden_de(repo, proyecto_id) == list(NOMBRES)


def test_no_se_puede_bajar_la_ultima(
    repo: RepositorioMaterias, proyecto_id: int
) -> None:
    ultima = repo.listar(proyecto_id)[-1]
    assert not repo.mover(ultima.id, 1)
    assert orden_de(repo, proyecto_id) == list(NOMBRES)


def test_mover_una_materia_que_ya_no_existe(repo: RepositorioMaterias) -> None:
    assert not repo.mover(9999, 1)


def test_mover_funciona_con_ordenes_empatados(
    conn: sqlite3.Connection, repo: RepositorioMaterias
) -> None:
    """El importador crea las materias con `orden` empatado si se le deja."""
    proyecto = RepositorioProyectos(conn).crear("MSc")
    for nombre in ("Alfa", "Beta", "Gamma"):
        repo.crear(proyecto.id, nombre, orden=0)

    assert orden_de(repo, proyecto.id) == ["Alfa", "Beta", "Gamma"]
    gamma = repo.listar(proyecto.id)[2]
    assert repo.mover(gamma.id, -1)
    assert orden_de(repo, proyecto.id) == ["Alfa", "Gamma", "Beta"]


# --- Reordenar -------------------------------------------------------------


def test_reordenar_fija_las_posiciones(
    repo: RepositorioMaterias, proyecto_id: int
) -> None:
    ids = [m.id for m in repo.listar(proyecto_id)]
    repo.reordenar(proyecto_id, [ids[3], ids[1], ids[0], ids[2]])
    assert orden_de(repo, proyecto_id) == [
        "Derivatives", "Quantitative Methods", "Ethics", "Economics"
    ]


def test_reordenar_ignora_materias_de_otro_proyecto(
    conn: sqlite3.Connection, repo: RepositorioMaterias, proyecto_id: int
) -> None:
    ajeno = RepositorioProyectos(conn).crear("MSc")
    intrusa = repo.crear(ajeno.id, "Econometria", orden=7)

    repo.reordenar(proyecto_id, [intrusa.id])
    sin_tocar = repo.obtener(intrusa.id)
    assert sin_tocar is not None and sin_tocar.orden == 7


# --- Color -----------------------------------------------------------------


def test_una_materia_nace_sin_color_propio(
    repo: RepositorioMaterias, proyecto_id: int
) -> None:
    assert all(m.color is None for m in repo.listar(proyecto_id))


def test_fijar_color_se_guarda(repo: RepositorioMaterias, proyecto_id: int) -> None:
    ethics = repo.listar(proyecto_id)[0]
    repo.fijar_color(ethics.id, "#8E4EC6")

    guardada = repo.obtener(ethics.id)
    assert guardada is not None and guardada.color == "#8E4EC6"


def test_fijar_color_a_ninguno_lo_limpia(
    repo: RepositorioMaterias, proyecto_id: int
) -> None:
    ethics = repo.listar(proyecto_id)[0]
    repo.fijar_color(ethics.id, "#8E4EC6")
    repo.fijar_color(ethics.id, None)

    limpia = repo.obtener(ethics.id)
    assert limpia is not None and limpia.color is None


def test_el_color_llega_al_conteo_por_materia(
    conn: sqlite3.Connection, repo: RepositorioMaterias, proyecto_id: int
) -> None:
    """El Panel pinta desde el conteo, no desde `listar`: tiene que traerlo."""
    from mukuwareru.nucleo.repositorios import RepositorioModulos

    ethics = repo.listar(proyecto_id)[0]
    repo.fijar_color(ethics.id, "#0D9488")

    conteos = RepositorioModulos(conn).conteo_por_materia(proyecto_id)
    colores = {c.nombre: c.color for c in conteos}
    assert colores["Ethics"] == "#0D9488"
    assert colores["Economics"] is None


def test_el_color_llega_al_resumen_de_progreso(
    conn: sqlite3.Connection, repo: RepositorioMaterias, proyecto_id: int
) -> None:
    from mukuwareru.nucleo.servicios import ServicioProgreso

    ethics = repo.listar(proyecto_id)[0]
    repo.fijar_color(ethics.id, "#0D9488")

    resumen = ServicioProgreso(conn).resumen(proyecto_id)
    assert next(m for m in resumen.materias if m.nombre == "Ethics").color == "#0D9488"


def test_conteo_y_listar_ordenan_igual(
    conn: sqlite3.Connection, repo: RepositorioMaterias, proyecto_id: int
) -> None:
    """Invariante del respaldo de color: si divergen, cada vista pinta distinto.

    Sin color propio, Panel y Progreso caen al color de la serie **por
    posicion**, y cada uno recorre una de estas dos consultas.
    """
    from mukuwareru.nucleo.repositorios import RepositorioModulos

    repo.mover(repo.listar(proyecto_id)[3].id, -1)
    conteos = RepositorioModulos(conn).conteo_por_materia(proyecto_id)
    assert [c.nombre for c in conteos] == orden_de(repo, proyecto_id)
