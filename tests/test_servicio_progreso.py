"""Servicio de progreso del temario."""

from __future__ import annotations

import sqlite3

import pytest

from mukuwareru.nucleo.repositorios import (
    RepositorioMaterias,
    RepositorioModulos,
    RepositorioProyectos,
)
from mukuwareru.nucleo.servicios import PESOS_CFA_NIVEL_I, ServicioProgreso


@pytest.fixture
def temario(conn: sqlite3.Connection) -> int:
    """Proyecto con dos materias: 2 de 3 modulos y 0 de 2."""
    proyecto = RepositorioProyectos(conn).crear("CFA")
    materias = RepositorioMaterias(conn)
    modulos = RepositorioModulos(conn)

    quant = materias.crear(proyecto.id, "Quantitative Methods", orden=0)
    for nombre, hecho in [("Uno", True), ("Dos", True), ("Tres", False)]:
        modulos.crear(quant.id, nombre, completado=hecho)

    ethics = materias.crear(proyecto.id, "Ethics", orden=1)
    for nombre in ("Code", "Guidance"):
        modulos.crear(ethics.id, nombre)

    return proyecto.id


def test_resumen_global(conn: sqlite3.Connection, temario: int) -> None:
    resumen = ServicioProgreso(conn).resumen(temario)
    assert (resumen.total, resumen.completados, resumen.pendientes) == (5, 2, 3)
    assert resumen.porcentaje == 40


def test_resumen_por_materia(conn: sqlite3.Connection, temario: int) -> None:
    resumen = ServicioProgreso(conn).resumen(temario)
    porcentajes = {m.nombre: m.porcentaje for m in resumen.materias}
    assert porcentajes == {"Quantitative Methods": 67, "Ethics": 0}


def test_las_materias_respetan_su_orden(conn: sqlite3.Connection, temario: int) -> None:
    resumen = ServicioProgreso(conn).resumen(temario)
    assert [m.nombre for m in resumen.materias] == ["Quantitative Methods", "Ethics"]


def test_marcar_cambia_el_porcentaje(conn: sqlite3.Connection, temario: int) -> None:
    servicio = ServicioProgreso(conn)
    pendiente = next(
        m
        for materia in RepositorioMaterias(conn).listar(temario)
        for m in RepositorioModulos(conn).listar(materia.id)
        if not m.completado
    )
    servicio.marcar(pendiente.id, True)
    assert servicio.resumen(temario).completados == 3


def test_marcar_registra_la_fecha(conn: sqlite3.Connection, temario: int) -> None:
    modulos = RepositorioModulos(conn)
    materia = RepositorioMaterias(conn).listar(temario)[1]
    modulo = modulos.listar(materia.id)[0]

    modulos.marcar(modulo.id, True)
    assert modulos.listar(materia.id)[0].completado_en is not None

    modulos.marcar(modulo.id, False)
    assert modulos.listar(materia.id)[0].completado_en is None


def test_una_materia_sin_modulos_sigue_apareciendo(
    conn: sqlite3.Connection, temario: int
) -> None:
    RepositorioMaterias(conn).crear(temario, "Derivatives", orden=2)
    resumen = ServicioProgreso(conn).resumen(temario)
    vacia = next(m for m in resumen.materias if m.nombre == "Derivatives")
    assert (vacia.total, vacia.porcentaje) == (0, 0)


def test_proyecto_sin_temario(conn: sqlite3.Connection) -> None:
    proyecto = RepositorioProyectos(conn).crear("Vacio")
    resumen = ServicioProgreso(conn).resumen(proyecto.id)
    assert (resumen.total, resumen.porcentaje, resumen.materias) == (0, 0, ())


# -- Pesos por asignatura ----------------------------------------------------


def test_sin_pesos_el_ponderado_es_el_conteo(
    conn: sqlite3.Connection, temario: int
) -> None:
    resumen = ServicioProgreso(conn).resumen(temario)
    assert not resumen.hay_pesos
    assert resumen.porcentaje_ponderado == resumen.porcentaje == 40


def test_el_peso_cambia_el_ponderado_y_no_el_conteo(
    conn: sqlite3.Connection, temario: int
) -> None:
    servicio = ServicioProgreso(conn)
    quant, ethics = RepositorioMaterias(conn).listar(temario)

    # Quant va al 2/3 y pesa el triple que Ethics, que va a cero.
    servicio.fijar_pesos(temario, {quant.id: 3.0, ethics.id: 1.0})
    resumen = servicio.resumen(temario)

    assert resumen.porcentaje == 40                      # 2 de 5 modulos
    assert resumen.porcentaje_ponderado == 50            # 3/4 x 2/3 + 1/4 x 0
    assert resumen.hay_pesos


