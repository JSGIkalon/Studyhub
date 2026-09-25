"""Importa el consolidado de quizzes del Q-Bank de Mark Meldrum como evaluaciones.

Cada quiz queda como una evaluacion del proyecto CFA con **peso cero** —es un
simulacro, no cuenta para ninguna nota final— y con el desglose por materia
sacado pregunta a pregunta. La nota global usa el encabezado oficial del quiz.

Es idempotente: un quiz cuyo titulo ya existe se salta.

    python herramientas/importar_meldrum.py "ruta/Preguntas Mark Meldurm.md" [ruta_bd]
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mukuwareru.nucleo.bd.conexion import abrir
from mukuwareru.nucleo.bd.migrador import migrar
from mukuwareru.nucleo.modelos.entidades import LineaEvaluacion
from mukuwareru.nucleo.servicios.resultados import (
    DatosEvaluacion,
    ServicioResultados,
)

PROYECTO = "CFA Level I"
# Libro del Q-Bank -> materia tal como esta en la base.
LIBROS = {"Financial Statement Analysis": "FSA"}

_QUIZ = re.compile(r"^## Quiz (\d+) — (\d{4}-\d{2}-\d{2}) (.+)$", re.M)
_CABECERA = re.compile(r"\*\*Correctas:\*\* (\d+) \| \*\*Incorrectas:\*\* (\d+)")
_LIBRO = re.compile(r"^\*\*Libro:\*\* ([^·]+?) ·", re.M)
_RESULTADO = re.compile(r"\*\*Resultado:\*\* (✅|❌)")
_FALLADAS = re.compile(r"^\*\*Falladas:\*\* (.+)$", re.M)


def _quizzes(texto: str) -> list[dict]:
    marcas = list(_QUIZ.finditer(texto))
    salida = []
    for i, m in enumerate(marcas):
        cuerpo = texto[m.end() : marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)]
        bien, mal = map(int, _CABECERA.search(cuerpo).groups())
        desglose: dict[str, list[int]] = {}
        for bloque in re.split(r"^### Pregunta ", cuerpo, flags=re.M)[1:]:
            libro = _LIBRO.search(bloque).group(1).strip()
            acierto = _RESULTADO.search(bloque).group(1) == "✅"
            cuenta = desglose.setdefault(LIBROS.get(libro, libro), [0, 0])
            cuenta[0] += acierto
            cuenta[1] += 1
        falladas = _FALLADAS.search(cuerpo)
        salida.append({
            "titulo": f"Meldrum Q-Bank · Quiz {m.group(1)} ({m.group(3)})",
            "fecha": date.fromisoformat(m.group(2)),
            "obtenidos": bien,
            "posibles": bien + mal,
            "desglose": desglose,
            "nota": f"Falladas: {falladas.group(1)}" if falladas else None,
        })
    return salida


def main() -> None:
    origen = Path(sys.argv[1])
    ruta_bd = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Mukuwareru\datos\basedatos.db")
    )
    conexion = abrir(ruta_bd)
    migrar(conexion, ruta_bd)
    fila = conexion.execute("SELECT id FROM proyecto WHERE nombre = ?", (PROYECTO,)).fetchone()
    proyecto_id = fila[0]
    materias = {
        nombre: mid
        for mid, nombre in conexion.execute(
            "SELECT id, nombre FROM materia WHERE proyecto_id = ?", (proyecto_id,)
        )
    }
    existentes = {
        t for (t,) in conexion.execute(
            "SELECT titulo FROM evaluacion WHERE proyecto_id = ?", (proyecto_id,)
        )
    }
    servicio = ServicioResultados(conexion)
    nuevos = 0
    for quiz in _quizzes(origen.read_text(encoding="utf-8")):
        if quiz["titulo"] in existentes:
            continue
        faltan = set(quiz["desglose"]) - set(materias)
        if faltan:
            raise SystemExit(f"Materias sin equivalente en la base: {faltan}")
        lineas = tuple(
            LineaEvaluacion(materia_id=materias[m], puntos_obtenidos=b, puntos_posibles=t)
            for m, (b, t) in quiz["desglose"].items()
        )
        servicio.registrar(proyecto_id, DatosEvaluacion(
            titulo=quiz["titulo"],
            fecha=quiz["fecha"],
            puntos_obtenidos=quiz["obtenidos"],
            puntos_posibles=quiz["posibles"],
            peso=0.0,
            nota=quiz["nota"],
            materias=lineas,
        ))
        nuevos += 1
    conexion.commit()
    print(f"{nuevos} quizzes importados en {ruta_bd}")


if __name__ == "__main__":
    main()
