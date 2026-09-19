"""Maquina de estados del Pomodoro.

Todo el ciclo se simula sin esperar tiempo real: esa es la razon de que el
reloj no dependa de Qt.
"""

from __future__ import annotations

import pytest

from mukuwareru.nucleo.servicios import Configuracion, Estado, Fase, RelojPomodoro

RAPIDA = Configuracion(
    trabajo_min=25, descanso_corto_min=5, descanso_largo_min=15, sesiones_por_ciclo=4
)


@pytest.fixture
def reloj() -> RelojPomodoro:
    return RelojPomodoro(RAPIDA)


# --- Estado inicial --------------------------------------------------------


def test_arranca_detenido_en_trabajo(reloj: RelojPomodoro) -> None:
    assert reloj.fase is Fase.TRABAJO
    assert reloj.estado is Estado.DETENIDO
    assert reloj.restante_seg == 1500
    assert reloj.sesion_del_ciclo == 1


def test_detenido_no_consume_tiempo(reloj: RelojPomodoro) -> None:
    assert reloj.avanzar(60) is None
    assert reloj.restante_seg == 1500


# --- Control ---------------------------------------------------------------


def test_iniciar_y_avanzar(reloj: RelojPomodoro) -> None:
    reloj.iniciar()
    reloj.avanzar(60)
    assert reloj.restante_seg == 1440
    assert reloj.transcurrido_seg == 60
    assert reloj.progreso == pytest.approx(0.04)


def test_pausar_congela_el_tiempo(reloj: RelojPomodoro) -> None:
    reloj.iniciar()
    reloj.avanzar(300)
    reloj.pausar()
    reloj.avanzar(300)
    assert reloj.restante_seg == 1200
    assert reloj.estado is Estado.PAUSADO


def test_alternar(reloj: RelojPomodoro) -> None:
    reloj.alternar()
    assert reloj.estado is Estado.CORRIENDO
    reloj.alternar()
    assert reloj.estado is Estado.PAUSADO
    reloj.alternar()
    assert reloj.estado is Estado.CORRIENDO


def test_reiniciar_vuelve_al_principio_de_la_fase(reloj: RelojPomodoro) -> None:
    reloj.iniciar()
    reloj.avanzar(600)
    reloj.reiniciar()
    assert (reloj.restante_seg, reloj.estado, reloj.fase) == (1500, Estado.DETENIDO, Fase.TRABAJO)


# --- Fin de fase -----------------------------------------------------------


def test_terminar_trabajo_devuelve_el_evento_y_pasa_a_descanso(reloj: RelojPomodoro) -> None:
    reloj.iniciar()
    terminada = reloj.avanzar(1500)

    assert terminada is not None
    assert terminada.fase is Fase.TRABAJO
    assert terminada.duracion_seg == 1500
    assert reloj.fase is Fase.DESCANSO_CORTO
    assert reloj.restante_seg == 300


def test_al_terminar_una_fase_el_reloj_se_detiene(reloj: RelojPomodoro) -> None:
    reloj.iniciar()
    reloj.avanzar(1500)
    assert reloj.estado is Estado.DETENIDO
    # El descanso no arranca solo: hay que pulsar iniciar.
    assert reloj.avanzar(60) is None
    assert reloj.restante_seg == 300


def test_el_exceso_de_tiempo_se_descarta(reloj: RelojPomodoro) -> None:
    reloj.iniciar()
    reloj.avanzar(9999)
    assert reloj.restante_seg == 300


def test_la_cuarta_sesion_lleva_a_descanso_largo(reloj: RelojPomodoro) -> None:
    for numero in range(1, 5):
        assert reloj.sesion_del_ciclo == numero
        reloj.iniciar()
        reloj.avanzar(1500)          # termina trabajo
        esperado = Fase.DESCANSO_LARGO if numero == 4 else Fase.DESCANSO_CORTO
        assert reloj.fase is esperado, f"tras la sesion {numero}"
        reloj.iniciar()
        reloj.avanzar(reloj.restante_seg)  # termina el descanso

    assert reloj.completadas == 4
    assert reloj.fase is Fase.TRABAJO
    assert reloj.sesion_del_ciclo == 1   # el ciclo vuelve a empezar


# --- Saltar ----------------------------------------------------------------


def test_saltar_trabajo_no_cuenta_como_completado(reloj: RelojPomodoro) -> None:
    reloj.iniciar()
    reloj.avanzar(60)
    reloj.saltar()
    assert reloj.completadas == 0
    assert reloj.fase is Fase.DESCANSO_CORTO
    assert reloj.estado is Estado.DETENIDO


def test_saltar_un_descanso_vuelve_a_trabajo(reloj: RelojPomodoro) -> None:
    reloj.iniciar()
    reloj.avanzar(1500)
    reloj.saltar()
    assert reloj.fase is Fase.TRABAJO
    assert reloj.completadas == 1


# --- Configuracion ---------------------------------------------------------


def test_aplicar_configuracion_reinicia_la_fase(reloj: RelojPomodoro) -> None:
    reloj.iniciar()
    reloj.avanzar(1400)
    reloj.aplicar(Configuracion(trabajo_min=10))
    assert reloj.restante_seg == 600
    assert reloj.estado is Estado.DETENIDO


def test_reiniciar_ciclo(reloj: RelojPomodoro) -> None:
    reloj.iniciar()
    reloj.avanzar(1500)
    reloj.reiniciar_ciclo()
    assert (reloj.completadas, reloj.fase, reloj.restante_seg) == (0, Fase.TRABAJO, 1500)


def test_la_secuencia_describe_el_ciclo_completo(reloj: RelojPomodoro) -> None:
    secuencia = reloj.secuencia()
    assert len(secuencia) == 8
    assert [f for f, _ in secuencia[:2]] == [Fase.TRABAJO, Fase.DESCANSO_CORTO]
    assert secuencia[-1] == (Fase.DESCANSO_LARGO, 900)


def test_las_fases_se_traducen_al_modelo_de_datos() -> None:
    from mukuwareru.nucleo.modelos import TipoSesion

    assert Fase.TRABAJO.a_tipo_sesion() is TipoSesion.TRABAJO
    assert Fase.DESCANSO_LARGO.a_tipo_sesion() is TipoSesion.DESCANSO_LARGO
