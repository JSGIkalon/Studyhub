"""Edicion del temario modulo a modulo.

El curriculo del CFA se renumera cada ano: un modulo cambia de nombre o se parte
en tres. Estas pruebas cubren que corregirlo no cueste perder lo ya completado ni
descolocar el orden.
"""

from __future__ import annotations

import sqlite3

import pytest

from mukuwareru.nucleo.repositorios import (
    RepositorioMaterias,
    RepositorioModulos,
    RepositorioProyectos,
)

NOMBRES = ("Uno", "Dos", "Tres", "Cuatro")


@pytest.fixture
def materia_id(conn: sqlite3.Connection) -> int:
    """Materia con cuatro modulos ordenados, el segundo completado."""
    proyecto = RepositorioProyectos(conn).crear("CFA")
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Equity Investments")
    modulos = RepositorioModulos(conn)
    for posicion, nombre in enumerate(NOMBRES):
        modulos.crear(materia.id, nombre, orden=posicion, completado=nombre == "Dos")
    return materia.id


@pytest.fixture
def repo(conn: sqlite3.Connection) -> RepositorioModulos:
    return RepositorioModulos(conn)


def orden_de(repo: RepositorioModulos, materia_id: int) -> list[str]:
    return [m.nombre for m in repo.listar(materia_id)]


# --- Renombrar -------------------------------------------------------------


def test_renombrar_conserva_el_completado_y_su_fecha(
    repo: RepositorioModulos, materia_id: int
) -> None:
    antes = next(m for m in repo.listar(materia_id) if m.nombre == "Dos")
    repo.renombrar(antes.id, "Company Analysis: Past and Present")

    despues = repo.obtener(antes.id)
    assert despues is not None
    assert despues.nombre == "Company Analysis: Past and Present"
    assert despues.completado
    assert despues.completado_en == antes.completado_en
    assert despues.orden == antes.orden


def test_renombrar_no_altera_el_orden(repo: RepositorioModulos, materia_id: int) -> None:
    segundo = repo.listar(materia_id)[1]
    repo.renombrar(segundo.id, "Zzz ultimo alfabeticamente")
    assert orden_de(repo, materia_id)[1] == "Zzz ultimo alfabeticamente"


# --- Mover -----------------------------------------------------------------


def test_subir_intercambia_con_el_anterior(
    repo: RepositorioModulos, materia_id: int
) -> None:
    tercero = repo.listar(materia_id)[2]
    assert repo.mover(tercero.id, -1)
    assert orden_de(repo, materia_id) == ["Uno", "Tres", "Dos", "Cuatro"]


def test_bajar_intercambia_con_el_siguiente(
    repo: RepositorioModulos, materia_id: int
) -> None:
    primero = repo.listar(materia_id)[0]
    assert repo.mover(primero.id, 1)
    assert orden_de(repo, materia_id) == ["Dos", "Uno", "Tres", "Cuatro"]


def test_no_se_puede_subir_el_primero(repo: RepositorioModulos, materia_id: int) -> None:
    primero = repo.listar(materia_id)[0]
    assert not repo.mover(primero.id, -1)
    assert orden_de(repo, materia_id) == list(NOMBRES)


def test_no_se_puede_bajar_el_ultimo(repo: RepositorioModulos, materia_id: int) -> None:
    ultimo = repo.listar(materia_id)[-1]
    assert not repo.mover(ultimo.id, 1)
    assert orden_de(repo, materia_id) == list(NOMBRES)


def test_mover_un_modulo_que_ya_no_existe(repo: RepositorioModulos) -> None:
    assert not repo.mover(9999, 1)


def test_mover_funciona_con_ordenes_empatados(
    conn: sqlite3.Connection, repo: RepositorioModulos
) -> None:
    """El Excel importa todo con `orden = 0`; intercambiar valores no bastaria."""
    proyecto = RepositorioProyectos(conn).crear("Otro")
    materia = RepositorioMaterias(conn).crear(proyecto.id, "FSA")
    for nombre in ("Alfa", "Beta", "Gamma"):
        repo.crear(materia.id, nombre, orden=0)

    # Con `orden` empatado, `listar` desempata por nombre.
    assert orden_de(repo, materia.id) == ["Alfa", "Beta", "Gamma"]
    gamma = repo.listar(materia.id)[2]
    assert repo.mover(gamma.id, -1)
    assert orden_de(repo, materia.id) == ["Alfa", "Gamma", "Beta"]


