"""Importa el consolidado de quizzes del Q-Bank de Mark Meldrum como evaluaciones.

Cada quiz queda como una evaluacion del proyecto CFA con **peso cero** —es un
simulacro, no cuenta para ninguna nota final— y con el desglose por materia
sacado pregunta a pregunta. La nota global usa el encabezado oficial del quiz.

Es idempotente: un quiz cuyo titulo ya existe se salta.

    python herramientas/importar_meldrum.py "ruta/Preguntas Mark Meldurm.md"
    python herramientas/importar_meldrum.py "..." --ensayo      # solo mira
    python herramientas/importar_meldrum.py "..." --base ruta\\a\\basedatos.db
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from herramientas._comun import base_instalada  # noqa: E402
from mukuwareru.nucleo.bd import conexion as bd  # noqa: E402
from mukuwareru.nucleo.modelos.entidades import LineaEvaluacion  # noqa: E402
from mukuwareru.nucleo.repositorios import (  # noqa: E402
    RepositorioEvaluaciones,
    RepositorioMaterias,
    RepositorioProyectos,
)
from mukuwareru.nucleo.repositorios.base import transaccion  # noqa: E402
from mukuwareru.nucleo.servicios.resultados import (  # noqa: E402
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


class FormatoInesperadoError(ValueError):
    """El Markdown no tiene la forma que espera el parser."""


@dataclass(frozen=True, slots=True)
class Quiz:
    titulo: str
    fecha: date
    obtenidos: int
    posibles: int
    desglose: dict[str, tuple[int, int]]   # materia -> (aciertos, preguntas)
    nota: str | None


def _buscar(patron: re.Pattern[str], texto: str, que: str, donde: str) -> re.Match[str]:
    """``patron.search`` que, si no encuentra nada, dice que y donde."""
    encontrado = patron.search(texto)
    if encontrado is None:
        raise FormatoInesperadoError(f"{donde}: no se encuentra {que}")
    return encontrado


def quizzes(texto: str) -> list[Quiz]:
    """Parsea el consolidado entero. Falla con un mensaje claro si cambia el formato."""
    marcas = list(_QUIZ.finditer(texto))
    salida: list[Quiz] = []
    for i, m in enumerate(marcas):
        donde = f"Quiz {m.group(1)}"
        cuerpo = texto[m.end() : marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)]
        cabecera = _buscar(_CABECERA, cuerpo, "la cabecera Correctas/Incorrectas", donde)
        bien, mal = map(int, cabecera.groups())
        desglose: dict[str, list[int]] = {}
        for n, bloque in enumerate(re.split(r"^### Pregunta ", cuerpo, flags=re.M)[1:], 1):
            lugar = f"{donde}, pregunta {n}"
            libro = _buscar(_LIBRO, bloque, "el libro", lugar).group(1).strip()
            acierto = _buscar(_RESULTADO, bloque, "el resultado", lugar).group(1) == "✅"
            cuenta = desglose.setdefault(LIBROS.get(libro, libro), [0, 0])
            cuenta[0] += acierto
            cuenta[1] += 1
        falladas = _FALLADAS.search(cuerpo)
        salida.append(Quiz(
            titulo=f"Meldrum Q-Bank · Quiz {m.group(1)} ({m.group(3)})",
            fecha=date.fromisoformat(m.group(2)),
            obtenidos=bien,
            posibles=bien + mal,
            desglose={k: (v[0], v[1]) for k, v in desglose.items()},
            nota=f"Falladas: {falladas.group(1)}" if falladas else None,
        ))
    return salida


def main() -> int:
    """Punto de entrada."""
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("origen", type=Path, help="Markdown consolidado del Q-Bank")
    analizador.add_argument(
        "--base", type=Path, default=None, help="base de datos (por defecto, la instalada)"
    )
    analizador.add_argument(
        "--ensayo", action="store_true", help="muestra que importaria sin escribir"
    )
    argumentos = analizador.parse_args()

    ruta_bd = argumentos.base or base_instalada()
    if not ruta_bd.exists():
        print(f"No existe la base de datos: {ruta_bd}")
        return 1
    try:
        leidos = quizzes(argumentos.origen.read_text(encoding="utf-8"))
    except FormatoInesperadoError as error:
        print(f"El archivo no tiene el formato esperado. {error}")
        return 1

    conexion = bd.abrir(ruta_bd)
    try:
        proyecto = next(
            (p for p in RepositorioProyectos(conexion).listar() if p.nombre == PROYECTO), None
        )
        if proyecto is None:
            print(f"No existe el proyecto «{PROYECTO}» en {ruta_bd}.")
            return 1
        materias = {m.nombre: m.id for m in RepositorioMaterias(conexion).listar(proyecto.id)}
        existentes = {e.titulo for e in RepositorioEvaluaciones(conexion).listar(proyecto.id)}

        nuevos = [q for q in leidos if q.titulo not in existentes]
        faltan = {m for q in nuevos for m in q.desglose} - set(materias)
        if faltan:
            print(f"Materias sin equivalente en la base: {', '.join(sorted(faltan))}")
            print("Anadelas a LIBROS o crea la materia antes de importar.")
            return 1

        print(f"Base de datos: {ruta_bd}")
        for q in nuevos:
            print(f"  + {q.fecha}  {q.titulo}  {q.obtenidos}/{q.posibles}")
        print(f"{len(nuevos)} nuevos, {len(leidos) - len(nuevos)} ya estaban.")
        if argumentos.ensayo:
            print("\n--ensayo: no se escribio nada.")
            return 0

        servicio = ServicioResultados(conexion)
        with transaccion(conexion):
            for q in nuevos:
                servicio.registrar(proyecto.id, DatosEvaluacion(
                    titulo=q.titulo,
                    fecha=q.fecha,
                    puntos_obtenidos=q.obtenidos,
                    puntos_posibles=q.posibles,
                    peso=0.0,
                    nota=q.nota,
                    materias=tuple(
                        LineaEvaluacion(
                            materia_id=materias[m], puntos_obtenidos=b, puntos_posibles=t
                        )
                        for m, (b, t) in q.desglose.items()
                    ),
                ))
        print(f"\nHecho: {len(nuevos)} quizzes importados.")
    finally:
        conexion.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
