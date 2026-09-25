"""Acceso a las tablas ``bloque_plan`` y ``bloque_materia``.

Un bloque es lo que se piensa estudiar; las sesiones son lo que se estudio. No
hay ninguna columna que los una: el cumplimiento se calcula comparando horas
(ver ``servicios/calendario.py``).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import date

from mukuwareru.nucleo.modelos.entidades import BloquePlan
from mukuwareru.nucleo.repositorios.base import (
    Repositorio,
    a_fecha,
    a_fecha_hora,
    ahora_iso,
    transaccion,
)

_CAMPOS = """
    id, proyecto_id, fecha, hora_inicio, duracion_min, titulo, nota, creado_en
"""


class RepositorioBloques(Repositorio):
    """Bloques de estudio planeados y las materias que preven."""

    def listar(self, proyecto_id: int, desde: str, hasta: str) -> list[BloquePlan]:
        """Bloques del rango de fechas locales, con sus materias resueltas.

        Las materias se leen en una sola consulta y se reparten en memoria: una
        consulta por bloque convertiria pintar un mes en decenas de viajes.
        """
        filas = self._cx.execute(
            f"""
            SELECT {_CAMPOS} FROM bloque_plan
             WHERE proyecto_id = ? AND fecha BETWEEN ? AND ?
             ORDER BY fecha, hora_inicio, id
            """,
            (proyecto_id, desde, hasta),
        ).fetchall()
        bloques = [_a_bloque(f) for f in filas]
        if not bloques:
            return []

        marcadores = ",".join("?" * len(bloques))
        vinculos = self._cx.execute(
            f"SELECT bloque_id, materia_id FROM bloque_materia "
            f"WHERE bloque_id IN ({marcadores})",
            [b.id for b in bloques],
        ).fetchall()
        por_bloque: dict[int, list[int]] = {}
        for fila in vinculos:
            por_bloque.setdefault(int(fila["bloque_id"]), []).append(
                int(fila["materia_id"])
            )
        for bloque in bloques:
            bloque.materias = por_bloque.get(bloque.id, [])
        return bloques

    def obtener(self, bloque_id: int) -> BloquePlan | None:
        """Un bloque por id, con sus materias."""
        fila = self._cx.execute(
            f"SELECT {_CAMPOS} FROM bloque_plan WHERE id = ?", (bloque_id,)
        ).fetchone()
        if fila is None:
            return None
        bloque = _a_bloque(fila)
        bloque.materias = self.materias_de(bloque_id)
        return bloque

    def crear(
        self,
        proyecto_id: int,
        fecha: date,
        *,
        duracion_min: int = 25,
        hora_inicio: str | None = None,
        titulo: str = "",
        nota: str | None = None,
        materias: Sequence[int] | None = None,
    ) -> BloquePlan:
        """Inserta un bloque planeado y lo devuelve ya con su id."""
        with transaccion(self._cx):
            cursor = self._cx.execute(
                """
                INSERT INTO bloque_plan
                    (proyecto_id, fecha, hora_inicio, duracion_min, titulo, nota, creado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proyecto_id, fecha.isoformat(), hora_inicio, duracion_min,
                    titulo, nota, ahora_iso(),
                ),
            )
            bloque_id = int(cursor.lastrowid or 0)
            if materias:
                self.etiquetar(bloque_id, materias)
        creado = self.obtener(bloque_id)
        assert creado is not None
        return creado

    def actualizar(self, bloque: BloquePlan) -> None:
        """Guarda los campos editables del bloque, sin tocar sus materias."""
        self._cx.execute(
            """
            UPDATE bloque_plan
               SET fecha = ?, hora_inicio = ?, duracion_min = ?, titulo = ?, nota = ?
             WHERE id = ?
            """,
            (
                bloque.fecha.isoformat(), bloque.hora_inicio, bloque.duracion_min,
                bloque.titulo, bloque.nota, bloque.id,
            ),
        )

    def mover(self, bloque_id: int, fecha: date, hora_inicio: str | None) -> None:
        """Lleva el bloque a otro dia u otra hora. Es el arrastre del calendario."""
        self._cx.execute(
            "UPDATE bloque_plan SET fecha = ?, hora_inicio = ? WHERE id = ?",
            (fecha.isoformat(), hora_inicio, bloque_id),
        )

    def materias_de(self, bloque_id: int) -> list[int]:
        """Materias previstas para el bloque."""
        filas = self._cx.execute(
            "SELECT materia_id FROM bloque_materia WHERE bloque_id = ?", (bloque_id,)
        ).fetchall()
        return [int(f[0]) for f in filas]

    def etiquetar(self, bloque_id: int, materias: Sequence[int]) -> None:
        """Reemplaza las materias previstas. Calca ``sesiones.etiquetar``."""
        with transaccion(self._cx):
            self._cx.execute(
                "DELETE FROM bloque_materia WHERE bloque_id = ?", (bloque_id,)
            )
            self._cx.executemany(
                "INSERT INTO bloque_materia (bloque_id, materia_id) VALUES (?, ?)",
                [(bloque_id, materia_id) for materia_id in materias],
            )

    def eliminar(self, bloque_id: int) -> None:
        """Borra el bloque y sus materias previstas."""
        self._cx.execute("DELETE FROM bloque_plan WHERE id = ?", (bloque_id,))

    def fechas_sin_hora(self, proyecto_id: int, desde: str, hasta: str) -> set[str]:
        """Fechas del rango que ya tienen un bloque de dia entero (sin hora).

        La vista previa del plan pregunta esto para cada dia del rango; una
        consulta por dia era una consulta por dia.
        """
        filas = self._cx.execute(
            "SELECT DISTINCT fecha FROM bloque_plan "
            " WHERE proyecto_id = ? AND fecha BETWEEN ? AND ? AND hora_inicio IS NULL",
            (proyecto_id, desde, hasta),
        ).fetchall()
        return {f["fecha"] for f in filas}

    def existe_en(
        self, proyecto_id: int, fecha: date, hora_inicio: str | None
    ) -> bool:
        """Si ya hay un bloque en esa franja.

        Lo usa el generador del plan para ser idempotente: volver a generar no
        debe llenar el calendario de duplicados.
        """
        if hora_inicio is None:
            fila = self._cx.execute(
                "SELECT 1 FROM bloque_plan "
                " WHERE proyecto_id = ? AND fecha = ? AND hora_inicio IS NULL",
                (proyecto_id, fecha.isoformat()),
            ).fetchone()
        else:
            fila = self._cx.execute(
                "SELECT 1 FROM bloque_plan "
                " WHERE proyecto_id = ? AND fecha = ? AND hora_inicio = ?",
                (proyecto_id, fecha.isoformat(), hora_inicio),
            ).fetchone()
        return fila is not None


def _a_bloque(fila: sqlite3.Row) -> BloquePlan:
    fecha = a_fecha(fila["fecha"])
    assert fecha is not None
    return BloquePlan(
        id=fila["id"],
        proyecto_id=fila["proyecto_id"],
        fecha=fecha,
        duracion_min=fila["duracion_min"],
        hora_inicio=fila["hora_inicio"],
        titulo=fila["titulo"],
        nota=fila["nota"],
        creado_en=a_fecha_hora(fila["creado_en"]),
    )
