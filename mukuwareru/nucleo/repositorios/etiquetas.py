"""Acceso a la tabla ``etiqueta``.

Las etiquetas son la clasificacion transversal de las notas: el cuaderno dice
donde vive una nota, la etiqueta de que trata. Son las dos cosas a la vez porque
una nota sobre «dudas de examen» puede estar en cualquier cuaderno.
"""

from __future__ import annotations

import sqlite3

from mukuwareru.nucleo.modelos.entidades import Etiqueta
from mukuwareru.nucleo.repositorios.base import Repositorio

_CAMPOS = "id, proyecto_id, nombre, color"


class RepositorioEtiquetas(Repositorio):
    """Etiquetas de notas dentro de un proyecto."""

    def listar(self, proyecto_id: int) -> list[Etiqueta]:
        """Etiquetas del proyecto, por nombre."""
        filas = self._cx.execute(
            f"SELECT {_CAMPOS} FROM etiqueta WHERE proyecto_id = ? ORDER BY nombre",
            (proyecto_id,),
        ).fetchall()
        return [_a_etiqueta(f) for f in filas]

    def obtener(self, etiqueta_id: int) -> Etiqueta | None:
        """Una etiqueta por id, o ``None``."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM etiqueta WHERE id = ?", (etiqueta_id,)
        ).fetchone()
        return _a_etiqueta(fila) if fila else None

    def por_nombre(self, proyecto_id: int, nombre: str) -> Etiqueta | None:
        """Busca una etiqueta por su nombre exacto dentro del proyecto."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM etiqueta WHERE proyecto_id = ? AND nombre = ?",
            (proyecto_id, nombre),
        ).fetchone()
        return _a_etiqueta(fila) if fila else None

    def crear(
        self, proyecto_id: int, nombre: str, *, color: str | None = None
    ) -> Etiqueta:
        """Inserta una etiqueta."""
        cursor = self._cx.execute(
            "INSERT INTO etiqueta (proyecto_id, nombre, color) VALUES (?, ?, ?)",
            (proyecto_id, nombre, color),
        )
        return Etiqueta(
            id=int(cursor.lastrowid or 0),
            proyecto_id=proyecto_id,
            nombre=nombre,
            color=color,
        )

    def obtener_o_crear(
        self, proyecto_id: int, nombre: str, *, color: str | None = None
    ) -> Etiqueta:
        """Etiqueta con ese nombre, creandola si hace falta.

        Escribir una etiqueta nueva en el campo de etiquetas no deberia obligar
        a crearla antes en otro sitio.
        """
        existente = self.por_nombre(proyecto_id, nombre)
        if existente is not None:
            return existente
        return self.crear(proyecto_id, nombre, color=color)

    def renombrar(self, etiqueta_id: int, nombre: str) -> None:
        """Cambia el nombre de una etiqueta en todas las notas de golpe."""
        self._cx.execute(
            "UPDATE etiqueta SET nombre = ? WHERE id = ?", (nombre, etiqueta_id)
        )

    def eliminar(self, etiqueta_id: int) -> None:
        """Borra la etiqueta. Las notas que la tenian no se tocan."""
        self._cx.execute("DELETE FROM etiqueta WHERE id = ?", (etiqueta_id,))

    def conteo(self, proyecto_id: int) -> dict[int, int]:
        """Notas por etiqueta, para ordenar y para no ofrecer etiquetas vacias."""
        filas = self._cx.execute(
            """
            SELECT e.id AS etiqueta_id, COUNT(ne.nota_id) AS total
              FROM etiqueta e
              LEFT JOIN nota_etiqueta ne ON ne.etiqueta_id = e.id
             WHERE e.proyecto_id = ?
             GROUP BY e.id
            """,
            (proyecto_id,),
        ).fetchall()
        return {int(f["etiqueta_id"]): int(f["total"]) for f in filas}


def _a_etiqueta(fila: sqlite3.Row) -> Etiqueta:
    return Etiqueta(
        id=fila["id"],
        proyecto_id=fila["proyecto_id"],
        nombre=fila["nombre"],
        color=fila["color"],
    )
