"""Hace cumplir la regla arquitectonica principal del proyecto.

``mukuwareru.nucleo`` debe seguir siendo Python puro. Si alguna vez importa Qt, la
logica deja de ser testeable sin ventana y la separacion entre UI y negocio se
pierde de forma silenciosa. Este test lo impide.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

NUCLEO = Path(__file__).resolve().parents[1] / "mukuwareru" / "nucleo"
PROHIBIDOS = ("PySide6", "shiboken6")


def _modulos_importados(archivo: Path) -> set[str]:
    arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
    nombres: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres.add(nodo.module)
    return nombres


@pytest.mark.parametrize("archivo", sorted(NUCLEO.rglob("*.py")), ids=lambda p: p.name)
def test_el_nucleo_no_importa_qt(archivo: Path) -> None:
    importados = _modulos_importados(archivo)
    infractores = {
        nombre
        for nombre in importados
        if any(nombre == p or nombre.startswith(f"{p}.") for p in PROHIBIDOS)
    }
    assert not infractores, f"{archivo.name} importa Qt: {sorted(infractores)}"


def test_el_nucleo_no_importa_la_ui() -> None:
    for archivo in NUCLEO.rglob("*.py"):
        importados = _modulos_importados(archivo)
        assert not any(n.startswith("mukuwareru.ui") for n in importados), archivo.name
