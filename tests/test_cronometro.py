"""Cronometro de la sesion de trabajo indefinida.

Tres horas de estudio se simulan en microsegundos: esa es la razon de que el
cronometro no dependa de Qt.
"""

from __future__ import annotations

import pytest

from mukuwareru.nucleo.servicios import Cronometro, Estado


@pytest.fixture
def crono() -> Cronometro:
    return Cronometro()


# --- Estado inicial --------------------------------------------------------


def test_arranca_detenido_y_a_cero(crono: Cronometro) -> None:
    assert crono.estado is Estado.DETENIDO
    assert crono.transcurrido_seg == 0
    assert not crono.activo


def test_detenido_no_cuenta(crono: Cronometro) -> None:
    crono.avanzar(600)
    assert crono.transcurrido_seg == 0


# --- Control ---------------------------------------------------------------


def test_iniciar_y_avanzar(crono: Cronometro) -> None:
    crono.iniciar()
    crono.avanzar(60)
    crono.avanzar(60)
    assert crono.transcurrido_seg == 120
    assert crono.corriendo


def test_pausar_congela_pero_no_cierra(crono: Cronometro) -> None:
    crono.iniciar()
    crono.avanzar(300)
    crono.pausar()
    crono.avanzar(300)

    assert crono.transcurrido_seg == 300
    assert crono.estado is Estado.PAUSADO
    # La sesion sigue abierta: el tiempo esta pendiente de registrarse.
    assert crono.activo
    assert not crono.corriendo


def test_alternar(crono: Cronometro) -> None:
    crono.alternar()
    assert crono.estado is Estado.CORRIENDO
    crono.alternar()
    assert crono.estado is Estado.PAUSADO
    crono.alternar()
    assert crono.estado is Estado.CORRIENDO


def test_reanudar_no_pierde_lo_contado(crono: Cronometro) -> None:
    crono.iniciar()
    crono.avanzar(120)
    crono.pausar()
    crono.iniciar()
    crono.avanzar(60)
    assert crono.transcurrido_seg == 180


# --- Cierre ----------------------------------------------------------------


def test_detener_devuelve_lo_contado_y_deja_a_cero(crono: Cronometro) -> None:
    crono.iniciar()
    crono.avanzar(3 * 3600)

    assert crono.detener() == 10800
    assert crono.estado is Estado.DETENIDO
    assert crono.transcurrido_seg == 0
    assert not crono.activo


def test_detener_en_pausa_registra_igual(crono: Cronometro) -> None:
    crono.iniciar()
    crono.avanzar(90)
    crono.pausar()
    assert crono.detener() == 90


def test_una_sesion_nueva_empieza_limpia(crono: Cronometro) -> None:
    crono.iniciar()
    crono.avanzar(90)
    crono.detener()

    crono.iniciar()
    crono.avanzar(30)
    assert crono.transcurrido_seg == 30
