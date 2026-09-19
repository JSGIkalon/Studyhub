"""Escaneo de la biblioteca y reconciliacion con la base de datos."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from mukuwareru.nucleo.modelos import Proyecto
from mukuwareru.nucleo.repositorios import RepositorioDocumentos, RepositorioProyectos
from mukuwareru.nucleo.servicios import ServicioBiblioteca
from mukuwareru.utilidades import huella


def _pdf(carpeta: Path, nombre: str, contenido: bytes = b"%PDF-1.4 contenido") -> Path:
    ruta = carpeta / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido)
    return ruta


@pytest.fixture
def proyecto(conn: sqlite3.Connection, tmp_path: Path) -> Proyecto:
    return RepositorioProyectos(conn).crear("CFA", ruta_biblioteca=str(tmp_path / "lib"))


# --- Huella ----------------------------------------------------------------


def test_la_huella_distingue_contenidos(tmp_path: Path) -> None:
    uno = _pdf(tmp_path, "a.pdf", b"contenido uno")
    otro = _pdf(tmp_path, "b.pdf", b"contenido dos")
    assert huella.calcular(uno) != huella.calcular(otro)


def test_la_huella_es_estable(tmp_path: Path) -> None:
    ruta = _pdf(tmp_path, "a.pdf")
    assert huella.calcular(ruta) == huella.calcular(ruta)


def test_la_huella_no_depende_del_nombre(tmp_path: Path) -> None:
    uno = _pdf(tmp_path, "a.pdf", b"identico")
    otro = _pdf(tmp_path, "b.pdf", b"identico")
    assert huella.calcular(uno) == huella.calcular(otro)


# --- Escaneo ---------------------------------------------------------------


def test_descubre_pdfs_incluidos_los_de_subcarpetas(
    conn: sqlite3.Connection, proyecto: Proyecto, tmp_path: Path
) -> None:
    carpeta = tmp_path / "lib"
    _pdf(carpeta, "uno.pdf", b"uno")
    _pdf(carpeta, "Repaso/dos.pdf", b"dos")
    _pdf(carpeta, "notas.txt", b"no es un pdf")

    resultado = ServicioBiblioteca(conn).escanear(proyecto)
    assert (resultado.nuevos, resultado.total) == (2, 2)
    rutas = {d.ruta_relativa for d in RepositorioDocumentos(conn).listar(proyecto.id)}
    assert rutas == {"uno.pdf", "Repaso/dos.pdf"}


def test_escanear_dos_veces_no_duplica(
    conn: sqlite3.Connection, proyecto: Proyecto, tmp_path: Path
) -> None:
    _pdf(tmp_path / "lib", "uno.pdf")
    servicio = ServicioBiblioteca(conn)
    servicio.escanear(proyecto)
    segundo = servicio.escanear(proyecto)
    assert segundo.nuevos == 0
    assert not segundo.hubo_cambios
    assert RepositorioDocumentos(conn).contar(proyecto.id) == 1


def test_renombrar_conserva_la_posicion_de_lectura(
    conn: sqlite3.Connection, proyecto: Proyecto, tmp_path: Path
) -> None:
    carpeta = tmp_path / "lib"
    ruta = _pdf(carpeta, "original.pdf", b"contenido unico")
    servicio = ServicioBiblioteca(conn)
    documentos = RepositorioDocumentos(conn)

    servicio.escanear(proyecto)
    previo = documentos.listar(proyecto.id)[0]
    documentos.guardar_posicion(previo.id, pagina=42, zoom=1.5)

    ruta.rename(carpeta / "renombrado.pdf")
    resultado = servicio.escanear(proyecto)

    assert (resultado.movidos, resultado.nuevos, resultado.eliminados) == (1, 0, 0)
    actual = documentos.listar(proyecto.id)[0]
    assert actual.id == previo.id
    assert actual.ruta_relativa == "renombrado.pdf"
    assert (actual.pagina_actual, actual.zoom) == (42, 1.5)


def test_mover_a_subcarpeta_tambien_conserva_el_registro(
    conn: sqlite3.Connection, proyecto: Proyecto, tmp_path: Path
) -> None:
    carpeta = tmp_path / "lib"
    ruta = _pdf(carpeta, "uno.pdf", b"contenido unico")
    servicio = ServicioBiblioteca(conn)
    servicio.escanear(proyecto)

    (carpeta / "Archivo").mkdir()
    ruta.rename(carpeta / "Archivo" / "uno.pdf")
    resultado = servicio.escanear(proyecto)

    assert resultado.movidos == 1
    assert RepositorioDocumentos(conn).contar(proyecto.id) == 1


def test_borrar_el_archivo_lo_quita_del_registro(
    conn: sqlite3.Connection, proyecto: Proyecto, tmp_path: Path
) -> None:
    ruta = _pdf(tmp_path / "lib", "uno.pdf")
    servicio = ServicioBiblioteca(conn)
    servicio.escanear(proyecto)

    ruta.unlink()
    resultado = servicio.escanear(proyecto)
    assert resultado.eliminados == 1
    assert RepositorioDocumentos(conn).contar(proyecto.id) == 0


def test_reemplazar_el_contenido_marca_el_documento_como_modificado(
    conn: sqlite3.Connection, proyecto: Proyecto, tmp_path: Path
) -> None:
    ruta = _pdf(tmp_path / "lib", "uno.pdf", b"version uno")
    servicio = ServicioBiblioteca(conn)
    documentos = RepositorioDocumentos(conn)
    servicio.escanear(proyecto)
    documentos.establecer_paginas(documentos.listar(proyecto.id)[0].id, 10)

    ruta.write_bytes(b"version dos, distinta del todo")
    resultado = servicio.escanear(proyecto)

    assert resultado.modificados == 1
    # Las paginas se olvidan: el archivo ya no es el mismo.
    assert documentos.listar(proyecto.id)[0].paginas is None


def test_una_carpeta_inexistente_se_crea_vacia(
    conn: sqlite3.Connection, proyecto: Proyecto, tmp_path: Path
) -> None:
    resultado = ServicioBiblioteca(conn).escanear(proyecto)
    assert (resultado.total, resultado.nuevos) == (0, 0)
    assert (tmp_path / "lib").is_dir()
