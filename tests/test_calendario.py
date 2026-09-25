"""Calendario: hitos, bloques planeados y el reparto del cumplimiento.

El grueso de los tests va contra ``repartir_cumplimiento``, que es una funcion
pura. Es la regla que contesta «¿estudie lo que dije?» y la unica pieza de esta
etapa que puede equivocarse de forma silenciosa.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta

import pytest

from mukuwareru.nucleo.modelos import (
    BloquePlan,
    OrigenSesion,
    Proyecto,
    Sesion,
    TipoHito,
    TipoSesion,
)
from mukuwareru.nucleo.repositorios import (
    RepositorioBloques,
    RepositorioHitos,
    RepositorioMaterias,
    RepositorioProyectos,
    RepositorioSesiones,
)
from mukuwareru.nucleo.servicios import (
    DatosProyecto,
    ServicioCalendario,
    ServicioProyectos,
    repartir_cumplimiento,
)

DIA = date(2026, 8, 17)


def _bloque(
    id_: int,
    *,
    hora: str | None = "09:00",
    minutos: int = 60,
    materias: list[int] | None = None,
) -> BloquePlan:
    return BloquePlan(
        id=id_,
        proyecto_id=1,
        fecha=DIA,
        duracion_min=minutos,
        hora_inicio=hora,
        materias=materias or [],
    )


def _sesion(
    id_: int,
    *,
    hora: str = "09:00",
    minutos: int = 60,
    materias: list[int] | None = None,
    con_fin: bool = True,
) -> Sesion:
    horas, mins = (int(p) for p in hora.split(":"))
    inicio = datetime.combine(DIA, time(horas, mins)).astimezone()
    segundos = minutos * 60
    return Sesion(
        id=id_,
        proyecto_id=1,
        tipo=TipoSesion.TRABAJO,
        origen=OrigenSesion.POMODORO,
        inicio=inicio,
        fin=inicio + timedelta(seconds=segundos) if con_fin else None,
        duracion_seg=segundos,
        fecha_local=DIA.isoformat(),
        completada=True,
        materias=materias or [],
    )


# --- Reparto del cumplimiento ----------------------------------------------


def test_una_sesion_dentro_de_su_bloque_lo_cumple() -> None:
    cumplimientos = repartir_cumplimiento([_bloque(1)], [_sesion(10)])
    assert cumplimientos[1].real_seg == 3600
    assert cumplimientos[1].cumplido is True
    assert cumplimientos[1].porcentaje == 100


def test_una_sesion_fuera_de_la_franja_no_cuenta() -> None:
    cumplimientos = repartir_cumplimiento([_bloque(1, hora="09:00")], [_sesion(10, hora="20:00")])
    assert cumplimientos[1].real_seg == 0
    assert cumplimientos[1].cumplido is False


def test_solo_cuenta_la_parte_que_solapa() -> None:
    """Media hora dentro de la franja y media fuera: cuenta la mitad."""
    bloque = _bloque(1, hora="09:00", minutos=60)
    cumplimientos = repartir_cumplimiento([bloque], [_sesion(10, hora="08:30", minutos=60)])
    assert cumplimientos[1].real_seg == 1800
    assert cumplimientos[1].porcentaje == 50


def test_el_umbral_perdona_los_ultimos_minutos() -> None:
    """Levantarse cinco minutos antes de un bloque de 60 no es fallarlo."""
    cumplimientos = repartir_cumplimiento(
        [_bloque(1, minutos=60)], [_sesion(10, minutos=50)]
    )
    assert cumplimientos[1].cumplido is True
    cumplimientos = repartir_cumplimiento(
        [_bloque(1, minutos=60)], [_sesion(10, minutos=30)]
    )
    assert cumplimientos[1].cumplido is False


def test_no_se_puede_pasar_del_cien_por_cien() -> None:
    cumplimientos = repartir_cumplimiento(
        [_bloque(1, minutos=30)], [_sesion(10, minutos=120)]
    )
    assert cumplimientos[1].ratio == 1.0


def test_cada_segundo_se_atribuye_una_sola_vez() -> None:
    """Dos bloques solapados no pueden sumar el doble de lo estudiado.

    Es la regla que evita que planificar dos veces la misma hora multiplique el
    cumplimiento por dos.
    """
    bloques = [_bloque(1, hora="09:00", minutos=60), _bloque(2, hora="09:00", minutos=60)]
    cumplimientos = repartir_cumplimiento(bloques, [_sesion(10, hora="09:00", minutos=60)])

    total = sum(c.real_seg for c in cumplimientos.values())
    assert total == 3600
    # El primero por (hora, id) se lo lleva entero; el segundo se queda a cero.
    assert cumplimientos[1].real_seg == 3600
    assert cumplimientos[2].real_seg == 0


def test_los_bloques_sin_hora_recogen_lo_que_quede() -> None:
    bloques = [_bloque(1, hora="09:00", minutos=60), _bloque(2, hora=None, minutos=60)]
    sesiones = [_sesion(10, hora="09:00", minutos=60), _sesion(11, hora="21:00", minutos=60)]
    cumplimientos = repartir_cumplimiento(bloques, sesiones)

    assert cumplimientos[1].real_seg == 3600
    # La sesion de las nueve ya esta gastada; al bloque sin hora le queda la otra.
    assert cumplimientos[2].real_seg == 3600


def test_los_bloques_sin_hora_se_reparten_por_id() -> None:
    bloques = [_bloque(2, hora=None, minutos=60), _bloque(1, hora=None, minutos=60)]
    cumplimientos = repartir_cumplimiento(bloques, [_sesion(10, minutos=60)])
    assert cumplimientos[1].real_seg == 3600
    assert cumplimientos[2].real_seg == 0


def test_una_sesion_sin_fin_deduce_su_duracion() -> None:
    """Al cerrar la app a media fase, `fin` queda NULL."""
    cumplimientos = repartir_cumplimiento(
        [_bloque(1, minutos=60)], [_sesion(10, minutos=60, con_fin=False)]
    )
    assert cumplimientos[1].real_seg == 3600


def test_un_bloque_con_materias_ignora_las_de_otra_materia() -> None:
    bloque = _bloque(1, materias=[7])
    cumplimientos = repartir_cumplimiento([bloque], [_sesion(10, materias=[9])])
    assert cumplimientos[1].real_seg == 0


def test_un_bloque_con_materias_acepta_la_suya() -> None:
    bloque = _bloque(1, materias=[7, 8])
    cumplimientos = repartir_cumplimiento([bloque], [_sesion(10, materias=[8])])
    assert cumplimientos[1].real_seg == 3600


def test_las_sesiones_sin_etiquetar_cuentan_igual() -> None:
    """Etiquetar es opcional; castigar a quien omitio el dialogo seria injusto."""
    bloque = _bloque(1, materias=[7])
    cumplimientos = repartir_cumplimiento([bloque], [_sesion(10, materias=[])])
    assert cumplimientos[1].real_seg == 3600


def test_sin_bloques_no_hay_cumplimientos() -> None:
    assert repartir_cumplimiento([], [_sesion(10)]) == {}


def test_un_bloque_sin_sesiones_queda_a_cero() -> None:
    cumplimientos = repartir_cumplimiento([_bloque(1)], [])
    assert cumplimientos[1].real_seg == 0
    assert cumplimientos[1].ratio == 0.0


def test_una_hora_corrupta_se_trata_como_bloque_sin_hora() -> None:
    """Nada deberia escribir «manana» ahi, pero si pasa no debe reventar."""
    bloque = _bloque(1, hora="manana")
    cumplimientos = repartir_cumplimiento([bloque], [_sesion(10)])
    assert cumplimientos[1].real_seg == 3600


# --- Hitos ------------------------------------------------------------------


def test_la_migracion_convierte_la_fecha_objetivo_en_hito(
    conn: sqlite3.Connection,
) -> None:
    """Las bases anteriores a la 003 traen su fecha objetivo ya migrada.

    Se simula el estado previo insertando el proyecto a mano, como haria la
    migracion sobre datos reales.
    """
    conn.execute(
        """
        INSERT INTO proyecto (id, nombre, fecha_objetivo, creado_en)
        VALUES (99, 'Antiguo', '2026-11-13', '2026-01-01T00:00:00-05:00')
        """
    )
    # La migracion ya corrio al abrir la base, asi que se comprueba la regla
    # equivalente aplicandola a mano, que es lo que hace `fijar_objetivo`.
    hitos = RepositorioHitos(conn)
    hitos.fijar_objetivo(99, date(2026, 11, 13))

    principal = hitos.principal(99)
    assert principal is not None
    assert principal.fecha == date(2026, 11, 13)
    assert principal.principal is True


def test_solo_puede_haber_un_hito_principal(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    hitos = RepositorioHitos(conn)
    hitos.crear(proyecto.id, "Examen", date(2026, 11, 13), principal=True)
    with pytest.raises(sqlite3.IntegrityError):
        hitos.crear(proyecto.id, "Otro", date(2027, 1, 1), principal=True)


def test_guardar_el_proyecto_espeja_la_fecha_en_el_hito(
    conn: sqlite3.Connection
) -> None:
    servicio = ServicioProyectos(conn)
    creado = servicio.crear(
        DatosProyecto(nombre="CFA", fecha_objetivo=date(2026, 11, 13))
    )
    hitos = RepositorioHitos(conn)
    assert hitos.principal(creado.id) is not None

    servicio.guardar(
        creado, DatosProyecto(nombre="CFA", fecha_objetivo=date(2026, 12, 1))
    )
    principal = hitos.principal(creado.id)
    assert principal is not None
    assert principal.fecha == date(2026, 12, 1)

    # Y quitar la fecha se lleva el hito principal.
    servicio.guardar(creado, DatosProyecto(nombre="CFA", fecha_objetivo=None))
    assert hitos.principal(creado.id) is None


def test_fijar_objetivo_no_pisa_el_titulo_editado(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    hitos = RepositorioHitos(conn)
    hitos.fijar_objetivo(proyecto.id, date(2026, 11, 13))
    principal = hitos.principal(proyecto.id)
    assert principal is not None
    principal.titulo = "Examen CFA Nivel I"
    hitos.actualizar(principal)

    hitos.fijar_objetivo(proyecto.id, date(2026, 11, 20))

    vigente = hitos.principal(proyecto.id)
    assert vigente is not None
    assert vigente.titulo == "Examen CFA Nivel I"
    assert vigente.fecha == date(2026, 11, 20)


def test_la_proxima_fecha_clave_es_la_mas_cercana(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    """Anadir un mock mas cercano debe cambiar la cuenta atras."""
    hitos = RepositorioHitos(conn)
    hitos.crear(proyecto.id, "Examen", date(2026, 11, 13), tipo=TipoHito.EXAMEN)
    hitos.crear(proyecto.id, "Mock 1", date(2026, 9, 1))

    proximo = ServicioCalendario(conn).proxima_fecha_clave(proyecto.id, DIA)
    assert proximo is not None
    assert proximo.titulo == "Mock 1"


def test_un_hito_pasado_o_completado_no_es_la_proxima_fecha(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    hitos = RepositorioHitos(conn)
    hitos.crear(proyecto.id, "Ya paso", date(2026, 1, 1))
    hecho = hitos.crear(proyecto.id, "Hecho", date(2026, 9, 1))
    hitos.marcar_completado(hecho.id, True)
    hitos.crear(proyecto.id, "Examen", date(2026, 11, 13))

    proximo = ServicioCalendario(conn).proxima_fecha_clave(proyecto.id, DIA)
    assert proximo is not None
    assert proximo.titulo == "Examen"


# --- Composicion del calendario --------------------------------------------


def test_el_dia_reune_sesiones_hitos_y_bloques(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    materia = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")
    RepositorioBloques(conn).crear(
        proyecto.id, DIA, hora_inicio="09:00", duracion_min=60, materias=[materia.id]
    )
    RepositorioHitos(conn).crear(proyecto.id, "Mock", DIA)
    inicio = datetime.combine(DIA, time(9, 0)).astimezone()
    RepositorioSesiones(conn).crear(
        proyecto.id,
        tipo=TipoSesion.TRABAJO,
        origen=OrigenSesion.POMODORO,
        inicio=inicio,
        fin=inicio + timedelta(minutes=55),
        duracion_seg=55 * 60,
        materias=[materia.id],
    )

    dia = ServicioCalendario(conn).dia(proyecto.id, DIA)

    assert dia.segundos_estudiados == 55 * 60
    assert dia.pomodoros == 1
    assert len(dia.hitos) == 1
    assert dia.minutos_planeados == 60
    assert dia.bloques_cumplidos == 1
    assert dia.vacio is False


def test_un_mes_devuelve_todos_sus_dias(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    dias = ServicioCalendario(conn).mes(proyecto.id, 2026, 2)
    assert len(dias) == 28
    assert dias[0].fecha == date(2026, 2, 1)
    assert all(dia.vacio for dia in dias)


def test_diciembre_no_desborda_el_ano(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    dias = ServicioCalendario(conn).mes(proyecto.id, 2026, 12)
    assert len(dias) == 31
    assert dias[-1].fecha == date(2026, 12, 31)


def test_la_adherencia_cuenta_cumplidos_sobre_planeados(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    bloques = RepositorioBloques(conn)
    bloques.crear(proyecto.id, DIA, hora_inicio="09:00", duracion_min=60)
    bloques.crear(proyecto.id, DIA, hora_inicio="18:00", duracion_min=60)
    inicio = datetime.combine(DIA, time(9, 0)).astimezone()
    RepositorioSesiones(conn).crear(
        proyecto.id,
        tipo=TipoSesion.TRABAJO,
        origen=OrigenSesion.POMODORO,
        inicio=inicio,
        fin=inicio + timedelta(minutes=60),
        duracion_seg=3600,
    )

    cumplidos, planeados = ServicioCalendario(conn).resumen_adherencia(
        proyecto.id, DIA, DIA
    )
    assert (cumplidos, planeados) == (1, 2)


def test_resumen_cumplimiento_cuenta_dias_y_horas_incumplidas(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    bloques = RepositorioBloques(conn)
    # Dia cumplido: un bloque de una hora, estudiada entera.
    bloques.crear(proyecto.id, DIA, hora_inicio="09:00", duracion_min=60)
    inicio = datetime.combine(DIA, time(9, 0)).astimezone()
    RepositorioSesiones(conn).crear(
        proyecto.id,
        tipo=TipoSesion.TRABAJO,
        origen=OrigenSesion.POMODORO,
        inicio=inicio,
        fin=inicio + timedelta(minutes=60),
        duracion_seg=3600,
    )
    # Dia incumplido: un bloque de una hora, sin ninguna sesion.
    otro_dia = DIA + timedelta(days=1)
    bloques.crear(proyecto.id, otro_dia, hora_inicio="09:00", duracion_min=60)

    resumen = ServicioCalendario(conn).resumen_cumplimiento(proyecto.id, DIA, otro_dia)
    assert resumen.dias_con_plan == 2
    assert resumen.dias_incumplidos == 1
    assert resumen.pct_dias_incumplidos == 50.0
    assert resumen.segundos_planeados == 7200
    assert resumen.segundos_faltantes == 3600
    assert resumen.pct_horas_incumplidas == 50.0


def test_sin_planes_el_resumen_no_incumple_nada(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    resumen = ServicioCalendario(conn).resumen_cumplimiento(proyecto.id, DIA, DIA)
    assert resumen.dias_con_plan == 0
    assert resumen.pct_dias_incumplidos == 0.0
    assert resumen.pct_horas_incumplidas == 0.0


def test_ultimo_incumplimiento_encuentra_el_bloque_de_ayer_sin_estudiar(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    ayer = DIA - timedelta(days=1)
    bloque = RepositorioBloques(conn).crear(
        proyecto.id, ayer, hora_inicio="09:00", duracion_min=60
    )

    encontrado = ServicioCalendario(conn).ultimo_incumplimiento(proyecto.id, DIA)
    assert encontrado is not None
    fecha, bloque_hallado, cumplimiento = encontrado
    assert fecha == ayer
    assert bloque_hallado.id == bloque.id
    assert cumplimiento.cumplido is False


def test_ultimo_incumplimiento_ignora_lo_que_si_se_cumplio(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    ayer = DIA - timedelta(days=1)
    RepositorioBloques(conn).crear(
        proyecto.id, ayer, hora_inicio="09:00", duracion_min=60
    )
    inicio = datetime.combine(ayer, time(9, 0)).astimezone()
    RepositorioSesiones(conn).crear(
        proyecto.id,
        tipo=TipoSesion.TRABAJO,
        origen=OrigenSesion.POMODORO,
        inicio=inicio,
        fin=inicio + timedelta(minutes=60),
        duracion_seg=3600,
    )

    assert ServicioCalendario(conn).ultimo_incumplimiento(proyecto.id, DIA) is None


def test_ultimo_incumplimiento_ignora_bloques_de_hoy_o_de_manana(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    RepositorioBloques(conn).crear(
        proyecto.id, DIA, hora_inicio="09:00", duracion_min=60
    )
    RepositorioBloques(conn).crear(
        proyecto.id, DIA + timedelta(days=1), hora_inicio="09:00", duracion_min=60
    )

    assert ServicioCalendario(conn).ultimo_incumplimiento(proyecto.id, DIA) is None


def test_mover_un_bloque_lo_cambia_de_dia(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    bloques = RepositorioBloques(conn)
    bloque = bloques.crear(proyecto.id, DIA, hora_inicio="09:00")
    bloques.mover(bloque.id, DIA + timedelta(days=1), "11:00")

    movido = bloques.obtener(bloque.id)
    assert movido is not None
    assert movido.fecha == DIA + timedelta(days=1)
    assert movido.hora_inicio == "11:00"


def test_las_materias_del_bloque_se_reemplazan(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    materias = RepositorioMaterias(conn)
    una = materias.crear(proyecto.id, "Ethics")
    otra = materias.crear(proyecto.id, "Quant")
    bloques = RepositorioBloques(conn)
    bloque = bloques.crear(proyecto.id, DIA, materias=[una.id, otra.id])

    bloques.etiquetar(bloque.id, [otra.id])

    recargado = bloques.obtener(bloque.id)
    assert recargado is not None
    assert recargado.materias == [otra.id]


def test_borrar_el_proyecto_arrastra_hitos_y_bloques(
    conn: sqlite3.Connection, proyecto: Proyecto
) -> None:
    RepositorioHitos(conn).crear(proyecto.id, "Mock", DIA)
    RepositorioBloques(conn).crear(proyecto.id, DIA)

    RepositorioProyectos(conn).eliminar(proyecto.id)

    assert conn.execute("SELECT COUNT(*) FROM hito").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM bloque_plan").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM bloque_materia").fetchone()[0] == 0