# --- Reordenar -------------------------------------------------------------


def test_reordenar_fija_las_posiciones(
    repo: RepositorioModulos, materia_id: int
) -> None:
    ids = [m.id for m in repo.listar(materia_id)]
    repo.reordenar(materia_id, [ids[3], ids[1], ids[0], ids[2]])
    assert orden_de(repo, materia_id) == ["Cuatro", "Dos", "Uno", "Tres"]


def test_reordenar_ignora_modulos_de_otra_materia(
    conn: sqlite3.Connection, repo: RepositorioModulos, materia_id: int
) -> None:
    proyecto = RepositorioProyectos(conn).crear("Otro")
    ajena = RepositorioMaterias(conn).crear(proyecto.id, "Ajena")
    intruso = repo.crear(ajena.id, "Intruso", orden=7)

    repo.reordenar(materia_id, [intruso.id])
    assert repo.obtener(intruso.id).orden == 7  # type: ignore[union-attr]


# --- Insertar detras -------------------------------------------------------


def test_insertar_tras_coloca_en_su_sitio_y_corre_los_demas(
    repo: RepositorioModulos, materia_id: int
) -> None:
    primero = repo.listar(materia_id)[0]
    nuevo = repo.insertar_tras(primero.id, "Uno y medio")

    assert nuevo is not None
    assert nuevo.orden == 1
    assert orden_de(repo, materia_id) == ["Uno", "Uno y medio", "Dos", "Tres", "Cuatro"]


def test_insertar_tras_el_ultimo_lo_pone_al_final(
    repo: RepositorioModulos, materia_id: int
) -> None:
    ultimo = repo.listar(materia_id)[-1]
    repo.insertar_tras(ultimo.id, "Cinco")
    assert orden_de(repo, materia_id) == [*NOMBRES, "Cinco"]


def test_insertar_tras_no_toca_lo_completado(
    repo: RepositorioModulos, materia_id: int
) -> None:
    segundo = repo.listar(materia_id)[1]
    repo.insertar_tras(segundo.id, "Dos y medio")

    completados = [m.nombre for m in repo.listar(materia_id) if m.completado]
    assert completados == ["Dos"]


def test_insertar_tras_un_modulo_que_ya_no_existe(repo: RepositorioModulos) -> None:
    assert repo.insertar_tras(9999, "Fantasma") is None


def test_partir_un_modulo_en_tres(repo: RepositorioModulos, materia_id: int) -> None:
    """El caso real: un LM del curriculo viejo pasa a ser tres.

    Se renombra el original al primero de los nuevos —para no perder su estado— y
    los otros dos se insertan detras, en orden.
    """
    original = repo.listar(materia_id)[1]
    repo.renombrar(original.id, "Company Analysis: Past and Present")

    anterior = original.id
    for nombre in ("Industry and Competitive Analysis", "Company Analysis: Forecasting"):
        nuevo = repo.insertar_tras(anterior, nombre)
        assert nuevo is not None
        anterior = nuevo.id

    assert orden_de(repo, materia_id) == [
        "Uno",
        "Company Analysis: Past and Present",
        "Industry and Competitive Analysis",
        "Company Analysis: Forecasting",
        "Tres",
        "Cuatro",
    ]
    # El completado viaja con el renombrado, no con la posicion.
    hechos = [m.nombre for m in repo.listar(materia_id) if m.completado]
    assert hechos == ["Company Analysis: Past and Present"]


# --- Mover a otra materia --------------------------------------------------


@pytest.fixture
def otra_materia(conn: sqlite3.Connection, materia_id: int) -> int:
    """Segunda materia del mismo proyecto, con un modulo llamado «Uno»."""
    materia = RepositorioMaterias(conn).obtener(materia_id)
    assert materia is not None
    destino = RepositorioMaterias(conn).crear(materia.proyecto_id, "Fixed Income")
    RepositorioModulos(conn).crear(destino.id, "Uno", orden=0)
    return destino.id


