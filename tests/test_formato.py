"""Formateo de valores para la interfaz."""

from __future__ import annotations

from datetime import date

import pytest

from mukuwareru.utilidades import formato


@pytest.mark.parametrize(
    ("segundos", "esperado"),
    [(0, "0 min"), (1500, "25 min"), (3600, "1 h"), (12600, "3.5 h"), (770400, "214 h")],
)
def test_horas(segundos: int, esperado: str) -> None:
    assert formato.horas(segundos) == esperado


@pytest.mark.parametrize(
    ("segundos", "esperado"),
    [
        (1500, "25:00"),
        (59, "00:59"),
        (0, "00:00"),
        (-5, "00:00"),
        # Pasada la hora aparece el campo de horas: una sesion indefinida no
        # tiene fin previsto y "61:01" dejaria de leerse en cuanto crece.
        (3661, "1:01:01"),
        (3600, "1:00:00"),
        (9045, "2:30:45"),
    ],
)
def test_duracion_reloj(segundos: int, esperado: str) -> None:
    assert formato.duracion_reloj(segundos) == esperado


@pytest.mark.parametrize(
    ("bytes_", "esperado"),
    [(512, "512 B"), (1536, "1.5 KB"), (1_572_864, "1.5 MB")],
)
def test_tamano(bytes_: int, esperado: str) -> None:
    assert formato.tamano(bytes_) == esperado


def test_fecha_corta() -> None:
    assert formato.fecha_corta(date(2026, 11, 13)) == "13 nov 2026"


@pytest.mark.parametrize(
    ("parte", "total", "esperado"),
    [(29, 75, 39), (0, 0, 0), (11, 11, 100), (5, 0, 0)],
)
def test_porcentaje(parte: int, total: int, esperado: int) -> None:
    assert formato.porcentaje(parte, total) == esperado


def test_dias_relativos() -> None:
    assert formato.dias_relativos(5) == "en 5 dias"
    assert formato.dias_relativos(1) == "manana"
    assert formato.dias_relativos(0) == "hoy"
    assert formato.dias_relativos(-1) == "ayer"
    assert formato.dias_relativos(-3) == "hace 3 dias"


def test_apertura() -> None:
    from datetime import datetime

    hoy = date(2026, 9, 25)
    assert formato.apertura(None) == "sin abrir"
    assert formato.apertura(datetime(2026, 9, 25, 10, 30), hoy=hoy) == "hoy 10:30"
    assert formato.apertura(datetime(2026, 9, 24, 8, 0), hoy=hoy) == "ayer"
    assert formato.apertura(datetime(2026, 9, 1, 8, 0), hoy=hoy) == "1 sep 2026"