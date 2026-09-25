"""Herramientas de fuera de la aplicacion que escriben o borran datos reales."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from herramientas import importar_meldrum, respaldar
from mukuwareru.nucleo.bd import conexion as bd
from mukuwareru.nucleo.repositorios import RepositorioProyectos

_QUIZ = """# Consolidado

## Quiz 3 — 2026-09-20 FSA repaso

**Correctas:** 1 | **Incorrectas:** 1
**Falladas:** 2

### Pregunta 1
**Libro:** Financial Statement Analysis · LM 3
**Resultado:** ✅

### Pregunta 2
**Libro:** Financial Statement Analysis · LM 4
**Resultado:** ❌
"""


def test_el_parser_de_meldrum_saca_nota_y_desglose() -> None:
    (quiz,) = importar_meldrum.quizzes(_QUIZ)
    assert quiz.titulo == "Meldrum Q-Bank · Quiz 3 (FSA repaso)"
    assert quiz.fecha == date(2026, 9, 20)
    assert (quiz.obtenidos, quiz.posibles) == (1, 2)
    assert quiz.desglose == {"FSA": (1, 2)}
    assert quiz.nota == "Falladas: 2"


def test_el_parser_de_meldrum_dice_que_falta_si_cambia_el_formato() -> None:
    roto = _QUIZ.replace("**Libro:** Financial Statement Analysis · LM 4\n", "")
    with pytest.raises(importar_meldrum.FormatoInesperadoError, match="pregunta 2"):
        importar_meldrum.quizzes(roto)


def _base_con_proyecto(ruta: Path) -> None:
    cx = bd.abrir(ruta)
    RepositorioProyectos(cx).crear("CFA")
    cx.close()


def test_un_respaldo_se_verifica_y_es_un_solo_archivo(tmp_path: Path) -> None:
    origen = tmp_path / "basedatos.db"
    _base_con_proyecto(origen)

    copia = respaldar.respaldar(origen, tmp_path / "copias")
    correcta, detalle = respaldar.verificar(copia)

    assert correcta, detalle
    assert "1 proyectos" in detalle
    assert not copia.with_name(copia.name + "-wal").exists()


def test_un_respaldo_sin_proyectos_no_cuenta(tmp_path: Path) -> None:
    """Casi siempre significa que se respaldo la base equivocada."""
    vacia = tmp_path / "vacia.db"
    bd.abrir(vacia).close()
    correcta, _ = respaldar.verificar(vacia)
    assert not correcta


def test_podar_solo_borra_sus_copias_y_las_mas_viejas(tmp_path: Path) -> None:
    for sello in ("20260101-000000", "20260102-000000", "20260103-000000"):
        sqlite3.connect(tmp_path / f"basedatos-{sello}.db").close()
    ajeno = tmp_path / "mi_archivo.db"
    ajeno.write_bytes(b"")

    borradas = respaldar.podar(tmp_path, conservar=2)

    assert [b.name for b in borradas] == ["basedatos-20260101-000000.db"]
    assert ajeno.exists()
    assert len(list(tmp_path.glob("basedatos-*.db"))) == 2
