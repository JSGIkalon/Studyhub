"""Deja el temario de un proyecto exactamente igual que ``temario_cfa.py``.

    python herramientas/sincronizar_temario.py                # simulacion
    python herramientas/sincronizar_temario.py --aplicar      # escribe

Existe porque el importador de Excel **solo anade**: no renombra ni borra. Sirve
para la primera carga, pero no para corregir un temario que ya esta dentro y que
el curriculo ha renumerado.

Orden de las operaciones, y el orden importa:

1. **Renombrar** lo que es el mismo modulo con otro nombre (``RENOMBRADOS``).
   Va primero para que el paso 3 lo vea como «ya existe» y no lo borre.
2. **Crear** lo que falta.
3. **Borrar** lo que sobra. Se niega a borrar algo completado salvo ``--forzar``:
   perder un modulo logrado por una errata en la lista seria caro y silencioso.
4. **Reordenar** para que la lista quede en el orden del curriculo.

Todo dentro de una unica transaccion: o queda entero o no queda nada.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from herramientas._comun import base_instalada  # noqa: E402
from herramientas.temario_cfa import (  # noqa: E402
    RENOMBRADOS,
    TEMARIO,
    TEMAS_COMPLETOS,
    total,
)
from mukuwareru.nucleo.bd import conexion as bd  # noqa: E402
from mukuwareru.nucleo.repositorios import (  # noqa: E402
    RepositorioMaterias,
    RepositorioModulos,
    RepositorioProyectos,
)
from mukuwareru.nucleo.repositorios.base import transaccion  # noqa: E402

PROYECTO = "CFA Level I"


class Plan:
    """Lo que habria que hacer, para poder ensenarlo antes de hacerlo."""

    def __init__(self) -> None:
        self.renombrar: list[tuple[str, int, str, str]] = []
        self.crear: list[tuple[str, int, str, bool]] = []
        self.borrar: list[tuple[str, int, str, bool]] = []
        self.reordenar: list[tuple[str, int, list[int]]] = []
        self.materias_ausentes: list[str] = []

    @property
    def hay_algo(self) -> bool:
        return bool(self.renombrar or self.crear or self.borrar or self.reordenar)

    @property
    def completados_en_peligro(self) -> list[tuple[str, str]]:
        """Modulos completados que el plan borraria."""
        return [(tema, nombre) for tema, _id, nombre, hecho in self.borrar if hecho]


def planificar(conexion: sqlite3.Connection, proyecto_id: int) -> Plan:
    """Compara la base con el temario y devuelve lo que habria que cambiar."""
    materias = RepositorioMaterias(conexion)
    modulos = RepositorioModulos(conexion)
    plan = Plan()

    por_nombre = {m.nombre: m for m in materias.listar(proyecto_id)}

    for tema, objetivo in TEMARIO.items():
        materia = por_nombre.get(tema)
        if materia is None:
            plan.materias_ausentes.append(tema)
            continue

        actuales = modulos.listar(materia.id)
        # Paso 1: renombrados. Se aplican sobre la copia en memoria para que los
        # pasos siguientes razonen sobre los nombres finales.
        nombres: dict[int, str] = {}
        for modulo in actuales:
            final = RENOMBRADOS.get((tema, modulo.nombre), modulo.nombre)
            nombres[modulo.id] = final
            if final != modulo.nombre:
                plan.renombrar.append((tema, modulo.id, modulo.nombre, final))

        existentes = set(nombres.values())
        objetivo_set = set(objetivo)

        # Paso 2: lo que falta. En un tema ya terminado, lo nuevo nace hecho.
        nace_hecho = tema in TEMAS_COMPLETOS
        for nombre in objetivo:
            if nombre not in existentes:
                plan.crear.append((tema, materia.id, nombre, nace_hecho))

        # Paso 3: lo que sobra.
        hechos = {m.id: m.completado for m in actuales}
        for identificador, nombre in nombres.items():
            if nombre not in objetivo_set:
                plan.borrar.append((tema, identificador, nombre, hechos[identificador]))

        # Paso 4: el orden final, por nombre.
        supervivientes = {
            nombre: identificador
            for identificador, nombre in nombres.items()
            if nombre in objetivo_set
        }
        orden_actual = [
            identificador
            for identificador in (nombres[m.id] for m in actuales)
            if identificador in supervivientes
        ]
        if orden_actual != [n for n in objetivo if n in supervivientes]:
            plan.reordenar.append((tema, materia.id, []))

    return plan


def aplicar(conexion: sqlite3.Connection, proyecto_id: int, plan: Plan) -> None:
    """Ejecuta el plan en una sola transaccion."""
    materias = RepositorioMaterias(conexion)
    modulos = RepositorioModulos(conexion)

    with transaccion(conexion):
        for _tema, identificador, _antes, despues in plan.renombrar:
            modulos.renombrar(identificador, despues)
        for _tema, materia_id, nombre, hecho in plan.crear:
            modulos.crear(materia_id, nombre, completado=hecho)
        for _tema, identificador, _nombre, _hecho in plan.borrar:
            modulos.eliminar(identificador)

        # El orden se fija al final y de una vez: despues de crear y borrar, la
        # lista real ya coincide en contenido con el temario.
        por_nombre = {m.nombre: m for m in materias.listar(proyecto_id)}
        for tema, objetivo in TEMARIO.items():
            materia = por_nombre.get(tema)
            if materia is None:
                continue
            actuales = {m.nombre: m.id for m in modulos.listar(materia.id)}
            modulos.reordenar(
                materia.id, [actuales[n] for n in objetivo if n in actuales]
            )


def informar(plan: Plan) -> None:
    """Imprime el plan en lenguaje llano."""
    if plan.materias_ausentes:
        print("MATERIAS QUE NO EXISTEN EN LA BASE (se omiten):")
        for tema in plan.materias_ausentes:
            print(f"  · {tema}")
        print()

    if plan.renombrar:
        print(f"RENOMBRAR ({len(plan.renombrar)})  — conservan su «completado»")
        for tema, _id, antes, despues in plan.renombrar:
            print(f"  {tema}")
            print(f"      «{antes}»")
            print(f"   -> «{despues}»")
        print()

    if plan.crear:
        print(f"CREAR ({len(plan.crear)})")
        tema_previo = ""
        for tema, _materia_id, nombre, hecho in plan.crear:
            if tema != tema_previo:
                print(f"  {tema}")
                tema_previo = tema
            marca = "  <-- nace COMPLETADO (tema ya terminado)" if hecho else ""
            print(f"      + {nombre}{marca}")
        print()

    if plan.borrar:
        print(f"BORRAR ({len(plan.borrar)})")
        tema_previo = ""
        for tema, _id, nombre, hecho in plan.borrar:
            if tema != tema_previo:
                print(f"  {tema}")
                tema_previo = tema
            marca = "  <-- COMPLETADO" if hecho else ""
            print(f"      - {nombre}{marca}")
        print()

    if plan.reordenar:
        print(f"REORDENAR ({len(plan.reordenar)} temas)")
        for tema, _id, _ in plan.reordenar:
            print(f"  · {tema}")
        print()

    if not plan.hay_algo:
        print("El temario ya coincide con la lista. No hay nada que hacer.")


def resumen(conexion: sqlite3.Connection, proyecto_id: int) -> None:
    """Estado final: modulos y completados por tema."""
    materias = RepositorioMaterias(conexion)
    modulos = RepositorioModulos(conexion)
    suma = hechos_total = 0
    print(f"\n{'TEMA':<26} {'LM':>4} {'OBJETIVO':>9} {'HECHOS':>7}")
    for materia in materias.listar(proyecto_id):
        lista = modulos.listar(materia.id)
        hechos = sum(1 for m in lista if m.completado)
        esperado = len(TEMARIO.get(materia.nombre, ()))
        marca = " " if len(lista) == esperado else " <-- NO CUADRA"
        print(f"{materia.nombre:<26} {len(lista):>4} {esperado:>9} {hechos:>7}{marca}")
        suma += len(lista)
        hechos_total += hechos
    print(f"{'TOTAL':<26} {suma:>4} {total():>9} {hechos_total:>7}")


def main() -> int:
    """Punto de entrada."""
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument(
        "--aplicar", action="store_true", help="escribe los cambios (por defecto simula)"
    )
    analizador.add_argument(
        "--forzar", action="store_true", help="permite borrar modulos completados"
    )
    analizador.add_argument(
        "--base", type=Path, default=None, help="otra base de datos (por defecto, la instalada)"
    )
    argumentos = analizador.parse_args()

    ruta = argumentos.base or base_instalada()
    print(f"Base de datos: {ruta}")
    conexion = bd.abrir(ruta)

    proyecto = next(
        (p for p in RepositorioProyectos(conexion).listar() if p.nombre == PROYECTO), None
    )
    if proyecto is None:
        print(f"No existe el proyecto «{PROYECTO}».")
        return 1

    plan = planificar(conexion, proyecto.id)
    informar(plan)

    if peligro := plan.completados_en_peligro:
        print("AVISO: el plan borraria modulos ya completados:")
        for tema, nombre in peligro:
            print(f"  · {tema} — {nombre}")
        if not argumentos.forzar:
            print(
                "\nNo se aplica nada. Anade el nombre viejo a RENOMBRADOS en "
                "temario_cfa.py, o repite con --forzar si de verdad sobran."
            )
            return 1

    if not argumentos.aplicar:
        resumen(conexion, proyecto.id)
        print("\nSimulacion. Repite con --aplicar para escribir.")
        return 0

    aplicar(conexion, proyecto.id, plan)
    print("Cambios aplicados.")
    resumen(conexion, proyecto.id)
    conexion.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
