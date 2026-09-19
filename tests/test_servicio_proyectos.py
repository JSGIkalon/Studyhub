"""Ciclo de vida de un proyecto, con la biblioteca de PDFs de por medio.

El caso que de verdad importa es el renombrado: con ``ruta_biblioteca`` en NULL
la carpeta se deduce del nombre, y cambiarlo sin mover nada haria que el
siguiente escaneo borrase todos los documentos y, en cascada, sus anotaciones.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest

from mukuwareru.nucleo.modelos import OrigenSesion, Proyecto, TipoAnotacion, TipoSesion
from mukuwareru.nucleo.repositorios import (
    RepositorioAnotaciones,
    RepositorioDocumentos,
    RepositorioMaterias,
    RepositorioModulos,
    RepositorioProyectos,
    RepositorioSesiones,
)
from mukuwareru.nucleo.servicios import (
    DatosProyecto,
    ServicioBiblioteca,
    ServicioProyectos,
    ruta_biblioteca,
)
from mukuwareru.utilidades import rutas


@pytest.fixture
def biblioteca_en(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Reapunta ``Library/`` a una carpeta temporal.

    Se parchea el atributo del modulo ``rutas`` y no el de cada consumidor:
    tanto el servicio como ``servicios.biblioteca`` lo resuelven en cada
    llamada, asi que un solo parche cubre los dos caminos.
    """
    raiz = tmp_path / "Library"
    raiz.mkdir()
    monkeypatch.setattr(rutas, "carpeta_biblioteca", lambda: raiz)
    return raiz


def _pdf(carpeta: Path, nombre: str, contenido: bytes) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre
    ruta.write_bytes(contenido)
    return ruta


# --- Renombrado ------------------------------------------------------------


def test_renombrar_mueve_la_carpeta_por_defecto(
    conn: sqlite3.Connection, biblioteca_en: Path
) -> None:
    servicio = ServicioProyectos(conn)
    proyecto = servicio.crear(DatosProyecto(nombre="CFA Level I"))
    _pdf(biblioteca_en / "CFA Level I", "uno.pdf", b"contenido unico")

    renombrado = servicio.renombrar(proyecto, "CFA Nivel I")

    assert (biblioteca_en / "CFA Nivel I" / "uno.pdf").is_file()
    assert not (biblioteca_en / "CFA Level I").exists()
    # La ruta sigue siendo la de por defecto: no hay nada que fijar.
    assert renombrado.ruta_biblioteca is None
    assert ruta_biblioteca(renombrado) == biblioteca_en / "CFA Nivel I"


def test_renombrar_conserva_documentos_y_anotaciones(
    conn: sqlite3.Connection, biblioteca_en: Path
) -> None:
    servicio = ServicioProyectos(conn)
    proyecto = servicio.crear(DatosProyecto(nombre="CFA"))
    _pdf(biblioteca_en / "CFA", "uno.pdf", b"contenido unico")

    escaner = ServicioBiblioteca(conn)
    documentos = RepositorioDocumentos(conn)
    escaner.escanear(proyecto)
    documento = documentos.listar(proyecto.id)[0]
    documentos.guardar_posicion(documento.id, pagina=42, zoom=1.5)
    RepositorioAnotaciones(conn).crear(
        documento.id, tipo=TipoAnotacion.NOTA, pagina=42, comentario="importante"
    )

    renombrado = servicio.renombrar(proyecto, "CFA Nivel I")
    escaner.escanear(renombrado)

    supervivientes = documentos.listar(renombrado.id)
    assert len(supervivientes) == 1
    assert supervivientes[0].id == documento.id
    assert (supervivientes[0].pagina_actual, supervivientes[0].zoom) == (42, 1.5)
    assert RepositorioAnotaciones(conn).contar(renombrado.id) == 1


