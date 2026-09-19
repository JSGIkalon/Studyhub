"""Calculadora de notas: escala, nota necesaria y escenarios.

Los ejemplos son los del enunciado, con numeros que se comprueban a mano.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from mukuwareru.nucleo.modelos import Evaluacion
from mukuwareru.nucleo.repositorios import RepositorioMaterias, RepositorioProyectos
from mukuwareru.nucleo.servicios import (
    DatosEvaluacion,
    EscalaNotas,
    ServicioResultados,
    calcular,
)

CINCO = EscalaNotas(minimo=0, maximo=5, aprobado=3)
CIEN = EscalaNotas(minimo=0, maximo=100, aprobado=60)
DIA = date(2026, 9, 15)


def evaluacion(
    identificador: int, peso: float, obtenidos: float | None, posibles: float = 100
) -> Evaluacion:
    """Una evaluacion suelta, sin base de datos: `calcular` es una funcion pura."""
    return Evaluacion(
        id=identificador,
        proyecto_id=1,
        titulo=f"E{identificador}",
        fecha=DIA,
        puntos_obtenidos=obtenidos,
        puntos_posibles=posibles,
        peso=peso,
    )


# --- Escala ------------------------------------------------------------------


def test_la_escala_convierte_en_los_dos_sentidos() -> None:
    assert CINCO.desde_fraccion(0.8) == pytest.approx(4.0)
    assert CINCO.a_fraccion(4.0) == pytest.approx(0.8)
    assert CINCO.fraccion_aprobado == pytest.approx(0.6)
    assert CIEN.fraccion_aprobado == pytest.approx(0.6)


def test_una_escala_sin_sentido_no_es_valida() -> None:
    assert not EscalaNotas(minimo=5, maximo=0, aprobado=3).valida
    assert not EscalaNotas(minimo=0, maximo=5, aprobado=9).valida
    assert EscalaNotas(minimo=0, maximo=5, aprobado=3).valida


def test_formatear_da_decimales_solo_donde_hacen_falta() -> None:
    assert CINCO.formatear(0.7) == "3.5"
    assert CIEN.formatear(0.7) == "70"


# --- Nota acumulada y peso ---------------------------------------------------


def test_el_ejemplo_del_enunciado() -> None:
    """2,10 acumulado sobre el 50 % evaluado; hace falta 3,90 en lo que queda.

    Dos evaluaciones hechas que suman el 50 % con una media de 2,10 sobre 5
    (fraccion 0,42), y dos pendientes que suman el otro 50 %. Para llegar al 3,0:

        (0,6 * 100 - 50 * 0,42) / 50 = 0,78  ->  3,90 sobre 5

    El enunciado de la version 1.1 decia 3,80 en este mismo ejemplo, pero la
    cuenta no sale: con la mitad del curso a 2,10, la otra mitad tiene que dar
    3,90 para que la media sea 3,00. Manda la aritmetica.
    """
    evaluaciones = [
        evaluacion(1, peso=20, obtenidos=42),
        evaluacion(2, peso=30, obtenidos=42),
        evaluacion(3, peso=25, obtenidos=None),
        evaluacion(4, peso=25, obtenidos=None),
    ]
    resultado = calcular(evaluaciones, CINCO)

    assert resultado.peso_evaluado == 50
    assert resultado.peso_pendiente == 50
    assert CINCO.desde_fraccion(resultado.nota_acumulada) == pytest.approx(2.10)
    assert resultado.fraccion_necesaria is not None
    assert CINCO.desde_fraccion(resultado.fraccion_necesaria) == pytest.approx(3.90)
    assert resultado.alcanzable


def test_las_pendientes_no_hunden_la_nota_acumulada() -> None:
    """Un examen sin hacer no es un cero."""
    solo_una = calcular([evaluacion(1, peso=20, obtenidos=80)], CIEN)
    con_pendiente = calcular(
        [evaluacion(1, peso=20, obtenidos=80), evaluacion(2, peso=80, obtenidos=None)],
        CIEN,
    )
    assert solo_una.nota_acumulada == con_pendiente.nota_acumulada == pytest.approx(0.8)


def test_sin_pendientes_no_hay_nota_necesaria() -> None:
    resultado = calcular([evaluacion(1, peso=100, obtenidos=70)], CIEN)
    assert resultado.fraccion_necesaria is None
    assert resultado.alcanzable
    assert resultado.proyeccion == pytest.approx(0.7)


def test_aprobado_inalcanzable() -> None:
    """Un 0 en el 80 % del curso no se remonta ni con un 10 en el resto."""
    resultado = calcular(
        [evaluacion(1, peso=80, obtenidos=0), evaluacion(2, peso=20, obtenidos=None)],
        CIEN,
    )
    assert resultado.fraccion_necesaria is not None
    assert resultado.fraccion_necesaria > 1.0
    assert not resultado.alcanzable


def test_aprobado_ya_asegurado() -> None:
    """Con el 80 % del curso al maximo, lo que queda ya no puede suspenderte."""
    resultado = calcular(
        [evaluacion(1, peso=80, obtenidos=100), evaluacion(2, peso=20, obtenidos=None)],
        CIEN,
    )
    assert resultado.asegurado


# --- Peso cero: los mocks del CFA --------------------------------------------


def test_peso_cero_no_aporta_pero_cuenta_en_la_media() -> None:
    """Un mock con peso 0 % es un elemento valido: informa, pero no puntua."""
    resultado = calcular(
        [
            evaluacion(1, peso=0, obtenidos=70),
            evaluacion(2, peso=0, obtenidos=90),
        ],
        CIEN,
    )
    assert resultado.peso_evaluado == 0
    assert resultado.peso_pendiente == 0
    # Sin ningun peso, la media aritmetica es mejor respuesta que un cero.
    assert resultado.nota_acumulada == pytest.approx(0.8)


def test_un_mock_sin_peso_no_mueve_la_nota_final() -> None:
    con_mock = calcular(
        [evaluacion(1, peso=100, obtenidos=70), evaluacion(2, peso=0, obtenidos=10)],
        CIEN,
    )
    sin_mock = calcular([evaluacion(1, peso=100, obtenidos=70)], CIEN)
    assert con_mock.nota_acumulada == pytest.approx(sin_mock.nota_acumulada)


# --- Escenarios --------------------------------------------------------------


def test_un_escenario_sustituye_la_nota_pendiente() -> None:
    """«Y si saco un 3,5 en el final»."""
    evaluaciones = [
        evaluacion(1, peso=50, obtenidos=42),
        evaluacion(2, peso=50, obtenidos=None),
    ]
    supuesto = calcular(evaluaciones, CINCO, {2: CINCO.a_fraccion(3.5)})

    assert supuesto.peso_pendiente == 0
    # (0,42 + 0,70) / 2 = 0,56  ->  2,80 sobre 5
    assert CINCO.desde_fraccion(supuesto.nota_acumulada) == pytest.approx(2.80)


def test_un_escenario_no_toca_las_evaluaciones_recibidas() -> None:
    """Nunca modificar una nota real al simular: lo garantiza la pureza."""
    evaluaciones = [
        evaluacion(1, peso=50, obtenidos=42),
        evaluacion(2, peso=50, obtenidos=None),
    ]
    calcular(evaluaciones, CINCO, {1: 1.0, 2: 1.0})
    assert evaluaciones[0].puntos_obtenidos == 42
    assert evaluaciones[1].puntos_obtenidos is None


# --- Contra la base de datos -------------------------------------------------


@pytest.fixture
def proyecto_id(conn: sqlite3.Connection) -> int:
    proyecto = RepositorioProyectos(conn).crear("MSc")
    RepositorioMaterias(conn).crear(proyecto.id, "Probability")
    return proyecto.id


def test_la_escala_se_guarda_por_proyecto(
    conn: sqlite3.Connection, proyecto_id: int
) -> None:
    servicio = ServicioResultados(conn)
    assert servicio.escala(proyecto_id) == EscalaNotas()      # 0-100, aprobado 60

    assert servicio.fijar_escala(proyecto_id, CINCO)
    assert servicio.escala(proyecto_id) == CINCO


def test_una_escala_invalida_no_se_guarda(
    conn: sqlite3.Connection, proyecto_id: int
) -> None:
    servicio = ServicioResultados(conn)
    assert not servicio.fijar_escala(proyecto_id, EscalaNotas(minimo=5, maximo=0))
    assert servicio.escala(proyecto_id) == EscalaNotas()


def test_una_evaluacion_pendiente_se_guarda_sin_nota(
    conn: sqlite3.Connection, proyecto_id: int
) -> None:
    servicio = ServicioResultados(conn)
    servicio.registrar(
        proyecto_id,
        DatosEvaluacion(
            titulo="Final",
            fecha=date(2026, 12, 1),
            puntos_obtenidos=None,
            puntos_posibles=100,
            peso=50,
        ),
    )
    resumen = servicio.resumen(proyecto_id)
    assert len(resumen.pendientes) == 1
    assert not resumen.corregidas
    # Una pendiente no entra en ninguna media ni en la curva de evolucion.
    assert resumen.porcentaje == 0
    assert servicio.evolucion(proyecto_id) == ()


def test_simular_no_escribe_nada(conn: sqlite3.Connection, proyecto_id: int) -> None:
    servicio = ServicioResultados(conn)
    servicio.fijar_escala(proyecto_id, CINCO)
    servicio.registrar(
        proyecto_id,
        DatosEvaluacion("Parcial", DIA, 42, 100, peso=50),
    )
    servicio.registrar(
        proyecto_id,
        DatosEvaluacion("Final", date(2026, 12, 1), None, 100, peso=50),
    )
    pendiente = servicio.resumen(proyecto_id).pendientes[0]

    servicio.simular(proyecto_id, {pendiente.id: 1.0})

    # La evaluacion real sigue pendiente despues de la simulacion.
    assert servicio.resumen(proyecto_id).pendientes[0].puntos_obtenidos is None
