"""Preferencias globales y su almacen clave/valor."""

from __future__ import annotations

import sqlite3

from mukuwareru.nucleo.repositorios import RepositorioAjustes, RepositorioProyectos
from mukuwareru.nucleo.servicios import (
    Configuracion,
    DisposicionSecciones,
    Preferencias,
    ServicioPreferencias,
    reconciliar_orden,
)

# Un catalogo de mentira, para que estos tests no se rompan cada vez que la
# interfaz gane o pierda una seccion.
_CATALOGO = ("panel", "pomodoro", "biblioteca", "progreso", "ajustes")


def test_valores_por_defecto(conn: sqlite3.Connection) -> None:
    preferencias = ServicioPreferencias(conn).cargar()
    assert preferencias.pomodoro == Configuracion()
    assert preferencias.preguntar_materia is True


def test_guardar_y_recargar(conn: sqlite3.Connection) -> None:
    servicio = ServicioPreferencias(conn)
    servicio.guardar(
        Preferencias(
            pomodoro=Configuracion(
                trabajo_min=50, descanso_corto_min=10, descanso_largo_min=30,
                sesiones_por_ciclo=3,
            ),
            preguntar_materia=False,
        )
    )
    recargadas = servicio.cargar()
    assert recargadas.pomodoro.trabajo_min == 50
    assert recargadas.pomodoro.sesiones_por_ciclo == 3
    assert recargadas.preguntar_materia is False


def test_guardar_recorta_valores_absurdos(conn: sqlite3.Connection) -> None:
    servicio = ServicioPreferencias(conn)
    servicio.guardar(
        Preferencias(
            pomodoro=Configuracion(trabajo_min=0, descanso_corto_min=9999),
            preguntar_materia=True,
        )
    )
    pomodoro = servicio.cargar().pomodoro
    assert pomodoro.trabajo_min == 1
    assert pomodoro.descanso_corto_min == 60


def test_un_valor_corrupto_cae_al_defecto(conn: sqlite3.Connection) -> None:
    RepositorioAjustes(conn).establecer("pomodoro.trabajo_min", "veinticinco")
    assert ServicioPreferencias(conn).cargar().pomodoro.trabajo_min == 25


def test_guardar_dos_veces_no_duplica(conn: sqlite3.Connection) -> None:
    servicio = ServicioPreferencias(conn)
    for minutos in (30, 45):
        servicio.guardar(
            Preferencias(Configuracion(trabajo_min=minutos), preguntar_materia=True)
        )
    assert servicio.cargar().pomodoro.trabajo_min == 45
    assert conn.execute(
        "SELECT COUNT(*) FROM ajuste WHERE clave = 'pomodoro.trabajo_min'"
    ).fetchone()[0] == 1


# --- Disposicion de la barra lateral ---------------------------------------


def test_reconciliar_respeta_lo_guardado() -> None:
    orden = reconciliar_orden(["ajustes", "pomodoro"], _CATALOGO)
    assert orden[:2] == ("ajustes", "pomodoro")


def test_reconciliar_descarta_claves_desconocidas() -> None:
    """Una seccion retirada entre versiones se ignora, sin migracion."""
    orden = reconciliar_orden(["anotaciones", "pomodoro"], _CATALOGO)
    assert "anotaciones" not in orden
    assert orden[0] == "pomodoro"


def test_reconciliar_anade_las_secciones_nuevas_al_final() -> None:
    """Una seccion nueva aparece sola, visible, sin tocar la preferencia."""
    orden = reconciliar_orden(["ajustes", "panel"], _CATALOGO)
    assert orden == ("ajustes", "panel", "pomodoro", "biblioteca", "progreso")


def test_reconciliar_no_duplica() -> None:
    assert reconciliar_orden(["panel", "panel"], _CATALOGO).count("panel") == 1


def test_reconciliar_sin_nada_guardado_devuelve_el_catalogo() -> None:
    assert reconciliar_orden([], _CATALOGO) == _CATALOGO


def test_la_disposicion_por_defecto_lo_muestra_todo(conn: sqlite3.Connection) -> None:
    disposicion = ServicioPreferencias(conn).disposicion_secciones(_CATALOGO)
    assert disposicion.orden == _CATALOGO
    assert disposicion.visibles == _CATALOGO


def test_guardar_y_recargar_la_disposicion(conn: sqlite3.Connection) -> None:
    servicio = ServicioPreferencias(conn)
    servicio.guardar_disposicion_secciones(
        DisposicionSecciones(
            orden=("pomodoro", "panel", "biblioteca", "progreso", "ajustes"),
            ocultas=frozenset({"progreso"}),
        )
    )
    recargada = servicio.disposicion_secciones(_CATALOGO)
    assert recargada.orden[0] == "pomodoro"
    assert recargada.visibles == ("pomodoro", "panel", "biblioteca", "ajustes")


def test_ajustes_nunca_puede_quedar_oculta(conn: sqlite3.Connection) -> None:
    """Sin Ajustes visible no habria forma de volver a mostrar lo oculto."""
    servicio = ServicioPreferencias(conn)
    servicio.guardar_disposicion_secciones(
        DisposicionSecciones(orden=_CATALOGO, ocultas=frozenset({"ajustes", "panel"}))
    )
    disposicion = servicio.disposicion_secciones(_CATALOGO)
    assert "ajustes" in disposicion.visibles
    assert "panel" not in disposicion.visibles


def test_una_disposicion_corrupta_cae_al_catalogo(conn: sqlite3.Connection) -> None:
    RepositorioAjustes(conn).establecer("interfaz.orden_secciones", " , ,,  ")
    disposicion = ServicioPreferencias(conn).disposicion_secciones(_CATALOGO)
    assert disposicion.orden == _CATALOGO


def test_restablecer_vuelve_al_catalogo(conn: sqlite3.Connection) -> None:
    servicio = ServicioPreferencias(conn)
    servicio.guardar_disposicion_secciones(
        DisposicionSecciones(orden=("ajustes",), ocultas=frozenset({"panel"}))
    )
    servicio.restablecer_disposicion_secciones()
    disposicion = servicio.disposicion_secciones(_CATALOGO)
    assert disposicion.orden == _CATALOGO
    assert disposicion.ocultas == frozenset()


def test_la_disposicion_no_se_pierde_al_guardar_el_pomodoro(
    conn: sqlite3.Connection,
) -> None:
    """El motivo de que la disposicion no sea un campo de ``Preferencias``."""
    servicio = ServicioPreferencias(conn)
    servicio.guardar_disposicion_secciones(
        DisposicionSecciones(orden=("ajustes", "panel"), ocultas=frozenset())
    )
    servicio.guardar(Preferencias(Configuracion(trabajo_min=50), preguntar_materia=True))

    assert servicio.disposicion_secciones(_CATALOGO).orden[0] == "ajustes"


def test_los_ambitos_global_y_por_proyecto_no_se_pisan(conn: sqlite3.Connection) -> None:
    proyecto = RepositorioProyectos(conn).crear("CFA")
    ajustes = RepositorioAjustes(conn)

    ajustes.establecer("nota", "global")
    ajustes.establecer("nota", "del proyecto", proyecto.id)

    assert ajustes.obtener("nota") == "global"
    assert ajustes.obtener("nota", proyecto.id) == "del proyecto"
    assert ajustes.todos() == {"nota": "global"}
    assert ajustes.todos(proyecto.id) == {"nota": "del proyecto"}