def test_si_no_se_puede_mover_se_fija_la_ruta_antigua(
    conn: sqlite3.Connection, biblioteca_en: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El caso de OneDrive: la carpeta esta tomada y ``rename`` falla.

    Fijar la ruta antigua es la salida segura: se pierde la coherencia entre el
    nombre y la carpeta, que es cosmetica, y no los PDFs ni las anotaciones.
    """
    servicio = ServicioProyectos(conn)
    proyecto = servicio.crear(DatosProyecto(nombre="CFA"))
    vieja = biblioteca_en / "CFA"
    _pdf(vieja, "uno.pdf", b"contenido unico")

    escaner = ServicioBiblioteca(conn)
    escaner.escanear(proyecto)

    def negarse(self: Path, destino: object) -> Path:
        raise OSError("la carpeta esta en uso")

    monkeypatch.setattr(Path, "rename", negarse)
    renombrado = servicio.renombrar(proyecto, "CFA Nivel I")

    assert renombrado.nombre == "CFA Nivel I"
    assert renombrado.ruta_biblioteca == str(vieja)
    assert ruta_biblioteca(renombrado) == vieja

    monkeypatch.undo()
    escaner.escanear(renombrado)
    assert RepositorioDocumentos(conn).contar(renombrado.id) == 1


def test_renombrar_con_ruta_explicita_no_toca_el_disco(
    conn: sqlite3.Connection, biblioteca_en: Path, tmp_path: Path
) -> None:
    propia = tmp_path / "mis pdfs"
    _pdf(propia, "uno.pdf", b"contenido unico")
    servicio = ServicioProyectos(conn)
    proyecto = servicio.crear(DatosProyecto(nombre="CFA", ruta_biblioteca=str(propia)))

    renombrado = servicio.renombrar(proyecto, "CFA Nivel I")

    assert renombrado.ruta_biblioteca == str(propia)
    assert (propia / "uno.pdf").is_file()
    assert not (biblioteca_en / "CFA Nivel I").exists()


def test_renombrar_sin_carpeta_creada_no_falla(
    conn: sqlite3.Connection, biblioteca_en: Path
) -> None:
    servicio = ServicioProyectos(conn)
    proyecto = servicio.crear(DatosProyecto(nombre="Recien nacido"))

    renombrado = servicio.renombrar(proyecto, "Con nombre nuevo")

    assert renombrado.ruta_biblioteca is None
    assert not (biblioteca_en / "Recien nacido").exists()


def test_guardar_cambia_todos_los_campos(
    conn: sqlite3.Connection, biblioteca_en: Path
) -> None:
    servicio = ServicioProyectos(conn)
    proyecto = servicio.crear(DatosProyecto(nombre="Borrador"))

    guardado = servicio.guardar(
        proyecto,
        DatosProyecto(
            nombre="MSc Financial Engineering",
            icono="grafico",
            color="#3E63DD",
            fecha_objetivo=date(2027, 6, 1),
        ),
    )

    assert guardado.nombre == "MSc Financial Engineering"
    assert (guardado.icono, guardado.color) == ("grafico", "#3E63DD")
    assert guardado.fecha_objetivo == date(2027, 6, 1)


# --- Archivado, orden y borrado --------------------------------------------


def test_archivar_lo_saca_de_la_lista_sin_borrarlo(conn: sqlite3.Connection) -> None:
    servicio = ServicioProyectos(conn)
    proyecto = servicio.crear(DatosProyecto(nombre="Antiguo"))

    servicio.archivar(proyecto)

    repositorio = RepositorioProyectos(conn)
    assert repositorio.listar() == []
    assert len(repositorio.listar(incluir_archivados=True)) == 1


def test_reordenar_reasigna_desde_cero(conn: sqlite3.Connection) -> None:
    servicio = ServicioProyectos(conn)
    uno = servicio.crear(DatosProyecto(nombre="Uno"))
    dos = servicio.crear(DatosProyecto(nombre="Dos"))
    tres = servicio.crear(DatosProyecto(nombre="Tres"))

    servicio.reordenar([tres.id, uno.id, dos.id])

    repositorio = RepositorioProyectos(conn)
    assert [p.nombre for p in repositorio.listar()] == ["Tres", "Uno", "Dos"]
    assert [p.orden for p in repositorio.listar()] == [0, 1, 2]


def _poblar(conn: sqlite3.Connection, proyecto: Proyecto) -> None:
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    RepositorioModulos(conn).crear(materia.id, "Code of Standards")
    documento = RepositorioDocumentos(conn).crear(
        proyecto.id, ruta_relativa="uno.pdf", nombre="uno", huella="abc", bytes_=10
    )
    RepositorioAnotaciones(conn).crear(
        documento.id, tipo=TipoAnotacion.NOTA, pagina=0, comentario="hola"
    )
    RepositorioSesiones(conn).crear(
        proyecto.id,
        tipo=TipoSesion.TRABAJO,
        origen=OrigenSesion.POMODORO,
        inicio=datetime.now().astimezone(),
        duracion_seg=1500,
    )


def test_resumen_borrado_cuenta_la_cascada_completa(
    conn: sqlite3.Connection, biblioteca_en: Path
) -> None:
    servicio = ServicioProyectos(conn)
    proyecto = servicio.crear(DatosProyecto(nombre="CFA"))
    _poblar(conn, proyecto)

    resumen = servicio.resumen_borrado(proyecto)

    assert resumen.materias == 1
    assert resumen.modulos == 1
    assert resumen.documentos == 1
    # La anotacion cuelga del documento, no del proyecto: si no se cuenta
    # asi, el dialogo de confirmacion se calla lo que mas duele perder.
    assert resumen.anotaciones == 1
    assert resumen.sesiones == 1
    assert resumen.hay_algo is True
    assert resumen.carpeta == biblioteca_en / "CFA"


def test_resumen_borrado_de_un_proyecto_vacio(
    conn: sqlite3.Connection, biblioteca_en: Path
) -> None:
    servicio = ServicioProyectos(conn)
    resumen = servicio.resumen_borrado(servicio.crear(DatosProyecto(nombre="Vacio")))
    assert resumen.hay_algo is False


def test_eliminar_arrastra_la_cascada_transitiva(conn: sqlite3.Connection) -> None:
    servicio = ServicioProyectos(conn)
    proyecto = servicio.crear(DatosProyecto(nombre="CFA"))
    _poblar(conn, proyecto)

    servicio.eliminar(proyecto.id)

    for tabla in ("proyecto", "materia", "modulo", "documento", "anotacion", "sesion"):
        cuenta = conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
        assert cuenta == 0, f"quedaron filas en {tabla}"


def test_eliminar_no_borra_los_pdf_del_disco(
    conn: sqlite3.Connection, biblioteca_en: Path
) -> None:
    servicio = ServicioProyectos(conn)
    proyecto = servicio.crear(DatosProyecto(nombre="CFA"))
    pdf = _pdf(biblioteca_en / "CFA", "uno.pdf", b"contenido unico")

    servicio.eliminar(proyecto.id)

    assert pdf.is_file()
