"""Grafo de dependencias: estados derivados, Y/O, ciclos y no duplicacion."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from mukuwareru.nucleo.modelos import DestinoNodo, EstadoNodo
from mukuwareru.nucleo.repositorios import (
    RepositorioGrafo,
    RepositorioHitos,
    RepositorioMaterias,
    RepositorioModulos,
    RepositorioProyectos,
)
from mukuwareru.nucleo.servicios import (
    CicloError,
    ServicioGrafo,
    cierra_ciclo,
    estado_de,
)

# --- Reglas puras: sin base de datos -----------------------------------------


def test_sin_prerrequisitos_un_nodo_esta_disponible() -> None:
    assert estado_de(0.0, (), set()) is EstadoNodo.DISPONIBLE


def test_avance_completo_es_completado() -> None:
    assert estado_de(1.0, (), set()) is EstadoNodo.COMPLETADO


def test_avance_parcial_con_prerrequisitos_cumplidos_es_en_curso() -> None:
    assert estado_de(0.5, ((1,),), {1}) is EstadoNodo.EN_CURSO


def test_un_prerrequisito_sin_cumplir_bloquea() -> None:
    assert estado_de(0.0, ((1,),), set()) is EstadoNodo.BLOQUEADO


def test_empezar_por_donde_no_era_sigue_bloqueado() -> None:
    """El grafo esta para avisar de esto, no para disimularlo."""
    assert estado_de(0.5, ((1,),), set()) is EstadoNodo.BLOQUEADO


def test_completado_manda_aunque_este_bloqueado() -> None:
    """Lo hecho, hecho esta: no tiene sentido pintarlo como bloqueado."""
    assert estado_de(1.0, ((1,),), set()) is EstadoNodo.COMPLETADO


@pytest.mark.parametrize(
    ("calculo", "probabilidad", "estadistica", "esperado"),
    [
        (False, False, False, EstadoNodo.BLOQUEADO),
        (True, False, False, EstadoNodo.BLOQUEADO),   # falta el grupo O entero
        (False, True, False, EstadoNodo.BLOQUEADO),   # falta Calculo
        (True, True, False, EstadoNodo.DISPONIBLE),   # Calculo Y Probabilidad
        (True, False, True, EstadoNodo.DISPONIBLE),   # Calculo Y Estadistica
        (True, True, True, EstadoNodo.DISPONIBLE),
    ],
)
def test_calculo_y_probabilidad_o_estadistica(
    calculo: bool, probabilidad: bool, estadistica: bool, esperado: EstadoNodo
) -> None:
    """«Calculo Y (Probabilidad O Estadistica)», el ejemplo del enunciado.

    Dos grupos: el 1 con Calculo solo, el 2 con las dos alternativas.
    """
    completados = {
        identificador
        for identificador, hecho in ((1, calculo), (2, probabilidad), (3, estadistica))
        if hecho
    }
    assert estado_de(0.0, ((1,), (2, 3)), completados) is esperado


def test_cierra_ciclo_directo_y_transitivo() -> None:
    assert cierra_ciclo([], 1, 1)                      # consigo mismo
    assert cierra_ciclo([(2, 1)], 1, 2)                # A->B, luego B->A
    assert cierra_ciclo([(2, 1), (3, 2)], 1, 3)        # A->B->C, luego C->A


def test_un_diamante_no_es_un_ciclo() -> None:
    """A antes de B y de C, las dos antes de D: es la convergencia pedida."""
    aristas = [(2, 1), (3, 1), (4, 2)]
    assert not cierra_ciclo(aristas, 4, 3)


# --- Contra la base de datos -------------------------------------------------


@pytest.fixture
def proyecto_id(conn: sqlite3.Connection) -> int:
    """Tres materias, la primera con dos modulos."""
    proyecto = RepositorioProyectos(conn).crear("MSc")
    materias = RepositorioMaterias(conn)
    calculo = materias.crear(proyecto.id, "Calculus", orden=0)
    materias.crear(proyecto.id, "Probability", orden=1)
    materias.crear(proyecto.id, "Quant Finance", orden=2)

    modulos = RepositorioModulos(conn)
    modulos.crear(calculo.id, "LM 1", orden=0)
    modulos.crear(calculo.id, "LM 2", orden=1)
    return proyecto.id


@pytest.fixture
def servicio(conn: sqlite3.Connection) -> ServicioGrafo:
    return ServicioGrafo(conn)


def materias(conn: sqlite3.Connection, proyecto_id: int) -> list[int]:
    return [m.id for m in RepositorioMaterias(conn).listar(proyecto_id)]


def test_arrastrar_dos_veces_no_duplica(
    conn: sqlite3.Connection, servicio: ServicioGrafo, proyecto_id: int
) -> None:
    """El invariante central: el lienzo referencia, no copia."""
    calculo = materias(conn, proyecto_id)[0]
    primero = servicio.agregar(proyecto_id, DestinoNodo.MATERIA, calculo, 10, 20)
    segundo = servicio.agregar(proyecto_id, DestinoNodo.MATERIA, calculo, 99, 88)

    assert primero.id == segundo.id
    assert len(servicio.cargar(proyecto_id).nodos) == 1
    # Volver a soltarla la mueve, que es lo que espera quien arrastra.
    assert RepositorioGrafo(conn).obtener_nodo(primero.id).x == 99


def test_el_nombre_se_lee_de_la_entidad(
    conn: sqlite3.Connection, servicio: ServicioGrafo, proyecto_id: int
) -> None:
    """Renombrar en Progreso cambia el nodo sin sincronizar nada."""
    calculo = materias(conn, proyecto_id)[0]
    servicio.agregar(proyecto_id, DestinoNodo.MATERIA, calculo, 0, 0)
    RepositorioMaterias(conn).renombrar(calculo, "Calculo I")

    assert servicio.cargar(proyecto_id).nodos[0].nombre == "Calculo I"


def test_marcar_un_modulo_cambia_el_estado_del_nodo(
    conn: sqlite3.Connection, servicio: ServicioGrafo, proyecto_id: int
) -> None:
    """La prueba de que no hay un segundo sistema de progreso.

    Se marca desde el repositorio de modulos —lo que hace la vista Progreso— y
    el grafo lo refleja sin que nadie le haya dicho nada.
    """
    calculo = materias(conn, proyecto_id)[0]
    servicio.agregar(proyecto_id, DestinoNodo.MATERIA, calculo, 0, 0)
    assert servicio.cargar(proyecto_id).nodos[0].estado is EstadoNodo.DISPONIBLE

    modulos = RepositorioModulos(conn)
    listados = modulos.listar(calculo)
    modulos.marcar(listados[0].id, True)
    resuelto = servicio.cargar(proyecto_id).nodos[0]
    assert resuelto.estado is EstadoNodo.EN_CURSO
    assert resuelto.porcentaje == 50

    modulos.marcar(listados[1].id, True)
    assert servicio.cargar(proyecto_id).nodos[0].estado is EstadoNodo.COMPLETADO


def test_un_prerrequisito_bloquea_hasta_completarlo(
    conn: sqlite3.Connection, servicio: ServicioGrafo, proyecto_id: int
) -> None:
    calculo, _probabilidad, quant = materias(conn, proyecto_id)
    nodo_calculo = servicio.agregar(proyecto_id, DestinoNodo.MATERIA, calculo, 0, 0)
    nodo_quant = servicio.agregar(proyecto_id, DestinoNodo.MATERIA, quant, 200, 0)
    servicio.conectar(nodo_quant.id, nodo_calculo.id)

    grafo = servicio.cargar(proyecto_id)
    assert grafo.por_id(nodo_quant.id).estado is EstadoNodo.BLOQUEADO

    modulos = RepositorioModulos(conn)
    for modulo in modulos.listar(calculo):
        modulos.marcar(modulo.id, True)

    grafo = servicio.cargar(proyecto_id)
    assert grafo.por_id(nodo_quant.id).estado is EstadoNodo.DISPONIBLE


def test_dos_conexiones_nuevas_son_un_y(
    conn: sqlite3.Connection, servicio: ServicioGrafo, proyecto_id: int
) -> None:
    """Quien dibuja dos flechas espera que hagan falta las dos."""
    calculo, probabilidad, quant = materias(conn, proyecto_id)
    nodos = [
        servicio.agregar(proyecto_id, DestinoNodo.MATERIA, m, i * 100, 0)
        for i, m in enumerate((calculo, probabilidad, quant))
    ]
    servicio.conectar(nodos[2].id, nodos[0].id)
    servicio.conectar(nodos[2].id, nodos[1].id)

    grupos = servicio.cargar(proyecto_id).por_id(nodos[2].id).prerrequisitos
    assert grupos == ((nodos[0].id,), (nodos[1].id,))


def test_alternar_o_funde_y_separa_grupos(
    conn: sqlite3.Connection, servicio: ServicioGrafo, proyecto_id: int
) -> None:
    calculo, probabilidad, quant = materias(conn, proyecto_id)
    nodos = [
        servicio.agregar(proyecto_id, DestinoNodo.MATERIA, m, i * 100, 0)
        for i, m in enumerate((calculo, probabilidad, quant))
    ]
    servicio.conectar(nodos[2].id, nodos[0].id)
    servicio.conectar(nodos[2].id, nodos[1].id)

    assert servicio.alternar_o(nodos[2].id, nodos[0].id, nodos[1].id)
    grupos = servicio.cargar(proyecto_id).por_id(nodos[2].id).prerrequisitos
    assert grupos == ((nodos[0].id, nodos[1].id),)   # un solo grupo: son un O

    assert servicio.alternar_o(nodos[2].id, nodos[0].id, nodos[1].id)
    grupos = servicio.cargar(proyecto_id).por_id(nodos[2].id).prerrequisitos
    assert len(grupos) == 2                           # vuelven a ser un Y


def test_conectar_un_ciclo_no_escribe_nada(
    conn: sqlite3.Connection, servicio: ServicioGrafo, proyecto_id: int
) -> None:
    calculo, probabilidad, _quant = materias(conn, proyecto_id)
    uno = servicio.agregar(proyecto_id, DestinoNodo.MATERIA, calculo, 0, 0)
    dos = servicio.agregar(proyecto_id, DestinoNodo.MATERIA, probabilidad, 100, 0)
    servicio.conectar(dos.id, uno.id)

    with pytest.raises(CicloError):
        servicio.conectar(uno.id, dos.id)

    assert len(servicio.cargar(proyecto_id).aristas) == 1


def test_borrar_la_materia_se_lleva_su_nodo(
    conn: sqlite3.Connection, servicio: ServicioGrafo, proyecto_id: int
) -> None:
    calculo = materias(conn, proyecto_id)[0]
    servicio.agregar(proyecto_id, DestinoNodo.MATERIA, calculo, 0, 0)
    RepositorioMaterias(conn).eliminar(calculo)
    assert servicio.cargar(proyecto_id).vacio


def test_borrar_el_nodo_no_toca_la_materia(
    conn: sqlite3.Connection, servicio: ServicioGrafo, proyecto_id: int
) -> None:
    """Quitar algo del lienzo no puede borrar el temario."""
    calculo = materias(conn, proyecto_id)[0]
    nodo = servicio.agregar(proyecto_id, DestinoNodo.MATERIA, calculo, 0, 0)
    servicio.eliminar(nodo.id)

    assert servicio.cargar(proyecto_id).vacio
    assert RepositorioMaterias(conn).obtener(calculo) is not None


def test_candidatos_excluye_lo_ya_colocado(
    conn: sqlite3.Connection, servicio: ServicioGrafo, proyecto_id: int
) -> None:
    calculo = materias(conn, proyecto_id)[0]
    antes = servicio.candidatos(proyecto_id)
    servicio.agregar(proyecto_id, DestinoNodo.MATERIA, calculo, 0, 0)
    despues = servicio.candidatos(proyecto_id)

    assert len(despues) == len(antes) - 1
    assert all(
        not (c.destino is DestinoNodo.MATERIA and c.objeto_id == calculo)
        for c in despues
    )


def test_los_nodos_pueden_ser_de_varios_tipos(
    conn: sqlite3.Connection, servicio: ServicioGrafo, proyecto_id: int
) -> None:
    """Materia, modulo e hito conviven en el mismo lienzo."""
    calculo = materias(conn, proyecto_id)[0]
    modulo = RepositorioModulos(conn).listar(calculo)[0]
    hito = RepositorioHitos(conn).crear(proyecto_id, "Examen", date(2026, 12, 1))

    servicio.agregar(proyecto_id, DestinoNodo.MATERIA, calculo, 0, 0)
    servicio.agregar(proyecto_id, DestinoNodo.MODULO, modulo.id, 100, 0)
    servicio.agregar(proyecto_id, DestinoNodo.HITO, hito.id, 200, 0)

    destinos = {n.destino for n in servicio.cargar(proyecto_id).nodos}
    assert destinos == {DestinoNodo.MATERIA, DestinoNodo.MODULO, DestinoNodo.HITO}


def test_la_posicion_se_persiste_con_decimales(
    conn: sqlite3.Connection, servicio: ServicioGrafo, proyecto_id: int
) -> None:
    """Coordenadas de escena, no pixeles enteros de pantalla."""
    calculo = materias(conn, proyecto_id)[0]
    nodo = servicio.agregar(proyecto_id, DestinoNodo.MATERIA, calculo, 0, 0)
    servicio.mover(nodo.id, 12.5, -40.25)

    guardado = servicio.cargar(proyecto_id).nodos[0].nodo
    assert (guardado.x, guardado.y) == (12.5, -40.25)


def test_el_grafo_no_cruza_proyectos(
    conn: sqlite3.Connection, servicio: ServicioGrafo, proyecto_id: int
) -> None:
    otro = RepositorioProyectos(conn).crear("CFA")
    calculo = materias(conn, proyecto_id)[0]
    servicio.agregar(proyecto_id, DestinoNodo.MATERIA, calculo, 0, 0)

    assert servicio.cargar(otro.id).vacio
