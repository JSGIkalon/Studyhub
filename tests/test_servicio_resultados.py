"""Nota de las evaluaciones: por examen, por asignatura y del proyecto.

Los numeros estan elegidos redondos a proposito, para poder comprobarlos a mano
en el comentario de cada prueba.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from mukuwareru.nucleo.modelos import LineaEvaluacion
from mukuwareru.nucleo.repositorios import RepositorioMaterias, RepositorioProyectos
from mukuwareru.nucleo.servicios import (
    DatosEvaluacion,
    ServicioProgreso,
    ServicioResultados,
)

DIA = date(2026, 9, 14)


@pytest.fixture
def proyecto_id(conn: sqlite3.Connection) -> int:
    """Proyecto con dos asignaturas, ambas sin peso de momento."""
    proyecto = RepositorioProyectos(conn).crear("CFA")
    materias = RepositorioMaterias(conn)
    materias.crear(proyecto.id, "Ethics", orden=0)
    materias.crear(proyecto.id, "Derivatives", orden=1)
    return proyecto.id


@pytest.fixture
def servicio(conn: sqlite3.Connection) -> ServicioResultados:
    return ServicioResultados(conn)


def ids(conn: sqlite3.Connection, proyecto_id: int) -> tuple[int, int]:
    ethics, derivatives = RepositorioMaterias(conn).listar(proyecto_id)
    return ethics.id, derivatives.id


def pesar(conn: sqlite3.Connection, proyecto_id: int, *pesos: float) -> None:
    materias = RepositorioMaterias(conn)
    materias.fijar_pesos(
        proyecto_id,
        {m.id: p for m, p in zip(materias.listar(proyecto_id), pesos, strict=False)},
    )


# --- Estado vacio ----------------------------------------------------------


def test_proyecto_sin_evaluaciones(
    servicio: ServicioResultados, proyecto_id: int
) -> None:
    resumen = servicio.resumen(proyecto_id)
    assert not resumen.hay_evaluaciones
    assert resumen.porcentaje == 0
    assert resumen.porcentaje_ponderado == 0
    assert [a.nombre for a in resumen.asignaturas] == ["Ethics", "Derivatives"]
    assert all(not a.medible for a in resumen.asignaturas)


# --- Nota global -----------------------------------------------------------


def test_porcentaje_de_una_sola_evaluacion(
    servicio: ServicioResultados, proyecto_id: int
) -> None:
    servicio.registrar(proyecto_id, DatosEvaluacion("Mock 1", DIA, 38, 50))
    assert servicio.resumen(proyecto_id).porcentaje == 76


def test_la_nota_global_pondera_por_el_peso_de_la_evaluacion(
    servicio: ServicioResultados, proyecto_id: int
) -> None:
    """30 % de 60 + 70 % de 80 = 18 + 56 = 74."""
    servicio.registrar(proyecto_id, DatosEvaluacion("Parcial", DIA, 6, 10, peso=30))
    servicio.registrar(proyecto_id, DatosEvaluacion("Final", DIA, 8, 10, peso=70))
    assert servicio.resumen(proyecto_id).porcentaje == 74


def test_los_pesos_de_evaluacion_son_relativos(
    servicio: ServicioResultados, proyecto_id: int
) -> None:
    """3 y 7 dicen lo mismo que 30 y 70: se normalizan."""
    servicio.registrar(proyecto_id, DatosEvaluacion("Parcial", DIA, 6, 10, peso=3))
    servicio.registrar(proyecto_id, DatosEvaluacion("Final", DIA, 8, 10, peso=7))
    assert servicio.resumen(proyecto_id).porcentaje == 74


def test_sin_pesos_explicitos_la_media_es_aritmetica(
    servicio: ServicioResultados, proyecto_id: int
) -> None:
    """El peso por defecto es 1, no 0: tres simulacros se promedian solos."""
    for acierto in (6, 8, 10):
        servicio.registrar(proyecto_id, DatosEvaluacion("Mock", DIA, acierto, 10))
    assert servicio.resumen(proyecto_id).porcentaje == 80


def test_todos_los_pesos_a_cero_no_revienta(
    servicio: ServicioResultados, proyecto_id: int
) -> None:
    servicio.registrar(proyecto_id, DatosEvaluacion("Uno", DIA, 6, 10, peso=0))
    servicio.registrar(proyecto_id, DatosEvaluacion("Dos", DIA, 8, 10, peso=0))
    assert servicio.resumen(proyecto_id).porcentaje == 70


def test_decimales_no_enteros(servicio: ServicioResultados, proyecto_id: int) -> None:
    servicio.registrar(proyecto_id, DatosEvaluacion("Parcial", DIA, 8.5, 10))
    servicio.registrar(proyecto_id, DatosEvaluacion("Otro", DIA, 4.2, 5))
    # (85 + 84) / 2 = 84,5 -> 84 por redondeo bancario de Python.
    assert servicio.resumen(proyecto_id).porcentaje == 84


# --- Nota por asignatura ---------------------------------------------------


def test_la_nota_de_asignatura_sale_solo_de_su_desglose(
    conn: sqlite3.Connection, servicio: ServicioResultados, proyecto_id: int
) -> None:
    ethics, derivatives = ids(conn, proyecto_id)
    servicio.registrar(
        proyecto_id,
        DatosEvaluacion(
            "Mock", DIA, 38, 50,
            materias=(LineaEvaluacion(ethics, 20, 25), LineaEvaluacion(derivatives, 18, 25)),
        ),
    )

    notas = {a.nombre: a.porcentaje for a in servicio.resumen(proyecto_id).asignaturas}
    assert notas == {"Ethics": 80, "Derivatives": 72}


def test_la_asignatura_pondera_por_el_peso_de_cada_evaluacion(
    conn: sqlite3.Connection, servicio: ServicioResultados, proyecto_id: int
) -> None:
    """El caso del master: 30 % parcial al 60 % + 70 % final al 80 % = 74 %."""
    ethics, _ = ids(conn, proyecto_id)
    servicio.registrar(
        proyecto_id,
        DatosEvaluacion(
            "Parcial", DIA, 6, 10, peso=30, materias=(LineaEvaluacion(ethics, 6, 10),)
        ),
    )
    servicio.registrar(
        proyecto_id,
        DatosEvaluacion(
            "Final", DIA, 8, 10, peso=70, materias=(LineaEvaluacion(ethics, 8, 10),)
        ),
    )

    asignatura = next(
        a for a in servicio.resumen(proyecto_id).asignaturas if a.nombre == "Ethics"
    )
    assert asignatura.porcentaje == 74
    assert asignatura.evaluaciones == 2


def test_una_evaluacion_sin_desglose_no_cuenta_en_ninguna_asignatura(
    servicio: ServicioResultados, proyecto_id: int
) -> None:
    servicio.registrar(proyecto_id, DatosEvaluacion("Solo total", DIA, 38, 50))
    resumen = servicio.resumen(proyecto_id)

    assert resumen.porcentaje == 76
    assert all(not a.medible for a in resumen.asignaturas)
    assert [e.titulo for e in resumen.sin_desglose] == ["Solo total"]


def test_las_asignaturas_respetan_el_orden_del_temario(
    servicio: ServicioResultados, proyecto_id: int
) -> None:
    assert [a.nombre for a in servicio.resumen(proyecto_id).asignaturas] == [
        "Ethics",
        "Derivatives",
    ]


# --- Nota del proyecto, ponderada por materia.peso -------------------------


def test_sin_pesos_de_materia_el_ponderado_es_la_nota_global(
    conn: sqlite3.Connection, servicio: ServicioResultados, proyecto_id: int
) -> None:
    ethics, derivatives = ids(conn, proyecto_id)
    servicio.registrar(
        proyecto_id,
        DatosEvaluacion(
            "Mock", DIA, 38, 50,
            materias=(LineaEvaluacion(ethics, 20, 25), LineaEvaluacion(derivatives, 18, 25)),
        ),
    )

    resumen = servicio.resumen(proyecto_id)
    assert not resumen.hay_pesos
    assert resumen.porcentaje_ponderado == resumen.porcentaje == 76


def test_el_peso_de_materia_cambia_el_ponderado_y_no_la_nota_global(
    conn: sqlite3.Connection, servicio: ServicioResultados, proyecto_id: int
) -> None:
    """Ethics al 80 % pesando 3, Derivatives al 40 % pesando 1 -> 70 %."""
    ethics, derivatives = ids(conn, proyecto_id)
    pesar(conn, proyecto_id, 3.0, 1.0)
    servicio.registrar(
        proyecto_id,
        DatosEvaluacion(
            "Mock", DIA, 12, 20,
            materias=(LineaEvaluacion(ethics, 8, 10), LineaEvaluacion(derivatives, 4, 10)),
        ),
    )

    resumen = servicio.resumen(proyecto_id)
    assert resumen.porcentaje == 60             # 12 de 20 en global
    assert resumen.porcentaje_ponderado == 70   # 0,75 x 80 + 0,25 x 40
    assert resumen.hay_pesos


def test_una_asignatura_pesada_sin_evaluar_no_hunde_el_ponderado(
    conn: sqlite3.Connection, servicio: ServicioResultados, proyecto_id: int
) -> None:
    """Sin nota no hay nada que medir; contarla como cero fijaria un techo."""
    ethics, _ = ids(conn, proyecto_id)
    pesar(conn, proyecto_id, 3.0, 9.0)
    servicio.registrar(
        proyecto_id,
        DatosEvaluacion("Mock", DIA, 8, 10, materias=(LineaEvaluacion(ethics, 8, 10),)),
    )

    resumen = servicio.resumen(proyecto_id)
    assert resumen.porcentaje_ponderado == 80
    assert [a.nombre for a in resumen.pesadas_sin_evaluar] == ["Derivatives"]


def test_la_cuota_reparte_cien_entre_las_asignaturas(
    conn: sqlite3.Connection, servicio: ServicioResultados, proyecto_id: int
) -> None:
    pesar(conn, proyecto_id, 3.0, 1.0)
    resumen = servicio.resumen(proyecto_id)
    cuotas = {a.nombre: resumen.cuota(a) for a in resumen.asignaturas}
    assert cuotas == {"Ethics": 75.0, "Derivatives": 25.0}


# --- Edicion ---------------------------------------------------------------


def test_editar_rehace_el_desglose(
    conn: sqlite3.Connection, servicio: ServicioResultados, proyecto_id: int
) -> None:
    ethics, derivatives = ids(conn, proyecto_id)
    creada = servicio.registrar(
        proyecto_id,
        DatosEvaluacion("Mock", DIA, 38, 50, materias=(LineaEvaluacion(ethics, 20, 25),)),
    )

    servicio.editar(
        creada.id,
        DatosEvaluacion(
            "Mock corregido", DIA, 40, 50,
            materias=(LineaEvaluacion(derivatives, 18, 25),),
        ),
    )

    resumen = servicio.resumen(proyecto_id)
    assert resumen.evaluaciones[0].titulo == "Mock corregido"
    assert resumen.porcentaje == 80
    medibles = [a.nombre for a in resumen.asignaturas if a.medible]
    assert medibles == ["Derivatives"]


def test_registrar_descarta_una_materia_de_otro_proyecto(
    conn: sqlite3.Connection, servicio: ServicioResultados, proyecto_id: int
) -> None:
    ajeno = RepositorioProyectos(conn).crear("MSc")
    intrusa = RepositorioMaterias(conn).crear(ajeno.id, "Econometria")

    creada = servicio.registrar(
        proyecto_id,
        DatosEvaluacion("Mock", DIA, 38, 50, materias=(LineaEvaluacion(intrusa.id, 5, 10),)),
    )
    assert creada.materias == []


def test_eliminar_quita_la_evaluacion(
    servicio: ServicioResultados, proyecto_id: int
) -> None:
    creada = servicio.registrar(proyecto_id, DatosEvaluacion("Mock", DIA, 38, 50))
    servicio.eliminar(creada.id)
    assert not servicio.resumen(proyecto_id).hay_evaluaciones


# --- Evolucion y frontera con el progreso ----------------------------------


def test_evolucion_va_en_orden_cronologico(
    servicio: ServicioResultados, proyecto_id: int
) -> None:
    servicio.registrar(proyecto_id, DatosEvaluacion("Dos", date(2026, 6, 1), 7, 10))
    servicio.registrar(proyecto_id, DatosEvaluacion("Uno", date(2026, 3, 1), 5, 10))
    servicio.registrar(proyecto_id, DatosEvaluacion("Tres", date(2026, 9, 1), 9, 10))

    assert servicio.evolucion(proyecto_id) == (
        (date(2026, 3, 1), 50),
        (date(2026, 6, 1), 70),
        (date(2026, 9, 1), 90),
    )


def test_los_resultados_no_alteran_el_progreso(
    conn: sqlite3.Connection, servicio: ServicioResultados, proyecto_id: int
) -> None:
    """Progreso mide temario cubierto; esto mide rendimiento. Dos ejes."""
    from mukuwareru.nucleo.repositorios import RepositorioModulos

    ethics, _ = ids(conn, proyecto_id)
    RepositorioModulos(conn).crear(ethics, "Code of Ethics")
    antes = ServicioProgreso(conn).resumen(proyecto_id)

    servicio.registrar(
        proyecto_id,
        DatosEvaluacion("Mock", DIA, 38, 50, materias=(LineaEvaluacion(ethics, 20, 25),)),
    )

    despues = ServicioProgreso(conn).resumen(proyecto_id)
    assert (despues.total, despues.completados) == (antes.total, antes.completados)
    assert despues.porcentaje == antes.porcentaje == 0


def test_cuadra_detecta_un_desglose_que_no_suma(
    conn: sqlite3.Connection, servicio: ServicioResultados, proyecto_id: int
) -> None:
    ethics, derivatives = ids(conn, proyecto_id)
    cuadrada = servicio.registrar(
        proyecto_id,
        DatosEvaluacion(
            "Cuadra", DIA, 38, 50,
            materias=(LineaEvaluacion(ethics, 20, 25), LineaEvaluacion(derivatives, 18, 25)),
        ),
    )
    torcida = servicio.registrar(
        proyecto_id,
        DatosEvaluacion(
            "No cuadra", DIA, 45, 50, materias=(LineaEvaluacion(ethics, 20, 25),)
        ),
    )

    assert cuadrada.cuadra
    assert not torcida.cuadra
    # Un desglose que no cuadra se guarda igual: avisar, no impedir.
    assert servicio.resumen(proyecto_id).hay_evaluaciones
