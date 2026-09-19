"""Asigna una materia a las sesiones que entraron por el Excel sin clasificar.

    python herramientas/clasificar_importadas.py FSA
    python herramientas/clasificar_importadas.py FSA --proyecto 1
    python herramientas/clasificar_importadas.py FSA --bd ruta\\a\\basedatos.db
    python herramientas/clasificar_importadas.py FSA --ensayo   # solo mira

La hoja de registro diario del Excel trae fecha y horas, pero no el tema, asi
que la importacion crea esas sesiones sin materia y el tiempo aparece como
«Sin clasificar» en las estadisticas. Este guion las etiqueta de una vez.

Solo toca sesiones de trabajo con ``origen = 'importada'`` que **no** tengan ya
alguna materia: reejecutarlo no cambia nada y nunca sobrescribe una etiqueta
puesta a mano. Por defecto trabaja sobre la base de datos de la aplicacion
instalada, que es donde vive lo que el usuario ve.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def bd_instalada() -> Path:
    """Base de datos de la aplicacion instalada en esta maquina."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Programs" / "Mukuwareru" / "datos" / "basedatos.db"


def main(materia: str, proyecto_id: int, ruta: Path, ensayo: bool) -> int:
    """Etiqueta las sesiones importadas sin clasificar y resume lo hecho."""
    if not ruta.exists():
        print(f"No existe {ruta}")
        return 1

    cx = sqlite3.connect(str(ruta))
    cx.row_factory = sqlite3.Row
    try:
        fila = cx.execute(
            "SELECT id, nombre FROM materia WHERE proyecto_id = ? AND nombre = ?",
            (proyecto_id, materia),
        ).fetchone()
        if fila is None:
            nombres = [
                f["nombre"]
                for f in cx.execute(
                    "SELECT nombre FROM materia WHERE proyecto_id = ? ORDER BY nombre",
                    (proyecto_id,),
                )
            ]
            print(f"El proyecto {proyecto_id} no tiene la materia «{materia}».")
            print("Materias disponibles: " + (", ".join(nombres) or "ninguna"))
            return 1
        materia_id = int(fila["id"])

        pendientes = cx.execute(
            """
            SELECT id, fecha_local, duracion_seg FROM sesion
             WHERE proyecto_id = ? AND tipo = 'trabajo' AND origen = 'importada'
               AND NOT EXISTS (SELECT 1 FROM sesion_materia sm WHERE sm.sesion_id = sesion.id)
             ORDER BY fecha_local
            """,
            (proyecto_id,),
        ).fetchall()

        if not pendientes:
            print("No hay sesiones importadas sin clasificar. Nada que hacer.")
            return 0

        segundos = sum(int(f["duracion_seg"]) for f in pendientes)
        print(f"Base de datos: {ruta}")
        print(f"Materia:       {fila['nombre']} (id {materia_id})")
        for f in pendientes:
            print(f"  {f['fecha_local']}  {int(f['duracion_seg']) / 3600:.2f} h")
        print(f"Total: {len(pendientes)} sesiones, {segundos / 3600:.2f} h")

        if ensayo:
            print("\n--ensayo: no se escribio nada.")
            return 0

        with cx:
            cx.executemany(
                "INSERT INTO sesion_materia (sesion_id, materia_id) VALUES (?, ?)",
                [(int(f["id"]), materia_id) for f in pendientes],
            )
        print(f"\nHecho: {segundos / 3600:.2f} h atribuidas a {fila['nombre']}.")
    finally:
        cx.close()
    return 0


if __name__ == "__main__":
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("materia", help="Nombre exacto de la materia, p. ej. FSA")
    analizador.add_argument("--proyecto", type=int, default=1, help="Id del proyecto")
    analizador.add_argument(
        "--bd", type=Path, default=None, help="Base de datos (por defecto, la instalada)"
    )
    analizador.add_argument(
        "--ensayo", action="store_true", help="Muestra que haria sin escribir"
    )
    argumentos = analizador.parse_args()
    sys.exit(
        main(
            argumentos.materia,
            argumentos.proyecto,
            argumentos.bd or bd_instalada(),
            argumentos.ensayo,
        )
    )