def test_los_pesos_son_relativos(conn: sqlite3.Connection, temario: int) -> None:
    """Multiplicar todos los pesos por lo mismo no cambia nada: se normalizan."""
    servicio = ServicioProgreso(conn)
    quant, ethics = RepositorioMaterias(conn).listar(temario)

    servicio.fijar_pesos(temario, {quant.id: 3.0, ethics.id: 1.0})
    con_enteros = servicio.resumen(temario).porcentaje_ponderado

    servicio.fijar_pesos(temario, {quant.id: 75.0, ethics.id: 25.0})
    assert servicio.resumen(temario).porcentaje_ponderado == con_enteros


def test_la_cuota_reparte_cien_entre_las_materias(
    conn: sqlite3.Connection, temario: int
) -> None:
    servicio = ServicioProgreso(conn)
    quant, ethics = RepositorioMaterias(conn).listar(temario)
    servicio.fijar_pesos(temario, {quant.id: 3.0, ethics.id: 1.0})

    resumen = servicio.resumen(temario)
    cuotas = {m.nombre: resumen.cuota(m) for m in resumen.materias}
    assert cuotas == {"Quantitative Methods": 75.0, "Ethics": 25.0}


def test_una_materia_pesada_sin_modulos_no_hunde_el_ponderado(
    conn: sqlite3.Connection, temario: int
) -> None:
    """Sin modulos no hay nada que medir: contarla como cero fijaria un techo."""
    servicio = ServicioProgreso(conn)
    quant, ethics = RepositorioMaterias(conn).listar(temario)
    vacia = RepositorioMaterias(conn).crear(temario, "Derivatives", orden=2)

    servicio.fijar_pesos(temario, {quant.id: 3.0, ethics.id: 1.0, vacia.id: 6.0})
    resumen = servicio.resumen(temario)

    assert resumen.porcentaje_ponderado == 50
    assert [m.nombre for m in resumen.pesadas_sin_temario] == ["Derivatives"]


def test_marcarlo_todo_da_cien_por_ciento_ponderado(
    conn: sqlite3.Connection, temario: int
) -> None:
    servicio = ServicioProgreso(conn)
    materias = RepositorioMaterias(conn)
    quant, ethics = materias.listar(temario)
    servicio.fijar_pesos(temario, {quant.id: 17.1, ethics.id: 6.3})

    for materia in materias.listar(temario):
        for modulo in RepositorioModulos(conn).listar(materia.id):
            servicio.marcar(modulo.id, True)

    assert servicio.resumen(temario).porcentaje_ponderado == 100


def test_limpiar_pesos_vuelve_al_conteo(conn: sqlite3.Connection, temario: int) -> None:
    servicio = ServicioProgreso(conn)
    quant, ethics = RepositorioMaterias(conn).listar(temario)
    servicio.fijar_pesos(temario, {quant.id: 3.0, ethics.id: 1.0})

    servicio.limpiar_pesos(temario)
    resumen = servicio.resumen(temario)
    assert not resumen.hay_pesos
    assert resumen.porcentaje_ponderado == 40


def test_un_peso_negativo_se_guarda_como_cero(
    conn: sqlite3.Connection, temario: int
) -> None:
    servicio = ServicioProgreso(conn)
    quant, _ = RepositorioMaterias(conn).listar(temario)
    servicio.fijar_pesos(temario, {quant.id: -5.0})
    assert RepositorioMaterias(conn).obtener(quant.id).peso == 0.0


def test_los_pesos_no_saltan_de_proyecto(conn: sqlite3.Connection, temario: int) -> None:
    ajeno = RepositorioProyectos(conn).crear("MSc")
    suya = RepositorioMaterias(conn).crear(ajeno.id, "Econometria")

    ServicioProgreso(conn).fijar_pesos(temario, {suya.id: 40.0})
    assert RepositorioMaterias(conn).obtener(suya.id).peso == 0.0


# -- Preset del CFA ----------------------------------------------------------


def test_los_pesos_del_cfa_suman_cien() -> None:
    assert round(sum(PESOS_CFA_NIVEL_I.values()), 6) == 100.0


def test_propuesta_cfa_reconoce_los_nombres_del_temario(
    conn: sqlite3.Connection,
) -> None:
    """El Excel dice «Ethics» o «FSA», no el titulo largo del curriculo."""
    proyecto = RepositorioProyectos(conn).crear("CFA")
    materias = RepositorioMaterias(conn)
    ethics = materias.crear(proyecto.id, "Ethics")
    fsa = materias.crear(proyecto.id, "FSA")
    largo = materias.crear(proyecto.id, "Alternative Investments")
    ajena = materias.crear(proyecto.id, "Mock exams")

    propuesta = ServicioProgreso(conn).pesos_cfa(proyecto.id)
    assert propuesta == {ethics.id: 17.1, fsa.id: 12.2, largo.id: 8.3}
    assert ajena.id not in propuesta


