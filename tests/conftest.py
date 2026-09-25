"""Fixtures compartidas."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from mukuwareru.nucleo.bd import conexion as bd
from mukuwareru.nucleo.modelos import Proyecto
from mukuwareru.nucleo.repositorios import RepositorioProyectos


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    """Base de datos en memoria, ya migrada."""
    cx = bd.abrir(":memory:")
    yield cx
    cx.close()


@pytest.fixture
def repo_proyectos(conn: sqlite3.Connection) -> RepositorioProyectos:
    return RepositorioProyectos(conn)


@pytest.fixture
def proyecto(conn: sqlite3.Connection) -> Proyecto:
    """Un proyecto vacio. Los tests que necesitan temario siembran el suyo."""
    return RepositorioProyectos(conn).crear("CFA")