def test_mover_a_materia_conserva_el_completado_y_su_fecha(
    repo: RepositorioModulos, materia_id: int, otra_materia: int
) -> None:
    """Es toda la gracia: hasta ahora habia que borrar y recrear."""
    antes = next(m for m in repo.listar(materia_id) if m.nombre == "Dos")
    assert repo.mover_a_materia(antes.id, otra_materia)

    despues = repo.obtener(antes.id)
    assert despues is not None
    assert despues.materia_id == otra_materia
    assert despues.completado
    assert despues.completado_en == antes.completado_en


def test_mover_a_materia_lo_deja_al_final_del_destino(
    repo: RepositorioModulos, materia_id: int, otra_materia: int
) -> None:
    tres = next(m for m in repo.listar(materia_id) if m.nombre == "Tres")
    repo.mover_a_materia(tres.id, otra_materia)
    assert orden_de(repo, otra_materia) == ["Uno", "Tres"]


def test_mover_a_materia_lo_quita_del_origen(
    repo: RepositorioModulos, materia_id: int, otra_materia: int
) -> None:
    tres = next(m for m in repo.listar(materia_id) if m.nombre == "Tres")
    repo.mover_a_materia(tres.id, otra_materia)
    assert orden_de(repo, materia_id) == ["Uno", "Dos", "Cuatro"]


def test_mover_a_materia_rechaza_un_nombre_ya_usado(
    repo: RepositorioModulos, materia_id: int, otra_materia: int
) -> None:
    """El `UNIQUE (materia_id, nombre)` se comprueba antes, no se deja reventar."""
    uno = next(m for m in repo.listar(materia_id) if m.nombre == "Uno")
    assert not repo.mover_a_materia(uno.id, otra_materia)

    sin_mover = repo.obtener(uno.id)
    assert sin_mover is not None and sin_mover.materia_id == materia_id
    assert orden_de(repo, otra_materia) == ["Uno"]


def test_mover_a_la_misma_materia_no_hace_nada(
    repo: RepositorioModulos, materia_id: int
) -> None:
    primero = repo.listar(materia_id)[0]
    assert not repo.mover_a_materia(primero.id, materia_id)
    assert orden_de(repo, materia_id) == list(NOMBRES)


def test_mover_a_materia_un_modulo_que_ya_no_existe(repo: RepositorioModulos) -> None:
    assert not repo.mover_a_materia(9999, 1)


# --- Marcado masivo --------------------------------------------------------


def test_marcar_materia_marca_los_pendientes_y_los_cuenta(
    repo: RepositorioModulos, materia_id: int
) -> None:
    assert repo.marcar_materia(materia_id, True) == 3   # «Dos» ya estaba
    assert all(m.completado for m in repo.listar(materia_id))


def test_marcar_materia_no_reescribe_la_fecha_de_los_ya_hechos(
    repo: RepositorioModulos, materia_id: int
) -> None:
    """Reescribirla reiniciaria en silencio las sugerencias de repaso."""
    antes = next(m for m in repo.listar(materia_id) if m.nombre == "Dos")
    repo.marcar_materia(materia_id, True)

    despues = repo.obtener(antes.id)
    assert despues is not None
    assert despues.completado_en == antes.completado_en


def test_marcar_materia_dos_veces_no_cambia_nada_la_segunda(
    repo: RepositorioModulos, materia_id: int
) -> None:
    repo.marcar_materia(materia_id, True)
    assert repo.marcar_materia(materia_id, True) == 0


def test_desmarcar_materia_limpia_la_fecha(
    repo: RepositorioModulos, materia_id: int
) -> None:
    assert repo.marcar_materia(materia_id, False) == 1   # solo «Dos» estaba
    assert all(m.completado_en is None for m in repo.listar(materia_id))


def test_marcar_materia_no_toca_otras_materias(
    repo: RepositorioModulos, materia_id: int, otra_materia: int
) -> None:
    repo.marcar_materia(materia_id, True)
    assert not any(m.completado for m in repo.listar(otra_materia))


def test_marcar_una_materia_vacia_devuelve_cero(
    conn: sqlite3.Connection, repo: RepositorioModulos
) -> None:
    proyecto = RepositorioProyectos(conn).crear("Vacio")
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Sin temario")
    assert repo.marcar_materia(materia.id, True) == 0
