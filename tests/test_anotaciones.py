"""Repositorio de anotaciones: marcadores, notas y resaltados."""

from __future__ import annotations

import sqlite3

import pytest

from mukuwareru.nucleo.modelos import TipoAnotacion
from mukuwareru.nucleo.repositorios import (
    RepositorioAnotaciones,
    RepositorioDocumentos,
    RepositorioProyectos,
)

RECTS = [(65.0, 74.0, 201.0, 16.0), (65.0, 111.0, 194.0, 14.0)]


@pytest.fixture
def documento(conn: sqlite3.Connection) -> int:
    proyecto = RepositorioProyectos(conn).crear("CFA")
    return RepositorioDocumentos(conn).crear(
        proyecto.id,
        ruta_relativa="temario.pdf",
        nombre="Temario",
        huella="123-abc",
        bytes_=1024,
    ).id


def test_crear_y_listar(conn: sqlite3.Connection, documento: int) -> None:
    repo = RepositorioAnotaciones(conn)
    repo.crear(documento, tipo=TipoAnotacion.RESALTADO, pagina=3, rects=RECTS,
               texto_seleccionado="muestra")
    anotaciones = repo.listar(documento)
    assert len(anotaciones) == 1
    assert anotaciones[0].tipo is TipoAnotacion.RESALTADO
    assert anotaciones[0].pagina == 3


def test_los_rectangulos_sobreviven_al_viaje_por_json(
    conn: sqlite3.Connection, documento: int
) -> None:
    repo = RepositorioAnotaciones(conn)
    repo.crear(documento, tipo=TipoAnotacion.RESALTADO, pagina=0, rects=RECTS)
    recuperados = repo.listar(documento)[0].rects
    assert recuperados == RECTS


def test_se_ordenan_por_pagina(conn: sqlite3.Connection, documento: int) -> None:
    repo = RepositorioAnotaciones(conn)
    for pagina in (5, 1, 3):
        repo.crear(documento, tipo=TipoAnotacion.MARCADOR, pagina=pagina)
    assert [a.pagina for a in repo.listar(documento)] == [1, 3, 5]


def test_filtrar_por_tipo(conn: sqlite3.Connection, documento: int) -> None:
    repo = RepositorioAnotaciones(conn)
    proyecto_id = RepositorioDocumentos(conn).obtener(documento).proyecto_id
    repo.crear(documento, tipo=TipoAnotacion.NOTA, pagina=0, comentario="una nota")
    repo.crear(documento, tipo=TipoAnotacion.MARCADOR, pagina=1)

    solo_notas = repo.listar_del_proyecto(proyecto_id, TipoAnotacion.NOTA)
    assert len(solo_notas) == 1
    assert solo_notas[0][0].comentario == "una nota"
    assert solo_notas[0][1] == "Temario"
    assert len(repo.listar_del_proyecto(proyecto_id)) == 2


def test_actualizar_comentario(conn: sqlite3.Connection, documento: int) -> None:
    repo = RepositorioAnotaciones(conn)
    anotacion = repo.crear(documento, tipo=TipoAnotacion.NOTA, pagina=0, comentario="borrador")
    repo.actualizar_comentario(anotacion.id, "definitivo")
    assert repo.listar(documento)[0].comentario == "definitivo"


def test_eliminar(conn: sqlite3.Connection, documento: int) -> None:
    repo = RepositorioAnotaciones(conn)
    anotacion = repo.crear(documento, tipo=TipoAnotacion.MARCADOR, pagina=0)
    repo.eliminar(anotacion.id)
    assert repo.listar(documento) == []


def test_borrar_el_documento_arrastra_sus_anotaciones(
    conn: sqlite3.Connection, documento: int
) -> None:
    repo = RepositorioAnotaciones(conn)
    repo.crear(documento, tipo=TipoAnotacion.MARCADOR, pagina=0)
    RepositorioDocumentos(conn).eliminar(documento)
    assert conn.execute("SELECT COUNT(*) FROM anotacion").fetchone()[0] == 0