def test_propuesta_cfa_no_escribe_nada(conn: sqlite3.Connection) -> None:
    proyecto = RepositorioProyectos(conn).crear("CFA")
    ethics = RepositorioMaterias(conn).crear(proyecto.id, "Ethics")

    ServicioProgreso(conn).pesos_cfa(proyecto.id)
    assert RepositorioMaterias(conn).obtener(ethics.id).peso == 0.0


# -- Atencion: horas dedicadas frente al peso --------------------------------


def test_sin_pesos_no_hay_desvio_que_calcular(
    conn: sqlite3.Connection, temario: int
) -> None:
    quant, ethics = RepositorioMaterias(conn).listar(temario)
    resumen = ServicioProgreso(conn).resumen(temario)
    assert resumen.desvio_atencion({quant.id: 3600, ethics.id: 3600}) == ()


def test_un_reparto_proporcional_al_peso_no_desatiende_nada(
    conn: sqlite3.Connection, temario: int
) -> None:
    servicio = ServicioProgreso(conn)
    quant, ethics = RepositorioMaterias(conn).listar(temario)
    servicio.fijar_pesos(temario, {quant.id: 3.0, ethics.id: 1.0})

    # 3 h y 1 h: exactamente el 75 % y el 25 % que piden los pesos.
    desvios = servicio.resumen(temario).desvio_atencion(
        {quant.id: 3 * 3600, ethics.id: 3600}
    )
    assert {d.nombre: round(d.real) for d in desvios} == {
        "Quantitative Methods": 75,
        "Ethics": 25,
    }
    assert not any(d.desatendida for d in desvios)


def test_la_materia_que_recibe_menos_de_su_peso_sale_desatendida(
    conn: sqlite3.Connection, temario: int
) -> None:
    servicio = ServicioProgreso(conn)
    quant, ethics = RepositorioMaterias(conn).listar(temario)
    servicio.fijar_pesos(temario, {quant.id: 3.0, ethics.id: 1.0})

    # Todo el tiempo a la ligera: la pesada se queda en cero frente a un 75 %.
    desvios = servicio.resumen(temario).desvio_atencion({ethics.id: 4 * 3600})
    desatendidas = [d.nombre for d in desvios if d.desatendida]
    assert desatendidas == ["Quantitative Methods"]


def test_los_desvios_salen_ordenados_por_deficit(
    conn: sqlite3.Connection, temario: int
) -> None:
    """Lo primero que se lee tiene que ser lo que falta."""
    servicio = ServicioProgreso(conn)
    quant, ethics = RepositorioMaterias(conn).listar(temario)
    servicio.fijar_pesos(temario, {quant.id: 3.0, ethics.id: 1.0})

    desvios = servicio.resumen(temario).desvio_atencion({ethics.id: 4 * 3600})
    assert [d.nombre for d in desvios] == ["Quantitative Methods", "Ethics"]


def test_una_materia_sin_peso_no_aparece_en_el_desvio(
    conn: sqlite3.Connection, temario: int
) -> None:
    """Sin peso no hay objetivo con el que comparar."""
    servicio = ServicioProgreso(conn)
    quant, ethics = RepositorioMaterias(conn).listar(temario)
    servicio.fijar_pesos(temario, {quant.id: 3.0, ethics.id: 0.0})

    desvios = servicio.resumen(temario).desvio_atencion(
        {quant.id: 3600, ethics.id: 3600}
    )
    assert [d.nombre for d in desvios] == ["Quantitative Methods"]
    # El denominador sigue siendo todo el tiempo clasificado, tambien el de la
    # materia sin peso: si no, el real de la pesada saldria inflado al 100 %.
    assert round(desvios[0].real) == 50


def test_sin_tiempo_clasificado_no_revienta(
    conn: sqlite3.Connection, temario: int
) -> None:
    servicio = ServicioProgreso(conn)
    quant, ethics = RepositorioMaterias(conn).listar(temario)
    servicio.fijar_pesos(temario, {quant.id: 3.0, ethics.id: 1.0})

    desvios = servicio.resumen(temario).desvio_atencion({})
    assert all(d.real == 0.0 for d in desvios)
    assert all(d.segundos == 0 for d in desvios)


def test_un_id_desconocido_no_descuadra_los_porcentajes(
    conn: sqlite3.Connection, temario: int
) -> None:
    servicio = ServicioProgreso(conn)
    quant, ethics = RepositorioMaterias(conn).listar(temario)
    servicio.fijar_pesos(temario, {quant.id: 3.0, ethics.id: 1.0})

    desvios = servicio.resumen(temario).desvio_atencion(
        {quant.id: 3600, ethics.id: 3600, 9999: 36000}
    )
    assert round(sum(d.real for d in desvios)) == 100
